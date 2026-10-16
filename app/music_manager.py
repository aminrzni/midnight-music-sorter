#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Music Library Manager  v2.0
===========================

Audits, tags and organizes music into a new library that follows the artist's REAL discography
(MusicBrainz first, then Discogs / Deezer / Apple Music), keeps a permanent provenance record of every
original, and - only as the very last step and only with your approval - moves the originals into an archive.

Library layout (v2):
    Artist/Year - Album/                 Credited Artist - Year Album - 01 Title
    Artist/Live|EP|OST|Remix|Comp|Box|Bootleg|Mix|Single Year Name/
    Artist/Singles/                      Credited Artist - Title         (one-song singles)
    Artist/_Unverified/                  artist confirmed, release unclear (tags unchanged)
    _Unverified/ (V2.0.3: also short / long / tagless files)  _Playlists/

    Phase 1  Scan & audit ............ read-only
    Phase 2  Propose changes ......... read-only (asks grouped review questions)
    Phase 3  Apply (copy + tag) ...... only after you answer  y
    Phase 4  Archive originals ....... only after you answer  y  (and choose the archive folder)

Nothing is ever deleted. Originals are never modified. Files are never overwritten.

SETUP (Windows, once):
    1. Install Python 3.10+ from python.org (tick "Add python.exe to PATH").
    2. In a terminal:   pip install mutagen openpyxl pillow
    3. Recommended:     ffmpeg   (audio-stream hashing for every format)
                        https://www.gyan.dev/ffmpeg/builds/  -> put ffmpeg.exe next to this script or on PATH
    4. Optional:        fpcalc   (Chromaprint: fingerprints for duplicates + AcoustID)
                        https://acoustid.org/chromaprint  -> put fpcalc.exe next to this script
                        AcoustID lookups also need a free API key: https://acoustid.org/new-application

RUN:
    python music_manager.py
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import csv
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import string
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

try:
    import mutagen
    from mutagen.asf import ASF
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import (APIC, ID3, TALB, TCMP, TCOM, TCON, TDRC, TIT2, TPE1,
                             TPE2, TPOS, TRCK, TXXX, USLT, COMM)
    from mutagen.mp4 import MP4, MP4Cover
except ImportError:  # checked in main()
    mutagen = None

try:
    import openpyxl
    from openpyxl.styles import Font
except ImportError:
    openpyxl = None

VERSION = "2.0.1"
IS_WIN = os.name == "nt"
# Folder of the program: next to music_manager.py, or next to the .exe when the app is packaged (PyInstaller),
# so the shared _cache and ffmpeg / fpcalc are always looked for in the same place.
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)      # tools packed inside the .exe (used only if none sit next to it)
# Desktop app hook (midnight_app.py). None = text menu: everything below behaves exactly as before.
UI = None
CACHE_ONLY = False        # v1.1.4: build a plan from the lookup memory only (no internet): used after you cancel a scan
FAST_SCAN = False         # app: a Fast scan skips the slow extra lookups (album pages on other sites)
LIVE_CACHES = []          # lookup caches in use, so the app can save them when you press Stop
_LOADED = {}              # app only: big lookup caches loaded once and shared (the 270 MB file is read one time)
BATCH_SIZE = 200
AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".m4b", ".aac", ".ogg", ".opus", ".wav", ".wma", ".aiff", ".aif"}
LOSSLESS_EXTS = {".flac", ".wav", ".aiff", ".aif"}
VA_MBID = "89ad4ac3-39f7-470e-963a-56509c546377"
VA_NAMES = {"variousartists", "various", "va", "variosartistas", "multipleartists", "artistesdivers", "verschiedeneinterpreten"}
COMP_SECONDARY = {"Compilation", "Soundtrack", "DJ-mix", "Mixtape/Street"}
COMP_RE = re.compile(r"\b(soundtrack|o\.?s\.?t\.?|original score|motion picture|tribute to|now that'?s what i call|various artists)\b", re.I)
SKIP_DIR_NAMES = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin",
                  "system volume information", "recovery", "perflogs", "msocache", "$windows.~bt", "$windows.~ws",
                  "windowsapps", "node_modules", ".git", "proc", "sys", "dev", "snap", "boot"}
VERSION_WORDS = ("live", "remix", "mix", "remaster", "acoustic", "demo", "edit", "version", "instrumental", "karaoke",
                 "unplugged", "mono", "extended", "reprise", "session", "rehearsal", "alternate", "orchestral",
                 "acapella", "a cappella", "dub", "rework", "bootleg", "vip", "radio", "clean", "explicit", "censored")
TAG_KEYS = ["artist", "albumartist", "album", "title", "track", "tracktotal", "disc", "disctotal", "year", "genre",
            "compilation", "mb_trackid", "mb_albumid", "mb_artistid", "composer", "conductor"]
PROV_COLS = ["file_id", "original_full_path", "original_filename",
             "orig_artist", "orig_album", "orig_title", "orig_track", "orig_year",
             "sha256_hash", "audio_stream_hash",
             "new_full_path", "new_filename",
             "new_artist", "new_albumartist", "new_album", "new_title", "new_track", "new_disc", "new_year", "new_genre",
             "compilation_name", "original_track_number", "changes_made", "confidence", "data_source",
             "date_processed", "final_original_path", "final_original_filename", "status", "notes"]
CHANGE_COLS = ["file_id", "source_path", "new_path", "match_percent", "old_tags", "new_tags", "action", "data_source", "confidence",
               "approved", "needs_review", "reason"]

# ----------------------------------------------------------------------------- console helpers

class Cancelled(RuntimeError):
    pass


def check_cancel():
    """The app's Cancel button: every waiting lookup ends at once (the text menu never cancels)."""
    if UI is not None and getattr(UI, "cancelled", None) and UI.cancelled():
        raise Cancelled("Cancelled by you. Nothing was changed.")


class Progress:
    """One live status line: bar, percent, count, elapsed, time left, spinner and what is being worked on.
    Redrawn at most 5 times a second; the spinner also moves while waiting for websites."""
    active = None

    def __init__(self, label, total=None, lag=0):
        self.lag = lag          # 1.1.7: items counted as done only after they finish (the one in progress is not yet done)
        self.label, self.total, self.n, self.cur, self.extra = label, total, 0, "", ""
        self.t0 = self.last = time.time()
        self.last = 0
        self.lock = threading.Lock()
        self.finished = False
        Progress.active = self
        self.draw(force=True)

    @staticmethod
    def _t(sec):
        sec = int(sec)
        return f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"

    def step(self, cur=""):
        check_cancel()
        with self.lock:
            self.n += 1
            self.cur, self.extra = cur or self.cur, ""
        self.draw()

    def note(self, cur="", extra=None):
        if cur:
            self.cur = cur
        if extra is not None:
            self.extra = extra
        self.draw()

    @classmethod
    def ping(cls, extra=None):
        if cls.active:
            cls.active.note(extra=extra)

    def line(self):
        now = time.time()
        el = now - self.t0
        spin = "|/-\\"[int(now * 5) % 4]
        if self.total:
            nd = max(0, self.n - self.lag)
            pct = min(1.0, nd / self.total)
            fill = int(pct * 20)
            left = f", ~{self._t(el / nd * (self.total - nd))} left" if nd else ""
            head = f" {self.label} [{'#' * fill}{'-' * (20 - fill)}] {pct * 100:3.0f}%  {nd:,}/{self.total:,}  " \
                   f"{self._t(el)} elapsed{left}"
        else:
            head = f" {self.label}  {self.n:,} so far  {self._t(el)} elapsed"
        tail = f"  {spin} {self.cur}" + (f"  ({self.extra})" if self.extra else "")
        width = max(60, shutil.get_terminal_size((120, 20)).columns - 1)
        return (head + tail)[:width].ljust(width)

    def draw(self, force=False):
        now = time.time()
        if not force and now - self.last < 0.2:
            return
        if not self.lock.acquire(blocking=force):
            return
        self.last = now
        try:
            self._draw()
        finally:
            self.lock.release()

    def _draw(self):
        if UI:
            UI.progress(self)       # the app shows the same live line (and may ask to stop here)
            return
        try:
            sys.stdout.write("\r" + self.line())
            sys.stdout.flush()
        except Exception:
            pass

    def clear(self):
        if UI:
            return
        width = max(60, shutil.get_terminal_size((120, 20)).columns - 1)
        sys.stdout.write("\r" + " " * width + "\r")

    def done(self, msg=""):
        self.finished = True
        self.draw(force=True)
        if not UI:
            sys.stdout.write("\n")
            sys.stdout.flush()
        Progress.active = None
        if msg:
            say(msg)


def say(*a):
    if UI:
        UI.say(" ".join(str(x) for x in a))
        return
    p = Progress.active
    if p:
        p.clear()
    print(*a, flush=True)
    if p:
        p.draw(force=True)


def notify(msg):
    """Windows notification + sound when a long phase ends (silently ignored elsewhere)."""
    say(f"\a")
    if not IS_WIN:
        return
    try:
        import winsound
        winsound.MessageBeep()
    except Exception:
        pass
    m = msg.replace("'", "''")
    ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
          "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
          "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
          "$x = $t.GetElementsByTagName('text');"
          "$x.Item(0).AppendChild($t.CreateTextNode('Music Library Manager')) > $null;"
          f"$x.Item(1).AppendChild($t.CreateTextNode('{m}')) > $null;"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
          "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe')"
          ".Show([Windows.UI.Notifications.ToastNotification]::new($t))")
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    except Exception:
        pass


def hr(title=""):
    say("\n" + "=" * 78 + (f"\n {title}\n" + "=" * 78 if title else ""))


def ask(q, default=""):
    if UI:                  # the app answers from your choices on screen (approvals only after a green button)
        return UI.ask(q, default)
    try:
        s = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        s = ""
    return s or default


def ask_choice(q, options, default):
    """options: dict letter -> label. Returns the chosen letter."""
    opts = " / ".join(f"[{k.upper()}]{v}" for k, v in options.items())
    while True:
        s = ask(f"{q}\n   {opts}", default.upper()).lower()
        if s[:1] in options:
            return s[:1]
        say("   Please type one of: " + ", ".join(k.upper() for k in options))


def ask_yn(q, default="n"):
    return ask_choice(q, {"y": "es", "n": "o"}, default) == "y"


def clean_input_path(s):
    if isinstance(s, dict):                          # v2.0: the window may send {"path": ...}
        s = s.get("path") or s.get("value") or ""
    elif isinstance(s, (list, tuple)):
        s = s[0] if s else ""
    s = s if isinstance(s, str) else ("" if s is None else str(s))
    return os.path.normpath(s.strip().strip('"').strip("'")) if s.strip() else ""


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stamp():
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024


def lp(p):
    """Long-path safe version of a path for file operations on Windows."""
    if IS_WIN and p and not p.startswith("\\\\?\\"):
        p = os.path.abspath(p)
        if len(p) >= 240:
            return "\\\\?\\UNC\\" + p[2:] if p.startswith("\\\\") else "\\\\?\\" + p
    return p


def exists(p):
    return os.path.lexists(lp(p))


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def inside(p, root):
    p, root = os.path.normcase(os.path.abspath(p)), os.path.normcase(os.path.abspath(root))
    return p == root or p.startswith(root.rstrip("\\/") + os.sep)

# ----------------------------------------------------------------------------- storage

class Store:
    def __init__(self, logs):
        self.logs = logs
        self.backups = os.path.join(logs, "backups")
        os.makedirs(lp(self.backups), exist_ok=True)

    def p(self, name):
        return os.path.join(self.logs, name)

    def load(self, name, default):
        try:
            with open(lp(self.p(name)), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default

    def save(self, name, obj):
        tmp = self.p(f"{name}.{threading.get_ident()}.tmp")
        with open(lp(tmp), "w", encoding="utf-8") as f:
            if name.endswith("_cache.json"):
                json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(lp(tmp), lp(self.p(name)))

    _CACHE = {}
    _CACHE_LOCK = threading.Lock()

    def cached(self, name, default):
        """Read-only copy of a big log file (plan, inventory, analysis...), read from disk again only when the file
        changed. Callers must NOT change the returned object (app use only; the text menu never calls this)."""
        path = self.p(name)
        try:
            stt = os.stat(lp(path))
        except OSError:
            return default
        key = (os.path.normcase(path), stt.st_mtime_ns, stt.st_size)
        with Store._CACHE_LOCK:
            hit = Store._CACHE.get(key[0])
            if hit and hit[0] == key:
                return hit[1]
        val = self.load(name, default)
        with Store._CACHE_LOCK:
            Store._CACHE[key[0]] = (key, val)
        return val

    def retire(self, name):
        """Move an existing report into backups/ with a timestamp (never overwritten, never deleted)."""
        src = self.p(name)
        if exists(src):
            base, ext = os.path.splitext(name)
            os.replace(lp(src), lp(os.path.join(self.backups, f"{base}_{stamp()}{ext}")))


def write_csv(path, cols, rows):
    with open(lp(path), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})


def read_csv(path):
    if not exists(path):
        return []
    with open(lp(path), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_xlsx(path, cols, rows, sheet="provenance"):
    if not openpyxl:
        return False
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([str(r.get(k, "") or "") for k in cols])
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    for i, k in enumerate(cols, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 60 if "path" in k else 22
    tmp = path + ".tmp.xlsx"
    wb.save(lp(tmp))
    os.replace(lp(tmp), lp(path))
    return True

# ----------------------------------------------------------------------------- text normalisation

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_key(s):
    s = strip_accents(str(s or "")).lower().replace("&", " and ").replace("+", " and ")
    s = re.sub(r"^the\s+", "", s.strip())
    s = re.sub(r",\s*the$", "", s)
    return re.sub(r"[^0-9a-z\u0080-\uffff]+", "", s)


def ratio(a, b):
    a, b = norm_key(a), norm_key(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else difflib.SequenceMatcher(None, a, b).ratio()


FEAT_SPLIT = re.compile(r"\s*[\(\[]?\s*\b(?:feat\.?|ft\.?|featuring)\s+(.+?)[\)\]]?\s*$", re.I)
TITLE_FEAT = re.compile(r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+([^\)\]]+)[\)\]]|\s+(?:feat\.?|ft\.?|featuring)\s+(.+)$", re.I)


def split_feat(artist):
    artist = (artist or "").strip()
    m = FEAT_SPLIT.search(artist)
    if m and m.start() > 0:
        return artist[:m.start()].strip(" ,;-"), m.group(1).strip()
    return artist, ""


def normalize_title_feat(title):
    """'Song ft. X' / 'Song [feat X]' -> 'Song (feat. X)'."""
    m = TITLE_FEAT.search(title or "")
    if not m:
        return title, ""
    who = (m.group(1) or m.group(2) or "").strip()
    base = (title[:m.start()] + title[m.end():]).strip()
    return f"{base} (feat. {who})", who


def add_feat(title, feats):
    if feats and "feat." not in title.lower():
        return f"{title} (feat. {feats})"
    return title


JUNK_RES = [re.compile(p, re.I) for p in (
    r"https?://\S+", r"\bwww\.\S+", r"\b\S+\.(com|net|org|ir|ru|info|me|to|cc|fm)\b",
    r"[\(\[]\s*(official\s+)?(hd\s+)?(music\s+|lyrics?\s+)?(video|audio|visuali[sz]er|lyrics?|clip)\s*[\)\]]",
    r"[\(\[]\s*(hd|hq|4k|1080p|720p|320\s*kbps|128\s*kbps)\s*[\)\]]",
    r"\s+-\s+(official\s+)?(music\s+)?(video|audio)\s*$")]
LEAD_NUM = [re.compile(r"^(?:(\d{1,2})-)?(0\d{1,2})[\s._)\-]+(.+)$"),
            re.compile(r"^(?:(\d{1,2})-)?(\d{1,3})\s*[._)\-]\s*(.+)$")]


def has_junk(s):
    s = s or ""
    return any(r.search(s) for r in JUNK_RES) or "_" in s or any(r.match(s) for r in LEAD_NUM)


SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "vs",
               "vs.", "via", "with", "from", "into", "over", "feat."}


def smart_title(s):
    letters = [c for c in s if c.isalpha() and c.isascii()]
    if not letters or not (s == s.lower() or s == s.upper()):
        return s  # mixed case = possibly stylized official title -> keep
    words = s.lower().split(" ")
    out = []
    for i, w in enumerate(words):
        if 0 < i < len(words) - 1 and w in SMALL_WORDS:
            out.append(w)
            continue
        for j, c in enumerate(w):
            if c.isalpha():
                w = w[:j] + c.upper() + w[j + 1:]
                break
        out.append(w)
    return " ".join(out)


def clean_title(s, strip_number=True):
    s = (s or "").replace("_", " ")
    for r in JUNK_RES:
        s = r.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" -.")
    if strip_number:
        for r in LEAD_NUM:
            m = r.match(s)
            if m and m.group(3).strip():
                s = m.group(3).strip()
                break
    s, _ = normalize_title_feat(s)
    m = re.search(r"\s\(feat\. [^)]*\)$", s)
    base, tail = (s[:m.start()], s[m.start():]) if m else (s, "")
    return smart_title(base.strip(" -.")) + tail


def title_key(t):
    """Key that keeps version words, so Live/Remix/Remaster never match the studio version."""
    t, _ = normalize_title_feat(t or "")
    t = re.sub(r"\(feat\.[^)]*\)", "", t, flags=re.I)
    return norm_key(t)


NEUTRAL_RE = re.compile(r"\s*(?:[\(\[]\s*|\s-\s+)(?:(?:\d{4}\s+)?(?:digital(?:ly)?\s+)?re-?mast(?:er(?:ed|is[ée]e?s?|isiert|izad[oa]|izzat[oa])?|éris[ée]e?)(?:\s+(?:version|en|in|nel|em)\b)?(?:\s+\d{4})?(?:\s+(?:version|\d{4}))?|"
                        r"(?:album|lp|original|single|stereo|mono)\s+(?:version|mix)|stereo|mono)\s*[\)\]]?", re.I)


def neutral(t):
    """Labels that do not make a different song, for MATCHING only: 'Let It Be (Remastered 2009)' -> 'Let It Be',
    'Born Free (Album Version)' -> 'Born Free'. (Remasters still count as their own edition elsewhere.)"""
    out = NEUTRAL_RE.sub("", t or "").strip()
    return out or (t or "")


CATALOG_RE = re.compile(r"\b(BWV|HWV|RV|K|KV|D|Op|Opus|Hob|S|WoO|L|Kk|TWV|BuxWV|Sz|FP|M|Wq|H)\.?\s*([IVXLC]+[a-z]?:?\s*)?(\d+[a-z]?)"
                        r"(?:\s*(?:,\s*)?(?:No|Nr)\.?\s*(\d+))?", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}


def classical_key(t):
    """'Symphony No. 9 in C Major, D. 944: II. Andante' -> ('d944', 2). Catalogue number + movement, or None."""
    m = CATALOG_RE.search(t or "")
    if not m:
        return None
    cat = (m.group(1).lower().replace("opus", "op").replace("kv", "k") + m.group(3).lower() + (("-" + m.group(4)) if m.group(4) else ""))
    mv = re.search(r"(?:[:\-–]\s*|\b)([IVX]{1,4})\.\s|(?:[:\-–]\s*)(\d{1,2})\.\s", t)
    mov = ROMAN.get((mv.group(1) or "").lower()) or (int(mv.group(2)) if mv and mv.group(2) else None) if mv else None
    return cat, mov


def same_song_title(a, b):
    """Title similarity used by every matcher (ignores neutral labels; live/remix/edit... must agree).
    Classical: the same catalogue number (BWV, K., D., Op. ...) and the same movement count as the same piece,
    however differently the rest of the title is written. (Length and performer are still checked elsewhere.)"""
    na, nb = neutral(a), neutral(b)
    if version_words(na) != version_words(nb):
        return 0.0
    sim = max(ratio(title_key(na), title_key(nb)), ratio(title_key(base_title(na)), title_key(base_title(nb))) - 0.02)
    if sim < 0.88:
        ka, kb = classical_key(na), classical_key(nb)
        if ka and kb and ka[0] == kb[0] and ka[1] == kb[1] and (ka[1] is not None or ratio(title_key(na), title_key(nb)) > 0.6):
            return 0.9
    return sim


VERSION_LABEL_WORDS = re.compile(r"\b(?:alt(?:ernate|ernative)?|re-?scor\w*|re-?record\w*|re-?edit\w*|unused|outtake|take\s*\d*|session|demo|rough|early|"
                                 r"live|acoustic|instrumental|extended|radio|single|original|mono|stereo|mix|remix|edit|version|cut|film|score|theme|reprise|"
                                 r"orchestral|karaoke|unplugged|rehearsal|bootleg)\b", re.I)


def version_label_of(file_title, new_title=""):
    """V2.0.6: a label at the end of YOUR title - '(Rescored Alt)', '[Live 1979]', '- Alternate Take' - that says WHICH version this file is.
    Returns the label text when the matched title does not already carry it, else ''. The label then stays in the new title tag and file name."""
    t = str(file_title or "").strip()
    m = re.search(r"[\(\[]([^\(\)\[\]]{2,40})[\)\]]\s*$", t) or re.search(r"\s+-\s+([^-]{2,40})$", t)
    if not m:
        return ""
    lab = m.group(1).strip()
    if not VERSION_LABEL_WORDS.search(lab) or re.search(r"re-?mast", lab, re.I):
        return ""
    if norm_key(lab) and norm_key(lab) in norm_key(new_title or ""):
        return ""
    return lab


def version_words(t):
    tl = (t or "").lower()
    return {w for w in VERSION_WORDS if re.search(r"\b" + re.escape(w), tl)}


REMASTER_WORDS = re.compile(r"\b(?:\d{4}\s+)?(?:digital(?:ly)?\s+)?re-?master(?:ed|isation|ização|ing)?(?:\s+(?:hd|version|edition))?"
                            r"(?:\s+\d{4})?\b|\b(?:album|lp|single|original|stereo|45)\s+(?:version|mix)\b|\bstereo\b", re.I)
REMASTER_FILE = re.compile(r"(?:\b(\d{4})\s+)?(?:digital(?:ly)?\s+)?\bre-?mast[eé]r(?:ed|ing|is\w*|iz\w*)?\b(?:\s+(?:hd\s+)?(\d{4}))?", re.I)
OTHER_VERSION_RE = [r"\bmono\b", r"\btake\s*\d", r"\b\d{4}\s+(?:stereo\s+)?mix\b", r"\b5\.1\b", r"\bsurround\b", r"\bdts\b",
                    r"\batmos\b", r"\bdolby\b", r"\bquad(?:raphonic)?\b", r"\bbinaural\b", r"\bpromo(?:tional)?\b", r"\bfilm\b",
                    r"\bvideo\b", r"\bouttake\b", r"\brough\b", r"\bearly\b", r"\bbacking track\b", r"\bkaraoke\b", r"\bcover\b",
                    r"\btribute\b", r"\bin the style of\b", r"\bmade famous\b"]


REISSUE_RE = re.compile(r"\(\s*\d+\s*(?:th\s+)?(?:years?|anniversary)[^)]*\)|\banniversary\b|\bbest of\b|\bgreatest hits\b|"
                        r"\bthe very best\b|\bessential\b|\banthology\b|\bcollection\b|\b(?:super )?deluxe\b|\bexpanded\b|"
                        r"\blegacy edition\b|\bcollector'?s edition\b", re.I)


def different_version(mine, cand, cand_extra="", context=""):
    """True when a database track is ANOTHER version than your file: it carries version words (live, mix, remix,
    demo, take, instrumental, mono, edit ...) that your title (or its album / file name in context) does not.
    Remaster labels never count. Used so 'Something (Remastered 2009)' is not matched to 'Something (2019 mix)',
    and 'Michelle' is not matched to 'Michelle (mono)'."""
    a = REMASTER_WORDS.sub(" ", f"{mine or ''} {context or ''}").lower()
    b = REMASTER_WORDS.sub(" ", f"{cand or ''} {cand_extra or ''}").lower()
    if version_words(b) - version_words(a) - {"version"}:
        return True
    a2 = REMASTER_FILE.sub(" ", f"{mine or ''} {context or ''}").lower()      # 'stereo' kept here: '2019 stereo mix'
    b2 = REMASTER_FILE.sub(" ", f"{cand or ''} {cand_extra or ''}").lower()
    for w in OTHER_VERSION_RE:
        if re.search(w, b2) and not re.search(w, a2):
            return True
    return False




def file_remaster(r, h):
    """Does YOUR file say it is a remaster (title, album or file name)? -> (True, year or '')."""
    text = " ".join([h.get("title_raw", ""), h.get("album_raw", ""), r.get("filename", "")])
    m = REMASTER_FILE.search(text)
    if not m:
        return False, ""
    return True, (m.group(1) or m.group(2) or "")


ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize(s):
    s = str(s or "").replace(":", " -").replace('"', "'")
    s = re.sub(r"[\\/|]", "-", s)
    s = ILLEGAL.sub("", s)
    s = re.sub(r"\s+", " ", s).strip().rstrip(". ").strip()
    if s.split(".")[0].upper() in RESERVED:
        s += "_"
    return s


def split_num(v):
    v = str(v or "").strip()
    if not v:
        return "", ""
    a, _, b = v.partition("/")
    a = re.sub(r"\D", "", a)
    b = re.sub(r"\D", "", b)
    return (str(int(a)) if a else ""), (str(int(b)) if b else "")


def year_of(v):
    m = re.search(r"(1[89]\d\d|20\d\d)", str(v or ""))
    return m.group(1) if m else ""

# ----------------------------------------------------------------------------- audio reading

def image_size(b):
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")
        if b[:2] == b"\xff\xd8":
            i = 2
            while i < len(b) - 9:
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in (0xD8, 0x01, 0xFF) or 0xD0 <= m <= 0xD7:
                    i += 1 if m == 0xFF else 2
                    continue
                ln = int.from_bytes(b[i + 2:i + 4], "big")
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
                i += 2 + ln
    except Exception:
        pass
    return 0, 0


def image_mime(b):
    return "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def _s(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    if isinstance(v, tuple):
        v = v[0]
    if hasattr(v, "value") and not isinstance(v, (str, bytes)):
        v = v.value
    if isinstance(v, bytes):
        v = v.decode("utf-8", "ignore")
    return str(v).strip()


def extract_tags(f):
    """Return (tags dict, list of picture bytes) for any mutagen file object."""
    t = {k: "" for k in TAG_KEYS}
    pics = []
    tags = getattr(f, "tags", None)
    if tags is None:
        if isinstance(f, FLAC) and f.pictures:
            pics = [p.data for p in f.pictures]
        return t, pics
    if isinstance(tags, ID3):
        g = lambda k: _s(tags[k].text) if k in tags else ""
        t.update(artist=g("TPE1"), albumartist=g("TPE2"), album=g("TALB"), title=g("TIT2"), genre=g("TCON"),
                 compilation=g("TCMP"), year=year_of(g("TDRC") or g("TYER") or g("TORY")),
                 composer=g("TCOM"), conductor=g("TPE3"))
        t["track"], t["tracktotal"] = split_num(g("TRCK"))
        t["disc"], t["disctotal"] = split_num(g("TPOS"))
        for fr in tags.getall("TXXX"):
            d = fr.desc.lower()
            if d == "musicbrainz album id":
                t["mb_albumid"] = _s(fr.text)
            elif d == "musicbrainz artist id":
                t["mb_artistid"] = _s(fr.text)
        for fr in tags.getall("UFID"):
            if fr.owner == "http://musicbrainz.org":
                t["mb_trackid"] = fr.data.decode("ascii", "ignore")
        pics = [fr.data for fr in tags.getall("APIC")]
    elif isinstance(f, MP4):
        g = lambda k: _s(tags.get(k))
        t.update(artist=g("\xa9ART"), albumartist=g("aART"), album=g("\xa9alb"), title=g("\xa9nam"),
                 genre=g("\xa9gen"), year=year_of(g("\xa9day")), compilation="1" if tags.get("cpil") else "",
                 composer=g("\xa9wrt"),
                 mb_trackid=g("----:com.apple.iTunes:MusicBrainz Track Id"),
                 mb_albumid=g("----:com.apple.iTunes:MusicBrainz Album Id"),
                 mb_artistid=g("----:com.apple.iTunes:MusicBrainz Artist Id"))
        if tags.get("trkn"):
            n, tot = tags["trkn"][0]
            t["track"], t["tracktotal"] = (str(n) if n else ""), (str(tot) if tot else "")
        if tags.get("disk"):
            n, tot = tags["disk"][0]
            t["disc"], t["disctotal"] = (str(n) if n else ""), (str(tot) if tot else "")
        pics = [bytes(c) for c in tags.get("covr", [])]
    elif isinstance(f, ASF):
        g = lambda k: _s(tags.get(k))
        t.update(artist=g("Author"), albumartist=g("WM/AlbumArtist"), album=g("WM/AlbumTitle"), title=g("Title"),
                 genre=g("WM/Genre"), year=year_of(g("WM/Year")),
                 compilation="1" if g("WM/IsCompilation") in ("1", "True", "true") else "",
                 mb_trackid=g("MusicBrainz/Track Id"), mb_albumid=g("MusicBrainz/Album Id"))
        t["track"], t["tracktotal"] = split_num(g("WM/TrackNumber"))
        t["disc"], t["disctotal"] = split_num(g("WM/PartOfSet"))
        if tags.get("WM/Picture"):
            pics = [b"ASF"]  # present; size unknown
    else:  # Vorbis comments (FLAC / Ogg Vorbis / Opus)
        d = {}
        for k, v in tags.items() if hasattr(tags, "items") else []:
            d.setdefault(k.lower(), v)
        g = lambda k: _s(d.get(k))
        t.update(artist=g("artist"), albumartist=g("albumartist") or g("album artist"), album=g("album"),
                 title=g("title"), genre=g("genre"), year=year_of(g("originaldate") or g("date") or g("year")),
                 compilation=g("compilation"), mb_trackid=g("musicbrainz_trackid"),
                 composer=g("composer"), conductor=g("conductor"),
                 mb_albumid=g("musicbrainz_albumid"), mb_artistid=g("musicbrainz_artistid"))
        t["track"], tt = split_num(g("tracknumber"))
        t["tracktotal"] = tt or split_num(g("tracktotal") or g("totaltracks"))[0]
        t["disc"], dt_ = split_num(g("discnumber"))
        t["disctotal"] = dt_ or split_num(g("disctotal") or g("totaldiscs"))[0]
        if isinstance(f, FLAC):
            pics = [p.data for p in f.pictures]
        for b64 in tags.get("metadata_block_picture", []) if hasattr(tags, "get") else []:
            try:
                pics.append(Picture(base64.b64decode(b64)).data)
            except Exception:
                pass
    return t, pics


def read_audio(path):
    ext = os.path.splitext(path)[1].lower()
    out = {"error": "", "tags": {k: "" for k in TAG_KEYS}, "has_cover": False, "cover_px": 0,
           "duration": 0.0, "bitrate": 0, "sample_rate": 0, "codec": "", "lossless": ext in LOSSLESS_EXTS}
    try:
        f = mutagen.File(lp(path))
    except Exception as e:
        out["error"] = f"unreadable: {e}"
        return out
    if f is None:
        out["error"] = "not recognised as audio"
        return out
    i = f.info
    out["duration"] = round(float(getattr(i, "length", 0) or 0), 2)
    br = getattr(i, "bitrate", 0) or 0
    if not br and out["duration"]:
        br = os.path.getsize(lp(path)) * 8 / out["duration"]
    out["bitrate"] = int(round(br / 1000))
    out["sample_rate"] = int(getattr(i, "sample_rate", 0) or 0)
    codec = str(getattr(i, "codec", "") or getattr(i, "codec_name", "") or type(f).__name__)
    out["codec"] = codec
    if "alac" in codec.lower() or "lossless" in codec.lower():
        out["lossless"] = True
    try:
        out["tags"], pics = extract_tags(f)
    except Exception as e:
        pics = []
        out["error"] = f"tags unreadable: {e}"
    if pics:
        out["has_cover"] = True
        out["cover_px"] = max(min(image_size(p)) for p in pics)
    if out["duration"] <= 0 and not out["error"]:
        out["error"] = "zero length (possibly corrupt)"
    return out


def best_picture(path):
    try:
        f = mutagen.File(lp(path))
        _, pics = extract_tags(f)
    except Exception:
        return None
    pics = [p for p in pics if p != b"ASF"]
    if not pics:
        return None
    return max(pics, key=lambda p: min(image_size(p)))

# ----------------------------------------------------------------------------- hashing

def sha256_file(path):
    h = hashlib.sha256()
    with open(lp(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _range_md5(path, start, end):
    h = hashlib.md5()
    with open(lp(path), "rb") as f:
        f.seek(start)
        left = end - start
        while left > 0:
            b = f.read(min(1 << 20, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def raw_audio_hash(path):
    """Fallback without ffmpeg: hash only the audio bytes for MP3/FLAC/WAV/AIFF."""
    ext = os.path.splitext(path)[1].lower()
    size = os.path.getsize(lp(path))
    with open(lp(path), "rb") as f:
        head = f.read(10)
        start = 0
        if head[:3] == b"ID3" and ext in (".mp3", ".flac"):
            sz = (head[6] << 21) | (head[7] << 14) | (head[8] << 7) | head[9]
            start = 10 + sz + (10 if head[5] & 0x10 else 0)
        if ext == ".mp3":
            end = size
            f.seek(max(0, end - 128))
            if f.read(3) == b"TAG":
                end -= 128
            f.seek(max(0, end - 32))
            foot = f.read(32)
            if foot[:8] == b"APETAGEX":
                tag_size = int.from_bytes(foot[12:16], "little")
                flags = int.from_bytes(foot[20:24], "little")
                end -= tag_size + (32 if flags & 0x80000000 else 0)
            return "raw-md5:" + _range_md5(path, start, end)
        if ext == ".flac":
            f.seek(start)
            if f.read(4) != b"fLaC":
                return ""
            pos = start + 4
            while True:
                f.seek(pos)
                hdr = f.read(4)
                if len(hdr) < 4:
                    return ""
                pos += 4 + int.from_bytes(hdr[1:4], "big")
                if hdr[0] & 0x80:
                    break
            return "raw-md5:" + _range_md5(path, pos, size)
        if ext in (".wav", ".aiff", ".aif"):
            f.seek(0)
            riff = f.read(12)
            little = riff[:4] == b"RIFF"
            want = b"data" if little else b"SSND"
            pos = 12
            while pos + 8 <= size:
                f.seek(pos)
                ch = f.read(8)
                ln = int.from_bytes(ch[4:8], "little" if little else "big")
                if ch[:4] == want:
                    return "raw-md5:" + _range_md5(path, pos + 8, min(size, pos + 8 + ln))
                pos += 8 + ln + (ln & 1)
    return ""


def decoded_hash(path, ffmpeg):
    """MD5 of the decoded sound (slow, used only when the quick packet check disagrees)."""
    if not ffmpeg:
        return ""
    try:
        r = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0", "-f", "md5", "-"],
                           capture_output=True, text=True, timeout=900)
        m = re.search(r"MD5=([0-9a-f]{32})", r.stdout)
        return m.group(1) if m else ""
    except Exception:
        return ""


def audio_hash(path, ffmpeg):
    if ffmpeg:
        try:
            r = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0", "-c", "copy",
                                "-f", "md5", "-"], capture_output=True, text=True, timeout=600)
            m = re.search(r"MD5=([0-9a-f]{32})", r.stdout)
            if m:
                return "ffmpeg-md5:" + m.group(1)
        except Exception:
            pass
        return ""
    try:
        return raw_audio_hash(path)
    except Exception:
        return ""

# ----------------------------------------------------------------------------- online services

def lucene(s):
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s or "")


ARTIST_SPLIT_RE = re.compile(r"\s*(?:,|;|/|\sfeat\.?\s|\sft\.?\s)\s*", re.I)    # not '&' / 'and': duos are one act


def artist_parts(artist):
    """'Sir Georg Solti, Chicago Symphony Orchestra' -> [whole, 'Sir Georg Solti', 'Chicago Symphony Orchestra'];
    also '(Sandy) Alex G' -> [whole, 'Alex G']. Used only to SEARCH; a match must still agree on title + length."""
    out = [artist] if artist else []
    for p_ in ARTIST_SPLIT_RE.split(artist or ""):
        p_ = re.sub(r"^\(.*?\)\s*", "", p_).strip(" .-")
        if len(p_) >= 2 and not re.fullmatch(r"[\d\s,.-]+", p_) and p_ not in out:
            out.append(p_)
    stripped = re.sub(r"^\(.*?\)\s*", "", artist or "").strip()
    if stripped and stripped not in out:
        out.insert(1, stripped)
    return out[:5]


OTHER_ACT_RE = re.compile(r"\b(revival|tribute|karaoke|cover(?:s|band)?|band|orchestra|players|singers|ensemble|quartet|"
                          r"plays|sings|performs|sound ?alike|made famous|in the style|lullaby|lullabies|piano|string|music box|"
                          r"experience|project|show|kids|babies|baby|vs\.?|meets|remix(?:ed)?|dj)\b", re.I)


def other_act(longer, shorter):
    """'Simon & Garfunkel Revival Band' is not 'Simon & Garfunkel': a credit that only CONTAINS your artist's name
    plus words like Revival / Tribute / Band / Orchestra / Karaoke is another act (unless your tag says so too)."""
    extra = re.sub(re.escape(shorter or ""), " ", longer or "", flags=re.I)
    words = {w.lower() for w in OTHER_ACT_RE.findall(extra)}
    mine = {w.lower() for w in OTHER_ACT_RE.findall(shorter or "")}
    return bool(words - mine)


def artist_agrees(names, artist):
    """Does a site's credit (list of names) agree with your tag (which may hold several artists)?
    A tribute / revival / karaoke act whose name merely contains your artist never agrees."""
    parts = artist_parts(artist)
    for n in names:
        if not n:
            continue
        for p_ in parts:
            if ratio(n, p_) >= 0.85 and not other_act(n, p_) and not other_act(p_, n):
                return True
            if len(norm_key(n)) >= 4 and norm_key(n) in norm_key(p_) and not other_act(p_, n):
                return True
            if len(norm_key(p_)) >= 4 and norm_key(p_) in norm_key(n) and not other_act(n, p_):
                return True
    return False


class SharedCache:
    """Lookup answers are shared by ALL your libraries and test runs (folder _cache next to the script), so a new
    output folder never asks the same questions again. The first time, answers already saved in a library's _logs
    are merged in. Saved compactly, at most once a minute (and at the end) - never the whole file every few songs."""
    def __init__(self, store):
        self.store = store
        self.saved, self.lock = {}, threading.Lock()
        here = APP_DIR
        self.dir = os.path.join(here, "_cache")
        if not os.path.isdir(lp(self.dir)):
            for up in up_dirs(here)[1:]:      # keep using the lookup memory in a folder above (up to 3 levels)
                if os.path.isdir(lp(os.path.join(up, "_cache"))):
                    self.dir = os.path.join(up, "_cache")
                    break
        try:
            os.makedirs(lp(self.dir), exist_ok=True)
            probe = os.path.join(self.dir, ".write_test")
            with open(lp(probe), "w") as f:
                f.write("ok")
            os.remove(lp(probe))
        except OSError:
            self.dir = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Midnight 00-01", "_cache")
            os.makedirs(lp(self.dir), exist_ok=True)

    def load(self, name):
        key = (os.path.normcase(self.dir), name)
        if key in _LOADED:                     # already in memory (the app keeps it open): share it, read once
            self.saved.setdefault(name, set()).update(_LOADED[key].keys())
            return _LOADED[key]
        data, first = {}, False
        try:
            with open(lp(os.path.join(self.dir, name)), encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            first = True
        except ValueError:
            pass
        if first:      # one time: take in the answers of earlier test libraries next to the script
            here = os.path.dirname(self.dir)
            for d in os.listdir(lp(here)):
                for sub in ("_logs", "LOG", "Logs", "logs"):
                    f_ = os.path.join(here, d, sub, name)
                    if os.path.isfile(lp(f_)):
                        try:
                            with open(lp(f_), encoding="utf-8") as f:
                                for k, v in json.load(f).items():
                                    data.setdefault(k, v)
                        except (OSError, ValueError):
                            pass
        old = self.store.load(name, {}) if self.store else {}
        for k, v in old.items():               # answers from older runs of this library
            data.setdefault(k, v)
        journal = os.path.join(self.dir, name + ".new")    # answers added since the last full save
        if os.path.isfile(lp(journal)):
            with open(lp(journal), encoding="utf-8") as f:
                for line in f:
                    try:
                        k, v = json.loads(line)
                        data[k] = v
                    except ValueError:
                        pass                   # a half-written last line (power cut): just skip it
        self.saved.setdefault(name, set()).update(data.keys())
        if UI:
            _LOADED[key] = data
        return data

    def save(self, name, obj, full=False):
        """Only NEW answers are appended to <name>.new (fast, even with a 300 MB cache). The big file is rewritten
        only when the extra file grows past 64 MB, or when full=True."""
        with self.lock:
            path, journal = os.path.join(self.dir, name), os.path.join(self.dir, name + ".new")
            known = self.saved.setdefault(name, set())
            new = [(k, obj[k]) for k in list(obj.keys()) if k not in known]
            big = os.path.isfile(lp(journal)) and os.path.getsize(lp(journal)) > 64 * 1024 * 1024
            if full or big or not os.path.isfile(lp(path)):
                tmp = f"{path}.{threading.get_ident()}.tmp"
                with open(lp(tmp), "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(lp(tmp), lp(path))
                open(lp(journal), "w").close()  # everything is in the big file now: start a fresh extra file
                known.update(obj.keys())
                return
            if new:
                with open(lp(journal), "a", encoding="utf-8") as f:
                    for k, v in new:
                        f.write(json.dumps([k, v], ensure_ascii=False, separators=(",", ":")) + "\n")
                known.update(k for k, _ in new)


class MusicBrainz:
    def __init__(self, store, contact):
        self.store = SharedCache(store)
        self.ua = f"MusicLibraryManager/{VERSION} ( {contact or 'personal music library script'} )"
        self.cache = self.store.load("mb_cache.json")
        self.saved_at = time.time()
        self.last = 0.0
        self.dirty = 0
        self.lock = threading.Lock()          # cache + counters
        self.rate = threading.Lock()          # spaces request STARTS 1.1 s apart (MusicBrainz rule)
        self.inflight = {}                    # same question asked twice at once -> asked only once
        LIVE_CACHES.append(self)

    def get(self, endpoint, params):
        check_cancel()
        key = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            ev = self.inflight.get(key)
            mine = ev is None
            if mine:
                ev = self.inflight[key] = threading.Event()
        if not mine:
            ev.wait(120)
            with self.lock:
                if key in self.cache:
                    return self.cache[key]
        try:
            return self._fetch(endpoint, params, key)
        finally:
            if mine:
                with self.lock:
                    self.inflight.pop(key, None)
                ev.set()

    def _fetch(self, endpoint, params, key):
        if CACHE_ONLY:
            return None
        url = "https://musicbrainz.org/ws/2/" + endpoint + "?" + urllib.parse.urlencode({**params, "fmt": "json"})
        for attempt in range(6):
            with self.rate:
                wait = 1.1 - (time.time() - self.last)
                if wait > 0:
                    time.sleep(wait)
                self.last = time.time()
            Progress.ping("MusicBrainz" + (f", retry {attempt}" if attempt else ""))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 404):
                    data = None
                    break
                Progress.ping(f"MusicBrainz busy, waiting {3 * (attempt + 1)}s")
                time.sleep(3 * (attempt + 1))
            except Exception:
                Progress.ping(f"no answer from MusicBrainz, waiting {3 * (attempt + 1)}s")
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError("MusicBrainz is not reachable (check your internet connection).")
        with self.lock:
            self.cache[key] = data
            self.dirty += 1
            due = time.time() - self.saved_at > 60
            if due:
                self.saved_at = time.time()
        if due:
            self.save()
        return data

    def save(self):
        with self.lock:
            snap = dict(self.cache)
            self.saved_at = time.time()
        self.store.save("mb_cache.json", snap)

    def artist_ids(self, name):
        """MusicBrainz ids of the artist(s) known by this name OR by it as another name (alias), e.g. your tag
        'Farhad Mehrad' -> the artist MusicBrainz lists as 'Farhad'; 'Cat Stevens' -> 'Yusuf / Cat Stevens'.
        Only close name/alias matches are used. Cached like every other answer."""
        if not name or len(name) < 2:
            return []
        q = f'artist:"{lucene(name)}" OR alias:"{lucene(name)}"'
        d = self.get("artist", {"query": q, "limit": "5"}) or {}
        out = []
        for a in d.get("artists") or []:
            if int(a.get("score", 0)) < 90:
                continue
            names = [a.get("name"), a.get("sort-name")] + [x.get("name") for x in a.get("aliases") or []]
            if any(n_ and (ratio(n_, name) >= 0.9 or norm_key(n_) == norm_key(name)) for n_ in names):
                out.append(a["id"])
        return out[:2]

    def search_release(self, artist, album):
        q = f'release:"{lucene(album)}"' + (f' AND artist:"{lucene(artist)}"' if artist else "")
        d = self.get("release", {"query": q, "limit": "10"})
        found = (d or {}).get("releases", [])
        if not found and artist:              # the artist may be listed under another name
            for aid in self.artist_ids(artist):
                d = self.get("release", {"query": f'release:"{lucene(album)}" AND arid:{aid}', "limit": "10"})
                found = (d or {}).get("releases", [])
                if found:
                    break
        return found

    def release(self, mbid):
        return self.get(f"release/{mbid}", {"inc": "recordings+artist-credits+release-groups+media+genres"})

    def search_recording(self, artist, title, duration=0, precise=False, live=False):
        """precise: only official releases within +-10 s of the file's length, no live recordings unless live."""
        q = f'recording:"{lucene(title)}"' + (f' AND artist:"{lucene(artist)}"' if artist else "")
        if precise:
            if duration:
                q += f" AND dur:[{int((duration - 10) * 1000)} TO {int((duration + 10) * 1000)}]"
            q += " AND status:official" + ("" if live else " AND NOT secondarytype:live")
        d = self.get("recording", {"query": q, "limit": "25" if precise else "10"})
        found = (d or {}).get("recordings", [])
        if not found and artist:              # the artist may be listed under another name (alias)
            for aid in self.artist_ids(artist):
                q2 = q.replace(f' AND artist:"{lucene(artist)}"', f" AND arid:{aid}")
                d = self.get("recording", {"query": q2, "limit": "25" if precise else "10"})
                found = (d or {}).get("recordings", [])
                if found:
                    break
        return found

    def search_by_length(self, artist, duration, window=3):
        """1.1.5 (Dig deeper): this artist's recordings whose length is within +-window seconds - no title needed."""
        if not (artist and duration):
            return []
        q = f'artist:"{lucene(artist)}" AND dur:[{int((duration - window) * 1000)} TO {int((duration + window) * 1000)}] AND status:official'
        d = self.get("recording", {"query": q, "limit": "25"})
        found = (d or {}).get("recordings", [])
        if not found:
            for aid in self.artist_ids(artist)[:1]:
                d = self.get("recording", {"query": f"arid:{aid} AND dur:[{int((duration - window) * 1000)} TO {int((duration + window) * 1000)}] AND status:official", "limit": "25"})
                found = (d or {}).get("recordings", [])
        return found

    def recording(self, mbid):
        return self.get(f"recording/{mbid}", {"inc": "releases+release-groups+artist-credits"})

    def studio_albums(self, artist_id):
        """Release-group ids of the artist's discography, or None if unknown: studio albums (type Album, no secondary
        type). Film composers - at least as many soundtracks as studio albums - also count their soundtracks."""
        out, osts, offset = [], [], 0
        while True:
            d = self.get("release-group", {"artist": artist_id, "type": "album", "limit": "100", "offset": str(offset),
                                           "release-group-status": "website-default"})
            if not d:
                return out or None
            for g in d.get("release-groups") or []:
                if g.get("primary-type") != "Album" or (g.get("first-release-date") or "") > dt.date.today().isoformat():
                    continue
                sec = g.get("secondary-types") or []
                if not sec:
                    out.append(g["id"])
                elif sec == ["Soundtrack"]:
                    osts.append(g["id"])
            offset += 100
            if offset >= int(d.get("release-group-count") or 0):
                if osts and len(osts) >= len(out):
                    out = out + osts          # a film composer: soundtracks are the discography
                return out or None


class Chromaprint:
    def __init__(self, fpcalc, api_key=""):
        self.fpcalc, self.key, self.last = fpcalc, api_key, 0.0
        self.raw_cache = {}
        self.rate = threading.Lock()          # AcoustID allows 3 requests per second

    def _run(self, path, raw):
        args = [self.fpcalc, "-json"] + (["-raw", "-length", "120"] if raw else []) + [path]
        r = subprocess.run(args, capture_output=True, text=True, timeout=300)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None

    def raw(self, path):
        if path not in self.raw_cache:
            try:
                d = self._run(path, True)
                self.raw_cache[path] = d.get("fingerprint") if d else None
            except Exception:
                self.raw_cache[path] = None
        return self.raw_cache[path]

    @staticmethod
    def similarity(a, b):
        if not a or not b:
            return None
        best = 0.0
        for off in range(-5, 6):
            pairs = [(a[i], b[i + off]) for i in range(len(a)) if 0 <= i + off < len(b)]
            if len(pairs) < 20:
                continue
            err = sum(bin((x ^ y) & 0xFFFFFFFF).count("1") for x, y in pairs)
            best = max(best, 1 - err / (32.0 * len(pairs)))
        return best

    def lookup(self, path):
        self.err = ""
        if CACHE_ONLY:
            return []
        if not self.key:
            self.err = "No AcoustID key (Settings)."
            return []
        try:
            d = self._run(lp(path), False)
        except Exception as e:
            d, self.err = None, f"fpcalc could not read this file ({type(e).__name__})."
        if not d or not d.get("fingerprint"):
            self.err = self.err or "fpcalc could not make a fingerprint of this file."
            return []
        with self.rate:
            wait = 0.35 - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
        Progress.ping("AcoustID: identifying by sound")
        body = urllib.parse.urlencode({"client": self.key, "duration": int(d["duration"]), "meta": "recordingids",
                                       "fingerprint": d["fingerprint"], "format": "json"}).encode()
        try:
            req = urllib.request.Request("https://api.acoustid.org/v2/lookup", body,
                                         {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": f"MusicLibraryManager/{VERSION}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)
        except urllib.error.HTTPError as e:
            try:
                res = json.load(e)
            except Exception:
                self.err = f"AcoustID answered with an error ({e.code})."
                return []
        except Exception as e:
            self.err = f"AcoustID could not be reached ({type(e).__name__})."
            return []
        if res.get("status") != "ok":
            msg = ((res.get("error") or {}).get("message") or "unknown error")
            self.err = f"AcoustID: {msg}." + (" The key must be an APPLICATION key from acoustid.org/new-application "
                                               "(not the user key)." if "api key" in msg.lower() else "")
            return []
        out = []
        for m in res.get("results", []):
            for rec in m.get("recordings", []) or []:
                out.append((m.get("score", 0), rec["id"]))
        return sorted(out, reverse=True)



# ----------------------------------------------------------------------------- release model helpers

EDITION_RE = re.compile(r"\s*[\(\[][^\)\]]*\b(deluxe|expanded|anniversary|remaster\w*|remastéris\w*|special edition|bonus tracks?|"
                        r"collector'?s edition|legacy edition|super deluxe)\b[^\)\]]*[\)\]]", re.I)
REMASTER_RE = re.compile(r"remaster", re.I)
VERSION_DASH = re.compile(r"\s+-\s+((?:\d{4}\s+)?(?:digital(?:ly)?\s+)?(?:remaster\w*|remastéris\w*|live|remix|mix|edit|version|mono|"
                          r"stereo|acoustic|demo|instrumental|radio edit|single version|extended)\b.*)$", re.I)
PREFIX = {"Live": "Live", "EP": "EP", "OST": "OST", "Remix": "Remix", "Comp": "Compilation", "Box": "Box",
          "Bootleg": "Bootleg", "Mix": "Mix", "Single": "Single"}


PLACEHOLDER_ARTISTS = {"originalsoundtrack", "soundtrack", "ost", "originalmotionpicturesoundtrack", "originalscore",
                       "motionpicturesoundtrack", "originalcast", "unknown", "unknownartist", "artist", "various",
                       "variousartists", "va"}
OST_DESC = re.compile(r"\s*(?:[\(\[][^\)\]]*\b(?:soundtrack|original score|music from|motion picture|cast recording)\b[^\)\]]*[\)\]]|"
                      r"\s*[-:\u2013]\s*(?:the\s+)?(?:original\s+)?(?:motion picture|film|movie|tv|television|broadway|cast)?\s*"
                      r"(?:soundtrack|score|cast recording)(?:\s+(?:recording|album))?|"
                      r"\s*[-:–]\s*(?:original\s+)?music\s+(?:from|inspired by)\s+.*)\s*$", re.I)


def is_placeholder(name):
    return norm_key(name) in PLACEHOLDER_ARTISTS


def base_title(t):
    """Drop bracketed extras that are not versions: 'Main Title (Taxi Driver)' -> 'Main Title'."""
    out = re.sub(r"\s*[\(\[]([^\)\]]*)[\)\]]",
                 lambda m: m.group(0) if version_words(m.group(1)) or re.search(r"\bfeat", m.group(1), re.I) else "",
                 t or "")
    return out.strip() or (t or "")


def bracket_versions(t):
    """'Imagine - Remastered 2010' -> 'Imagine (Remastered 2010)'."""
    m = VERSION_DASH.search(t or "")
    return f"{t[:m.start()]} ({m.group(1).strip()})" if m else (t or "")


DISC_SUFFIX_RE = re.compile(r"[\s,:;-]*[\(\[\{]?\s*(?:(?:bonus|extra)\s+)?(?:disc|disk|cd)\s*(?:\d{1,2}|one|two|three|four|five|six|i{1,3}|iv|v|vi)(?:\s*(?:of|/)\s*\d{1,2})?\s*[\)\]\}]?\s*$|[\s,:;-]*[\(\[\{]\s*bonus\s+(?:disc|disk|cd)\s*[\)\]\}]\s*$", re.I)


def strip_disc(t):
    """'At Budokan (Disc 1)' / 'Album CD2' / 'Album - Disc Two' -> the real album name (1.1.5: these tags made 'release unclear')."""
    new = DISC_SUFFIX_RE.sub("", t or "").strip()
    return new if len(new) >= 2 else (t or "")


def strip_edition(t):
    t = strip_disc(t)
    t = EDITION_RE.sub("", t or "")
    t = OST_DESC.sub("", t)
    t = re.sub(r"\s+-\s+(single|ep)$", "", t, flags=re.I)
    return t.strip()


def is_latin(s):
    letters = [c for c in (s or "") if c.isalpha()]
    return bool(letters) and all("LATIN" in unicodedata.name(c, "") for c in letters)


try:
    from unidecode import unidecode as _unidecode          # V2.0.3: Latin spelling everywhere (installed by Start Midnight App.bat)
except Exception:                                           # pragma: no cover
    _unidecode = None


def latinize(s):
    """V2.0.3: always Latin spelling (tags, folders, files). Persian / Cyrillic / Japanese ... -> Latin letters. Latin text is untouched."""
    s = s or ""
    if not s or is_latin(s) or not any(c.isalpha() for c in s):
        return s
    if _unidecode is None:
        return s
    out = []
    for word in re.split(r"(\s+)", s):
        out.append(word if (not word.strip() or is_latin(word)) else _unidecode(word).strip().title() if word.isupper() or word.islower() else _unidecode(word))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def prefer_latin(db, mine):
    """V2.0.3: the result is ALWAYS Latin. Database text in another script + your Latin text -> yours; otherwise the database
    text, transliterated when it is not Latin."""
    if db and not is_latin(db) and mine and is_latin(mine):
        return mine
    return latinize(db or mine or "")


EDITION_WORDS = re.compile(r"\b(deluxe|expanded|anniversary|remaster\w*|special edition|bonus tracks?|collector'?s edition|legacy edition|"
                           r"super deluxe|japan(?:ese)? (?:mini[- ]?lp|edition|version)|mini[- ]?lp|mono|stereo|live|demos?|acoustic|"
                           r"limited edition|platinum edition|gold edition|reissue|re-?release|digipak|tour edition|original version|version \d+)\b", re.I)


def edition_words_of(t):
    return {w.lower() for w in EDITION_WORDS.findall(t or "")}


def keep_edition_album(db_album, file_album):
    """V2.0.3 decision 5: edition words of the file (Deluxe Edition, Live, Japan Mini LP ...) stay in the album name when the
    database album is the same album without them."""
    db_album, file_album = (db_album or "").strip(), strip_disc((file_album or "").strip())
    if not file_album or not edition_words_of(file_album):
        return db_album or file_album
    if edition_words_of(file_album) <= edition_words_of(db_album):
        return db_album
    if norm_key(strip_edition(file_album)) == norm_key(strip_edition(db_album)) or ratio(norm_key(strip_edition(file_album)), norm_key(strip_edition(db_album))) >= 0.9:
        return latinize(file_album) if is_latin(file_album) or not is_latin(db_album) else db_album + " " + " ".join(re.findall(r"[\(\[][^\)\]]*[\)\]]", file_album))
    return db_album or file_album


GENERIC_GENRES = {"", "other", "unknown", "genre", "undefined", "none", "various", "misc", "miscellaneous", "blank", "-"}


def keep_file_genre(file_genre, db_genre):
    """V2.0.3 decision 12: the file's own genre stays unless the file has none (or a placeholder). A sure database genre is
    offered per song in Check tags ('Accept, keep my genre' is the other way round)."""
    fg = (file_genre or "").strip()
    return fg if norm_key(fg) not in GENERIC_GENRES else (db_genre or fg)


def keep_version_title(db_title, file_title):
    """V2.0.3: version words in the file's title (Live, Demo, Mono, Acoustic, Remix ...) must stay in the title."""
    db_title, file_title = (db_title or "").strip(), (file_title or "").strip()
    miss = version_words(neutral(file_title)) - version_words(db_title) - {"version"}
    if not miss:
        return db_title or file_title
    groups = [g for g in re.findall(r"[\(\[][^\)\]]*[\)\]]", file_title) if version_words(neutral(g)) & miss]
    return (db_title + " " + " ".join(groups)).strip() if groups else db_title


def credit_info(credit):
    """Artist credit (MusicBrainz-style list) -> printed forms and the list of artists."""
    full, main, feats, names, in_feat = "", "", [], [], False
    credit = credit or []
    for i, c in enumerate(credit):
        nm = c.get("name") or (c.get("artist") or {}).get("name", "")
        names.append(nm)
        jp = c.get("joinphrase", "") or "" if i < len(credit) - 1 else ""
        full += nm + jp
        if in_feat:
            feats.append(nm)
        else:
            main += nm
        if re.search(r"\b(feat|ft|featuring)\b", jp, re.I):
            in_feat = True
        elif not in_feat:
            main += jp
    a0 = (credit[0].get("artist") or {}) if credit else {}
    return {"full": full.strip(), "main": main.strip(" &,"), "feats": feats, "names": names,
            "primary": credit[0].get("name", "") if credit else "", "primary_id": a0.get("id", ""),
            "entity": a0.get("name", "") or (credit[0].get("name", "") if credit else "")}


def simple_credit(name):
    return [{"name": name, "joinphrase": "", "artist": {"name": name, "id": ""}}] if name else []


def classify_mb(ptype, stypes, status, nmedia):
    if status == "Bootleg":
        return "Bootleg"
    if stypes & {"DJ-mix", "Mixtape/Street"}:
        return "Mix"
    if "Live" in stypes:
        return "Live"
    if "Soundtrack" in stypes:
        return "OST"
    if "Remix" in stypes:
        return "Remix"
    if "Compilation" in stypes:
        return "Box" if nmedia >= 4 else "Comp"
    if ptype == "EP":
        return "EP"
    if ptype == "Single":
        return "Single"
    return "Album"


def mb_match(rel, medium, tr, source="MusicBrainz"):
    rg = rel.get("release-group") or {}
    media = rel.get("media") or []
    rc = credit_info(rel.get("artist-credit"))
    tc = credit_info(tr.get("artist-credit") or rel.get("artist-credit"))
    genres = sorted(rel.get("genres") or [], key=lambda g: -g.get("count", 0))
    return {"source": source, "verified": True, "release_id": rel["id"], "mbid": rel["id"],
            "group_id": "mb:" + (rg.get("id") or rel["id"]), "group_title": rg.get("title") or rel.get("title", ""),
            "year": (rg.get("first-release-date") or rel.get("date") or "")[:4], "release_year": (rel.get("date") or "")[:4],
            "rtype": classify_mb(rg.get("primary-type") or "", set(rg.get("secondary-types") or []),
                                 rel.get("status") or "Official", len(media)),
            "ntracks": sum(m.get("track-count") or 0 for m in media),
            "is_va": rc["primary_id"] == VA_MBID or norm_key(rc["entity"]) in VA_NAMES,
            "remaster": bool(REMASTER_RE.search(f"{rel.get('disambiguation') or ''} {rel.get('title') or ''}")),
            "rel_credit": rc, "trk_credit": tc, "title": tr.get("title") or "",
            "track": str(tr.get("position") or ""), "disc": str(medium.get("position") or 1),
            "disctotal": str(len(media)), "tracktotal": str(medium.get("track-count") or ""),
            "maxtrack": max([m.get("track-count") or 0 for m in media] + [0]),
            "genre": genres[0]["name"].title() if genres else "",
            "recording_id": (tr.get("recording") or {}).get("id", ""), "cover_url": "", "hint": 0}

# ----------------------------------------------------------------------------- other sites


LANE = threading.local()          # v2.0: LANE.bg = True while a background search runs
ALT_ORDER = ("discogs", "deezer", "itunes", "tidal", "spotify", "lastfm")
def full_alt_order(cfg):
    """Your site order, with sites added in later versions (e.g. Tidal) placed before Last.fm."""
    cur = [k for k in (cfg.get("alt_order") or ALT_ORDER) if k in ALT_ORDER]
    for k in ALT_ORDER:
        if k not in cur:
            cur.insert(cur.index("lastfm") if "lastfm" in cur and k != "lastfm" else len(cur), k)
    return cur


ALT_NAMES = {"discogs": "Discogs", "deezer": "Deezer", "itunes": "Apple Music", "tidal": "Tidal", "spotify": "Spotify", "lastfm": "Last.fm"}
COVER_ORDER = ("deezer", "itunes", "caa", "discogs")
COVER_NAMES = {"deezer": "Deezer", "itunes": "Apple Music", "caa": "Cover Art Archive", "discogs": "Discogs"}


class AltSources:
    """Discogs (personal token), Deezer, Apple Music / iTunes (no key) and Last.fm (free API key, asked last).
    Used only when MusicBrainz cannot identify a song, and for cover art. Strict matching; nothing is guessed."""
    DZ_TYPES = {"album": "Album", "single": "Single", "ep": "EP", "compile": "Comp"}

    def __init__(self, store, use, discogs_token="", lastfm_key="", tidal_id="", tidal_secret="", spotify_id="", spotify_secret=""):
        self.store, self.use, self.token, self.lfm_key = SharedCache(store), use, discogs_token, lastfm_key
        self.tidal_id, self.tidal_secret, self._tidal_tok = tidal_id, tidal_secret, (None, 0)
        self.spotify_id, self.spotify_secret, self._sp_tok = spotify_id, spotify_secret, (None, 0)
        self.saved_at = time.time()
        self.order = list(ALT_ORDER)                 # other sites, in your priority order (Settings)
        self.cover_order = list(COVER_ORDER)
        self.cache = self.store.load("alt_cache.json")
        self.last = {}
        self.errs = {}                               # v2.0: site -> [count, last problem] (written to _logs\\app_alt_errors.json)
        self.speed = {}                              # v1.1: site -> [seconds spent, answers] (written to _logs\\app_speeds.json)
        self.dirty = 0
        self.locks = defaultdict(threading.Lock)     # one queue per site: each keeps its own speed limit
        self.slots = {}
        self.dead, self.fails = {}, {}
        self.save_lock = threading.Lock()
        LIVE_CACHES.append(self)

    def _get(self, src, url, gap, headers=None):
        check_cancel()
        if url in self.cache:
            return self.cache[url]
        # v2.0: background work (Prepare Review, Dig deeper) waits in its own line, so the song you are looking at is never stuck behind it
        # V2.0.3 decision 17: up to 4 songs are looked up at once. The lock only hands out the next free time slot of the site
        # (its speed limit is kept); the answer itself is awaited outside the lock.
        key_ = src + "#bg" if getattr(LANE, "bg", False) else src
        with self.locks[key_]:
            if url in self.cache:
                return self.cache[url]
            now = time.time()
            slot = max(now, self.slots.get(key_, 0.0))
            self.slots[key_] = slot + gap
        while slot - time.time() > 0:
            check_cancel()
            time.sleep(min(0.2, max(0.0, slot - time.time())))
        if url in self.cache:
            return self.cache[url]
        return self._fetch(src, url, 0, headers)

    def _fetch(self, src, url, gap, headers):
        if CACHE_ONLY:
            return None
        data = None
        if self.dead.get(src, 0) > time.time():          # V2.0.3: a site that keeps failing is skipped for a while instead of being retried (and waited for) song after song
            return None
        for attempt in range(4):
            wait = gap - (time.time() - self.last.get(src, 0))
            Progress.ping({"discogs": "Discogs", "deezer": "Deezer", "itunes": "Apple Music", "tidal": "Tidal", "spotify": "Spotify", "lastfm": "Last.fm"}.get(src, src))
            while wait > 0:                      # sleep in small steps so the spinner keeps moving
                time.sleep(min(wait, 0.2))
                Progress.ping()
                wait -= 0.2
            self.last[src] = time.time()
            try:
                real = url.replace("api_key=LFMKEY", "api_key=" + urllib.parse.quote(self.lfm_key)) if src == "lastfm" else url
                req = urllib.request.Request(real, headers={"User-Agent": f"MusicLibraryManager/{VERSION}",
                                                           "Accept": "application/json", **(headers or {})})
                t_req = time.time()
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.load(r)
                sp = self.speed.setdefault(src, [0.0, 0])
                sp[0] += time.time() - t_req
                sp[1] += 1
                break
            except urllib.error.HTTPError as e:
                self._note_err(src, f"HTTP {e.code}")
                if e.code == 401 and src == "spotify":
                    self._sp_tok = (None, 0)                  # the token ran out: ask for a new one next time
                if e.code in (400, 401, 403, 404):
                    break
                try:
                    ra = int(e.headers.get("Retry-After") or 0) if e.code == 429 else 0
                except Exception:
                    ra = 0
                time.sleep(min(30, ra) if ra else 5 * (attempt + 1))
            except Exception as e:
                self._note_err(src, type(e).__name__)
                if attempt >= 1:
                    break
                time.sleep(3)
        if data is None:
            self.fails[src] = self.fails.get(src, 0) + 1
            if self.fails[src] >= 3:
                self.dead[src] = time.time() + 600
                self.fails[src] = 0
                self._note_err(src, "skipped for 10 minutes after repeated failures")
        else:
            self.fails[src] = 0
        if data is None and src in ("spotify", "tidal"):      # 1.1.5: a failed answer (bad token, rate limit) must not be remembered as "no result"
            return None
        with self.save_lock:
            self.cache[url] = data
            self.dirty += 1
            due = time.time() - self.saved_at > 60
            if due:
                self.saved_at = time.time()
        if due:
            self.save()
        return data

    def _note_err(self, src, what):
        e = self.errs.setdefault(src, [0, ""])
        e[0] += 1
        e[1] = what

    def save(self):
        with self.save_lock:
            snap = dict(self.cache)
            self.saved_at = time.time()
        self.store.save("alt_cache.json", snap)
        try:                                         # v1.1: remember how fast each site really answers (Settings: Sort by fastest)
            logs = self.store.store
            old = logs.load("app_speeds.json", {})
            for k, (tot, n) in list(self.speed.items()):
                if n:
                    o = old.get(k) or {}
                    n0 = o.get("n", 0)
                    old[k] = {"avg": round((o.get("avg", 0) * n0 + tot) / (n0 + n), 3), "n": n0 + n}
            self.speed = {}
            logs.save("app_speeds.json", old)
            if self.errs:                            # v2.0: why a site gave nothing (no keys or answers are written)
                eo = logs.load("app_alt_errors.json", {})
                for k, (n, what) in self.errs.items():
                    eo[k] = {"problems": (eo.get(k) or {}).get("problems", 0) + n, "last": what}
                self.errs = {}
                logs.save("app_alt_errors.json", eo)
        except Exception:
            pass

    @property
    def dhdr(self):
        return {"Authorization": f"Discogs token={self.token}"} if self.token else {}

    @staticmethod
    def _ok(artist, title, duration, c_artist, c_title, c_len):
        if not artist_agrees([c_artist], artist):
            return False
        if same_song_title(c_title, title) < 0.88:
            return False
        if different_version(title, c_title):
            return False
        return not (c_len and duration and abs(c_len - duration) > 10)

    def identify(self, artist, title, album_hint, duration):
        if not artist or not title:
            return None
        for name in self.order:
            if name in self.use and (name != "discogs" or self.token) and (name != "lastfm" or self.lfm_key):
                try:
                    res = getattr(self, name)(artist, title, album_hint, duration)
                except Exception:
                    res = None
                if res:
                    return res
        return None

    @staticmethod
    def _better(a, b):
        return b is None or (a["hint"], a["rtype"] not in ("Comp", "Box")) > (b["hint"], b["rtype"] not in ("Comp", "Box"))

    # ---- Discogs
    @staticmethod
    def _dg_credit(artists):
        out = []
        for a in artists or []:
            ent = re.sub(r"\s\(\d+\)$", "", a.get("name") or "").strip("* ")
            nm = (a.get("anv") or ent).strip("* ")
            j = (a.get("join") or "").strip()
            out.append({"name": nm, "joinphrase": (", " if j == "," else f" {j} ") if j else " & ",
                        "artist": {"name": ent, "id": ""}})
        if out:
            out[-1]["joinphrase"] = ""
        return out

    def discogs(self, artist, title, album_hint, duration):
        base = "https://api.discogs.com/database/search?"
        found = []
        for extra in ([{"release_title": album_hint}] if album_hint else []) + [{}]:
            q = {"type": "release", "artist": artist, "track": title, "per_page": "10", **extra}
            found = (self._get("discogs", base + urllib.parse.urlencode(q), 1.1, self.dhdr) or {}).get("results") or []
            if found:
                break
        best = None
        for c in found[:5]:
            rel = self._get("discogs", f"https://api.discogs.com/releases/{c['id']}", 1.1, self.dhdr)
            if not rel:
                continue
            rcred = self._dg_credit(rel.get("artists"))
            rc = credit_info(rcred)
            tracks = [t for t in rel.get("tracklist") or [] if (t.get("type_") or "track") == "track"]
            for i, t in enumerate(tracks, 1):
                tcred = self._dg_credit(t.get("artists")) or rcred
                feats = [x for x in t.get("extraartists") or [] if "feat" in (x.get("role") or "").lower()]
                if feats:
                    tcred = tcred + [{"name": re.sub(r"\s\(\d+\)$", "", f.get("anv") or f.get("name") or ""),
                                      "joinphrase": "", "artist": {"name": f.get("name", ""), "id": ""}} for f in feats]
                    tcred[len(tcred) - len(feats) - 1]["joinphrase"] = " feat. "
                tc = credit_info(tcred)
                ln = 0
                if re.match(r"^\d+:\d\d$", t.get("duration") or ""):
                    m_, s_ = t["duration"].split(":")
                    ln = int(m_) * 60 + int(s_)
                if not (self._ok(artist, title, duration, tc["primary"], t.get("title"), ln) or
                        self._ok(artist, title, duration, rc["primary"], t.get("title"), ln)):
                    continue
                desc = {x.lower() for f in rel.get("formats") or [] for x in (f.get("descriptions") or [])}
                fnames = {(f.get("name") or "").lower() for f in rel.get("formats") or []}
                gs = {x.lower() for x in (rel.get("genres") or []) + (rel.get("styles") or [])}
                if "unofficial release" in desc:
                    rtype = "Bootleg"
                elif "mixed" in desc:
                    rtype = "Mix"
                elif re.search(r"\blive\b", rel.get("title") or "", re.I):
                    rtype = "Live"
                elif "soundtrack" in gs:
                    rtype = "OST"
                elif "compilation" in desc:
                    rtype = "Box" if "box set" in fnames else "Comp"
                elif {"single", "maxi-single"} & desc:
                    rtype = "Single"
                elif "ep" in desc:
                    rtype = "EP"
                else:
                    rtype = "Album"
                pos = t.get("position") or ""
                m = re.match(r"^(?:CD)?(\d+)[-.](\d+)$", pos, re.I)
                disc, num = (int(m.group(1)), int(m.group(2))) if m else (1, i)
                year = str(rel.get("year") or "")
                if rel.get("master_id"):
                    ms = self._get("discogs", f"https://api.discogs.com/masters/{rel['master_id']}", 1.1, self.dhdr) or {}
                    year = str(ms.get("year") or year)
                imgs = rel.get("images") or []
                res = {"source": "Discogs", "verified": True, "release_id": f"discogs:{rel.get('id')}", "mbid": "",
                       "group_id": f"discogs-master:{rel['master_id']}" if rel.get("master_id") else f"discogs:{rel.get('id')}",
                       "group_title": strip_edition(rel.get("title", "")), "year": "" if year == "0" else year,
                       "release_year": str(rel.get("year") or ""), "rtype": rtype, "ntracks": len(tracks),
                       "is_va": rc["entity"].lower() in ("various", "various artists"),
                       "remaster": "remastered" in desc or bool(REMASTER_RE.search(rel.get("title") or "")),
                       "rel_credit": rc, "trk_credit": tc, "title": t.get("title", ""), "track": str(num),
                       "disc": str(disc), "disctotal": "", "tracktotal": str(len(tracks)), "maxtrack": len(tracks),
                       "genre": (rel.get("genres") or [""])[0], "recording_id": "",
                       "cover_url": next((im.get("uri") for im in imgs if im.get("type") == "primary"),
                                         imgs[0].get("uri") if imgs else ""),
                       "hint": 1 if album_hint and ratio(rel.get("title"), album_hint) >= 0.85 else 0}
                if self._better(res, best):
                    best = res
                break
        return best

    # ---- Deezer
    def deezer(self, artist, title, album_hint, duration):
        found = []
        queries = [f'artist:"{a_}" track:"{title}"' for a_ in artist_parts(artist)[:3]] + [f"{(artist_parts(artist) + [artist])[1 if len(artist_parts(artist)) > 1 else 0]} {title}"]
        for qs in queries:                 # strict first; then each artist of a multi-artist tag; then plain words
            q = urllib.parse.urlencode({"q": qs, "limit": "15"})
            found = (self._get("deezer", "https://api.deezer.com/search?" + q, 0.15) or {}).get("data") or []
            if found:
                break
        best = None
        for c in found:
            if not self._ok(artist, title, duration, (c.get("artist") or {}).get("name"), c.get("title"), c.get("duration")):
                continue
            alb = self._get("deezer", f"https://api.deezer.com/album/{(c.get('album') or {}).get('id')}", 0.15) or {}
            trk = self._get("deezer", f"https://api.deezer.com/track/{c['id']}", 0.15) or {}
            if not alb or not trk or alb.get("error") or trk.get("error"):
                continue
            aa = (alb.get("artist") or {}).get("name", "")
            mains = [x.get("name") for x in trk.get("contributors") or [] if (x.get("role") or "Main") == "Main"] or \
                [(c.get("artist") or {}).get("name", "")]
            feats = [x.get("name") for x in trk.get("contributors") or [] if (x.get("role") or "") == "Featured"]
            tcred = [{"name": n, "joinphrase": " & ", "artist": {"name": n, "id": ""}} for n in mains] + \
                [{"name": n, "joinphrase": " & ", "artist": {"name": n, "id": ""}} for n in feats]
            if feats:
                tcred[len(mains) - 1]["joinphrase"] = " feat. "
            tcred[-1]["joinphrase"] = ""
            atitle = alb.get("title", "")
            rtype = self.DZ_TYPES.get(alb.get("record_type"), "Album")
            if rtype == "Album" and re.search(r"\blive\b", atitle, re.I):
                rtype = "Live"
            res = {"source": "Deezer", "verified": True, "release_id": f"deezer:{alb.get('id')}", "mbid": "",
                   "group_id": f"deezer:{norm_key(aa)}:{norm_key(strip_edition(atitle))}", "group_title": strip_edition(atitle),
                   "year": (alb.get("release_date") or "")[:4], "release_year": (alb.get("release_date") or "")[:4],
                   "rtype": rtype, "ntracks": alb.get("nb_tracks") or 0, "is_va": norm_key(aa) in VA_NAMES,
                   "remaster": bool(REMASTER_RE.search(atitle)), "rel_credit": credit_info(simple_credit(aa)),
                   "trk_credit": credit_info(tcred), "title": c.get("title", ""),
                   "track": str(trk.get("track_position") or ""), "disc": str(trk.get("disk_number") or 1),
                   "disctotal": "", "tracktotal": str(alb.get("nb_tracks") or ""), "maxtrack": alb.get("nb_tracks") or 0,
                   "genre": (((alb.get("genres") or {}).get("data") or [{}])[0]).get("name", ""), "recording_id": "",
                   "cover_url": alb.get("cover_xl") or "", "preview_url": c.get("preview") or trk.get("preview") or "", "deezer_track": c.get("id") or "",
                   "hint": 1 if album_hint and ratio(atitle, album_hint) >= 0.85 else 0}
            if self._better(res, best):
                best = res
            if best["hint"]:
                break
        return best

    # ---- Apple Music / iTunes
    def itunes(self, artist, title, album_hint, duration):
        res_ = []
        for a_ in artist_parts(artist)[:2]:
            q = urllib.parse.urlencode({"term": f"{a_} {title}", "entity": "song", "limit": "25"})
            res_ = (self._get("itunes", "https://itunes.apple.com/search?" + q, 3.1) or {}).get("results") or []
            if res_:
                break
        best = None
        for c in res_:
            ln = (c.get("trackTimeMillis") or 0) / 1000
            if not self._ok(artist, title, duration, c.get("artistName"), c.get("trackName"), ln):
                continue
            coll = c.get("collectionName") or ""
            rtype = "Album"
            m = re.search(r"\s-\s(Single|EP)$", coll)
            if m:
                rtype, coll = m.group(1), coll[:m.start()]
            aa = c.get("collectionArtistName") or c.get("artistName") or ""
            if norm_key(aa) in VA_NAMES:
                rtype = "Comp"
            elif rtype == "Album" and re.search(r"\blive\b", coll, re.I):
                rtype = "Live"
            res = {"source": "Apple Music", "verified": True, "release_id": f"itunes:{c.get('collectionId')}", "mbid": "",
                   "group_id": f"itunes:{norm_key(aa)}:{norm_key(strip_edition(coll))}", "group_title": strip_edition(coll),
                   "year": (c.get("releaseDate") or "")[:4], "release_year": (c.get("releaseDate") or "")[:4],
                   "rtype": rtype, "ntracks": c.get("trackCount") or 0, "is_va": norm_key(aa) in VA_NAMES,
                   "remaster": bool(REMASTER_RE.search(coll)), "rel_credit": credit_info(simple_credit(aa)),
                   "trk_credit": credit_info(simple_credit(c.get("artistName", ""))), "title": c.get("trackName", ""),
                   "track": str(c.get("trackNumber") or ""), "disc": str(c.get("discNumber") or 1),
                   "disctotal": str(c.get("discCount") or ""), "tracktotal": str(c.get("trackCount") or ""),
                   "maxtrack": c.get("trackCount") or 0, "genre": c.get("primaryGenreName", ""), "recording_id": "",
                   "cover_url": (c.get("artworkUrl100") or "").replace("100x100bb", "1000x1000bb"), "preview_url": c.get("previewUrl") or "",
                   "hint": 1 if album_hint and ratio(coll, album_hint) >= 0.85 else 0}
            if self._better(res, best):
                best = res
            if best["hint"]:
                break
        return best

    # ---- Tidal (beta): client credentials from developer.tidal.com. Any problem -> Tidal is simply skipped.
    TIDAL_API = "https://openapi.tidal.com/v2"

    def _tidal_token(self):
        tok, exp = self._tidal_tok
        if tok and time.time() < exp - 60:
            return tok
        if not (self.tidal_id and self.tidal_secret):
            return None
        try:
            import base64
            req = urllib.request.Request("https://auth.tidal.com/v1/oauth2/token", data=b"grant_type=client_credentials",
                                         headers={"Authorization": "Basic " + base64.b64encode(f"{self.tidal_id}:{self.tidal_secret}".encode()).decode(),
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            self._tidal_tok = (d.get("access_token"), time.time() + int(d.get("expires_in") or 3600))
            return self._tidal_tok[0]
        except Exception:
            self._tidal_tok = (None, time.time() + 600)       # do not ask again for 10 minutes
            return None

    def _tget(self, path):
        tok = self._tidal_token()
        if not tok:
            return None
        sep = "&" if "?" in path else "?"
        return self._get("tidal", f"{self.TIDAL_API}{path}{sep}countryCode=US", 0.6,
                         {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.api+json"})

    @staticmethod
    def _iso_len(v):
        m = re.match(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?$", v or "")
        return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3) or 0)) if m else 0

    @staticmethod
    def _incl(d):
        return {(x.get("type"), x.get("id")): x for x in (d or {}).get("included") or []}

    def tidal_album(self, album_id):
        """One Tidal album with all its tracks -> a release view (like a pasted link)."""
        d = self._tget(f"/albums/{album_id}?include=items,artists")
        if not d or not d.get("data"):
            return {"error": "Tidal does not know this album."}
        a = d["data"].get("attributes") or {}
        inc = self._incl(d)
        rel_artists = [((inc.get(("artists", x.get("id"))) or {}).get("attributes") or {}).get("name", "")
                       for x in (((d["data"].get("relationships") or {}).get("artists") or {}).get("data") or [])]
        aa = " & ".join(n for n in rel_artists if n) or ""
        year = (a.get("releaseDate") or "")[:4]
        items = (((d["data"].get("relationships") or {}).get("items") or {}).get("data") or [])
        tracks = []
        for i, it in enumerate(items, 1):
            t = inc.get(("tracks", it.get("id")))
            if not t:
                continue
            ta = t.get("attributes") or {}
            meta = it.get("meta") or {}
            m = _alt_track_match("Tidal", f"tidal:{album_id}", f"tidal:{norm_key(aa)}:{norm_key(strip_edition(a.get('title', '')))}",
                                 a.get("title", ""), aa, year, "Album" if (a.get("type") or "ALBUM") == "ALBUM" else a.get("type", "").title(),
                                 len(items), ta.get("title", "") + (f" ({ta['version']})" if ta.get("version") else ""), [aa],
                                 meta.get("trackNumber") or i, meta.get("volumeNumber") or 1, "", "")
            tracks.append((m, self._iso_len(ta.get("duration"))))
        return {"tracks": tracks, "head": {"title": a.get("title", ""), "artist": aa, "year": year, "source": "Tidal", "cover_url": ""}}

    def tidal(self, artist, title, album_hint, duration):
        try:
            q = urllib.parse.quote(f"{artist} {title}".strip(), safe="")
            d = self._tget(f"/searchResults/{q}?include=tracks")
            inc = self._incl(d)
            ids = [x.get("id") for x in ((((d or {}).get("data") or {}).get("relationships") or {}).get("tracks") or {}).get("data") or []]
            best = None
            for tid in ids[:8]:
                t = inc.get(("tracks", tid))
                ta = (t or {}).get("attributes") or {}
                if not ta:
                    continue
                td = self._tget(f"/tracks/{tid}?include=albums,artists") or {}
                tinc = self._incl(td)
                rel = (td.get("data") or {}).get("relationships") or {}
                names = [((tinc.get(("artists", x.get("id"))) or {}).get("attributes") or {}).get("name", "") for x in (rel.get("artists") or {}).get("data") or []]
                ttl = ta.get("title", "") + (f" ({ta['version']})" if ta.get("version") else "")
                if not self._ok(artist, title, duration, " & ".join(n for n in names if n) or artist, ttl, self._iso_len(ta.get("duration"))):
                    continue
                alb_ids = [x.get("id") for x in (rel.get("albums") or {}).get("data") or []]
                for aid in alb_ids[:2]:
                    v = self.tidal_album(aid)
                    for m, ln in v.get("tracks") or []:
                        if same_song_title(m["title"], ttl) >= 0.88:
                            m = dict(m, hint=1 if album_hint and ratio(v["head"]["title"], album_hint) >= 0.85 else 0)
                            if self._better(m, best):
                                best = m
                            break
                if best and best.get("hint"):
                    break
            return best
        except Cancelled:
            raise
        except Exception:
            return None


    # ---- Spotify (v1.1.5): search needs a free app key (client credentials, no login). Any problem -> Spotify is skipped.
    def _sp_token(self):
        tok, exp = self._sp_tok
        if tok and time.time() < exp - 60:
            return tok
        if not (self.spotify_id and self.spotify_secret) or CACHE_ONLY:
            return None
        try:
            import base64
            req = urllib.request.Request("https://accounts.spotify.com/api/token", data=b"grant_type=client_credentials",
                                         headers={"Authorization": "Basic " + base64.b64encode(f"{self.spotify_id}:{self.spotify_secret}".encode()).decode(),
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            self._sp_tok = (d.get("access_token"), time.time() + int(d.get("expires_in") or 3600))
            return self._sp_tok[0]
        except Exception as e:
            self._note_err("spotify", "token: " + (f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__))
            self._sp_tok = (None, time.time() + 60)
            return None

    def _spget(self, path):
        tok = self._sp_token()
        if not tok:
            return None
        return self._get("spotify", "https://api.spotify.com/v1" + path, 0.35, {"Authorization": f"Bearer {tok}"})

    def spotify_album(self, album_id):
        """One Spotify album with all its tracks -> a release view (like a pasted link)."""
        a = self._spget(f"/albums/{album_id}") or {}
        if not a.get("id"):
            return {"error": "Spotify does not know this album (or the Spotify key is missing)."}
        aa = " & ".join(x.get("name", "") for x in a.get("artists") or [] if x.get("name"))
        year = (a.get("release_date") or "")[:4]
        items = (a.get("tracks") or {}).get("items") or []
        rtype = {"album": "Album", "single": "Single", "compilation": "Comp"}.get(a.get("album_type"), "Album")
        cover = ((a.get("images") or [{}])[0]).get("url", "")
        tracks = []
        for i, t in enumerate(items, 1):
            m = _alt_track_match("Spotify", f"spotify:{album_id}", f"spotify:{norm_key(aa)}:{norm_key(strip_edition(a.get('name', '')))}",
                                 a.get("name", ""), aa, year, rtype, a.get("total_tracks") or len(items), t.get("name", ""),
                                 [x.get("name", "") for x in t.get("artists") or []] or [aa], t.get("track_number") or i,
                                 t.get("disc_number") or 1, "", cover)
            tracks.append((m, (t.get("duration_ms") or 0) / 1000))
        return {"tracks": tracks, "head": {"title": a.get("name", ""), "artist": aa, "year": year, "source": "Spotify", "cover_url": cover}}

    def spotify(self, artist, title, album_hint, duration):
        try:
            q = urllib.parse.quote(f'track:{title} artist:{artist}'.strip() if artist else f'track:{title}', safe="")
            d = self._spget(f"/search?q={q}&type=track&limit=8") or {}
            best = None
            for t in ((d.get("tracks") or {}).get("items") or [])[:8]:
                names = " & ".join(x.get("name", "") for x in t.get("artists") or [] if x.get("name")) or artist
                if not self._ok(artist, title, duration, names, t.get("name", ""), (t.get("duration_ms") or 0) / 1000):
                    continue
                aid = (t.get("album") or {}).get("id")
                if not aid:
                    continue
                v = self.spotify_album(aid)
                if not v.get("tracks"):                          # v2.0: the album page was refused -> use what the search itself told us about this track
                    al = t.get("album") or {}
                    rtype = {"album": "Album", "single": "Single", "compilation": "Comp"}.get(al.get("album_type"), "Album")
                    aa = " & ".join(x.get("name", "") for x in al.get("artists") or [] if x.get("name")) or names
                    cover = ((al.get("images") or [{}])[0]).get("url", "")
                    m = _alt_track_match("Spotify", f"spotify:{aid}", f"spotify:{norm_key(aa)}:{norm_key(strip_edition(al.get('name', '')))}",
                                         al.get("name", ""), aa, (al.get("release_date") or "")[:4], rtype, al.get("total_tracks") or 0, t.get("name", ""),
                                         [x.get("name", "") for x in t.get("artists") or []] or [aa], t.get("track_number") or 0, t.get("disc_number") or 1, "", cover)
                    m = dict(m, hint=1 if album_hint and ratio(al.get("name", ""), album_hint) >= 0.85 else 0)
                    if self._better(m, best):
                        best = m
                    continue
                for m, ln in v.get("tracks") or []:
                    if same_song_title(m["title"], t.get("name", "")) >= 0.88:
                        m = dict(m, hint=1 if album_hint and ratio(v["head"]["title"], album_hint) >= 0.85 else 0)
                        if self._better(m, best):
                            best = m
                        break
                if best and best.get("hint"):
                    break
            return best
        except Cancelled:
            raise
        except Exception:
            return None

    # ---- Last.fm (asked last). The key is never stored in the cache: URLs keep the placeholder LFMKEY.
    def _lfm(self, method, **params):
        q = urllib.parse.urlencode({"method": method, **params, "autocorrect": "1", "format": "json"})
        d = self._get("lastfm", f"https://ws.audioscrobbler.com/2.0/?api_key=LFMKEY&{q}", 0.25) or {}
        return {} if d.get("error") else d

    def lfm_similar(self, artist, limit=12):
        """v1.1.5 suggestions: artists like this one (Last.fm). [] if no key / no answer."""
        if not self.lfm_key:
            return []
        d = self._lfm("artist.getsimilar", artist=artist, limit=str(limit))
        out = []
        for a in ((d.get("similarartists") or {}).get("artist") or []):
            try:
                out.append((a.get("name", ""), float(a.get("match") or 0)))
            except (TypeError, ValueError):
                pass
        return out

    def lfm_artist(self, artist):
        """{'listeners': n, 'plays': n, 'name': name} or {}"""
        if not self.lfm_key:
            return {}
        a = self._lfm("artist.getinfo", artist=artist).get("artist") or {}
        st = a.get("stats") or {}
        try:
            return {"name": a.get("name", artist), "listeners": int(st.get("listeners") or 0), "plays": int(st.get("playcount") or 0)}
        except (TypeError, ValueError):
            return {}

    def lfm_top_albums(self, artist, limit=3):
        if not self.lfm_key:
            return []
        d = self._lfm("artist.gettopalbums", artist=artist, limit=str(limit))
        al = (d.get("topalbums") or {}).get("album") or []
        return [x.get("name", "") for x in (al if isinstance(al, list) else [al]) if x.get("name")]

    def lastfm(self, artist, title, album_hint, duration):
        """Accepted only if the song is found IN an album's track list on Last.fm with the same artist, title and
        length (within 10 s). If Last.fm links the album to MusicBrainz, the caller re-reads it from MusicBrainz.
        Last.fm has no reliable release dates or types, so the year is left empty unless MusicBrainz gives it."""
        tr = (self._lfm("track.getInfo", artist=artist, track=title).get("track") or {})
        albums = []
        if tr and self._ok(artist, title, duration, (tr.get("artist") or {}).get("name"), tr.get("name"),
                           int(tr.get("duration") or 0) / 1000):
            al = tr.get("album") or {}
            if al.get("title"):
                albums.append((al.get("artist") or artist, al["title"]))
        if album_hint and not any(ratio(a[1], album_hint) >= 0.85 for a in albums):
            albums.insert(0, (artist, album_hint))
        best = None
        for a_artist, a_title in albums[:2]:
            alb = self._lfm("album.getInfo", artist=a_artist, album=a_title).get("album") or {}
            tracks = (alb.get("tracks") or {}).get("track") or []
            if isinstance(tracks, dict):
                tracks = [tracks]
            if not tracks or ratio(alb.get("artist"), artist) < 0.85 and norm_key(artist) not in norm_key(alb.get("artist")):
                continue
            for i, t in enumerate(tracks, 1):
                t_artist = (t.get("artist") or {}).get("name") or alb.get("artist")
                if not self._ok(artist, title, duration, t_artist, t.get("name"), int(t.get("duration") or 0)):
                    continue
                name = alb.get("name") or a_title
                rtype = "Single" if len(tracks) == 1 or re.search(r"\s-\s*Single$", name, re.I) else \
                    "EP" if re.search(r"(\s-\s*|\s)EP$", name) else \
                    "Live" if re.search(r"\blive\b", name, re.I) else "Album"
                name = re.sub(r"\s-\s*(Single|EP)$", "", name)
                aa = alb.get("artist") or artist
                pos = int((t.get("@attr") or {}).get("rank") or i)
                res = {"source": "Last.fm", "verified": True, "release_id": f"lastfm:{norm_key(aa)}:{norm_key(name)}",
                       "mbid": "", "lfm_mbid": alb.get("mbid") or "",
                       "group_id": f"lastfm:{norm_key(aa)}:{norm_key(strip_edition(name))}", "group_title": strip_edition(name),
                       "year": "", "release_year": "", "rtype": rtype, "ntracks": len(tracks),
                       "is_va": norm_key(aa) in VA_NAMES, "remaster": bool(REMASTER_RE.search(name)),
                       "rel_credit": credit_info(simple_credit(aa)), "trk_credit": credit_info(simple_credit(t_artist)),
                       "title": t.get("name", ""), "track": str(pos), "disc": "1", "disctotal": "",
                       "tracktotal": str(len(tracks)), "maxtrack": len(tracks), "genre": "", "recording_id": "",
                       "cover_url": "", "hint": 1 if album_hint and ratio(name, album_hint) >= 0.85 else 0}
                if self._better(res, best):
                    best = res
                break
            if best and best["hint"]:
                break
        return best

    # ---- cover art: Deezer -> Apple Music -> Cover Art Archive -> Discogs (same release only).
    # A generator: each site is asked only if the previous one had nothing usable.
    def cover_candidates(self, artist, album, year, mbid, discogs_url):
        """Cover art, same release only, in your cover order (Settings; default Deezer -> Apple Music ->
        Cover Art Archive -> Discogs). A generator: each site is asked only if the previous one had nothing usable."""
        def same(a, al, y):
            return ratio(a, artist) >= 0.85 and ratio(strip_edition(al), album) >= 0.85 and \
                (not year or not y or abs(int(y) - int(year)) <= 1)

        def deezer():
            q = urllib.parse.urlencode({"q": f'artist:"{artist}" album:"{album}"', "limit": "10"})
            for c in (self._get("deezer", "https://api.deezer.com/search/album?" + q, 0.15) or {}).get("data") or []:
                if ratio((c.get("artist") or {}).get("name"), artist) >= 0.85 and ratio(strip_edition(c.get("title")), album) >= 0.85:
                    alb = self._get("deezer", f"https://api.deezer.com/album/{c['id']}", 0.15) or {}
                    if same((alb.get("artist") or {}).get("name"), alb.get("title", ""), (alb.get("release_date") or "")[:4]) \
                            and alb.get("cover_xl"):
                        return alb["cover_xl"]

        def itunes():
            q = urllib.parse.urlencode({"term": f"{artist} {album}", "entity": "album", "limit": "10"})
            for c in (self._get("itunes", "https://itunes.apple.com/search?" + q, 3.1) or {}).get("results") or []:
                coll = re.sub(r"\s-\s(Single|EP)$", "", c.get("collectionName") or "")
                if same(c.get("artistName"), coll, (c.get("releaseDate") or "")[:4]) and c.get("artworkUrl100"):
                    return c["artworkUrl100"].replace("100x100bb", "1000x1000bb")

        def caa():
            return f"https://coverartarchive.org/release/{mbid}/front-1200" if mbid else None

        def discogs():
            if discogs_url:
                return discogs_url
            if not self.token:
                return None
            q = urllib.parse.urlencode({"type": "release", "artist": artist, "release_title": album, "per_page": "5"})
            for c in (self._get("discogs", "https://api.discogs.com/database/search?" + q, 1.1, self.dhdr) or {}).get("results") or []:
                a_, _, al_ = c.get("title", "").partition(" - ")
                if same(a_, al_, str(c.get("year") or "")) and c.get("cover_image"):
                    return c["cover_image"]

        fns = {"deezer": deezer, "itunes": itunes, "caa": caa, "discogs": discogs}
        for site in self.cover_order:
            try:
                url = fns[site]()
            except Exception:
                url = None
            if url:
                yield (COVER_NAMES[site], url)

# ----------------------------------------------------------------------------- configuration

def up_dirs(here=None, levels=3):
    """This folder and up to 3 folders above it (e.g. _NEW WORLD ORDER\\Midnight App\\V1.0 -> _NEW WORLD ORDER)."""
    out = [here or APP_DIR]
    for _ in range(levels):
        up = os.path.dirname(out[-1])
        if not up or up == out[-1]:
            break
        out.append(up)
    return out


def _chosen_tool(name):
    """v1.1: a tool you picked by hand (Settings > Choose...) is remembered in the same small file as the library."""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".music_library_manager.json"), encoding="utf-8") as f:
            p = (json.load(f).get("tools") or {}).get(name, "")
        return p if p and os.path.isfile(p) else ""
    except Exception:
        return ""


def find_tool(name):
    chosen = _chosen_tool(name)
    if chosen:
        return chosen
    cands = [c for d in up_dirs() for c in (os.path.join(d, name + ".exe"), os.path.join(d, name))]
    for c in cands + [os.path.join(BUNDLE_DIR, name + ".exe")]:    # last: the copy packed inside the app
        if os.path.isfile(c):
            return c
    return shutil.which(name) or ""


def ask_order(title, current, names):
    """Show an order and let you change it: type the numbers in the order you want (e.g. 3 1 2 4)."""
    say(f"  {title}: " + "  ".join(f"{i}) {names[k]}" for i, k in enumerate(current, 1)))
    while True:
        a = ask("  New order (numbers, Enter = keep)", "").replace(",", " ").split()
        if not a:
            return list(current)
        if sorted(a) == [str(i) for i in range(1, len(current) + 1)]:
            new = [current[int(x) - 1] for x in a]
            say("  Now: " + " -> ".join(names[k] for k in new))
            return new
        say(f"  Please type each number 1-{len(current)} once.")


def setup(argv):
    hr(f"Midnight 00:01 · Music Sorter  v{VERSION}")
    memo_path = os.path.join(os.path.expanduser("~"), ".music_library_manager.json")
    try:
        with open(memo_path, encoding="utf-8") as f:
            memo = json.load(f)
    except Exception:
        memo = {}
    # 1) where is the music?
    say("\n Step 1 - Where is your music?")
    say("   Type a folder path, or type  whole scan  to search the entire computer.")
    while True:
        src = ask("   Music folder", memo.get("source", ""))
        if src.strip().lower().replace("!", "") in ("whole scan", "wholescan", "whole"):
            src = "whole scan"
            break
        src = clean_input_path(src)
        if src and os.path.isdir(src):
            break
        say("   That folder does not exist. Try again.")
    # 2) where should the organized library go? (logs are kept automatically in <library>\_logs)
    say("\n Step 2 - Where should the organized library go?")
    while True:
        lib = clean_input_path(ask("   Output folder (example: C:\\WORKPLACE\\_NEW WORLD ORDER\\MUSIC - 0001)",
                                   memo.get("library", "")))
        if not lib:
            continue
        if src != "whole scan" and inside(lib, src):
            say("   The output folder must not be inside the music folder. Choose another one.")
            continue
        break
    logs = argv[argv.index("--logs") + 1] if "--logs" in argv else os.path.join(lib, "_logs")
    os.makedirs(lp(logs), exist_ok=True)
    st = Store(logs)
    cfg = st.load("config.json", {})
    cfg["library"] = lib
    cfg["start_source"] = src
    cfg.setdefault("ffmpeg", find_tool("ffmpeg"))
    cfg.setdefault("fpcalc", find_tool("fpcalc"))
    if cfg["ffmpeg"] and not os.path.isfile(cfg["ffmpeg"]) and not shutil.which(cfg["ffmpeg"]):
        cfg["ffmpeg"] = find_tool("ffmpeg")
    if not cfg["ffmpeg"] and not cfg.get("ffmpeg_asked"):
        cfg["ffmpeg"] = clean_input_path(ask("ffmpeg not found. Path to ffmpeg.exe (recommended; Enter to skip)", ""))
        cfg["ffmpeg_asked"] = True
    st.save("config.json", cfg)
    memo.update(logs=logs, library=lib, source=src)
    try:
        with open(memo_path, "w", encoding="utf-8") as f:
            json.dump(memo, f)
    except Exception:
        pass
    say(f" Library : {cfg['library']}\n Logs    : {logs}\n ffmpeg  : {cfg['ffmpeg'] or 'not found (audio hash limited to MP3/FLAC/WAV/AIFF)'}"
        f"\n fpcalc  : {cfg['fpcalc'] or 'not found (duplicates matched by title+artist+duration)'}")
    return st, cfg


def protected_dirs(cfg):
    return [p for p in (cfg.get("library"), cfg.get("archive")) if p]

# ----------------------------------------------------------------------------- Phase 1: sources

SKIP_NESTED = False          # V2.0.3 (Settings): skip sub-folders whose name starts with "_" inside a source (_Full Collection, _Sorted ...)


def is_skipped_dir(path, name, excludes):
    n = name.lower()
    if SKIP_NESTED and n.startswith("_"):
        return True
    if n in ("_loonybin", "loony bin", "_leftout", "_duplicates"):          # app folders: extra copies / left-out songs are not music to sort
        return True
    if n in SKIP_DIR_NAMES or n.startswith("$") or (n.startswith(".") and n not in (".", "..")):
        return True
    return any(inside(path, ex) for ex in excludes)


def walk_music(root, recursive, excludes):
    if os.path.isfile(root):                      # v1.1.4: a single song can be a source
        if os.path.splitext(root)[1].lower() in AUDIO_EXTS:
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_skipped_dir(os.path.join(dirpath, d), d, excludes)) \
            if recursive else []
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1].lower() in AUDIO_EXTS:
                yield os.path.join(dirpath, fn)


def group_root(path):
    drive, rest = os.path.splitdrive(path)
    parts = [p for p in re.split(r"[\\/]", rest) if p]
    return os.path.join(drive + os.sep, *parts[:2]) if parts else drive + os.sep


def choose_sources(cfg):
    preset = cfg.pop("start_source", "")
    prev = [x["path"] for x in cfg.get("sources", [])]
    if preset and preset != "whole scan" and len(prev) == 1 and same_path(prev[0], preset):
        return                                    # same folder as last time: keep its excludes
    if preset:
        whole = preset == "whole scan"
        p = "" if whole else preset
    elif cfg.get("sources"):
        say("\nPrevious sources:")
        for s in cfg["sources"][:15]:
            say(f"   {s['path']}{'  (+ subfolders)' if s['recursive'] else ''}")
        if len(cfg["sources"]) > 15:
            say(f"   ... and {len(cfg['sources']) - 15} more")
        if ask_yn("Use the same sources again?", "y"):
            return
    if not preset:
      say("\nWhere is the music?  Type a folder path, or type  whole scan  to search the entire computer.")
      while True:
        s = ask("Source")
        if s.strip().lower().replace("!", "") in ("whole scan", "wholescan", "whole"):
            whole = True
            break
        p = clean_input_path(s)
        if p and os.path.isdir(p):
            whole = False
            break
        say("   That folder does not exist. Try again.")
    say("Folders to EXCLUDE (one per line, empty line to finish):")
    excludes = []
    while True:
        e = clean_input_path(ask("  exclude"))
        if not e:
            break
        excludes.append(e)
    excludes += protected_dirs(cfg)
    cfg["excludes"] = excludes
    if not whole:
        cfg["sources"] = [{"path": p, "recursive": True}]
        return
    roots = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if IS_WIN else ["/"]
    say(f"Searching {', '.join(roots)} for music (this can take a few minutes)...")
    counts = {}
    seen = 0
    prog = Progress("Searching folders")
    for r in roots:
        for dirpath, dirnames, filenames in os.walk(r):
            dirnames[:] = [d for d in dirnames if not is_skipped_dir(os.path.join(dirpath, d), d, excludes)]
            seen += 1
            prog.step(f"{sum(counts.values()):,} music files found - {dirpath[-60:]}")
            n = sum(1 for fn in filenames if os.path.splitext(fn)[1].lower() in AUDIO_EXTS)
            if n:
                counts[dirpath] = n
    prog.done()
    groups = defaultdict(list)
    for d in sorted(counts):
        groups[group_root(d)].append(d)
    say(f"Found {sum(counts.values()):,} music files in {len(counts):,} folders, in {len(groups)} areas.\n")
    chosen = []
    for g, dirs in groups.items():
        total = sum(counts[d] for d in dirs)
        if len(dirs) == 1:
            if ask_yn(f'Should I use "{dirs[0]}"? There are {total} music files inside it.', "y"):
                chosen.append(dirs[0])
            continue
        c = ask_choice(f'Should I use "{g}"? There are {total:,} music files in {len(dirs)} folders inside it.',
                       {"y": "es, all", "n": "o", "d": "ecide per folder"}, "y")
        if c == "y":
            chosen += dirs
        elif c == "d":
            for d in dirs:
                c2 = ask_choice(f'   "{d}" ({counts[d]} files)', {"y": "es", "n": "o", "a": "ll remaining here",
                                                                    "s": "kip remaining here"}, "y")
                if c2 == "y":
                    chosen.append(d)
                elif c2 == "a":
                    chosen += dirs[dirs.index(d):]
                    break
                elif c2 == "s":
                    break
    cfg["sources"] = [{"path": d, "recursive": False} for d in chosen]

# ----------------------------------------------------------------------------- Phase 1: inventory + audit

def inspect(path, old, ffmpeg):
    stt = os.stat(lp(path))
    if old and old.get("size") == stt.st_size and old.get("mtime") == int(stt.st_mtime) and old.get("sha256"):
        return old
    rec = {"path": path, "filename": os.path.basename(path), "folder": os.path.dirname(path),
           "ext": os.path.splitext(path)[1].lower(), "size": stt.st_size, "mtime": int(stt.st_mtime)}
    rec.update(read_audio(path))
    rec["sha256"] = sha256_file(path)
    rec["audio_hash"] = audio_hash(path, ffmpeg)
    return rec


def phase1(st, cfg):
    hr("PHASE 1 - Scan & audit (read-only: nothing is changed)")
    choose_sources(cfg)
    st.save("config.json", cfg)
    excludes = cfg.get("excludes", []) + protected_dirs(cfg)
    files, seen = [], set()
    for s in cfg["sources"]:
        for p in walk_music(s["path"], s["recursive"], excludes):
            k = os.path.normcase(p)
            if k not in seen:
                seen.add(k)
                files.append(p)
    if not files:
        say("No music files found in the chosen sources.")
        return
    say(f"Reading {len(files):,} files (tags, quality, SHA-256 and audio-stream hashes)...")
    old = {os.path.normcase(r["path"]): r for r in st.load("inventory.json", [])}
    inv, done, t0 = [], 0, time.time()
    prog = Progress("Reading files", len(files))
    with cf.ThreadPoolExecutor(max_workers=min(10, max(4, (os.cpu_count() or 4) + 2))) as ex:      # v1.1.5: reading is 80% of a scan (your timings: 298 s of 371 s)
        def inspect_c(*a):
            check_cancel()
            return inspect(*a)
        futs = {ex.submit(inspect_c, p, old.get(os.path.normcase(p)), cfg.get("ffmpeg")): p for p in files}
        for fu in cf.as_completed(futs):
            p = futs[fu]
            check_cancel()
            try:
                inv.append(fu.result())
            except Exception as e:
                inv.append({"path": p, "filename": os.path.basename(p), "folder": os.path.dirname(p),
                            "ext": os.path.splitext(p)[1].lower(), "size": 0, "mtime": 0, "error": f"unreadable: {e}",
                            "tags": {k: "" for k in TAG_KEYS}, "duration": 0, "bitrate": 0, "lossless": False,
                            "has_cover": False, "cover_px": 0, "sha256": "", "audio_hash": ""})
            done += 1
            prog.step(os.path.basename(p))
    prog.done()
    # stable file ids
    ids = {os.path.normcase(r["path"]): r.get("id") for r in old.values() if r.get("id")}
    nxt = max([int(i[1:]) for i in ids.values()] + [0]) + 1
    for r in sorted(inv, key=lambda r: r["path"].lower()):
        r["id"] = ids.get(os.path.normcase(r["path"])) or f"F{nxt:06d}"
        if r["id"] == f"F{nxt:06d}":
            nxt += 1
    # keep already-organized songs known (their originals may be archived now), so re-checks include them
    prov = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    have = {r["id"] for r in inv}
    kept = [o for o in old.values() if o.get("id") and o["id"] not in have and
            prov.get(o["id"], {}).get("status") in ("verified", "copied", "original_archived")]
    inv += kept
    inv.sort(key=lambda r: r["id"])
    st.save("inventory.json", inv)
    new_n = sum(1 for r in inv if os.path.normcase(r["path"]) not in old)
    say(f" {new_n:,} new files since the last scan" + (f"; {len(kept):,} organized songs kept on record" if kept else ""))
    # playlists (.m3u / .m3u8) in the same folders - only read, never touched
    pls, seen_pl = [], set()
    for s_ in cfg["sources"]:
        for dirpath, dirnames, filenames in os.walk(s_["path"]):
            if not s_["recursive"]:
                dirnames[:] = []
            else:
                dirnames[:] = [d for d in dirnames if not is_skipped_dir(os.path.join(dirpath, d), d, excludes)]
            for fn in filenames:
                if fn.lower().endswith((".m3u", ".m3u8")):
                    p = os.path.join(dirpath, fn)
                    if os.path.normcase(p) not in seen_pl:
                        seen_pl.add(os.path.normcase(p))
                        pls.append(p)
    st.save("playlists.json", pls)
    write_audit(st, inv)
    if pls:
        say(f" Playlists found: {len(pls)} (they will be recreated for the new library in Phase 3)")
    notify(f"Phase 1 finished - {len(inv):,} files scanned")


def write_audit(st, inv):
    flags = defaultdict(list)          # flag -> [(rec, detail)]
    fmt = Counter(r["ext"] for r in inv)
    total = sum(r.get("size", 0) for r in inv)
    for r in inv:
        t = r["tags"]
        if r.get("error"):
            flags["Corrupt or unreadable"].append((r, r["error"]))
            continue
        for k in ("artist", "albumartist", "album", "title", "track", "year", "genre"):
            if not t.get(k):
                flags[f"Missing tag: {k}"].append((r, ""))
        if not r.get("has_cover"):
            flags["Missing cover art"].append((r, ""))
        elif r.get("cover_px") and r["cover_px"] < 500:
            flags["Cover art smaller than 500x500"].append((r, f"{r['cover_px']}px"))
        for k in ("artist", "albumartist", "album", "title"):
            if has_junk(t.get(k)):
                flags["Junk in tags"].append((r, f"{k}: {t[k]}"))
        if has_junk(os.path.splitext(r["filename"])[0]) and not re.match(r"^\d", r["filename"]):
            flags["Junk in filename"].append((r, r["filename"]))
        if re.search(r"\b(ft\.?|featuring|feat)\b", t.get("artist", ""), re.I):
            flags["Featured artist inside Artist tag"].append((r, t["artist"]))
        if not (t.get("artist") or t.get("albumartist")) and " - " not in r["filename"]:
            flags["No identifiable artist"].append((r, ""))
        if r.get("duration", 0) < 60 and not (t.get("title") or t.get("artist")):
            flags["Short untagged file (< 1 min) -> _Short Files"].append((r, f"{r.get('duration', 0):.0f}s"))
        if r.get("duration", 0) > 1200 and looks_spoken(r, {}):
            flags["Looks like an audiobook / podcast (> 20 min) -> _Long Files unless confirmed"].append(
                (r, f"{r.get('duration', 0) / 60:.0f} min"))
        if r["ext"] == ".mp3" and 0 < r.get("bitrate", 0) < 128:
            flags["Low quality (MP3 below 128 kbps)"].append((r, f"{r['bitrate']} kbps"))
    # artist spelling variants
    spell = defaultdict(Counter)
    for r in inv:
        for k in ("artist", "albumartist"):
            a = split_feat(r["tags"].get(k, ""))[0]
            if a:
                spell[norm_key(a)][a] += 1
    variants = {k: c for k, c in spell.items() if len(c) > 1}
    # albums
    albums = defaultdict(list)
    for r in inv:
        if r["tags"].get("album") and not r.get("error"):
            albums[(norm_key(r["tags"]["album"]), r["folder"])].append(r)
    comps, incomplete, inconsistent = [], [], []
    for (ak, folder), rs in albums.items():
        t0 = rs[0]["tags"]
        artists = {norm_key(split_feat(r["tags"]["artist"])[0]) for r in rs if r["tags"]["artist"]}
        aa = norm_key(t0.get("albumartist"))
        if aa in VA_NAMES or any(r["tags"].get("compilation") in ("1", "true", "True") for r in rs) \
                or len(artists) >= 3 or COMP_RE.search(t0["album"]):
            comps.append((t0["album"], folder, len(rs), len(artists)))
        nums = sorted({int(r["tags"]["track"]) for r in rs if r["tags"].get("track", "").isdigit()})
        tot = max([int(r["tags"]["tracktotal"]) for r in rs if r["tags"].get("tracktotal", "").isdigit()] + [0])
        if (tot and len(nums) < tot) or (nums and len(nums) < nums[-1]):
            incomplete.append((t0.get("albumartist") or t0.get("artist"), t0["album"], len(nums), tot or nums[-1]))
        for k in ("albumartist", "year"):
            vals = {r["tags"].get(k) for r in rs}
            if len(vals) > 1:
                inconsistent.append((t0["album"], k, ", ".join(sorted(v or "(empty)" for v in vals))))
    # duplicate candidates (anywhere)
    dups = defaultdict(list)
    for r in inv:
        if r.get("audio_hash"):
            dups["same audio: " + r["audio_hash"]].append(r)
    by_song = defaultdict(list)
    for r in inv:
        t = r["tags"]
        a = norm_key(split_feat(t.get("artist") or t.get("albumartist"))[0])
        ti = title_key(clean_title(t.get("title")))
        if a and ti:
            by_song[(a, ti)].append(r)
    for (a, ti), rs in by_song.items():
        rs.sort(key=lambda r: r.get("duration", 0))
        cluster = [rs[0]]
        for r in rs[1:]:
            if abs(r.get("duration", 0) - cluster[-1].get("duration", 0)) <= 2:
                cluster.append(r)
            else:
                if len(cluster) > 1:
                    dups[f"same song: {a}/{ti}/{cluster[0]['id']}"] = cluster
                cluster = [r]
        if len(cluster) > 1:
            dups[f"same song: {a}/{ti}/{cluster[0]['id']}"] = cluster
    dup_groups = [v for v in dups.values() if len(v) > 1]

    st.retire("music_audit.md")
    L = [f"# Music audit  ({now()})", "",
         f"- Files scanned: **{len(inv):,}**  ({human(total)})",
         "- Formats: " + ", ".join(f"{k} {v:,}" for k, v in fmt.most_common()),
         f"- Albums (by tags): {len(albums):,}  |  compilations detected: {len(comps)}  |  incomplete: {len(incomplete)}",
         f"- Duplicate candidate groups: {len(dup_groups)}  |  artist spelling variants: {len(variants)}", "",
         "## Problems found", "", "| Issue | Files |", "|---|---|"]
    for k in sorted(flags, key=lambda k: -len(flags[k])):
        L.append(f"| {k} | {len(flags[k]):,} |")
    L += ["", "## Artist spelling variants", ""]
    for k, c in list(variants.items())[:200]:
        L.append("- " + " / ".join(f"{n} ({v})" for n, v in c.most_common()))
    L += ["", "## Compilations / multi-artist albums", ""]
    for alb, folder, n, na in comps[:300]:
        L.append(f"- {alb}  - {n} tracks, {na} artists  - `{folder}`")
    L += ["", "## Incomplete albums (from track numbers / totals in tags)", ""]
    for a, alb, have, tot in incomplete[:300]:
        L.append(f"- {a} - {alb}: {have} of {tot}")
    L += ["", "## Inconsistent album tags", ""]
    for alb, k, vals in inconsistent[:300]:
        L.append(f"- {alb}: {k} = {vals}")
    L += ["", "## Duplicate candidates (final duplicate handling is decided per folder in Phase 2)", ""]
    for g in dup_groups[:300]:
        L.append("- " + "  |  ".join(f"`{r['path']}` ({r['ext'][1:]}, {r.get('bitrate', 0)} kbps)" for r in g))
    L += ["", "Full per-file list: `audit_details.csv`."]
    with open(lp(st.p("music_audit.md")), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    st.retire("audit_details.csv")
    rows = [{"file_id": r["id"], "path": r["path"], "issue": k, "detail": d} for k, v in flags.items() for r, d in v]
    write_csv(st.p("audit_details.csv"), ["file_id", "path", "issue", "detail"], rows)
    hr("Audit summary")
    say(f" {len(inv):,} files, {human(total)}  |  " + ", ".join(f"{k} {v:,}" for k, v in fmt.most_common()))
    for k in sorted(flags, key=lambda k: -len(flags[k]))[:12]:
        say(f"   {len(flags[k]):>7,}  {k}")
    say(f"   {len(variants):>7,}  artist spelling variant groups\n   {len(dup_groups):>7,}  duplicate candidate groups"
        f"\n   {len(comps):>7,}  compilations / multi-artist albums\n   {len(incomplete):>7,}  incomplete albums")
    say(f"\n Report saved: {st.p('music_audit.md')}\n Next step: Phase 2 (propose changes).")

# ----------------------------------------------------------------------------- Phase 2: hints

SPOKEN_GENRE = re.compile(r"podcast|audio ?book|h[öo]rbuch|speech|spoken|comedy|stand.?up|lecture|talk|news|"
                          r"religious|sermon|books? & spoken|radio|interview|\u06a9\u062a\u0627\u0628 \u0635\u0648\u062a\u06cc", re.I)
SPOKEN_WORDS = re.compile(r"\b(podcast|episode|ep\.? ?\d+|chapter|chap\.? ?\d+|audio ?book|part \d+|kapitel|lecture|"
                          r"session \d+|lesson \d+)\b|\u0642\u0633\u0645\u062a|\u0641\u0635\u0644|\u067e\u0627\u062f\u06a9\u0633\u062a|"
                          r"\u06a9\u062a\u0627\u0628 \u0635\u0648\u062a\u06cc|\u0627\u067e\u06cc\u0632\u0648\u062f", re.I)
MUSIC_WORDS = re.compile(r"\b(symphon\w*|concerto|sonata|suite|quartet|quintet|trio|opus|op\.? ?\d+|bwv|k\. ?\d+|"
                         r"hob\.|movement|allegro|adagio|andante|largo|presto|mass|requiem|opera|act [ivx\d]+|overture|"
                         r"live at|concert|mix|dj set|megamix|medley|remix|classical|playlist|best of|greatest|"
                         r"collection|full album|compilation|anthology|essential|hits|nonstop|non-stop)\b|"
                         "موسیقی|آهنگ|میکس", re.I)


def looks_spoken(r, h):
    """_Long Files is for audiobooks, podcasts and other spoken audio that ended up among the music -
    never for long music (symphonies, live sets, mixes)."""
    t = r["tags"]
    text = " ".join([t.get("title", ""), t.get("album", ""), r["filename"], os.path.basename(r["folder"])])
    if MUSIC_WORDS.search(text) or t.get("composer") or "classic" in (t.get("genre") or "").lower():
        return False
    if r["ext"] == ".m4b" or SPOKEN_GENRE.search(t.get("genre") or "") or SPOKEN_WORDS.search(text):
        return True
    return not any(t.get(k) for k in ("artist", "albumartist", "title", "album"))   # nothing tagged at all


def split_track_tag(track, disc=""):
    """'2-01' / '2.01' (disc-track written in the track tag) -> ('2', '01'-> '1'); '3/12' -> ('', '3'). 1.1.5 (the 'Hung Up' 2-01 case)."""
    t = str(track or "").strip()
    m = re.match(r"^(\d{1,2})\s*[-.]\s*(\d{1,3})(?:\s*/\s*\d+)?$", t)
    if m:
        return (str(disc or "") or str(int(m.group(1)))), str(int(m.group(2)))
    m = re.match(r"^(\d{1,3})\s*/\s*\d+$", t)
    if m:
        return str(disc or ""), str(int(m.group(1)))
    return str(disc or ""), (str(int(t)) if t.isdigit() else t)


def parse_filename(stem):
    s = re.sub(r"\s+", " ", stem.replace("_", " ")).strip()
    disc = track = ""
    for r in LEAD_NUM:
        m = r.match(s)
        if m and m.group(3).strip():
            disc, track, s = (m.group(1) or ""), str(int(m.group(2))), m.group(3).strip()
            break
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+", s) if p.strip()]
    artist = album = ""
    if len(parts) == 2:
        artist, title = parts
    elif len(parts) >= 3:
        artist, album, title = parts[0], parts[1], " - ".join(parts[2:])
        for r in LEAD_NUM:
            m = r.match(title)
            if m and m.group(3).strip():
                track, title = str(int(m.group(2))), m.group(3).strip()
                break
    else:
        title = s
    return {"disc": disc, "track": track, "artist": artist, "album": album, "title": title}


def parse_folder(folder):
    m = re.match(r"^(1[89]\d\d|20\d\d)\s*[-–.]?\s+(.+)$", folder)
    if m:
        return m.group(1), m.group(2), ""
    m = re.match(r"^(.+?)\s*[\(\[](1[89]\d\d|20\d\d)[\)\]]$", folder)
    if m:
        return m.group(2), m.group(1), ""
    m = re.match(r"^(.+?)\s+-\s+(.+)$", folder)
    if m:
        return "", m.group(2), m.group(1)
    return "", "", ""


SINGLE_SUFFIX = re.compile(r"\s*(?:[\(\[]\s*(single|ep)\s*[\)\]]|[-\u2013]\s*(single|ep)|\b(single|ep))\s*$", re.I)


def strip_release_suffix(album):
    """'Del Yar Single' / 'Del Yar (Single)' / 'X - EP' -> ('Del Yar', 'Single')."""
    m = SINGLE_SUFFIX.search(album or "")
    if m and m.start() > 0 and album[:m.start()].strip(" -\u2013"):
        kind = (m.group(1) or m.group(2) or m.group(3)).lower()
        return album[:m.start()].strip(" -\u2013"), ("Single" if kind == "single" else "EP")
    return album or "", ""


def strip_artist_from_title(title, artist):
    """'Asylum For The Feeling - Silent Poets' -> 'Asylum For The Feeling' (artist = Silent Poets)."""
    if not artist or not title:
        return title
    for pat in (r"^\s*{}\s*[-\u2013]\s*", r"\s*[-\u2013]\s*{}\s*$"):
        new = re.sub(pat.format(re.escape(artist)), "", title, flags=re.I)
        if new != title and new.strip():
            return new.strip()
    return title


CREDIT_ROLES = re.compile(r"^(associated performer|main artist|featured artist|primary artist|composer|author|lyricist|writer|"
                          r"producer|co-producer|arranger|mixer|engineer|mastering engineer|performer|vocals?|piano|violin|"
                          r"viola|cello|guitar|bass|drums|keyboards?|studio personnel|music publisher|[a-z ]+ - .+)$", re.I)
ENSEMBLE_WORDS = re.compile(r"\b(orchestra|orchester|orchestre|orquesta|orchestr\w*|symphon\w*|philharmoni\w*|sinfoni\w*|"
                            r"choir|chor|chorus|ensemble|quartet|consort|academy|kammer\w*|chamber|singers|soloists)\b", re.I)


SITE_JUNK = re.compile(r"(?:[\(\[\{]\s*)?(?:https?://\S+|www\.\S+|\b[\w-]+\.(?:com|net|org|info|ir|ru|biz|mobi|pk)\b)(?:\s*[\)\]\}])?|"
                       r"[\(\[\{]\s*(?:mp3\s?juices?|mp3\s?skull|mp3\s?paw|songs?\s?pk|ytmp3|y2mate|zippyshare|beatport|free\s?download|official\s?(?:audio|video|lyrics?)|"
                       r"hd|hq|320\s?kbps|128\s?kbps|download(?:ed)?(?: from)?[^)\]}]*)\s*[\)\]\}]|"
                       r"\b(?:downloaded from|download from|free download|mp3juices?|mp3skull|mp3paw|ytmp3|y2mate|zippyshare)\b", re.I)


def strip_site_words(text):
    """v1.1.5: site names / URLs / 'downloaded from' words are left out of the deep search words."""
    t = SITE_JUNK.sub(" ", text or "")
    t = re.sub(r"\s*[-_|~\u2022:]+\s*$", "", re.sub(r"\s+", " ", t).strip())     # a separator left at the end: 'Madonna _'
    t = re.sub(r"^\s*[-_|~\u2022:]+\s*", "", t)
    return re.sub(r"\s+", " ", t).strip(" -_.")


def clean_credit(name):
    """Credits written as long lists by shops and rippers -> the main name to SEARCH with (your tags stay as they are):
    'Max Richter, Associated Performer, Author, Composer, Main Artist, Piano - ...' -> 'Max Richter';
    'Herbert Blomstedt, San Francisco Symphony' -> 'Herbert Blomstedt'; 'Original Dixieland Jazz Band 1919-1920' ->
    'Original Dixieland Jazz Band'; 'Joe Venuti`s Blue Four' -> "Joe Venuti's Blue Four"."""
    s = strip_site_words((name or "").replace("`", "'").replace("´", "'").replace("’", "'").strip())   # v1.1.5: 'Madonna _ Navasong.com' -> 'Madonna'
    s = re.sub(r"\s+\(?(1[89]\d\d|20\d\d)\s*[-–]\s*(1[89]\d\d|20\d\d)\)?$", "", s)
    parts = [p_.strip() for p_ in re.split(r"\s*[,;]\s*", s) if p_.strip()]
    if len(parts) > 1 and (any(CREDIT_ROLES.match(p_) for p_ in parts[1:]) or any(ENSEMBLE_WORDS.search(p_) for p_ in parts[1:])
                           or len(parts) >= 4):
        return parts[0]
    return s


def hints(r):
    t = r["tags"]
    fn = parse_filename(os.path.splitext(r["filename"])[0])
    fy, falb, fart = parse_folder(os.path.basename(r["folder"]))
    raw_artist = t.get("artist") or t.get("albumartist") or smart_title(fn["artist"] or fart)
    primary, feats = split_feat(clean_credit(raw_artist))
    title_src = strip_artist_from_title(strip_site_words(t.get("title") or fn["title"]), primary)
    album_raw = strip_disc(strip_site_words(t.get("album") or fn["album"]))      # 1.1.5: "(Disc 1)" is not part of the album name
    album, release_type = strip_release_suffix(album_raw)
    title, tfeat = normalize_title_feat(clean_title(title_src))
    feats = feats or ""
    return {
        "artist": primary, "artist_full": raw_artist, "feats": feats or tfeat,
        "artist_from": "tags" if t.get("artist") or t.get("albumartist") else ("filename" if raw_artist else ""),
        "title": add_feat(title, feats) if feats else title, "title_plain": clean_title(title_src),
        "title_raw": (t.get("title") or os.path.splitext(r["filename"])[0]).strip(),
        "album_raw": (t.get("album") or "").strip(), "artist_raw": (t.get("artist") or "").strip(),
        "album": album, "release_type": release_type, "album_from": "tags" if t.get("album") else ("filename" if fn["album"] else ""),
        "folder_album": falb, "folder_year": fy,
        "albumartist": "" if is_placeholder(t.get("albumartist")) else split_feat(clean_credit(t.get("albumartist")))[0],
        "track": split_track_tag(t.get("track"), t.get("disc"))[1] or fn["track"], "disc": split_track_tag(t.get("track"), t.get("disc"))[0] or fn["disc"],
        "year": t.get("year") or "", "genre": t.get("genre") or "",
        "compilation": t.get("compilation") in ("1", "true", "True", "yes"),
        "composer": t.get("composer", ""), "conductor": t.get("conductor", ""),
    }

# ----------------------------------------------------------------------------- Phase 2: identify


SKIP_IDS = set()          # V2.0.6: ids a re-scan must not search again


class Resolver:
    """Finds, for every file, the real release it belongs to (or decides it cannot be confirmed)."""

    def __init__(self, inv, cfg, mb, cp, alt=None):
        self.inv, self.cfg, self.mb, self.cp, self.alt = inv, cfg, mb, cp, alt
        self.results = {}   # file_id -> (match | {"artist_only":...} | None, confidence)
        self.h = {}

    # -- MusicBrainz helpers
    def match_tracks(self, rel, recs):
        out = {}
        rel_names = [x.get("name") or (x.get("artist") or {}).get("name") for x in rel.get("artist-credit") or []]
        rg = rel.get("release-group") or {}
        live_rel = "Live" in (rg.get("secondary-types") or []) or bool(re.search(r"\blive\b", rel.get("title") or "", re.I))
        album_words = strip_edition(rel.get("title") or "")

        def clean(t):
            """On a live album '(Live in Vienna, 1993)' is the album, not a different version of the song."""
            if live_rel:
                t = re.sub(r"\s*[\(\[]\s*live\b[^\)\]]*[\)\]]|\s+-\s+live\b.*$", "", t or "", flags=re.I)
            if album_words:
                t = re.sub(r"\s*[\(\[]" + re.escape(album_words) + r"[\)\]]", "", t or "", flags=re.I)
            return (t or "").strip()
        for r in recs:
            h = self.h[r["id"]]
            tag_artists = [a_ for a_ in (h.get("artist_full") or h.get("artist"), r["tags"].get("albumartist"),
                                         r["tags"].get("composer")) if a_ and not is_placeholder(a_)]
            best = None
            for medium in rel.get("media") or []:
                for tr in medium.get("tracks") or []:
                    recid = (tr.get("recording") or {}).get("id")
                    if r["tags"].get("mb_trackid") and r["tags"]["mb_trackid"] == recid:
                        best = (2.0, medium, tr)
                        break
                    if tag_artists:      # same title on a compilation can be a cover/karaoke version: performer must agree
                        names = rel_names + [x.get("name") or (x.get("artist") or {}).get("name")
                                             for x in (tr.get("artist-credit") or (tr.get("recording") or {}).get("artist-credit") or [])]
                        if not any(artist_agrees(names, a_) for a_ in tag_artists):
                            ids = {(x.get("artist") or {}).get("id") for x in (rel.get("artist-credit") or []) +
                                   (tr.get("artist-credit") or (tr.get("recording") or {}).get("artist-credit") or [])}
                            if not any(ids & set(self.mb.artist_ids(a_)) for a_ in tag_artists):
                                continue
                    if different_version(clean(h["title_plain"]), clean(tr.get("title")),
                                         (tr.get("recording") or {}).get("disambiguation"), f"{h['album_raw']} {r['filename']}"):
                        continue          # mono / other mix / take of the same song: not your file
                    sim = max(same_song_title(h["title_plain"], tr.get("title")),
                              same_song_title(clean(h["title_plain"]), clean(tr.get("title"))))
                    ln = (tr.get("length") or (tr.get("recording") or {}).get("length") or 0) / 1000
                    if ln and r.get("duration") and abs(ln - r["duration"]) > 7:
                        continue
                    same_pos = h["track"] and str(tr.get("position")) == h["track"] and \
                        (not h["disc"] or str(medium.get("position")) == h["disc"])
                    if same_pos:
                        sim += 0.05
                        # same album, same track number, same length (within 3 s): differently spelled titles
                        # (transliterated Persian: 'Khab Dar Bidari' / 'Khaab Dar Bidaree') still count
                        close = ratio(title_key(clean(h["title_plain"])), title_key(clean(tr.get("title"))))
                        if ln and r.get("duration") and abs(ln - r["duration"]) <= 3 and close >= 0.6 and \
                                version_words(clean(h["title_plain"])) == version_words(clean(tr.get("title"))):
                            sim = max(sim, 0.9)
                    if sim >= 0.88 and (best is None or sim > best[0]):
                        best = (sim, medium, tr)
                if best and best[0] == 2.0:
                    break
            if best:
                out[r["id"]] = best
        return out

    def find_release(self, recs, artist, album):
        mbids = {r["tags"].get("mb_albumid") for r in recs} - {""}
        cands = []
        if len(mbids) == 1:
            rel = self.mb.release(mbids.pop())
            if rel:
                cands.append(rel)
        if not cands:
            tries = [(artist, album)]
            if strip_edition(album) != album:
                tries.append((artist, strip_edition(album)))
            if artist:
                tries.append(("", strip_edition(album)))
            seen = set()
            for qa, qal in tries:
                for c in self.mb.search_release(qa, qal)[:10]:
                    if c["id"] in seen or int(c.get("score", 0)) < 80:
                        continue
                    if max(ratio(c.get("title"), album), ratio(strip_edition(c.get("title")), strip_edition(album))) < 0.85:
                        continue
                    seen.add(c["id"])
                    rel = self.mb.release(c["id"])
                    if rel:
                        cands.append(rel)
                    if len(cands) >= 6:
                        break
                if cands:
                    break
        want = max([int(r["tags"]["tracktotal"]) for r in recs if str(r["tags"].get("tracktotal", "")).isdigit()] + [0])
        best = None
        for rel in cands:
            m = self.match_tracks(rel, recs)
            official = (rel.get("status") or "Official") == "Official"
            ntr = sum(md.get("track-count", 0) for md in rel.get("media") or [])
            key = (len(m), official, -abs(ntr - (want or len(recs))))
            if m and (best is None or key > best[0]):
                best = (key, rel, m)
        if best and best[0][0] >= max(1, len(recs) // 2):
            return best[1], best[2]
        return None, {}

    def choose_release(self, recs, album_hint):
        """Album hint first; then the artist's own official releases; bootlegs only if nothing else.
        Compilations only when your tags name them."""
        order = {"Album": 6, "EP": 5, "Single": 4, "Live": 3, "OST": 3, "Remix": 2, "Mix": 1}
        best = None
        for rec in recs:
            rp = credit_info(rec.get("artist-credit"))
            for rel in rec.get("releases") or []:
                status = rel.get("status") or "Official"
                if status == "Pseudo-Release":
                    continue
                rg = rel.get("release-group") or {}
                rtype = classify_mb(rg.get("primary-type") or "", set(rg.get("secondary-types") or []), status, 1)
                rc = credit_info(rel.get("artist-credit") or rec.get("artist-credit"))
                year = (rg.get("first-release-date") or rel.get("date") or "")[:4]
                hint = 1 if album_hint and (ratio(rel.get("title"), album_hint) >= 0.85 or
                                            ratio(strip_edition(rel.get("title")), strip_edition(album_hint)) >= 0.85) else 0
                comp = rtype in ("Comp", "Box") or rc["primary_id"] == VA_MBID or norm_key(rc["entity"]) in VA_NAMES
                if comp and not hint:
                    continue
                if not hint and rc["primary_id"] and rp["primary_id"] and rc["primary_id"] != rp["primary_id"]:
                    continue
                exact = ratio(rel.get("title"), album_hint) if album_hint else 0
                # 1.1.5: a remaster in your tags goes to the remaster release, a plain album to the plain one (not the other way round)
                remk = 1 if bool(REMASTER_FILE.search(album_hint or "")) == bool(REMASTER_FILE.search(f"{rel.get('title') or ''} {rel.get('disambiguation') or ''}")) else 0
                key = (hint, remk, status == "Official", order.get(rtype, 0), round(exact, 3), -(int(year) if year.isdigit() else 9999))
                if best is None or key > best[0]:
                    best = (key, rel, rec)
        return best

    # -- per file
    def resolve_loose(self, r, album_hint=""):
        h = self.h[r["id"]]
        if self.mb:
            recs, source = [], "MusicBrainz"
            if r["tags"].get("mb_trackid"):
                d = self.mb.recording(r["tags"]["mb_trackid"])
                if d:
                    recs.append(d)
            searches = []
            if not recs and h["artist"] and h["title_plain"]:
                for q_ in (neutral(h["title_plain"]), h["title_plain"], base_title(neutral(h["title_plain"]))):
                    if q_ and q_ not in searches:
                        searches.append(q_)
            is_live = bool(re.search(r"\blive\b", f"{h['title_plain']} {h['album']} {r['filename']}", re.I))

            def only_live_or_bootleg(c):
                rels = c.get("releases") or []
                return bool(rels) and all((x.get("status") or "Official") == "Bootleg" or
                                          "Live" in ((x.get("release-group") or {}).get("secondary-types") or []) for x in rels)
            tries = [(a_, t, True) for a_ in artist_parts(h["artist"])[:3] for t in searches] + \
                [(h["artist"], t, False) for t in searches]
            for q_artist, qtitle, precise in tries:
                if recs:
                    break                     # an earlier search already found it: skip the rest
                for c in self.mb.search_recording(q_artist, qtitle, r.get("duration") or 0, precise, is_live):
                    if not is_live and only_live_or_bootleg(c):
                        continue              # a live/bootleg performance is not your studio file
                    if int(c.get("score", 0)) < 75:
                        continue
                    ci = credit_info(c.get("artist-credit"))
                    ln = (c.get("length") or 0) / 1000
                    if not artist_agrees([ci["primary"], ci["entity"], ci["full"]] + list(ci.get("names") or []),
                                         h["artist_full"] or h["artist"]) and \
                            ci.get("primary_id") not in self.mb.artist_ids(h["artist"]):
                        continue
                    if same_song_title(c.get("title"), h["title_plain"]) < 0.88:
                        continue
                    if different_version(h["title_plain"], c.get("title"), c.get("disambiguation"),
                                         f"{h['album_raw']} {r['filename']}"):
                        continue              # e.g. a mono / 2019 mix / live recording of the same song
                    if ln and r.get("duration") and abs(ln - r["duration"]) > 10:
                        continue
                    recs.append(c)
            if not recs and self.cp and self.cp.key:
                for score, rid in self.cp.lookup(r["path"])[:3]:
                    if score >= 0.85:
                        d = self.mb.recording(rid)
                        if d:
                            recs.append(d)
                            source = "AcoustID + MusicBrainz"
            if recs:
                left = list(recs)
                while left:
                    best = self.choose_release(left, album_hint)
                    if not best:
                        break
                    rel = self.mb.release(best[1]["id"])
                    recid = best[2]["id"]
                    found = None
                    for medium in (rel or {}).get("media") or []:
                        for tr in medium.get("tracks") or []:
                            if (tr.get("recording") or {}).get("id") == recid:
                                found = (medium, tr)
                                break
                        if found:
                            break
                    if found and not different_version(h["title_plain"], found[1].get("title"), "",
                                                       f"{h['album_raw']} {r['filename']}"):
                        m = mb_match(rel, found[0], found[1], source)
                        m["hint"] = best[0][0]
                        return m, ("high" if best[0][0] else "medium")
                    left = [x for x in left if x["id"] != recid]       # that track is another version: next one
                rec = recs[0]
                return {"artist_only": True, "credit": credit_info(rec.get("artist-credit")),
                        "source": source}, "medium"
        if self.alt:
            return {"alt_pending": True, "hint": album_hint}, "low"   # asked in the parallel second pass
        return None, "low"

    @staticmethod
    def _is_comp(m):
        """A compilation - or a later collection / anniversary / expanded edition of an older album
        (e.g. 'The Blue Notebooks (15 Years)', 'Best of', 'Deluxe Edition'): songs from it go to the artist's
        original studio album when the same recording is there (remasters and new mixes are other recordings
        or keep their own '(Remastered)' folder, so they are not affected)."""
        if not (isinstance(m, dict) and m.get("verified")):
            return False
        if m.get("rtype") in ("Comp", "Box") or m.get("is_va"):
            return True
        return m.get("rtype") == "Album" and bool(REISSUE_RE.search(m.get("group_title") or m.get("album") or ""))

    def choose_original(self, rec):
        """The artist's ORIGINAL release of this recording: earliest official studio album, else EP, else single."""
        order = {"Album": 3, "EP": 2, "Single": 1}
        best = None
        for rel in rec.get("releases") or []:
            rg = rel.get("release-group") or {}
            if (rel.get("status") or "Official") != "Official" or (rg.get("secondary-types") or []):
                continue
            rc = credit_info(rel.get("artist-credit") or rec.get("artist-credit"))
            if rc["primary_id"] == VA_MBID or norm_key(rc["entity"]) in VA_NAMES:
                continue
            kind = order.get(rg.get("primary-type") or "")
            if not kind:
                continue
            year = (rg.get("first-release-date") or rel.get("date") or "")[:4]
            key = (kind, -(int(year) if year.isdigit() else 9999))
            if best is None or key > best[0]:
                best = (key, rel)
        return best[1] if best else None

    def prefer_originals(self):
        """A song found on a compilation goes to the artist's ORIGINAL album instead - unless you already have the
        song on that original release (then the compilation copy follows its tags)."""
        if not self.mb:
            return
        owned_rec, owned_title = set(), set()
        for m, _ in self.results.values():
            if isinstance(m, dict) and m.get("verified") and not self._is_comp(m):
                owned_rec.add(m.get("recording_id"))
                owned_title.add((norm_key(m["trk_credit"]["entity"]), title_key(neutral(m["title"]))))
        # 1.1.5: compilations you own at least 90% of stay together (one Compilation folder); if more than 10% of the tracks
        # are missing, the songs go to their original albums instead
        have = defaultdict(set)
        for m, _ in self.results.values():
            if self._is_comp(m) and m.get("release_id"):
                have[m["release_id"]].add((m.get("disc") or "1", m.get("track")))
        complete = {rid for rid, got in have.items()
                    if any(m.get("release_id") == rid and m.get("ntracks") and len(got) >= 0.9 * m["ntracks"]
                           for m, _ in self.results.values() if isinstance(m, dict))}
        comps = [(fid, m, conf) for fid, (m, conf) in self.results.items() if self._is_comp(m) and m.get("recording_id")
                 and m.get("release_id") not in complete]
        if not comps:
            return
        self.dur_of = {r_["id"]: r_.get("duration") or 0 for r_ in self.inv}
        prog = Progress("Looking for original albums", len(comps))
        for fid, m, conf in comps:
            prog.step(f"{m['trk_credit']['entity']} - {m['title']}"[:70])
            tkey = (norm_key(m["trk_credit"]["entity"]), title_key(neutral(m["title"])))
            if m["recording_id"] in owned_rec or tkey in owned_title:
                continue                      # you already have it on the original: keep the compilation copy
            if conf != "high":
                continue                      # V2.0.3 decision 6: a compilation is split only when the match is sure
            dur_ = self.dur_of.get(fid, 0)
            try:
                rec = self.mb.recording(m["recording_id"])
                orig = self.choose_original(rec) if rec else None
                rel = self.mb.release(orig["id"]) if orig else None
            except RuntimeError:
                rel = None
            for medium in (rel or {}).get("media") or []:
                tr = next((t for t in medium.get("tracks") or [] if (t.get("recording") or {}).get("id") == m["recording_id"]), None)
                if tr and different_version(m["title"], tr.get("title")):
                    tr = None
                if tr and same_song_title(m["title"], tr.get("title") or "") < 0.95:
                    tr = None                  # V2.0.3: same title only
                if tr and dur_ and mb_track_len(tr) and abs(mb_track_len(tr) - dur_) > 3:
                    tr = None                  # V2.0.3: same length only (a different mix / edit is another recording)
                if tr:
                    new = mb_match(rel, medium, tr, m.get("source", "MusicBrainz"))
                    new["hint"] = 1
                    new["from_comp"] = m.get("group_title", "")
                    num = f"{m.get('disc')}-{int(m['track']):02d}" if str(m.get("disctotal") or "1") not in ("", "1") and \
                        str(m.get("track", "")).isdigit() else (f"{int(m['track']):02d}" if str(m.get("track", "")).isdigit() else "")
                    new["from_comp_info"] = f"{m.get('group_title', '')}" + (f" ({m.get('release_year') or m.get('year')})" if (m.get('release_year') or m.get('year')) else "") + (f", track {num}" if num else "")
                    self.results[fid] = (new, conf)
                    owned_rec.add(m["recording_id"])
                    owned_title.add(tkey)
                    break
        prog.done()

    def run(self):
        good = []
        for r in self.inv:
            if r.get("error"):
                self.results[r["id"]] = ("skip", "low")
                continue
            self.h[r["id"]] = hints(r)
            if r["id"] in SKIP_IDS:                  # V2.0.6: decided / approved songs are not searched again (their old plan entry is put back afterwards)
                self.results[r["id"]] = ("skip", "low")
                continue
            t = r["tags"]
            if r.get("duration", 0) < 60 and not (t.get("title") or t.get("artist")):
                self.results[r["id"]] = ("short", "high")
                continue
            good.append(r)
        groups, loose = defaultdict(list), []
        mixed = UI.mixed_ids() if UI is not None and hasattr(UI, "mixed_ids") else set()   # 'Not one album' (app)
        for r in good:
            h = self.h[r["id"]]
            if h["album"] and r["id"] not in mixed:
                key = (norm_key(h["album"]), norm_key(h["albumartist"]) or "dir:" + os.path.normcase(r["folder"]))
                groups[key].append(r)
            else:
                loose.append(r)
        total = len(groups) + len(loose)
        names = ["MusicBrainz"] if self.mb else []
        names += [ALT_NAMES[x] for x in (self.alt.order if self.alt else []) if x in self.alt.use]
        say(f"Identifying {len(groups):,} album groups and {len(loose):,} loose files"
            + (f" using {', '.join(names)} (answers are cached)..." if names else " (offline: nothing can be confirmed)..."))
        prog = Progress("Identifying", len(good))
        # several songs/albums are worked on at once; MusicBrainz still gets at most one NEW question per second,
        # but waiting for slow answers no longer blocks everything else
        def do_group(recs):
            h0 = self.h[recs[0]["id"]]
            prog.note(f"{h0['albumartist'] or h0['artist']} - {h0['album']}"[:70])
            self.resolve_group(recs)
            for _ in recs:
                prog.step()

        def do_loose(r):
            h0 = self.h[r["id"]]
            prog.note(f"{h0['artist']} - {h0['title_plain']}"[:70])
            self.results[r["id"]] = self.resolve_loose(r, h0["folder_album"])
            prog.step()
        with cf.ThreadPoolExecutor(max_workers=4 if self.mb else 1) as ex:
            futs = [ex.submit(do_group, g) for g in groups.values()] + [ex.submit(do_loose, r) for r in loose]
            for fu in cf.as_completed(futs):
                fu.result()          # re-raises "MusicBrainz is not reachable" so Phase 2 can stop cleanly
        prog.done()
        self.prefer_originals()
        pending = [(fid, res[0]["hint"]) for fid, res in self.results.items()
                   if isinstance(res[0], dict) and res[0].get("alt_pending")]
        if pending:
            by_id = {r["id"]: r for r in good}
            prog = Progress("Checking other sites", len(pending))

            def ask_sites(job):
                fid, hint = job
                h = self.h[fid]
                try:
                    m = self.alt.identify(h["artist"], h["title_plain"], hint, by_id[fid].get("duration"))
                except Exception:
                    return fid, None
                if m and m.get("lfm_mbid") and self.mb:
                    try:
                        rel = self.mb.release(m["lfm_mbid"])
                        hit = self.match_tracks(rel, [by_id[fid]]) if rel else {}
                    except Exception:
                        hit = {}
                    if fid in hit:
                        _, medium, tr = hit[fid]
                        m = mb_match(rel, medium, tr, "Last.fm > MusicBrainz")
                        m["hint"] = 1
                return fid, m
            with cf.ThreadPoolExecutor(max_workers=6) as ex:
                for fu in cf.as_completed([ex.submit(ask_sites, j) for j in pending]):
                    fid, m = fu.result()
                    self.results[fid] = (m, "medium") if m else (None, "low")
                    h = self.h[fid]
                    prog.step(f"{h['artist']} - {h['title_plain']}"[:70])
            prog.done()
        if self.mb:
            self.mb.save()
        if self.alt:
            self.alt.save()
        return self.results

    def resolve_group(self, recs):
        hs = [self.h[r["id"]] for r in recs]
        album = Counter(h["album"] for h in hs).most_common(1)[0][0]
        aa = Counter(h["albumartist"] for h in hs if h["albumartist"]).most_common(1)
        aa = aa[0][0] if aa else ""
        if self.mb:
            q_artist = aa if aa and norm_key(aa) not in VA_NAMES else \
                (Counter(h["artist"] for h in hs if h["artist"]).most_common(1) or [("", 0)])[0][0]
            if len({norm_key(h["artist"]) for h in hs}) >= 3 and not aa:
                q_artist = ""
            if is_placeholder(q_artist):
                q_artist = (Counter(h["artist"] for h in hs if h["artist"] and not is_placeholder(h["artist"]))
                            .most_common(1) or [("", 0)])[0][0]
            rel, matched = self.find_release(recs, q_artist, album)
            if not rel:                    # classical / messy credits: the first performer, then the composer
                for alt_a in self.group_artists(recs, q_artist):
                    rel, matched = self.find_release(recs, alt_a, album)
                    if rel:
                        break
            if rel:
                conf = "high" if all(h["album_from"] == "tags" for h in hs) else "medium"
                for r in recs:
                    if r["id"] in matched:
                        _, medium, tr = matched[r["id"]]
                        m = mb_match(rel, medium, tr)
                        m["hint"] = 1
                        self.results[r["id"]] = (m, conf)
                    else:
                        self.results[r["id"]] = self.resolve_loose(r, album)
                self.unify_group(recs)
                return
        if self.alt_album_group(recs, album, aa):
            return
        for r in recs:
            self.results[r["id"]] = self.resolve_loose(r, album)
        self.unify_group(recs)

    def group_artists(self, recs, tried):
        out = []
        for r in recs[:6]:
            h = self.h[r["id"]]
            for a_ in (clean_credit(r["tags"].get("artist") or ""), h.get("composer") or "", clean_credit(h.get("composer") or "")):
                a_ = (a_ or "").strip()
                if a_ and norm_key(a_) != norm_key(tried or "") and a_ not in out and not is_placeholder(a_):
                    out.append(a_)
        return out[:3]

    def alt_album_group(self, recs, album, albumartist):
        """An album MusicBrainz does not know: look it up as a whole on the other sites you allowed (Deezer, Discogs,
        Tidal, Apple Music) and match every song to its track. Results are 'medium': they wait for your check."""
        if not self.alt or not album or FAST_SCAN or len(recs) < 2:
            return False
        sites = [x for x in ("deezer", "discogs", "tidal", "spotify", "itunes") if x in (self.alt.use or [])]
        if not sites:
            return False
        h0 = self.h[recs[0]["id"]]
        artist = albumartist if albumartist and norm_key(albumartist) not in VA_NAMES else h0.get("artist") or ""
        best = None
        for site in sites:
            try:
                views = alt_album_views(self.alt, artist, album, self.alt.use, (site,), per_site=2)
            except Exception:
                views = []
            for v in views:
                mp = match_group_to_release(v, recs)
                if mp and (best is None or len(mp) > len(best[1])):
                    best = (v, mp)
            if best and len(best[1]) == len(recs):
                break
        if not best or len(best[1]) < max(2, (len(recs) + 1) // 2):
            return False
        v, mp = best
        for r in recs:
            hit = mp.get(r["id"])
            t = hit and (v.get("tracks") or [])[hit["i"]]
            if t and t.get("match"):
                m = dict(t["match"])
                m["hint"] = 1
                self.results[r["id"]] = (m, "medium")
            else:
                self.results[r["id"]] = self.resolve_loose(r, album)
        return True

    def unify_group(self, recs):
        """Files of one album must come from ONE edition: re-match the whole group against every release the
        songs were found on and keep the one that fits most of them (ties: closest to your track total)."""
        if not self.mb or len(recs) < 2:
            return
        rids = {res[0]["mbid"] for res in (self.results.get(r["id"]) for r in recs)
                if res and isinstance(res[0], dict) and res[0].get("mbid")}
        if len(rids) < 2:
            return
        want = max([int(r["tags"]["tracktotal"]) for r in recs if str(r["tags"].get("tracktotal", "")).isdigit()] + [0])
        best = None
        for rid in rids:
            rel = self.mb.release(rid)
            if not rel:
                continue
            m = self.match_tracks(rel, recs)
            ntr = sum(md.get("track-count", 0) for md in rel.get("media") or [])
            # same recordings appear on translated editions (e.g. a German soundtrack): prefer YOUR titles
            tsim = round(sum(same_song_title(tr.get("title"), self.h[fid]["title_plain"]) for fid, (_, _, tr) in m.items()), 1)
            key = (len(m), tsim, -abs(ntr - (want or len(recs))))
            if best is None or key > best[0]:
                best = (key, rel, m)
        if not best:
            return
        _, rel, m = best
        for r in recs:
            if r["id"] in m:
                _, medium, tr = m[r["id"]]
                old = self.results.get(r["id"], (None, "low"))
                mm = mb_match(rel, medium, tr, old[0].get("source", "MusicBrainz") if isinstance(old[0], dict) else "MusicBrainz")
                mm["hint"] = 1
                self.results[r["id"]] = (mm, old[1] if old[1] in ("high", "medium") else "medium")

# ----------------------------------------------------------------------------- Phase 2: placement


def make_item(r, h, res, conf):
    """Turn an identification result into a planned item (kind, folder parts, tags)."""
    it = {"file_id": r["id"], "src": r["path"], "ext": r["ext"], "duration": r.get("duration", 0),
          "confidence": conf, "data_source": "", "verified": False, "review": None, "reason": "",
          "approved": False, "notes": [], "new_tags": {}, "action": "copy"}
    if res == "skip":
        it.update(kind="skip", reason=r.get("error", ""))
        return it
    if res == "short":
        it.update(kind="short", approved=True, data_source="length < 1 min, no tags", reason="short untagged file")
        return it
    if res is None:
        if r.get("duration", 0) > 1200 and looks_spoken(r, h):
            it.update(kind="long", approved=True, data_source="not confirmed",
                      reason="longer than 20 minutes and looks like an audiobook / podcast / spoken audio")
            return it
        a = h["artist_raw"] or h["artist"]
        it.update(kind="unverified", artist=a, title=h["title_raw"], data_source="existing tags",
                  reason="not confirmed by any site", review=("unverified", norm_key(a) or "_noartist", a or "(no artist)"))
        return it
    if res.get("artist_only"):
        c = res["credit"]
        it.update(kind="artist_unverified", artist_id=c["primary_id"], entity=c["entity"], credited=c["primary"],
                  credit_text=prefer_latin(c["main"], h["artist_raw"]), title=h["title_raw"], year="",
                  data_source=res["source"], reason="artist confirmed, release unclear",
                  review=("unverified", norm_key(c["entity"] or c["primary"]), c["entity"] or c["primary"]))
        it["tag_latin"] = h["artist_raw"]
        return it
    m = res
    rc, tc = m["rel_credit"], m["trk_credit"]
    own_comp = m["rtype"] in ("Comp", "Box") and not m["is_va"] and norm_key(rc["entity"]) == norm_key(tc["entity"])
    by_track = m["is_va"] or (m["rtype"] in ("Comp", "Box") and not own_comp)
    fc = tc if by_track else rc                       # whose folder
    credit_text = tc["main"] if by_track else rc["full"]
    rel_names = {norm_key(x) for x in (tc["names"] if by_track else rc["names"])}
    song_guests = [f for f in tc["feats"] if norm_key(f) not in rel_names] if not by_track else tc["feats"]
    title = prefer_latin(keep_version_title(bracket_versions(m["title"]), h["title_raw"]), h["title_raw"])
    if song_guests and "feat" not in title.lower():
        title = f"{title} (feat. {' & '.join(song_guests)})"
    album = prefer_latin(keep_edition_album(m["group_title"], h["album_raw"]), strip_edition(h["album_raw"]))
    if m["rtype"] == "EP":
        album = re.sub(r"\s*[\(\[]?\bEP\b[\)\]]?\s*$", "", album).strip() or album
    year = m["year"] or h["year"]
    genre_db = m.get("genre") or ""
    classical = bool(h.get("composer")) and ("classical" in f"{genre_db} {h['genre']}".lower() or classical_by_words(h, genre_db, album))
    it.update(release_id=m.get("release_id", ""), ntracks=m.get("ntracks") or 0,
              mb_artist=fc["primary_id"] if m["source"].endswith("MusicBrainz") else "")
    it.update(kind="singles" if m["rtype"] == "Single" and (m.get("ntracks") or 0) <= 1 else "release",
              verified=True, data_source=m["source"], rtype=m["rtype"], group_id=m["group_id"], album=album,
              year=year, release_year=m.get("release_year") or "", remaster=m.get("remaster", False),
              title=title, track=m["track"], disc=m["disc"] or "1", disctotal=m.get("disctotal") or "",
              tracktotal=m.get("tracktotal") or "", maxtrack=m.get("maxtrack") or 0,
              artist_id=fc["primary_id"], entity=fc["entity"], credited=fc["primary"],
              credit_text=prefer_latin(credit_text, h["artist_raw"]), tag_latin=h["artist_raw"],
              artists=[x for x in tc["names"] if x], display_artist=prefer_latin(tc["full"], h["artist_full"]),
              compilation=m["rtype"] in ("Comp", "Box") or m["is_va"], mbid=m.get("mbid", ""),
              cover_url=m.get("cover_url", ""), recording_id=m.get("recording_id", ""),
              genre=keep_file_genre(h["genre"], genre_db))
    rm, rm_year = file_remaster(r, h)
    if rm and not it.get("remaster"):         # your file is a remaster: its own '(Remastered)' album folder
        it["remaster"] = True
        if rm_year:
            it["release_year"] = rm_year
        it["notes"].append("remastered edition (from your tags)")
    if rm:                                    # 1.1.7: the version stays visible - it goes into the file name: 'Hey Jude (2009 Remaster).mp3'
        it["version"] = f"{rm_year} Remaster" if rm_year else "Remaster"
    if not it.get("version"):                 # V2.0.6: '(Rescored Alt)', '[Live 1979]' ... of YOUR title stays in the new title and the file name
        vl = version_label_of(h.get("title_raw") or (r.get("tags") or {}).get("title") or "", it.get("title") or "")
        if vl:
            it["version"] = vl
            it["notes"].append("version label of your title kept: " + vl)
    if m.get("trusted"):
        it["trusted"] = True
        it["notes"].append("placed with your own tags (Trust my tags)")
    if m.get("from_comp"):
        it["notes"].append(f"also on the compilation '{m['from_comp']}' - placed on the original release")
        it["compilation_name"] = m["from_comp"]
        it["original_release"] = m.get("from_comp_info") or m["from_comp"]
    if classical:
        # V2.0.3 decision 4: the PERFORMER (orchestra / soloist) stays the artist in the tags; the composer goes in the composer tag.
        # Never replace the performer with the composer.
        perf = clean_credit(h.get("artist_full") or h.get("artist_raw") or "") or h.get("artist") or ""
        albart = clean_credit(r["tags"].get("albumartist") or "") or perf
        it["composer"] = latinize(h["composer"])
        it["classical"] = True
        it.update(display_artist=latinize(perf), credited=latinize(albart), credit_text=latinize(albart), entity=latinize(albart), artist_id="")
        it["artists"] = [latinize(x) for x in re.split(r"\s*[;/]\s*", perf) if x.strip()] or [latinize(perf)]
        it["notes"].append("classical: performer stays the artist, composer in the composer tag")
        if CLASSICAL_MODE == "composer":
            comp = latinize(h["composer"])
            it.update(entity=comp, credit_text=comp)       # folder only; tags unchanged
            who = classical_performer(h)
            if who:
                it["album_suffix"] = f" ({who.split()[-1]})"
    # V2.0.3 decision 20: the album artist of a compilation is the main (first) artist, never "Various Artists"
    if is_placeholder(it.get("credited")) or is_placeholder(it.get("credit_text")):
        first = (it.get("artists") or [""])[0] or re.split(r"\s*(?:&|;|/| feat\.? | and )\s*", it.get("display_artist") or "")[0]
        if first:
            it["credited"], it["credit_text"] = first, first
            it["entity"] = it.get("entity") if not is_placeholder(it.get("entity")) else first
    for k_ in ("display_artist", "credited", "credit_text", "entity", "album", "title", "tag_latin"):
        if it.get(k_):
            it[k_] = latinize(it[k_])
    it["artists"] = [latinize(x) for x in it.get("artists") or []]
    # a version / edition word that the file has and the match lost is a mismatch -> never silently accepted
    if edition_words_of(f"{h['album_raw']} {h['title_raw']}") - edition_words_of(f"{it.get('album')} {it.get('title')}") - {"stereo"} and conf == "high":
        conf = "medium"
        it["notes"].append("edition / version word of your file is missing in the match")
    it["file_artist"] = h["artist_raw"]
    if conf != "high":
        it["review"] = ("medium", norm_key(it["entity"] or it["credited"]), it["entity"] or it["credited"])
        it["reason"] = f"matched by song search on {m['source']}"
    it["confidence"] = conf
    it["approved"] = conf == "high"
    return it


CLASSICAL_GROUP_WORDS = re.compile(r"orchestra|orchestre|philharmoni|symphon|choir|chor\b|chorus|ensemble|consort|quartet|quintet|trio|academy|"
                                   r"chamber|camerata|players|singers|sinfonietta|kammer|capella|cappella|opera|radio|\bband\b", re.I)
OPERA_GENRES = re.compile(r"opera|baroque|chamber music|renaissance|choral|orchestral|contemporary classical|early music|symphon|concerto", re.I)


def classical_by_words(h, genre_db, album):
    """Batch 01: a composer tag alone is not enough. Genres like 'Opera' / 'Baroque' count; a work-like title counts only together with a
    conductor, an orchestra / choir / ensemble in the artist, or the composer among the performers. A pop song with a songwriter in the
    composer tag stays pop."""
    comp = norm_key(h.get("composer") or "")
    arts_raw = h.get("artist_full") or h.get("artist") or ""
    arts = norm_key(arts_raw)
    if not comp or comp == arts:
        return False
    if OPERA_GENRES.search(f"{genre_db} {h.get('genre') or ''}"):
        return True
    if not looks_classical(h.get("title"), album):
        return False
    return bool(h.get("conductor")) or bool(CLASSICAL_GROUP_WORDS.search(arts_raw)) or comp in arts


def classical_performer(h):
    """The name for the album folder suffix: the conductor, else the first PERSON among the performers (not an orchestra / choir)."""
    cond = (h.get("conductor") or "").split("/")[0].split(";")[0].strip()
    if cond:
        return cond
    comp = norm_key(h.get("composer") or "")
    names = [n.strip() for n in re.split(r"\s*[,;/&]\s*|\s+and\s+", h.get("artist_full") or h.get("artist") or "") if n.strip()]
    names = [n for n in names if norm_key(n) != comp and comp not in norm_key(n)]
    people = [n for n in names if not CLASSICAL_GROUP_WORDS.search(n)]
    return (people or names or [""])[0]


def unify_classical_suffix(items):
    """One album, one folder: tracks of the same classical album that got different performer names (tag noise) share the most common one."""
    groups = defaultdict(list)
    for it in items.values():
        if it.get("album_suffix") and it.get("kind") == "release":
            groups[(it.get("artist_folder"), norm_key(it.get("album") or ""), it.get("year"))].append(it)
    for its in groups.values():
        best = Counter(i["album_suffix"] for i in its).most_common(1)[0][0]
        for i in its:
            i["album_suffix"] = best


MERGE_ALIAS_FOLDERS = False      # V2.0.4: True = the old "Current - Old name" folders


def name_artist_folders(items):
    """One folder per artist. Renamed artists: 'Current - Old'. Persian-script names -> your Latin spelling."""
    by = defaultdict(list)
    for it in items.values():
        if it["kind"] in ("release", "singles", "artist_unverified"):
            by[it.get("artist_id") or norm_key(it.get("entity") or it.get("credited"))].append(it)
    for key, its in by.items():
        latin = Counter(i.get("tag_latin") for i in its if is_latin(i.get("tag_latin") or "")).most_common(1)
        latin = latin[0][0] if latin else ""
        names = {}
        counts = Counter()
        for i in its:
            n = prefer_latin(i.get("credited") or i.get("entity"), latin)
            y = int(i["year"]) if str(i.get("year", "")).isdigit() else 0
            k = norm_key(n)
            counts[k] += 1
            if k not in names or y > names[k][1]:
                names[k] = (n, y)
        if len(names) > 1 and not MERGE_ALIAS_FOLDERS:
            # V2.0.4: ONE canonical name per artist (the most used spelling; a tie goes to the newest credit) - never 'Name - Old name'
            best = max(names, key=lambda k_: (counts[k_], names[k_][1], -len(names[k_][0])))
            folder = names[best][0]
        elif len(names) > 1:
            folder = " - ".join(n for n, _ in sorted(names.values(), key=lambda x: -x[1]))
        else:
            folder = next(iter(names.values()))[0] if names else (latin or "Unknown Artist")
        for i in its:
            i["artist_folder"] = folder
    unify_classical_suffix(items)


CLASSICAL_MODE = "performer"     # V2.0.3 default: performer; was "skip". v1.1.5 (Settings): "skip" = classical artists get no tier number, "composer" = measured by composer, "performer" = filed under the performer
TIER_CLASSICAL = "00 Classical (not measured)"
TIER_GOLD, TIER_GETTO, TIER_START, TIER_SCAT, TIER_UNK = (
    "100 Golden Full Collection", "79 Get To Collection", "25 Starter Collection", "10 Scattered Collection",
    "00 Unknown Discography")
SORT_EXPLAIN = """How should artists be sorted in the library?
  [S]imple     - every artist folder directly in the library, A-Z.
  [C]ollection - artists grouped by how complete their STUDIO-ALBUM discography is (from MusicBrainz):
       100 Golden Full Collection   every studio album complete
       79 Get To Collection         50-99% of the studio albums complete
       25 Starter Collection        at least one complete studio album
       10 Scattered Collection      no complete studio album - plus every artist's partial albums
       00 Unknown Discography       the artist's discography is not known (e.g. not on MusicBrainz)
     Good if you collect full albums. Artists move up a tier (with your approval) as your collection grows."""


def assign_tiers(items, mb, apply=True):
    """Collection sort: give every artist-based item a tier folder (apply=False: only measure, for Analyze).
    Returns per-artist stats for the report."""
    by_folder = defaultdict(list)
    for it in items.values():
        if it["kind"] in ("release", "singles", "artist_unverified") and it.get("artist_folder"):
            by_folder[norm_key(it["artist_folder"]) or it["artist_folder"]].append(it)
    stats = {}
    prog = Progress("Checking discographies", len(by_folder)) if by_folder else None
    for key, its in by_folder.items():
        name = its[0]["artist_folder"]
        if prog:
            prog.step(name[:70])
        ids = Counter(i.get("mb_artist") for i in its if i.get("mb_artist"))
        studio = None
        if mb and ids:
            try:
                studio = mb.studio_albums(ids.most_common(1)[0][0])
            except RuntimeError:
                studio = None
        # which studio albums do you own COMPLETELY (any edition)?
        owned = defaultdict(set)
        totals = {}
        for i in its:
            if i["kind"] == "release" and i.get("release_id") and str(i.get("track", "")).isdigit():
                owned[i["release_id"]].add((i.get("disc") or "1", i["track"]))
                totals[i["release_id"]] = i.get("ntracks") or 0
        complete_releases = {r for r, got in owned.items() if totals.get(r) and len(got) >= totals[r]}
        complete_groups = {i["group_id"] for i in its if i.get("release_id") in complete_releases}
        if not studio:
            tier, done, pct = TIER_UNK, 0, None
        else:
            sg = {f"mb:{g}" for g in studio}
            done = len(sg & complete_groups)
            pct = done / len(sg)
            tier = TIER_GOLD if done == len(sg) else TIER_GETTO if pct >= 0.5 else TIER_START if done else TIER_SCAT
        if CLASSICAL_MODE == "skip" and any(str(n_).startswith("classical") for i in its for n_ in i.get("notes") or []):
            tier, done, pct = TIER_CLASSICAL, 0, None            # v1.1.5: classical artists have no known discography -> not measured
            studio = None
        stats[name] = (tier, done, len(studio or []), pct)
        for i in its if apply else ():
            partial_studio = (studio and i["kind"] == "release" and i.get("group_id", "")[3:] in studio
                              and i.get("release_id") not in complete_releases)
            i["tier"] = TIER_SCAT if partial_studio and tier not in (TIER_UNK, TIER_CLASSICAL) else tier
            # v1.1.5: under 2% of the studio albums complete -> the artist folder name gets no tier number ("Ben Folds", not "[10] Ben Folds")
            i["tier_plain"] = (bool(studio) and pct is not None and pct < 0.02) or tier in (TIER_CLASSICAL, TIER_UNK)      # 1.1.7: "[00] Unknown discography" artists get no number either: only artists with 2% or more are numbered
    if prog:
        prog.done()
    return stats


def edition_suffixes(items):
    """Original + remasters: '(Remastered)' if one remaster edition, '(2011 Remastered)' if several."""
    groups = defaultdict(list)
    for it in items.values():
        if it["kind"] == "release":
            groups[(it.get("artist_folder"), it.get("group_id"))].append(it)
    for its in groups.values():
        rem = sorted({i.get("release_year") or "?" for i in its if i.get("remaster")})
        for i in its:
            if i.get("remaster") and re.search(r"remaster", i.get("album") or "", re.I):
                continue                                   # V2.0.3: the album name already says it
            if i.get("remaster"):
                i["edition"] = " (Remastered)" if len(rem) == 1 else f" ({i.get('release_year') or ''} Remastered)".replace("( ", "(")


DEFAULT_LAYOUT = {"levels": ["tier", "artist"], "release": "year_album", "file": "full"}
LAYOUT = dict(DEFAULT_LAYOUT)
LEVEL_NAMES = {"tier": "Collection tier", "artist": "Artist", "genre": "Genre", "decade": "Decade", "letter": "First letter",
               "type": "Release type"}


def tier_artist_name(tier, artist, style="bracket"):
    """Collection tier in the ARTIST folder name instead of a tier folder (toggle in Plan preview):
    'bracket' -> '[100] Dean Martin', 'dash' -> '100 Golden - Dean Martin', 'suffix' -> 'Dean Martin [Golden 100]'."""
    parts = (tier or "").split()
    num, word = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    if style == "dash":
        return sanitize(f"{num} {word} - {artist}")
    if style == "suffix":
        return sanitize(f"{artist} [{word} {num}]")
    return sanitize(f"[{num}] {artist}")


def level_value(level, it, artist_folder):
    """One folder level of your custom layout (Settings / Plan preview)."""
    if level == "tier":
        return "" if LAYOUT.get("tier_style") == "name" else (it.get("tier") or "")
    if level == "artist":
        return artist_folder
    if level == "genre":
        return sanitize((it.get("genre") or "").split(";")[0].split("/")[0].strip().title()) or "Other"
    if level == "decade":
        y = str(it.get("year") or "")[:4]
        return f"{y[:3]}0s" if y.isdigit() else "Unknown Year"
    if level == "letter":
        a = re.sub(r"^(the|a|an)\s+", "", artist_folder, flags=re.I)
        ch = (a[:1] or "#").upper()
        return ch if ch.isalpha() and ch.isascii() else "#"
    if level == "type":
        return {"Album": "Albums", "EP": "EPs", "Single": "Singles", "Live": "Live", "OST": "Soundtracks", "Comp": "Compilations",
                "Box": "Box Sets", "Remix": "Remixes", "Bootleg": "Bootlegs", "Mix": "Mixes"}.get(it.get("rtype") or "Album", "Albums")
    return ""


def short_credit(text, limit=70):
    """v1.1.5: classical credits are long lists of soloists / choirs / orchestras / conductors; a file name keeps the first two names
    ('Wilfred Brown, Choir of King's College, Cambridge, Tom Krause, ...' -> 'Wilfred Brown, Choir of King's College'). Tags are not changed."""
    t = (text or "").strip()
    parts = [p_.strip() for p_ in re.split(r"\s*[,;]\s*", t) if p_.strip()]
    if len(t) <= limit and len(parts) <= 3:
        return t
    t = ", ".join(parts[:2])
    return t[:limit].rstrip(" ,;-") if len(t) > limit else t


SFX_FOLDER = "_Sound Effects"
SFX_WIDE = re.compile(r"\b(sfx|sound ?effects?|foley|whoosh|swoosh|explosion|footsteps?|door (?:open|close|slam)|beep|ringtone|jingle|stinger|ambience|ambient loop|impact|glitch|riser)\b", re.I)
SFX_STRICT = re.compile(r"\b(sfx|sound ?effects?|foley|whoosh|swoosh|footsteps?|ringtone|stinger|ambience)\b", re.I)


def is_sound_effect(it, kind):
    """V2.0.5 (decision): sound effects go to their own folder. Only files nobody matched to a real song are moved there:
    short / long files whose name, folder or title looks like an effect, and unverified files whose name clearly says so."""
    text = " ".join([os.path.basename(it.get("src", "")), os.path.basename(os.path.dirname(it.get("src", ""))), str(it.get("title") or "")])
    return bool((SFX_WIDE if kind in ("short", "long") else SFX_STRICT).search(text))


def build_paths(items, library):
    for it in items.values():
        k, ext = it["kind"], it["ext"]
        if k == "skip":
            continue
        base = os.path.splitext(os.path.basename(it["src"]))[0]
        if k in ("short", "long", "unverified") and is_sound_effect(it, k):
            it["folder"], it["name"] = os.path.join(library, SFX_FOLDER), sanitize(base) + ext
            it.setdefault("notes", []).append("looks like a sound effect: goes to the _Sound Effects folder")
            continue
        if k == "short":
            it["folder"], it["name"] = os.path.join(library, "_Unverified"), sanitize(base) + ext
            continue
        if k == "long":
            it["folder"], it["name"] = os.path.join(library, "_Unverified"), sanitize(base) + ext
            continue
        if k == "unverified":
            it["folder"] = os.path.join(library, "_Unverified")
            a, t = sanitize(it.get("artist")), sanitize(it.get("title"))
            it["name"] = (f"{a} - {t}" if a and t else sanitize(base)) + ext
            continue
        artist = sanitize(it["artist_folder"]) or "Unknown Artist"
        if LAYOUT.get("tier_style") == "name" and it.get("tier") and not it.get("tier_plain"):
            artist = tier_artist_name(it["tier"], artist, LAYOUT.get("tier_name", "bracket"))
        levels = [v for v in (level_value(lv, it, artist) for lv in LAYOUT["levels"]) if v]
        af = os.path.join(*levels) if levels else ""
        no_artist_level = "artist" not in LAYOUT["levels"]
        credit = short_credit(sanitize(it["credit_text"]) or artist)
        t = sanitize(it["title"]) or sanitize(base)
        if it.get("version") and not re.search(r"re-?master", t, re.I):          # 1.1.7: remaster / version label kept in the FILE name
            t = f"{t} ({sanitize(it['version'])})"
        if " : " in (it["title"] or "") and looks_classical(it["title"]):        # 1.1.5: 'Work : Composer: Work: No. 5 ...' -> one short name (tags are not changed)
            t = sanitize(classical_clean(it["title"])) or t
        if k == "artist_unverified":
            it["folder"], it["name"] = os.path.join(library, af, f"{artist} - _Unverified" if no_artist_level else "_Unverified"), f"{credit} - {t}{ext}"
            continue
        if k == "singles":
            it["folder"], it["name"] = os.path.join(library, af, f"{artist} - Singles" if no_artist_level else "Singles"), f"{credit} - {t}{ext}"
            continue
        alb = sanitize(it["album"] + it.get("edition", "") + it.get("album_suffix", "")) or "Unknown Release"
        y = it.get("year") or ""
        n = int(it["track"]) if str(it.get("track")).isdigit() else 0
        w = 3 if (it.get("maxtrack") or 0) >= 100 else 2
        num = f"{n:0{w}d}" if n else ""
        if num and str(it.get("disctotal") or "1").isdigit() and int(it.get("disctotal") or 1) > 1:
            num = f"{it['disc']}-{num}"

        if no_artist_level:                       # no artist folder: keep the artist in the album folder name
            alb = f"{artist} - {alb}"
        it["_parts"] = (library, af, credit, y, num, ext, None if "type" in LAYOUT["levels"] else PREFIX.get(it["rtype"]), alb, t,
                        {"albumartist": artist, "disc": str(it.get("disc") or ""), "genre": sanitize((it.get("genre") or "").split(";")[0].strip().title())})
        it["folder"], it["name"] = release_path(it["_parts"], alb, t)
    shorten_releases(items)


PATTERN_TOKENS = ("{artist}", "{albumartist}", "{year}", "{album}", "{track}", "{disc}", "{title}", "{genre}", "{type}")


def fill_pattern(pattern, vals):
    """Your own name format (Plan preview, drag blocks): ['{year}', ' - ', '{album}'] -> '1969 - Abbey Road'.
    Empty values disappear together with brackets around them."""
    out = "".join(vals.get(p_[1:-1], "") if p_ in PATTERN_TOKENS else p_ for p_ in pattern or [])
    out = re.sub(r"\(\s*\)|\[\s*\]", "", out)
    out = re.sub(r"(\s*-\s*){2,}", " - ", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" -._")
    return sanitize(out)


def release_path(parts, alb, t):
    library, af, credit, y, num, ext, pre, _, _ = parts[:9]
    extra = parts[9] if len(parts) > 9 else {}
    style = LAYOUT.get("release", "year_album")
    vals = {"artist": credit, "albumartist": extra.get("albumartist") or credit, "year": y, "album": alb, "track": num,
            "disc": extra.get("disc", ""), "title": t, "genre": extra.get("genre", ""), "type": pre or ""}
    if style == "custom" and LAYOUT.get("release_pattern"):
        fold = fill_pattern(LAYOUT["release_pattern"], vals) or alb
    elif style == "album_year":
        fold = f"{alb} ({y})" if y else alb
        fold = f"{pre} {fold}" if pre else fold
    elif style == "album":
        fold = f"{pre} {alb}" if pre else alb
    else:
        fold = (f"{pre} {y} {alb}" if y else f"{pre} {alb}") if pre else (f"{y} - {alb}" if y else alb)
    fstyle = LAYOUT.get("file", "full")
    if fstyle == "custom" and LAYOUT.get("file_pattern"):
        name = (fill_pattern(LAYOUT["file_pattern"], vals) or t) + ext
    elif fstyle == "track_title":
        name = f"{(num + ' ') if num else ''}{t}{ext}"
    elif fstyle == "artist_track_title":
        name = f"{credit} - {(num + ' ') if num else ''}{t}{ext}"
    else:
        name = f"{credit} - {(y + ' ') if y else ''}{alb} - {(num + ' ') if num else ''}{t}{ext}"
    return os.path.join(library, af, fold) if af else os.path.join(library, fold), name


def shorten_releases(items, limit=254 - 9):
    """Keep paths under 255 characters. The album part is shortened ONCE per release (so every song of an album
    stays in the same folder); only then are long song titles shortened, one by one."""
    groups = defaultdict(list)
    for it in items.values():
        if it.get("_parts"):
            groups[os.path.normcase(it["folder"])].append(it)
    for its in groups.values():
        def too_long(alb_):
            return max(len(os.path.join(*release_path(i["_parts"], alb_, i["_parts"][8]))) for i in its) > limit
        alb = its[0]["_parts"][7]
        if not too_long(alb):
            continue
        while too_long(alb) and len(alb) > 20:
            alb = alb[:-1].rstrip(" -.")
        if alb != its[0]["_parts"][7] and " " in alb:          # end on a whole word, no dangling quote or comma
            alb = alb[:alb.rfind(" ")] if not its[0]["_parts"][7].startswith(alb + " ") else alb
            alb = alb.rstrip(" -.,;:'\"(\u2018\u2019\u201c\u201d") or alb
        for i in its:
            t = i["_parts"][8]
            folder, name = release_path(i["_parts"], alb, t)
            while len(os.path.join(folder, name)) > limit and len(t) > 20:
                t = t[:-1].rstrip(" -.")
                folder, name = release_path(i["_parts"], alb, t)
            i["folder"], i["name"] = folder, name
            if "path shortened" not in i["notes"]:
                i["notes"].append("path shortened")


def cap_path_lengths(items):
    """Any remaining name over the 255-character limit (unverified, singles...) is trimmed and reported."""
    for it in items.values():
        if it.get("folder") and len(os.path.join(it["folder"], it["name"])) > 245:
            stem, ext = os.path.splitext(it["name"])
            keep = max(20, 245 - len(it["folder"]) - 1 - len(ext))
            it["name"] = stem[:keep].rstrip(" -.") + ext
            if "path shortened" not in it["notes"]:
                it["notes"].append("path shortened")


def suffixed(name, n):
    stem, ext = os.path.splitext(name)
    return f"{stem} ({n:02d}){ext}"


def dup_suffixed(name, n):
    """V2.0.3: an extra copy of the same song is named "Title (2)", "Title (3)"..."""
    stem, ext = os.path.splitext(name)
    return f"{stem} ({n}){ext}"


CODEC_WEIGHT = {".opus": 1.6, ".m4a": 1.3, ".aac": 1.3, ".ogg": 1.2, ".mp3": 1.0, ".wma": 0.9}


def quality_score(r, it=None):
    """Best to worst: lossless first (then sample rate x bit depth), then bitrate weighted by codec
    (AAC/Opus sound better than MP3 at the same bitrate), then complete tags, cover size, confidence."""
    tags = r.get("tags") or {}
    complete = sum(1 for k in ("artist", "albumartist", "album", "title", "track", "year", "genre") if tags.get(k))
    sound = (r.get("sample_rate") or 44100) * (r.get("bits") or 16) if r.get("lossless") else \
        (r.get("bitrate") or 0) * CODEC_WEIGHT.get(r.get("ext"), 1.0)
    conf = {"high": 2, "medium": 1, "low": 0}.get((it or {}).get("confidence"), 0)
    return (1 if r.get("lossless") else 0, round(sound), complete, min(r.get("cover_px") or 0, 1000), conf)


_VERSION_RE = re.compile(r"\b(live|unplugged|demo|alternate|alternative|alt\.?|acoustic|instrumental|a cappella|acapella|mono|stereo|remix|mix|rehearsal|outtake|take \d+|session|radio edit|single edit|album version|single version|extended|edit|reprise|version \d*|bbc|vocal)\b", re.I)


def version_tags(title):
    """Words in a title that say it is another version of the song (live, demo, alternate, mono, remix...).
    'Remaster' is NOT one: a remaster is the same recording. Used so Bowie's other versions are not duplicates."""
    t = re.sub(r"remaster(ed)?( \d{4})?|\d{4} remaster(ed)?", "", title or "", flags=re.I)
    return frozenset(m.group(1).lower().rstrip(".") for m in _VERSION_RE.finditer(t))


def mark_duplicates(items, inv_by_id, cp):
    """Same song in the same folder (any format). Ranked best -> worst by quality_score.
    Kept: the best LOSSLESS copy and the best COMPRESSED copy (same name, different extension - a FLAC and an MP3
    of one song both stay). Extra copies of the same kind are NOT copied by default; they are listed in
    duplicates.csv / on the Duplicates page, where any of them can be included ('keep' -> named Title (02)...).
    Different songs that only share a name: Singles get the year, others are asked about. Originals: never touched."""
    folders = defaultdict(lambda: defaultdict(list))
    for it in items.values():                                  # V2.0.3: a re-check starts clean (stale flags made a kept song an "extra")
        if it.get("dup_orig_folder"):
            it["folder"] = it.pop("dup_orig_folder")
        for k_ in ("dup_flat", "dup_keep", "dup_tag", "dup_name", "dup_of", "dup_identical"):
            it.pop(k_, None)
    for it in items.values():
        it.pop("dup_possible", None)
        if it["kind"] != "skip" and (it["approved"] or it.get("fixed")):
            stem = os.path.splitext(it["name"])[0].lower()
            folders[os.path.normcase(it["folder"])][stem].append(it)
    dup_groups, collisions = [], []
    # V2.0.5 (#11): songs still waiting for review are not grouped (their place may still change), but a waiting song that would land
    # on the same name in the same folder as another planned song, with the same length, is flagged "possible duplicate" so you see it
    # in Review and on the Duplicates page BEFORE you accept it. Nothing is dropped or moved because of this flag.
    pending = defaultdict(lambda: defaultdict(list))
    for it in items.values():
        if it["kind"] != "skip" and not it.get("fixed") and not it["approved"] and it.get("folder") and it.get("name"):
            pending[os.path.normcase(it["folder"])][os.path.splitext(it["name"])[0].lower()].append(it)

    def key(it):
        return (bool(it.get("fixed")),) + quality_score(inv_by_id[it["file_id"]], it) + (-int(it["file_id"][1:]),)

    def same_song(a_it, b_it):
        a, b = inv_by_id[a_it["file_id"]], inv_by_id[b_it["file_id"]]
        if version_tags(a_it.get("title") or a_it.get("name")) != version_tags(b_it.get("title") or b_it.get("name")):
            if not (a.get("audio_hash") and a["audio_hash"] == b.get("audio_hash")):
                return False                                   # another version of the song (live, demo, alternate...)
        if a.get("audio_hash") and a["audio_hash"] == b.get("audio_hash"):
            return True
        if abs((a.get("duration") or 0) - (b.get("duration") or 0)) > 3:
            return False                                       # V2.0.3 decision 7: another length = another version, never a copy
        ra, rb = a_it.get("recording_id"), b_it.get("recording_id")
        if ra and rb:
            return ra == rb
        if a_it.get("verified") and b_it.get("verified") and a_it.get("group_id") != b_it.get("group_id") \
                and a_it.get("year") != b_it.get("year"):
            return False
        if cp and cp.fpcalc:
            sim = cp.similarity(cp.raw(a["path"]), cp.raw(b["path"]))
            if sim is not None:
                return sim >= 0.80
        return abs((a.get("duration") or 0) - (b.get("duration") or 0)) <= 3

    def flag_pending():
        for f_, names_ in pending.items():
            for stem_, waiting_ in names_.items():
                others = list(folders.get(f_, {}).get(stem_, [])) + waiting_
                if len(others) < 2:
                    continue
                try:
                    others.sort(key=key, reverse=True)
                except Exception:
                    continue
                best_ = others[0]
                for w_ in waiting_:
                    if w_ is not best_ and same_song(best_, w_):
                        w_["dup_possible"] = best_["file_id"]
                if best_ in waiting_:                       # the waiting one is the best copy: flag the others instead
                    for o_ in others[1:]:
                        if same_song(best_, o_) and o_ in waiting_:
                            o_["dup_possible"] = best_["file_id"]

    try:
        flag_pending()
    except Exception:                                       # a hint only: never stop the plan because of it
        pass
    for f, names in folders.items():
        for stem, group in list(names.items()):
            if len(group) < 2:
                continue
            group.sort(key=key, reverse=True)
            best = group[0]
            same, diff = [best], []
            for it in group[1:]:
                (same if same_song(best, it) else diff).append(it)
            kept_kind = {}
            for rank, it in enumerate(same, 1):
                r = inv_by_id[it["file_id"]]
                kind = "lossless" if r.get("lossless") else "compressed"
                it["dup_group"], it["dup_rank"], it["dup_kind"] = best["file_id"], rank, kind
                twin = next((o for o in same[:rank - 1] if r.get("audio_hash") and
                             inv_by_id[o["file_id"]].get("audio_hash") == r["audio_hash"]), None)
                identical = twin is not None
                it["dup_identical"] = bool(identical)
                if it.get("fixed") or it.get("dup_user_keep"):      # V2.0.3: "keep both" on the Duplicates page = stays in its album
                    kept_kind.setdefault(kind, it)
                    continue
                if kind not in kept_kind and r["ext"] not in {inv_by_id[k["file_id"]]["ext"] for k in kept_kind.values()}:
                    kept_kind[kind] = it                       # best of its kind: kept under the song's own name
                    continue
                it["dup_of"] = (twin or kept_kind.get(kind, best))["file_id"]
                # V2.0.3 (Amin): the best copy stays in its artist/album folder; every extra copy of the same song is COPIED too, named
                # "Title (2)", into ONE flat _Duplicates folder outside the artists. Exactly identical audio also gets a removable
                # Comment tag "DUPLICATE". Nothing is dropped; the Duplicates page can still leave a copy out.
                it["dup_keep"], it["dup_flat"], it["dup_tag"] = True, True, bool(identical)
                it["dup_name"] = dup_suffixed(it["name"], rank)
            if len(same) > 1:
                dup_groups.append(same)
            for it in diff:
                if it.get("fixed"):
                    continue
                if it["kind"] == "singles" and it.get("year"):
                    it["name"] = suffixed(it["name"], 0).replace(" (00)", f" ({it['year']})")
                    it["notes"].append("same title as another single - year added")
                else:
                    it["collision"] = True
                    collisions.append(it)
    return dup_groups, collisions


def write_duplicates(st, dup_groups, inv_by_id):
    """duplicates.csv + .json: every group, best -> worst, with all the data the Duplicates page shows."""
    rows = []
    for g in dup_groups:
        for it in g:
            r = inv_by_id[it["file_id"]]
            t = r.get("tags") or {}
            rows.append({"group": g[0]["file_id"], "rank": it.get("dup_rank"), "decision":
                         "kept" if not it.get("dup_extra") else "not copied (tick to include)",
                         "why": it.get("reason", "") if it.get("dup_extra") else ("best " + (it.get("dup_kind") or "")),
                         "identical_audio": "yes" if it.get("dup_identical") else "",
                         "format": r["ext"][1:].upper(), "lossless": "yes" if r.get("lossless") else "",
                         "bitrate_kbps": r.get("bitrate") or "", "sample_rate": r.get("sample_rate") or "",
                         "length": round(r.get("duration") or 0), "size_mb": round((r.get("size") or 0) / 1e6, 1),
                         "tags_filled": sum(1 for k in ("artist", "albumartist", "album", "title", "track", "year", "genre") if t.get(k)),
                         "cover_px": r.get("cover_px") or "", "artist": t.get("artist", ""), "title": t.get("title", ""),
                         "album": t.get("album", ""), "source": r["path"], "new_name": os.path.basename(it.get("new_path", "") or ""),
                         "file_id": it["file_id"]})
    st.retire("duplicates.csv")
    write_csv(st.p("duplicates.csv"), list(rows[0]) if rows else ["group"], rows)
    st.save("duplicates.json", rows)
    extra = [x for x in rows if x["decision"].startswith("not")]
    return len(dup_groups), len(extra), sum(x["size_mb"] for x in extra)


def finalize_names(items):
    """Final names. Two files may never share one path (that would stop Phase 3 under 'never overwrite'):
    a second file with the same name gets (02), (03)..."""
    used = {os.path.normcase(it["new_path"]) for it in items.values() if it.get("fixed") and it.get("new_path")}
    for it in sorted(items.values(), key=lambda x: (not x["approved"], x["file_id"])):
        if it["kind"] == "skip":
            it["new_path"] = ""
            continue
        if it.get("fixed"):
            continue
        name = it.get("dup_name") or it["name"]
        base = re.sub(r" \((\d{2})\)(\.[^.]+)$", r"\2", name)
        m_ = re.search(r" \((\d{2})\)\.[^.]+$", name)
        n = int(m_.group(1)) + 1 if m_ else 2
        while os.path.normcase(os.path.join(it["folder"], name)) in used:
            name = suffixed(base, n)
            n += 1
        if name != (it.get("dup_name") or it["name"]):
            it["notes"].append("numbered: another file already has this name")
        used.add(os.path.normcase(os.path.join(it["folder"], name)))
        it["new_path"] = os.path.join(it["folder"], name)
        if it["approved"] and exists(it["new_path"]) and not same_path(it["new_path"], it.get("current_path") or ""):
            it["approved"] = False
            it["reason"] = "a file with this name already exists in the library"


def plan_tags(it):
    if not it.get("verified"):
        return {}   # not confirmed by the real discography -> tags stay exactly as they are
    multi = str(it.get("disctotal") or "1").isdigit() and int(it.get("disctotal") or 1) > 1
    return {"artist": it["display_artist"], "artists": it.get("artists") or [], "albumartist": it.get("credited") or "",
            "album": (it.get("album") or "") + it.get("edition", "") if it["kind"] == "release" else (it.get("album") or ""),
            "title": (f"{it['title']} ({it['version']})" if it.get("version") and it.get("title") and not re.search(r"re-?master", it["title"], re.I) else it["title"]),      # v2.0: a remaster stays visible in the title tag too
            "track": it.get("track", ""), "tracktotal": it.get("tracktotal", ""),
            "disc": it.get("disc", "") if multi else "", "disctotal": it.get("disctotal", "") if multi else "",
            "year": it.get("year", ""), "genre": it.get("genre", ""), "compilation": bool(it.get("compilation")),
            "original_release": it.get("original_release", ""), "composer": it.get("composer", ""),
            "dup_comment": "DUPLICATE" if it.get("dup_tag") else ""}


def auto_gate(st, plan, inv_by_id):
    """V2.0.3 decision 2: a song is placed on its own ONLY when its tags are already 100% identical to the match (nothing to change).
    Every other matched song waits for an OK in Review / Check tags. The automatic ones are listed in auto_accepted.json (the app
    shows them with an Undo)."""
    decided = UI.decisions() if UI is not None and hasattr(UI, "decisions") else {}
    auto, held = [], 0
    for it in plan:
        if it.get("kind") not in ("release", "singles") or not it.get("verified") or not it.get("approved"):
            continue
        if it.get("fixed") or it.get("action") in ("relocate", "keep", "skip") or it.get("dup_extra") or it["file_id"] in decided:
            continue
        per = it.get("tag_match") or {}
        same = all(v == 100 for v in per.values() if v is not None) and all(per.get(k) == 100 for k in ("artist", "title", "album"))
        if same and it.get("confidence") == "high":
            auto.append({"file_id": it["file_id"], "src": it["src"], "artist": it.get("display_artist", ""), "title": it.get("title", ""),
                         "album": it.get("album", "")})
            it["auto_ok"] = True
        else:
            it["approved"], it["held"] = False, True
            it["reason"] = "tags would change - waits for your OK"
            it["review"] = ("medium", norm_key(it.get("entity") or it.get("credited") or ""), it.get("entity") or it.get("credited") or "")
            held += 1
    st.save("auto_accepted.json", auto)
    say(f"Placed automatically (tags already identical): {len(auto):,}. Waiting for your OK because tags would change: {held:,}.")


def tag_str(d):
    return "; ".join(f"{k}={'/'.join(v) if isinstance(v, list) else v}" for k, v in d.items() if v not in ("", None, False, []))

# ----------------------------------------------------------------------------- Phase 2: questions


def ask_grouped(decisions, cat, header, groups, options, default, explain="", bulk_default=None):
    saved = decisions.setdefault(cat, {})
    pending = {k: v for k, v in groups.items() if k not in saved}
    if not pending:
        return
    if UI and UI.defer_review:      # the app decides song by song on its Review / Duplicates screens
        return
    hr(header)
    if explain:
        say(explain)
    items = list(pending.items())
    for k, v in (items[:15] if len(items) > 1 else []):
        say(f"   - {v}")
    if len(items) > 15:
        say(f"   ... and {len(items) - 15} more (full list in needs_review.csv)")
    if len(items) > 1:
        c = ask_choice("One answer for all of these?", {**options, "r": "eview one by one"}, bulk_default or default)
        if c != "r":
            for k in pending:
                saved[k] = c
            return
    for k, v in items:
        saved[k] = ask_choice(f"  {v}", options, default)


def review_groups(items, cat):
    g = defaultdict(Counter)
    label = {}
    for it in items.values():
        rv = it.get("review")
        if rv and rv[0] == cat:
            label[rv[1]] = rv[2]
            if cat == "unverified":
                g[rv[1]][it.get("title") or os.path.basename(it["src"])] += 1
            else:
                src = "" if it.get("data_source", "").startswith("MusicBrainz") else f" [{it.get('data_source')}]"
                kind = "Singles" if it["kind"] == "singles" else (it.get("rtype") or "")
                g[rv[1]][f"{it.get('album') or '(no release)'} ({kind}){src}"] += 1
    out = {}
    for k, c in g.items():
        parts = [f"{a}" + (f" x{n}" if n > 1 else "") for a, n in c.most_common(6)]
        out[k] = f"{label[k]}: " + ", ".join(parts) + (" ..." if len(c) > 6 else "")
    return out


def apply_decisions(items, decisions):
    for it in items.values():
        rv = it.get("review")
        if not rv or it["kind"] == "skip":
            continue
        ans = decisions.get(rv[0], {}).get(rv[1])
        if rv[0] == "medium":
            it["approved"] = ans == "a"
        elif rv[0] == "unverified":
            it["approved"] = ans == "y"
        elif rv[0] == "recheck":
            it["approved"] = ans == "a"
        if not it["approved"]:
            it["reason"] = it.get("reason") or "waiting for your review"


def phase2(st, cfg):
    hr("PHASE 2 - Propose changes (read-only: nothing is changed)")
    inv = st.load("inventory.json", [])
    if not inv:
        say("Run Phase 1 first.")
        return
    inv_by_id = {r["id"]: r for r in inv}
    say("Online lookups confirm songs against the real discography. I will ask before using each service.\n"
        "Every site receives text only (artist, album, song title, length) - never your files or paths.")
    mb = None
    if ask_yn("\nMusicBrainz (main source, free, ~1 request/second)?", "y" if cfg.get("use_mb", True) else "n"):
        cfg["use_mb"] = True
        cfg["mb_contact"] = ask("MusicBrainz asks for a contact (email or website) in requests; optional",
                                cfg.get("mb_contact", ""))
        mb = MusicBrainz(st, cfg["mb_contact"])
    else:
        cfg["use_mb"] = False
    if not cfg.get("fpcalc") or not os.path.isfile(cfg["fpcalc"]):
        cfg["fpcalc"] = find_tool("fpcalc")
    cp = Chromaprint(cfg["fpcalc"]) if cfg.get("fpcalc") else None
    if mb and not cp:
        say("\nIdentify by sound (AcoustID) is not available: fpcalc.exe is missing.\n"
            "   Start the program with 'Start Music Manager.bat' once - it downloads fpcalc automatically.")
    if cp and mb:
        say("\nIdentify by sound (AcoustID, api.acoustid.org): for songs that cannot be found by name, the audio is\n"
            "recognized from a fingerprint computed on your PC (a list of numbers - not the audio) plus its length.")
        if ask_yn("Use identify by sound?", "n" if cfg.get("acoustid_off") else "y"):
            cfg.pop("acoustid_off", None)
            if not cfg.get("acoustid_key"):
                say("   It needs a free API key (one time):\n"
                    "     1. open  https://acoustid.org/new-application  and log in (a MusicBrainz account works)\n"
                    "     2. Application name: anything, e.g. 'Music Sorter'; Version: 1.0\n"
                    "     3. copy the API key it shows and paste it here")
            cfg["acoustid_key"] = ask("   AcoustID API key", cfg.get("acoustid_key", "")).strip()
            cp.key = cfg["acoustid_key"]
            if not cp.key:
                say("   No key - identify by sound is skipped this time.")
        else:
            cfg["acoustid_off"] = True
    say("\nOther sites, used only for songs MusicBrainz cannot identify:")
    use = []
    if ask_yn("  Discogs? (needs a free personal token; sends artist, album and song names)",
              "y" if cfg.get("discogs_token") else "n"):
        if not cfg.get("discogs_token"):
            say("   How to get the token (one time):\n"
                "     1. sign in at  https://www.discogs.com  (a free account is enough)\n"
                "     2. open  https://www.discogs.com/settings/developers\n"
                "     3. click 'Generate new token', copy it and paste it here")
        cfg["discogs_token"] = ask("  Discogs personal token", cfg.get("discogs_token", "")).strip()
        if cfg["discogs_token"]:
            use.append("discogs")
        else:
            say("   No token - Discogs is skipped this time.")
    if ask_yn("  Deezer? (free, no account needed)", "y" if "deezer" in cfg.get("alt_use", []) else "n"):
        use.append("deezer")
    if ask_yn("  Apple Music / iTunes? (free; about 20 lookups per minute)", "y" if "itunes" in cfg.get("alt_use", []) else "n"):
        use.append("itunes")
    if ask_yn("  Tidal? (beta; needs a Client ID + Client Secret from developer.tidal.com; sends artist, album and song names)",
              "y" if "tidal" in cfg.get("alt_use", []) else "n"):
        if not cfg.get("tidal_id"):
            say("   How to get the keys (one time):\n"
                "     1. sign in at  https://developer.tidal.com/dashboard\n"
                "     2. create a new app (any name, e.g. Midnight)\n"
                "     3. copy the Client ID and the Client Secret")
        cfg["tidal_id"] = ask("  Tidal Client ID", cfg.get("tidal_id", "")).strip()
        cfg["tidal_secret"] = ask("  Tidal Client Secret", cfg.get("tidal_secret", "")).strip()
        if cfg["tidal_id"] and cfg["tidal_secret"]:
            use.append("tidal")
        else:
            say("   No keys - Tidal is skipped this time.")
    if ask_yn("  Last.fm? (free API key; asked last, only for songs no other site found;\n"
              "   sends artist, song and album names)", "y" if "lastfm" in cfg.get("alt_use", []) else "n"):
        if not cfg.get("lastfm_key"):
            say("   How to get the key (one time):\n"
                "     1. sign in at  https://www.last.fm  (a free account is enough)\n"
                "     2. open  https://www.last.fm/api/account/create\n"
                "        Application name: Midnight 00:01 (description and callback can stay empty)\n"
                "     3. copy the 'API key' (not the 'Shared secret') and paste it here")
        cfg["lastfm_key"] = ask("  Last.fm API key", cfg.get("lastfm_key", "")).strip()
        if cfg["lastfm_key"]:
            use.append("lastfm")
        else:
            say("   No key - Last.fm is skipped this time.")
    cfg["alt_use"] = use
    if len(use) > 1:
        cur = [k for k in cfg.get("alt_order", ALT_ORDER) if k in ALT_ORDER] + [k for k in ALT_ORDER if k not in cfg.get("alt_order", ALT_ORDER)]
        cfg["alt_order"] = ask_order("Other sites are asked in this order", cur, ALT_NAMES)
    hr("Library layout")
    say(SORT_EXPLAIN)
    cfg["sort_mode"] = "collection" if ask_choice("Sort mode", {"s": "imple", "c": "ollection"},
                                                  "c" if cfg.get("sort_mode") == "collection" else "s") == "c" else "simple"
    presets = {"1": ("Standard", ["tier", "artist"]), "2": ("Artist only", ["artist"]), "3": ("By genre", ["genre", "artist"]),
               "4": ("By decade", ["decade", "artist"]), "5": ("A-Z letter", ["letter", "artist"]), "6": ("Artist, then type", ["artist", "type"])}
    lay = dict(DEFAULT_LAYOUT, **(cfg.get("layout") or {}))
    say("\nFolder layout (inside the library):  now  " + " / ".join(LEVEL_NAMES[x] for x in lay["levels"]) + " / release folder")
    for k_, (nm, lv) in presets.items():
        say(f"   {k_}) {nm:18} " + " / ".join(LEVEL_NAMES[x] for x in lv) + " / Year - Album")
    say("   c) custom: type the levels, e.g.  genre decade artist   (choose from: " + ", ".join(LEVEL_NAMES) + ")")
    ch = ask("   Layout (Enter = keep)", "").strip().lower()
    if ch in presets:
        lay["levels"] = presets[ch][1]
    elif ch == "c":
        lv = [w for w in ask("   Levels", " ".join(lay["levels"])).lower().replace(",", " ").split() if w in LEVEL_NAMES]
        if lv:
            lay["levels"] = lv
    if ch:
        r_ = ask_choice("   Release folder name", {"y": "ear - Album", "a": "lbum (Year)", "n": "ame only"},
                        {"year_album": "y", "album_year": "a", "album": "n"}[lay.get("release", "year_album")])
        lay["release"] = {"y": "year_album", "a": "album_year", "n": "album"}[r_]
        f_ = ask_choice("   File name", {"f": "ull: Artist - Year Album - 01 Title", "t": "rack: 01 Title", "a": "rtist - 01 Title"},
                        {"full": "f", "track_title": "t", "artist_track_title": "a"}[lay.get("file", "full")])
        lay["file"] = {"f": "full", "t": "track_title", "a": "artist_track_title"}[f_]
    cfg["layout"] = lay
    if cfg["sort_mode"] == "collection" and not mb:
        say("   Note: without MusicBrainz no discography is known - every artist would land in 00 Unknown Discography.")
    cfg["analyze"] = ask_yn("\nAnalyze the collection (how much of each artist and album you own)?\n"
                            "   Checks each artist's discography on MusicBrainz (answers are cached).",
                            "y" if cfg.get("analyze", True) else "n") if mb and cfg["sort_mode"] != "collection" else True
    cover_order = [k for k in cfg.get("cover_order", COVER_ORDER) if k in COVER_ORDER] + \
        [k for k in COVER_ORDER if k not in cfg.get("cover_order", COVER_ORDER)]
    cfg["covers"] = ask_yn("\nCover art for confirmed songs (" + " -> ".join(COVER_NAMES[k] for k in cover_order) + ",\n"
                           "same release only, max 1000x1000)?", "y" if cfg.get("covers", True) else "n")
    if cfg["covers"]:
        cfg["cover_order"] = ask_order("Cover art is looked for in this order", cover_order, COVER_NAMES)
    cfg["lyrics"] = ask_yn("Lyrics for confirmed songs from LRCLIB (lrclib.net; sends artist, title, album, length)?",
                           "y" if cfg.get("lyrics") else "n")
    st.save("config.json", cfg)
    alt = AltSources(st, use, cfg.get("discogs_token", ""), cfg.get("lastfm_key", ""), cfg.get("tidal_id", ""), cfg.get("tidal_secret", ""), cfg.get("spotify_id", ""), cfg.get("spotify_secret", "")) if (use or cfg["covers"]) else None
    if alt:
        alt.order = full_alt_order(cfg)
        alt.cover_order = list(cfg.get("cover_order") or COVER_ORDER)
    if alt:
        alt.use = use

    prov = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    organized = {fid for fid, r in prov.items() if r.get("status") in ("verified", "copied", "original_archived")
                 and r.get("new_full_path")}
    res = Resolver(inv, cfg, mb, cp, alt if use else None)
    try:
        results = res.run()
        if UI:      # your own picks from the app's Review screen win over what was found
            UI.review_results(results, res, inv_by_id)
    except RuntimeError as e:
        say(f"\nStopped: {e}\nAnswers received so far are cached; run Phase 2 again to continue.")
        if mb:
            mb.save()
        return
    items = {}
    for r in inv:
        h = res.h.get(r["id"]) or hints(r)
        out, conf = results.get(r["id"], (None, "low"))
        items[r["id"]] = make_item(r, h, out, conf)
    name_artist_folders(items)
    edition_suffixes(items)
    collection = cfg.get("sort_mode") == "collection"
    measure = mb and (collection or cfg.get("analyze"))
    tier_stats = assign_tiers(items, mb, apply=collection) if measure else {}
    if mb:
        mb.save()
    st.save("tier_stats.json", {k: list(v) for k, v in tier_stats.items()} if collection else {})
    LAYOUT.clear()
    LAYOUT.update(DEFAULT_LAYOUT, **(cfg.get("layout") or {}))
    if cfg.get("sort_mode") != "collection":
        LAYOUT["levels"] = [lv for lv in LAYOUT["levels"] if lv != "tier"]
    build_paths(items, cfg["library"])
    cap_path_lengths(items)
    write_analysis(st, cfg, items, tier_stats, mb)

    decisions = st.load("decisions.json", {})
    if decisions and not ask_yn("Reuse your earlier review answers where they still apply?", "y"):
        decisions = {}
    new_items = {k: v for k, v in items.items() if k not in organized}
    say(f"\n{len(new_items):,} new files" + (f", {len(organized):,} already organized" if organized else "") + ".")
    ask_grouped(decisions, "medium", "Songs matched by search (please check)", review_groups(new_items, "medium"),
                {"a": "ccept", "l": "eave for later"}, "a",
                "Matched on MusicBrainz or on the site shown in [brackets]. Accept if they look right.")
    ask_grouped(decisions, "unverified", "Songs that could NOT be confirmed anywhere", review_groups(new_items, "unverified"),
                {"y": "es, copy to _Unverified (tags unchanged)", "l": "eave for later (not copied)"}, "y",
                "They go to _Unverified (or the artist's _Unverified folder) exactly as tagged.", bulk_default="r")
    apply_decisions(new_items, decisions)
    if UI:
        UI.review_approvals(new_items)

    # already organized files: fixed in place unless you accept a re-check proposal
    recheck = False
    if organized:
        recheck = ask_yn(f"\nRe-check the {len(organized):,} already organized files for improvements?", "n")
    for fid in organized:
        it = items.get(fid)
        if not it:
            continue
        cur = prov[fid]["new_full_path"]
        it["current_path"] = cur
        was_stand_in = "placed on the original release" in (prov[fid].get("changes_made") or "")
        now_stand_in = any("placed on the original release" in n for n in it.get("notes", []))
        give_back = was_stand_in and not now_stand_in and it.get("verified")   # the real original has arrived
        if (recheck or give_back) and it["kind"] not in ("skip",) and it.get("verified"):
            it["action"] = "relocate"
            it["review"] = ("recheck", "_giveback" if give_back else norm_key(it.get("artist_folder") or ""),
                            "Compilation copies giving their place to the real original album" if give_back
                            else (it.get("artist_folder") or ""))
            it["approved"] = True   # provisional for naming; confirmed below
        else:
            it.update(fixed=True, approved=False, action="keep", folder=os.path.dirname(cur), name=os.path.basename(cur),
                      new_path=cur)
    dup_groups, collisions = mark_duplicates(items, inv_by_id, cp)
    extras = {g[0]["file_id"]: g for g in dup_groups if any(i.get("dup_extra") for i in g)}
    if extras:
        say("\nSame song more than once: the best copy of each kind is kept (a FLAC and an MP3 both stay).")
        ask_grouped(decisions, "dupextra", "Extra copies of the same song (best to worst)",
                    {k: " | ".join(f"{inv_by_id[i['file_id']]['ext'][1:]} {inv_by_id[i['file_id']].get('bitrate', 0)}k"
                                   + (" =same audio" if i.get("dup_identical") else "") + (" KEPT" if not i.get("dup_extra") else "")
                                   for i in g) + "  " + g[0]["name"] for k, g in extras.items()},
                    {"s": "kip the extra copies (listed in duplicates.csv; originals untouched)", "k": "eep them too, numbered (02)..."}, "s")
        for k, g in extras.items():
            if decisions["dupextra"].get(k) == "k":
                for i in g:
                    if i.get("dup_extra"):
                        i.update(approved=True, dup_extra=False, dup_keep=True, reason="")
                        i["dup_name"] = suffixed(i["name"], i["dup_rank"])
    if UI is not None and hasattr(UI, "dup_choices"):     # the app's Duplicates page: your choice per copy
        UI.dup_choices(dup_groups)
    if collisions:
        g = {it["file_id"]: f"{it['name']}  <-  {it['src']}" for it in collisions}
        ask_grouped(decisions, "collision", "Same file name, but the audio is different", g,
                    {"n": "umber them: Name (02)", "s": "kip the extra files"}, "s")
        for it in collisions:
            if decisions["collision"].get(it["file_id"]) == "n":
                it["dup_name"] = suffixed(it["name"], 2 + collisions.index(it))
            else:
                it["approved"] = False
                it["reason"] = "name collision - audio differs from the other file"
    if True:                                           # V2.0.3: extra copies always go to the flat _Duplicates folder
        flat = os.path.join(cfg["library"], "_Duplicates")
        for it in items.values():
            if (it.get("dup_flat") or (cfg.get("dup_place") == "flat" and it.get("dup_keep"))) and it.get("dup_name") and it["kind"] != "skip":
                it.setdefault("dup_orig_folder", it["folder"])
                it["folder"] = flat
                it["notes"].append("extra copy: placed in the flat _Duplicates folder")
    finalize_names(items)
    n_g, n_x, mb_x = write_duplicates(st, dup_groups, inv_by_id)
    if n_g:
        say(f"Duplicates: {n_g:,} groups, {n_x:,} extra copies not copied ({mb_x / 1000:.1f} GB saved) - see duplicates.csv")
    for it in items.values():   # a re-check that changes nothing is not a proposal
        if it.get("action") == "relocate" and same_path(it["new_path"], it["current_path"]):
            it.update(action="keep", approved=False, fixed=True, review=None, new_path=it["current_path"])
    rel = [it for it in items.values() if it.get("action") == "relocate"]
    if rel:
        g = defaultdict(list)
        for it in rel:
            g[it["review"][1]].append(it)
        ask_grouped(decisions, "recheck", "Improvements for already organized files",
                    {k: f"{v[0]['review'][2]}: {len(v)} files, e.g. {os.path.basename(v[0]['current_path'])} -> "
                        f"{os.path.basename(v[0]['new_path'])}" for k, v in g.items()},
                    {"a": "pply (moves the library copy)", "l": "eave as is"}, "l")
        for it in rel:
            it["approved"] = decisions["recheck"].get(it["review"][1]) == "a"
        # a new file blocked only because an approved move frees its place: it may go ahead
        freed = {os.path.normcase(it["current_path"]) for it in rel if it["approved"]}
        for it in items.values():
            if not it["approved"] and it.get("reason") == "a file with this name already exists in the library" \
                    and os.path.normcase(it.get("new_path", "")) in freed:
                it["approved"], it["reason"] = True, ""
    st.save("decisions.json", decisions)

    plan = []
    for fid in sorted(items):
        it = items[fid]
        r = inv_by_id[fid]
        it["new_tags"] = plan_tags(it)
        if it["kind"] == "skip":
            it["action"] = "skip"
        elif it.get("action") not in ("relocate", "keep"):
            it["action"] = "dup" if it.get("dup_name") else \
                ("copy" if os.path.basename(it.get("new_path", "")) == r["filename"] else "rename")
        plan.append(it)
    keep_mine = UI.keep_tags_ids() if UI is not None and hasattr(UI, "keep_tags_ids") else set()
    for it in plan:                       # Neat Picky: how close the new tags are to what the file had
        if it["file_id"] in keep_mine and it.get("new_tags"):    # 'Keep my tags' in the app: placed, but tags unchanged
            it["proposed_tags"], it["new_tags"] = it["new_tags"], {}
            it.setdefault("notes", []).append("your own tags kept (Neat Picky)")
        it["tag_match"], it["match_percent"] = tag_match(inv_by_id[it["file_id"]]["tags"], it.get("new_tags") or {}, inv_by_id[it["file_id"]].get("filename", ""))
    auto_gate(st, plan, inv_by_id)
    st.save("plan.json", plan)
    rows = [{"file_id": it["file_id"], "source_path": it["src"], "new_path": it.get("new_path", ""),
             "match_percent": it["match_percent"],
             "old_tags": tag_str({k: inv_by_id[it["file_id"]]["tags"].get(k) for k in
                                  ("artist", "albumartist", "album", "title", "track", "disc", "year", "genre")}),
             "new_tags": tag_str(it["new_tags"]), "action": it["action"], "data_source": it.get("data_source", ""),
             "confidence": it.get("confidence", ""), "approved": "yes" if it["approved"] else "no",
             "needs_review": "no" if (it["approved"] or it.get("fixed") or it.get("dup_extra")) else "yes", "reason": it.get("reason", "")}
            for it in plan]
    st.retire("music_changes.csv")
    write_csv(st.p("music_changes.csv"), CHANGE_COLS, rows)
    st.retire("needs_review.csv")
    write_csv(st.p("needs_review.csv"), CHANGE_COLS, [r for r in rows if r["needs_review"] == "yes"])
    write_plan_report(st, cfg, plan, inv_by_id, dup_groups)
    notify(f"Phase 2 finished - {sum(1 for r in rows if r['needs_review'] == 'yes'):,} files wait for review")


def write_analysis(st, cfg, items, tier_stats, mb):
    """Analyze: how much of each artist (complete studio albums) and of each album (tracks) you own.
    Writes collection_analysis.xlsx (Artists / Albums / Almost complete) + analysis.json for the app. Read-only."""
    lib = cfg["library"]
    artists = defaultdict(lambda: {"songs": set(), "releases": set()})
    albums = {}
    for it in items.values():
        if it["kind"] not in ("release", "singles", "artist_unverified") or not it.get("artist_folder"):
            continue
        a = it["artist_folder"]
        # a song counts once, however many copies you have (copies are found later, in the duplicates step)
        artists[a]["songs"].add(it.get("recording_id") or (it.get("release_id"), str(it.get("disc") or "1"), str(it.get("track") or ""))
                                if it.get("release_id") and it.get("track") else ("t", title_key(neutral(it.get("title") or ""))))
        if it["kind"] != "release" or not it.get("release_id"):
            continue
        rid = it["release_id"]
        artists[a]["releases"].add(rid)
        al = albums.setdefault((a, rid), {"artist": a, "release_id": rid, "rtype": it.get("rtype") or "Album",
                                           "name": it.get("album") or os.path.basename(it.get("folder") or ""),
                                           "year": it.get("year") or "", "total": it.get("ntracks") or 0, "have": set()})
        if str(it.get("track", "")).isdigit():
            al["have"].add((str(it.get("disc") or "1"), str(int(it["track"]))))
    # where else in the library is a song? (for missing tracks: same recording first, then same title)
    by_rec, by_title = {}, {}
    for it in items.values():
        if it["kind"] in ("release", "singles") and it.get("artist_folder"):
            where = f"{os.path.basename(it.get('folder') or '')}" + (f" (track {it['track']})" if it.get("track") else "")
            if it.get("recording_id"):
                by_rec.setdefault(it["recording_id"], (where, it["file_id"]))
            by_title.setdefault((norm_key(it["artist_folder"]), title_key(it.get("title"))), (where, it["file_id"]))
    alb_rows, almost = [], []
    for al in albums.values():
        have, tot = len(al["have"]), al["total"]
        pct = round(100 * min(have, tot) / tot) if tot else None
        missing = ""
        if tot and 0 < tot - have <= 2 and tot >= 3:
            names, elsewhere, helpers = [], [], []
            if mb and re.fullmatch(r"[0-9a-f-]{36}", al["release_id"]):
                try:
                    rel = mb.release(al["release_id"]) or {}
                except RuntimeError:
                    rel = {}
                multi = len(rel.get("media") or []) > 1
                for m in rel.get("media") or []:
                    for t in m.get("tracks") or []:
                        pos = (str(m.get("position") or 1), str(t.get("position") or ""))
                        if pos not in al["have"]:
                            label = (f"{pos[0] + '-' if multi else ''}{int(pos[1]):02d} {t.get('title', '')}"
                                     if pos[1].isdigit() else t.get("title", ""))
                            names.append(label)
                            rec = (t.get("recording") or {}).get("id")
                            h_ = {"label": label, "title": t.get("title", ""), "disc": pos[0], "track": pos[1],
                                  "length": round(((t.get("length") or 0) / 1000)), "recording_id": rec or ""}
                            if rec and rec in by_rec:
                                elsewhere.append(f"{label}: same recording on {by_rec[rec][0]}")
                                h_.update(where=by_rec[rec][0], src=by_rec[rec][1], same=True)
                            elif (norm_key(al["artist"]), title_key(t.get("title"))) in by_title:
                                w_ = by_title[(norm_key(al["artist"]), title_key(t.get("title")))]
                                elsewhere.append(f"{label}: another version on {w_[0]}")
                                h_.update(where=w_[0], src=w_[1], same=False)
                            helpers.append(h_)
            missing = ", ".join(names) or f"{tot - have} songs"
            almost.append({"artist": al["artist"], "album": al["name"], "have": have, "total": tot, "missing": missing,
                           "you_have_it_on": "; ".join(elsewhere), "release_id": al["release_id"], "tracks": helpers})
        alb_rows.append({"artist": al["artist"], "album": al["name"], "type": al["rtype"], "year": al["year"], "release_id": al["release_id"],
                         "tracks_owned": have, "tracks_total": tot or "", "percent": "" if pct is None else pct,
                         "complete": "yes" if tot and have >= tot else "", "missing": missing})
    art_rows = []
    for a, d in artists.items():
        tier, done, total, pct = tier_stats.get(a, (TIER_UNK, 0, 0, None))
        art_rows.append({"artist": a, "tier": tier.split(" ", 1)[1] if " " in tier else tier,
                         "studio_complete": done, "studio_total": total or "",
                         "percent": "" if pct is None else round(pct * 100),
                         "songs": len(d["songs"]), "releases": len(d["releases"]),
                         "complete_releases": sum(1 for r in alb_rows if r["artist"] == a and r["complete"])})
    art_rows.sort(key=lambda r: (-(r["percent"] or 0), -r["songs"], r["artist"].lower()))
    alb_rows.sort(key=lambda r: (r["artist"].lower(), str(r["year"]), r["album"].lower()))
    almost.sort(key=lambda r: (r["total"] - r["have"], r["artist"].lower()))
    # the summary counts real albums only (studio albums, EPs, live albums, soundtracks) - not compilations or singles
    real = [r for r in alb_rows if r["type"] not in ("Comp", "Box", "Single")]
    real_names = {(r["artist"], r["album"]) for r in real}
    known = [r["percent"] for r in real if r["percent"] != ""]
    summary = {"artists": len(art_rows), "songs": sum(r["songs"] for r in art_rows), "releases": len(real),
               "all_releases": len(alb_rows), "complete_releases": sum(1 for r in real if r["complete"]),
               "average_release_percent": round(sum(known) / len(known)) if known else 0,
               "almost_complete": sum(1 for x in almost if (x["artist"], x["album"]) in real_names),
               "tiers_known": any(r["studio_total"] for r in art_rows)}
    st.save("analysis.json", {"made": now(), "summary": summary, "artists": art_rows, "albums": alb_rows, "almost": almost})
    name = "collection_analysis.xlsx"
    st.retire(name)
    if openpyxl:
        wb = openpyxl.Workbook()
        for idx, (title, cols, rows) in enumerate([
                ("Artists", ["artist", "tier", "studio_complete", "studio_total", "percent", "songs", "releases",
                             "complete_releases"], art_rows),
                ("Albums", ["artist", "album", "type", "year", "tracks_owned", "tracks_total", "percent", "complete",
                            "missing"], alb_rows),
                ("Almost complete", ["artist", "album", "have", "total", "missing", "you_have_it_on"], almost)]):
            ws = wb.active if idx == 0 else wb.create_sheet()
            ws.title = title
            ws.append(cols)
            for c in ws[1]:
                c.font = Font(bold=True)
            for r in rows:
                ws.append([r.get(k, "") for k in cols])
            ws.freeze_panes = "A2"
            for i, k in enumerate(cols, 1):
                ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 44 if k in ("artist", "album", "missing", "you_have_it_on") else 14
        wb.save(lp(st.p(name)))
    else:
        write_csv(st.p("collection_analysis.csv"), list(alb_rows[0]) if alb_rows else ["artist"], alb_rows)
    hr("Analyze")
    say(f" {summary['artists']:,} artists | {summary['releases']:,} releases | {summary['complete_releases']:,} complete | "
        f"average {summary['average_release_percent']}% of each release")
    for r in art_rows[:5]:
        if r["studio_total"]:
            say(f"   {r['artist'][:40]:40} {r['studio_complete']} of {r['studio_total']} studio albums ({r['percent']}%)")
    if almost:
        say(f" Almost complete ({len(almost)}): " + "; ".join(f"{a['album']} needs {a['missing']}" for a in almost[:3])[:300])
    say(f" Full analysis: {st.p(name)}")


TAG_WEIGHTS = {"artist": 3, "title": 3, "album": 2, "year": 1, "track": 1, "genre": 0.5}


def tag_match(old, new, fname=""):
    """Per-field and overall similarity (0-100) between the file's tags and the planned tags. A field the plan does
    not set keeps its value (100). Track '3' vs '3/12' and year '1976-02-01' vs '1976' count as the same."""
    per, tot, wsum = {}, 0.0, 0.0
    for k, w in TAG_WEIGHTS.items():
        a, b = str(old.get(k) or "").strip(), str(new.get(k) or "").strip()
        if not b or a == b:
            pct = 100
        elif not a and k == "title" and fname:
            a = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", str(fname)).strip()      # V2.0.6: no title tag -> compare the FILE NAME ("09 Regrets (Duet with ...)" is not "Regrets")
            pct = round(100 * max(ratio(a, b), ratio(neutral(a), neutral(b)), same_song_title(a, b)))
            pct = min(pct, 99)
        elif not a:
            per[k] = None              # the file had nothing here: 'added', not a disagreement
            continue
        elif k == "track":
            pct = 100 if a.split("/")[0].lstrip("0") == b.split("/")[0].lstrip("0") else 0
        elif k == "year":
            pct = 100 if a[:4] == b[:4] else (max(0, 100 - 10 * abs(int(a[:4]) - int(b[:4])))
                                              if a[:4].isdigit() and b[:4].isdigit() else 0)
        else:
            pct = round(100 * max(ratio(a, b), ratio(neutral(a), neutral(b)), same_song_title(a, b) if k == "title" else 0))
            if pct >= 100:                 # V2.0.5: 100% only when the text is really the same (a different spelling, a remaster label
                pct = 99                   # or a different case is "almost", never "100% match")
        per[k] = pct
        tot += w * pct
        wsum += w
    overall = round(tot / wsum) if wsum else 0
    if overall >= 100 and any(v is not None and v < 100 for v in per.values()):
        overall = 99
    return per, overall


def write_plan_report(st, cfg, plan, inv_by_id, dup_groups):
    go = [it for it in plan if it["approved"] and it["action"] != "keep"]
    size = sum(inv_by_id[it["file_id"]]["size"] for it in go if it["action"] != "relocate")
    probe = cfg["library"]
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe.rstrip("\\/"))
        probe = parent if parent != probe else ""
    free = shutil.disk_usage(probe).free if probe else 0
    kinds = Counter(it["kind"] for it in go)
    rtypes = Counter(it.get("rtype") for it in go if it["kind"] == "release")
    # same song in different folders (kept, only reported)
    where = defaultdict(set)
    for it in plan:
        if it["kind"] in ("release", "singles") and (it["approved"] or it.get("fixed")):
            key = it.get("recording_id") or f"{norm_key(it.get('artist_folder'))}|{title_key(it.get('title'))}"
            where[key].add(os.path.dirname(it.get("new_path", "")))
    cross = {k: v for k, v in where.items() if len(v) > 1}
    folders = defaultdict(list)
    for it in go:
        if it["kind"] == "release":
            folders[it["folder"]].append(it)
    incomplete = []
    for f, its in folders.items():
        per_disc = {str(i["disc"]): i["tracktotal"] for i in its}
        tot = sum(int(x) for x in per_disc.values() if str(x).isdigit())
        have = len({(i["disc"], i["track"]) for i in its})
        if tot and have < tot:
            incomplete.append((f, have, tot))
    short = [it for it in go if "path shortened" in it.get("notes", [])]
    st.retire("music_plan_report.md")
    L = [f"# Proposed changes  ({now()})", "",
         f"- Files to copy: **{sum(1 for it in go if it['action'] != 'relocate'):,}** ({human(size)}) - free space: {human(free)}",
         f"- Library copies to move (re-check): {sum(1 for it in go if it['action'] == 'relocate'):,}",
         "- " + " | ".join(f"{k}: {v:,}" for k, v in kinds.most_common()),
         "- Release folders by type: " + ", ".join(f"{k or 'Album'} {v:,}" for k, v in rtypes.most_common()),
         f"- Waiting for your review: {sum(1 for it in plan if not it['approved'] and not it.get('fixed') and not it.get('dup_extra') and it['kind'] != 'skip'):,}",
         f"- Extra copies of the same song, not copied (duplicates.csv): {sum(1 for it in plan if it.get('dup_extra')):,}",
         f"- Skipped (corrupt): {sum(1 for it in plan if it['kind'] == 'skip'):,}", "",
         "## Duplicate groups (best to worst; FLAC + MP3 both kept; extras not copied unless you include them)", ""]
    for g in dup_groups[:500]:
        L.append("- " + "  |  ".join(f"{'KEPT' if not it.get('dup_extra') else 'not copied'}: "
                                     f"`{os.path.basename(it.get('new_path', '') or it['src'])}` ({inv_by_id[it['file_id']]['ext'][1:]} "
                                     f"{inv_by_id[it['file_id']].get('bitrate', 0)} kbps"
                                     f"{', identical audio' if it.get('dup_identical') else ''})" for it in g))
    L += ["", "## Same song in several folders (all kept)", ""]
    for k, v in list(cross.items())[:500]:
        L.append("- " + "  |  ".join(sorted(os.path.relpath(x, cfg["library"]) for x in v)))
    tiers = st.load("tier_stats.json", {})
    if tiers:
        L += ["", "## Collection tiers (complete studio albums / all studio albums)", ""]
        order = [TIER_GOLD, TIER_GETTO, TIER_START, TIER_SCAT, TIER_UNK, TIER_CLASSICAL]
        for name, (tier, done, total, pct) in sorted(tiers.items(), key=lambda x: (order.index(x[1][0]) if x[1][0] in order else len(order), x[0].lower())):
            L.append(f"- **{tier}** - {name}: " + (f"{done} of {total} ({pct * 100:.0f}%)" if total else "discography unknown"))
    L += ["", "## Incomplete releases", ""]
    for f, have, tot in sorted(incomplete):
        L.append(f"- {os.path.relpath(f, cfg['library'])}: {have} of {tot} tracks")
    L += ["", "## Shortened names (255-character limit)", ""]
    for it in short[:300]:
        L.append(f"- `{it['new_path']}`")
    with open(lp(st.p("music_plan_report.md")), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    hr("Proposal summary")
    say(f" Will copy {sum(1 for it in go if it['action'] != 'relocate'):,} files ({human(size)}); free space: {human(free)}"
        + ("   <-- NOT ENOUGH SPACE" if free and size > free else ""))
    say("   " + " | ".join(f"{k} {v:,}" for k, v in kinds.most_common()))
    if tiers:
        tc = Counter(v[0] for v in tiers.values())
        say("   artists by tier: " + " | ".join(f"{t.split(' ', 1)[1]} {tc[t]}" for t in
                                              (TIER_GOLD, TIER_GETTO, TIER_START, TIER_SCAT, TIER_UNK) if tc[t]))
    say(f"   duplicate groups {len(dup_groups):,} | same song in several folders {len(cross):,} | "
        f"incomplete releases {len(incomplete):,} | shortened names {len(short):,}")
    say(f"   extra copies not copied {sum(1 for it in plan if it.get('dup_extra')):,} (duplicates.csv)  |  "
        f"waiting for review {sum(1 for it in plan if not it['approved'] and not it.get('fixed') and not it.get('dup_extra') and it['kind'] != 'skip'):,}"
        "  (needs_review.csv)")
    say(f"\n Full plan: {st.p('music_changes.csv')}\n Report   : {st.p('music_plan_report.md')}")
    say(" Nothing has been changed. When you are happy, run Phase 3 and answer  y")


# ----------------------------------------------------------------------------- Phase 3: tags, covers, lyrics

JUNK_TAG_RE = re.compile(r"(https?://|www\.|\.com\b|\.ir\b|\.net\b|\.org\b|download|telegram|t\.me/|@\w{3,}|instagram)", re.I)


def _id3_text(cls, val):
    return cls(encoding=1, text=[str(val)])


def write_dup_comment(path, ext, text="DUPLICATE"):
    """V2.0.3 (Amin): an exactly identical extra copy gets a removable Comment tag even when its other tags are left alone
    (song not confirmed, or 'Keep my tags'). Writes the COPY only; nothing else in the file changes. Clear the Comment to remove it."""
    f = mutagen.File(lp(path))
    if f is None:
        raise RuntimeError("mutagen cannot open the copy")
    if isinstance(f, MP4):
        f["\xa9cmt"] = [text]
    elif isinstance(f, ASF):
        f["Description"] = [text]
    elif ext in (".mp3", ".wav", ".aiff", ".aif") or getattr(f, "tags", None) is None and ext in (".mp3",):
        if f.tags is None:
            f.add_tags()
        f.tags.delall("COMM")
        f.tags.add(COMM(encoding=1, lang="eng", desc="", text=[text]))
    elif isinstance(f, FLAC) or hasattr(f, "tags"):
        if f.tags is None:
            f.add_tags()
        f["COMMENT"] = [text]
    else:
        return False
    f.save()
    return True


def write_tags(path, ext, nt, cover=None, replace_cover=False, lyrics=""):
    """Write tags to the COPY only (confirmed songs). Returns a list of what was removed as junk."""
    removed = []
    if ext == ".aac":
        return ["raw AAC cannot hold tags; copied without tag changes"]
    f = mutagen.File(lp(path))
    if f is None:
        raise RuntimeError("mutagen cannot open the copy")
    if ext in (".mp3", ".wav", ".aiff", ".aif", ".m4a", ".m4b", ".flac", ".wma"):   # v2.0: trust what the file really is, not its extension
        real = ".m4a" if isinstance(f, MP4) else ".flac" if isinstance(f, FLAC) else ".wma" if isinstance(f, ASF) else None
        if real and real != ext and not (real == ".m4a" and ext == ".m4b"):
            ext = real
    trk = f"{nt['track']}/{nt['tracktotal']}" if nt.get("track") and nt.get("tracktotal") else nt.get("track", "")
    dsc = f"{nt['disc']}/{nt['disctotal']}" if nt.get("disc") and nt.get("disctotal") else nt.get("disc", "")
    artists = [a for a in nt.get("artists") or [] if a]
    if ext in (".mp3", ".wav", ".aiff", ".aif"):
        if f.tags is None:
            f.add_tags()
        t = f.tags
        for cls, val in ((TPE1, nt["artist"]), (TPE2, nt["albumartist"]), (TALB, nt["album"]), (TIT2, nt["title"]),
                         (TRCK, trk), (TPOS, dsc), (TDRC, nt["year"]), (TCON, nt["genre"])):
            if val:
                t.setall(cls.__name__, [_id3_text(cls, val)])
        if artists:
            t.delall("TXXX:ARTISTS")
            t.add(TXXX(encoding=1, desc="ARTISTS", text=artists))
        if nt.get("composer"):
            t.setall("TCOM", [_id3_text(TCOM, nt["composer"])])
        if nt.get("dup_comment"):
            t.delall("COMM")
            t.add(COMM(encoding=1, lang="eng", desc="", text=[nt["dup_comment"]]))
        if nt.get("original_release"):
            t.delall("TXXX:ORIGINAL RELEASE")
            t.add(TXXX(encoding=1, desc="ORIGINAL RELEASE", text=[nt["original_release"]]))
        if nt["compilation"]:
            t.setall("TCMP", [_id3_text(TCMP, "1")])
        for fr in list(t.values()):
            fid = fr.FrameID
            txt = " ".join(str(x) for x in getattr(fr, "text", []) or []) + " " + str(getattr(fr, "url", "") or "")
            if fid.startswith("W") or fid == "TENC" or (fid in ("COMM", "TXXX") and JUNK_TAG_RE.search(txt)
                                                       and getattr(fr, "desc", "") not in ("ARTISTS", "ORIGINAL RELEASE")):
                removed.append(f"{fid}: {txt.strip()[:60]}")
                t.delall(fr.HashKey)
        if cover and (replace_cover or not t.getall("APIC")):
            t.delall("APIC")
            t.add(APIC(encoding=1, mime=image_mime(cover), type=3, desc="Cover", data=cover))
        if lyrics:
            t.delall("USLT")
            t.add(USLT(encoding=1, lang="eng", desc="", text=lyrics))
        f.save(v2_version=3, v23_sep="; ")
    elif ext in (".m4a", ".m4b"):
        if f.tags is None:
            f.add_tags()
        t = f.tags
        if artists:
            t["\xa9ART"] = artists
            t["----:com.apple.iTunes:ARTISTS"] = [a.encode("utf-8") for a in artists]
        elif nt["artist"]:
            t["\xa9ART"] = [nt["artist"]]
        for k, val in (("aART", nt["albumartist"]), ("\xa9alb", nt["album"]), ("\xa9nam", nt["title"]),
                       ("\xa9day", nt["year"]), ("\xa9gen", nt["genre"])):
            if val:
                t[k] = [str(val)]
        if str(nt.get("track")).isdigit():
            t["trkn"] = [(int(nt["track"]), int(nt["tracktotal"]) if str(nt.get("tracktotal")).isdigit() else 0)]
        if str(nt.get("disc")).isdigit():
            t["disk"] = [(int(nt["disc"]), int(nt["disctotal"]) if str(nt.get("disctotal")).isdigit() else 0)]
        if nt["compilation"]:
            t["cpil"] = True
        if nt.get("composer"):
            t["\xa9wrt"] = [nt["composer"]]
        if nt.get("dup_comment"):
            t["\xa9cmt"] = [nt["dup_comment"]]
        if nt.get("original_release"):
            t["----:com.apple.iTunes:ORIGINAL RELEASE"] = [nt["original_release"].encode("utf-8")]
        for k in list(t.keys()):
            vals = " ".join(str(v) for v in (t[k] if isinstance(t[k], list) else [t[k]]))
            if k in ("\xa9cmt", "\xa9too", "desc") or (k.startswith("----") and "ARTISTS" not in k
                                                         and "ORIGINAL RELEASE" not in k):
                if k == "\xa9too" or JUNK_TAG_RE.search(vals):
                    removed.append(f"{k}: {vals[:60]}")
                    del t[k]
        if cover and (replace_cover or not t.get("covr")):
            fmt = MP4Cover.FORMAT_PNG if image_mime(cover) == "image/png" else MP4Cover.FORMAT_JPEG
            t["covr"] = [MP4Cover(cover, imageformat=fmt)]
        if lyrics:
            t["\xa9lyr"] = [lyrics]
        f.save()
    elif ext == ".wma":
        t = f.tags
        if artists:
            t["Author"] = artists
            t["ARTISTS"] = artists
        for k, val in (("WM/AlbumArtist", nt["albumartist"]), ("WM/AlbumTitle", nt["album"]), ("Title", nt["title"]),
                       ("WM/TrackNumber", nt["track"]), ("WM/PartOfSet", dsc), ("WM/Year", nt["year"]),
                       ("WM/Genre", nt["genre"])):
            if val:
                t[k] = [str(val)]
        if nt["compilation"]:
            t["WM/IsCompilation"] = ["1"]
        if nt.get("original_release"):
            t["ORIGINAL RELEASE"] = [nt["original_release"]]
        for k in list(t.keys()):
            vals = " ".join(str(getattr(v, "value", v)) for v in t[k])
            if k in ("Description", "WM/URL", "WM/AuthorURL", "WM/PromotionURL", "WM/EncodedBy") and \
                    (k != "Description" or JUNK_TAG_RE.search(vals)):
                removed.append(f"{k}: {vals[:60]}")
                del t[k]
        if lyrics:
            t["WM/Lyrics"] = [lyrics]
        f.save()
    else:  # FLAC / Ogg Vorbis / Opus
        if f.tags is None:
            f.add_tags()
        if artists:
            f["ARTIST"] = artists
            f["ARTISTS"] = artists
        elif nt["artist"]:
            f["ARTIST"] = [nt["artist"]]
        for k, val in (("ALBUMARTIST", nt["albumartist"]), ("ALBUM", nt["album"]), ("TITLE", nt["title"]),
                       ("TRACKNUMBER", nt["track"]), ("TRACKTOTAL", nt["tracktotal"]), ("DISCNUMBER", nt["disc"]),
                       ("DISCTOTAL", nt["disctotal"]), ("DATE", nt["year"]), ("GENRE", nt["genre"])):
            if val:
                f[k] = [str(val)]
        if nt["compilation"]:
            f["COMPILATION"] = ["1"]
        if nt.get("composer"):
            f["COMPOSER"] = [nt["composer"]]
        if nt.get("dup_comment"):
            f["COMMENT"] = [nt["dup_comment"]]
        if nt.get("original_release"):
            f["ORIGINALRELEASE"] = [nt["original_release"]]
        for k in list(f.keys()):
            vals = " ".join(f[k])
            kl = k.lower()
            if kl in ("url", "www", "website", "purchaseurl", "encoded-by", "encodedby", "encoder_settings") or \
                    (kl in ("comment", "description") and JUNK_TAG_RE.search(vals)):
                removed.append(f"{k}: {vals[:60]}")
                del f[k]
        if cover:
            w, h = image_size(cover)
            pic = Picture()
            pic.type, pic.mime, pic.desc, pic.data, pic.width, pic.height, pic.depth = \
                3, image_mime(cover), "Cover", cover, w, h, 24
            if isinstance(f, FLAC):
                if replace_cover or not f.pictures:
                    f.clear_pictures()
                    f.add_picture(pic)
            elif replace_cover or not f.get("metadata_block_picture"):
                f["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]
        if lyrics:
            f["LYRICS"] = [lyrics]
        f.save()
    return removed


def fit_cover(b):
    """Keep covers between 500 and 1000 px (downscale bigger ones). Returns bytes or None."""
    if not b:
        return None
    w, h = image_size(b)
    if min(w, h) and min(w, h) < 500:
        return None
    if max(w, h) <= 1000 and image_mime(b) == "image/jpeg":
        return b
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(b)).convert("RGB")
        im.thumbnail((1000, 1000))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return b if max(w, h) <= 1600 else None


def http_bytes(url, token=""):
    hdr = {"User-Agent": f"MusicLibraryManager/{VERSION}"}
    if token and "discogs" in url:
        hdr["Authorization"] = f"Discogs token={token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30) as r:
            return r.read()
    except Exception:
        return b""


def get_cover(st, cfg, alt, it):
    """Deezer -> Apple Music -> Cover Art Archive -> Discogs, same release only. Cached per release."""
    key = re.sub(r"[^\w.-]", "_", f"{it.get('group_id')}_{it.get('release_year')}_{it.get('edition', '')}")[:150]
    cache = os.path.join(st.logs, "covers")
    os.makedirs(lp(cache), exist_ok=True)
    fp = os.path.join(cache, key + ".img")
    if exists(fp):
        with open(lp(fp), "rb") as fh:
            b = fh.read()
        return b or None
    b = None
    disc_url = it.get("cover_url") if it.get("data_source") == "Discogs" else ""
    for src, url in alt.cover_candidates(it.get("credited") or it.get("artist_folder"), it.get("album"),
                                         it.get("release_year") or it.get("year"), it.get("mbid"), disc_url):
        b = fit_cover(http_bytes(url, cfg.get("discogs_token", "")))
        if b:
            it["notes"].append(f"cover from {src}")
            break
    with open(lp(fp), "wb") as fh:
        fh.write(b or b"")
    return b


def save_lyrics():
    """Save the lyrics cache now (shared _cache folder). Safe to call from several threads."""
    if not hasattr(get_lyrics, "c"):
        return
    with get_lyrics.lock:
        get_lyrics.saved = time.time()
        snap = dict(get_lyrics.c)
    get_lyrics.shared.save("lyrics_cache.json", snap)


def get_lyrics(st, it, duration, fetch=True, save=True):
    if not hasattr(get_lyrics, "c"):
        get_lyrics.shared = SharedCache(st)          # one lyrics cache for every library, like the lookups
        get_lyrics.c = get_lyrics.shared.load("lyrics_cache.json")
        get_lyrics.lock = threading.Lock()
    cache = get_lyrics.c
    if not fetch:
        return ""
    q = {"artist_name": it.get("credited") or "", "track_name": re.sub(r"\s*\(feat\.[^)]*\)", "", it["title"]),
         "album_name": it.get("album") or "", "duration": str(int(duration or 0))}
    url = "https://lrclib.net/api/get?" + urllib.parse.urlencode(q)
    if url not in cache:
        txt = ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"MusicLibraryManager/{VERSION}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            txt = d.get("plainLyrics") or re.sub(r"^\[\d+:\d+(?:\.\d+)?\]\s?", "", d.get("syncedLyrics") or "", flags=re.M)
        except Exception:
            txt = ""
        cache[url] = txt
        if time.time() - getattr(get_lyrics, "saved", 0) > 60:     # at most once a minute, also while prefetching
            save_lyrics()
    return cache[url]


def prov_rows(st, inv_by_id, plan):
    rows = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    for it in plan:
        r = inv_by_id.get(it["file_id"])
        if not r:
            continue
        row = rows.get(it["file_id"])
        if row and row.get("status") in ("copied", "verified", "original_archived"):
            continue
        t = r["tags"]
        rows[it["file_id"]] = {
            "file_id": it["file_id"], "original_full_path": r["path"], "original_filename": r["filename"],
            "orig_artist": t.get("artist"), "orig_album": t.get("album"), "orig_title": t.get("title"),
            "orig_track": t.get("track"), "orig_year": t.get("year"), "sha256_hash": r.get("sha256"),
            "audio_stream_hash": r.get("audio_hash"), "new_full_path": "", "new_filename": "",
            "compilation_name": it.get("album", "") if it.get("compilation") else "",
            "original_track_number": it.get("track", "") if it.get("compilation") else "",
            "confidence": it.get("confidence", ""), "data_source": it.get("data_source", ""), "date_processed": "",
            "final_original_path": "", "final_original_filename": "",
            "status": "skipped" if it["kind"] == "skip" else ("" if it["approved"] else "needs_review"),
            "notes": it.get("reason", "")}
    return rows


def save_prov(st, rows, backup=True):
    data = [rows[k] for k in sorted(rows)]
    write_csv(st.p("music_provenance.csv"), PROV_COLS, data)
    if backup:
        shutil.copy2(lp(st.p("music_provenance.csv")),
                     lp(os.path.join(st.backups, f"music_provenance_{stamp()}_{int(time.time() * 1000) % 1000:03d}.csv")))
    try:
        write_xlsx(st.p("music_provenance.xlsx"), PROV_COLS, data)
    except PermissionError:
        say("   (music_provenance.xlsx is open in Excel - the CSV was saved; the xlsx will update next time)")


def read_text_any(path):
    raw = open(lp(path), "rb").read()
    for enc in ("utf-8-sig", "cp1256", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def rebuild_playlists(st, cfg, rows):
    pls = st.load("playlists.json", [])
    if not pls:
        return 0
    m = {}
    for r in rows.values():
        if r.get("new_full_path") and r.get("status") in ("verified", "copied", "original_archived"):
            m[os.path.normcase(os.path.abspath(r["original_full_path"]))] = r["new_full_path"]
    out_dir = os.path.join(cfg["library"], "_Playlists")
    os.makedirs(lp(out_dir), exist_ok=True)
    made = 0
    for pl in pls:
        if not exists(pl):
            continue
        lines, hit = ["#EXTM3U"], 0
        for line in read_text_any(pl).splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                if s.startswith("#EXTINF"):
                    lines.append(s)
                continue
            p = s if os.path.isabs(s) else os.path.join(os.path.dirname(pl), s)
            new = m.get(os.path.normcase(os.path.abspath(p)))
            if new:
                lines.append(new)
                hit += 1
            else:
                lines.append(f"# not in the new library: {s}")
        if not hit:
            continue
        name = sanitize(os.path.splitext(os.path.basename(pl))[0]) + ".m3u8"
        dest = os.path.join(out_dir, name)
        body = "\n".join(lines) + "\n"
        n = 2
        while exists(dest):
            if read_text_any(dest) == body:
                break
            dest = os.path.join(out_dir, suffixed(name, n))
            n += 1
        else:
            with open(lp(dest), "w", encoding="utf-8") as fh:
                fh.write(body)
            made += 1
    return made


def write_split_playlists(st, cfg, rows):
    """V2.0.3 decisions 6 + 25: a compilation whose songs were placed on their original albums keeps a playlist
    <library>\\_Playlists\\<compilation>.m3u8 with RELATIVE paths, in the compilation's own order. Never overwrites a different file."""
    plan = st.load("plan.json", [])
    inv = {r["id"]: r for r in st.cached("inventory.json", [])}
    groups = defaultdict(list)
    for it in plan:
        name = it.get("compilation_name")
        row = rows.get(it["file_id"]) or {}
        if name and row.get("new_full_path") and row.get("status") in ("verified", "copied", "original_archived"):
            groups[(norm_key(it.get("original_release", "").split(" (")[0]) or norm_key(name), name)].append((it, row))
    out_dir = os.path.join(cfg["library"], "_Playlists")
    made = 0
    for (_, name), lst in groups.items():
        if len(lst) < 2:
            continue
        os.makedirs(lp(out_dir), exist_ok=True)

        def order(x):
            t = (inv.get(x[0]["file_id"]) or {}).get("tags") or {}
            m_ = re.search(r"track (?:(\d+)-)?(\d+)", x[0].get("original_release") or "")
            if m_:
                return (int(m_.group(1) or 1), int(m_.group(2)))
            d, n = str(t.get("disc") or "1").split("/")[0], str(t.get("track") or "0").split("/")[0]
            return (int(d) if d.isdigit() else 1, int(n) if n.isdigit() else 0)
        lines = ["#EXTM3U"]
        for it, row in sorted(lst, key=order):
            rel = os.path.relpath(row["new_full_path"], out_dir).replace("\\", "/")
            lines.append(f"#EXTINF:{int(it.get('duration') or 0)},{it.get('display_artist', '')} - {it.get('title', '')}")
            lines.append(rel)
        body = "\n".join(lines) + "\n"
        dest = os.path.join(out_dir, sanitize(name) + ".m3u8")
        n = 2
        while exists(dest) and read_text_any(dest) != body:
            dest = os.path.join(out_dir, suffixed(sanitize(name) + ".m3u8", n))
            n += 1
        if not exists(dest):
            with open(lp(dest), "w", encoding="utf-8") as fh:
                fh.write(body)
            made += 1
    return made


def copy_fail_entry(src, row, why, busy=False):
    """One line of the 'Not copied' list: what failed, in plain words, and what to do about it (1.1.7)."""
    w = (why or "").lower()
    if busy or "winerror 32" in w or "being used by another process" in w or "permission denied" in w or "winerror 5" in w:
        code, plain = "in_use", "Another program had the file open (a player, antivirus, Explorer preview or cloud sync)."
        guide = "Close players and the Explorer preview pane, pause cloud sync / antivirus scanning for the folder, then press Retry. Only these files are copied again."
    elif "destination already exists" in w or "destination appeared" in w:
        code, plain = "exists", "A file with the new name is already in the library (never overwritten)."
        guide = "Open Duplicates to see if it is the same song. If it is, nothing more to do. If not, change the title or edition in Review and press Retry."
    elif "original changed" in w:
        code, plain = "changed", "The original changed after the scan."
        guide = "Run Scan again, then Copy & tag."
    elif "audio of the copy differed" in w:
        code, plain = "audio_diff", "The copy did not sound identical to the original, so it was set aside in _undone."
        guide = "Press Retry. If it fails again the file may be damaged: play the original and tell me which song it is."
    elif "no space" in w or "winerror 112" in w:
        code, plain = "disk_full", "The library drive is full."
        guide = "Free some space on the library drive, then press Retry."
    elif "path" in w and ("too long" in w or "winerror 206" in w or "winerror 3" in w):
        code, plain = "path", "The new path is too long or a folder could not be made."
        guide = "Shorten the artist / album name in Review, or move the library closer to the drive root, then Retry."
    else:
        code, plain = "other", "The copy failed: " + (why or "unknown")[:200]
        guide = "Press Retry once. If it fails again, open _logs\\app_errors.txt and send me the line."
    return {"src": src, "name": os.path.basename(src or ""), "code": code, "reason": plain, "guide": guide,
            "detail": (why or "")[:300], "time": now()}


def phase3(st, cfg):
    hr("PHASE 3 - Apply: copy + tag into the new library (originals are not touched)")
    plan = st.load("plan.json", [])
    inv_by_id = {r["id"]: r for r in st.load("inventory.json", [])}
    if not plan:
        say("Run Phase 2 first.")
        return
    rows = prov_rows(st, inv_by_id, plan)
    todo = [it for it in plan if it["approved"] and it["action"] not in ("keep", "skip") and
            (it["action"] == "relocate" or rows.get(it["file_id"], {}).get("status") not in
             ("copied", "verified", "original_archived"))]
    only = getattr(UI, "copy_ids", None) if UI is not None else None
    if only:                                                 # the app: copy only the songs you picked
        todo = [it for it in todo if it["file_id"] in only]
    todo.sort(key=lambda it: it["action"] != "relocate")    # moves first: they free places for new copies
    if not todo:
        say("Nothing approved is waiting.")
        return
    n_rel = sum(1 for it in todo if it["action"] == "relocate")
    size = sum(inv_by_id[it["file_id"]]["size"] for it in todo if it["action"] != "relocate")
    say(f"{len(todo) - n_rel:,} files ({human(size)}) will be COPIED into {cfg['library']} in batches of {BATCH_SIZE}.")
    if n_rel:
        say(f"{n_rel:,} library copies will be MOVED to their improved place (old copies go to an _undone folder).")
    say("Originals stay exactly where they are. Existing files are never overwritten.")
    if not ask_yn("Start now?", "n"):
        say("Cancelled. Nothing was changed.")
        return
    undo = os.path.join(st.logs, "undo_log.csv")
    if exists(undo):
        undo = os.path.join(st.logs, f"undo_log_{stamp()}.csv")
    write_csv(undo, ["file_id", "operation", "from_path", "new_path", "how_to_undo"],
              [{"file_id": it["file_id"], "operation": it["action"],
                "from_path": it.get("current_path") if it["action"] == "relocate" else it["src"], "new_path": it["new_path"],
                "how_to_undo": "menu option 6 moves this copy to _undone (the original was never changed)"} for it in todo])
    say(f"Undo log written: {undo}")
    save_prov(st, rows)
    alt = AltSources(st, cfg.get("alt_use", []), cfg.get("discogs_token", ""), cfg.get("lastfm_key", ""), cfg.get("tidal_id", ""), cfg.get("tidal_secret", ""), cfg.get("spotify_id", ""), cfg.get("spotify_secret", "")) if cfg.get("covers") else None
    if alt:
        alt.order = full_alt_order(cfg)
        alt.cover_order = list(cfg.get("cover_order") or COVER_ORDER)
    created = st.load("created_files.json", [])
    covers = {}
    undone_root = os.path.join(cfg["library"], f"_undone_{stamp()}")
    errors = None
    # fetch all covers and lyrics first, in parallel (each site still keeps its own speed limit)
    cover_jobs, lyric_jobs = {}, []
    for it in todo:
        r = inv_by_id[it["file_id"]]
        if not it["new_tags"]:
            continue
        if alt and (not r.get("has_cover") or 0 < (r.get("cover_px") or 0) < 500):
            cover_jobs.setdefault(f"{it.get('group_id')}|{it.get('edition', '')}|{it.get('release_year')}", it)
        if cfg.get("lyrics"):
            lyric_jobs.append((it, r.get("duration")))
    if cover_jobs or lyric_jobs:
        get_lyrics(st, {"title": "", "credited": "", "album": ""}, 0, fetch=False)   # load the cache
        prog = Progress("Fetching covers + lyrics", len(cover_jobs) + len(lyric_jobs))

        def job_cover(item):
            ck, it = item
            try:
                return "c", ck, get_cover(st, cfg, alt, it)
            except Exception:
                return "c", ck, None

        def job_lyr(item):
            it, dur = item
            try:
                return "l", None, get_lyrics(st, it, dur, save=False)
            except Exception:
                return "l", None, ""
        with cf.ThreadPoolExecutor(max_workers=16) as ex:      # V2.0.5: covers/lyrics are waiting on the network, so more at once is faster
            futs = [ex.submit(job_cover, x) for x in cover_jobs.items()] + [ex.submit(job_lyr, x) for x in lyric_jobs]
            for fu in cf.as_completed(futs):
                kind, ck, val = fu.result()
                if kind == "c":
                    covers[ck] = val
                prog.step("covers + lyrics")
        prog.done()
        save_lyrics()
        alt.save() if alt else None
    t0 = time.time()
    prog = Progress("Copying + tagging", len(todo), lag=1)
    busy_skipped = []
    fail_log = []                                # 1.1.7: every file not copied, with a plain reason and a fix guide (copy_failures.json)
    failed = []                                  # v1.1.2: one bad file must never stop the whole copy

    def park_tmp(tmp_path):
        try:
            if tmp_path and exists(tmp_path):
                pk = os.path.join(undone_root, "_interrupted", os.path.relpath(tmp_path, cfg["library"]))
                os.makedirs(lp(os.path.dirname(pk)), exist_ok=True)
                shutil.move(lp(tmp_path), lp(pk))
        except Exception:
            pass

    def fail_item(row_, src_, why_, tmp_path=None):
        fail_log.append(copy_fail_entry(src_, row_, why_))
        park_tmp(tmp_path)
        row_["status"], row_["notes"] = "needs_review", "not copied: " + why_
        failed.append((src_, why_))
        say(f"   NOT copied (continuing with the rest): {src_}\n      reason: {why_}")
    for b in range(0, len(todo), BATCH_SIZE):
        for it in todo[b:b + BATCH_SIZE]:
            prog.step(os.path.basename(it.get("new_path", ""))[:70])
            r = inv_by_id[it["file_id"]]
            row = rows[it["file_id"]]
            dst = it["new_path"]
            relocate = it["action"] == "relocate"
            src = it.get("current_path") if relocate else r["path"]
            tmp = None
            try:
                if not relocate:
                    stt = os.stat(lp(r["path"]))
                    if stt.st_size != r["size"] or int(stt.st_mtime) != r["mtime"]:
                        row["status"], row["notes"] = "needs_review", "original changed since the scan - run Phase 1 again"
                        continue
                if exists(dst):
                    fail_item(row, src, f"the destination already exists (never overwritten): {dst}")
                    continue
                os.makedirs(lp(it["folder"]), exist_ok=True)
                tmp = os.path.join(it["folder"], f"~mlm_tmp_{it['file_id']}{it['ext']}")
                if exists(tmp):   # left over from an interrupted run: park it (never deleted)
                    park = os.path.join(undone_root, "_interrupted", os.path.relpath(tmp, cfg["library"]))
                    os.makedirs(lp(os.path.dirname(park)), exist_ok=True)
                    shutil.move(lp(tmp), lp(park))
                    say(f"   parked a leftover temp file from an interrupted run: {park}")
                busy_err = None                       # v1.1: a file in use (for example playing) must not stop the whole copy
                for _try in range(8):                 # 1.1.7: 8 tries, waiting longer each time (antivirus / preview / sync often let go in a few seconds)
                    try:
                        shutil.copy2(lp(src), lp(tmp))
                        busy_err = None
                        break
                    except (PermissionError, OSError) as ce:
                        if getattr(ce, "winerror", 0) not in (5, 32, 33) and not isinstance(ce, PermissionError):
                            raise
                        busy_err = ce
                        if exists(tmp):
                            try:
                                os.remove(lp(tmp))        # only our own half-written temp copy, never an original
                            except OSError:
                                pass
                        time.sleep(1.0 + _try * 1.5)
                if busy_err is not None:
                    if exists(tmp):
                        park = os.path.join(undone_root, "_interrupted", os.path.relpath(tmp, cfg["library"]))
                        os.makedirs(lp(os.path.dirname(park)), exist_ok=True)
                        shutil.move(lp(tmp), lp(park))
                    row["status"], row["notes"] = "needs_review", f"not copied: the file could not be read (in use by another program?) - {busy_err}"
                    busy_skipped.append(src)
                    fail_log.append(copy_fail_entry(src, row, str(busy_err), busy=True))
                    say(f"   skipped (in use, try again later): {src}")
                    continue
                os.chmod(lp(tmp), stat.S_IREAD | stat.S_IWRITE)   # originals may be read-only; the copy must not be
                changes = ["moved library copy" if relocate else "copied"]
                removed, note = [], ""
                if it["new_tags"]:
                    cover = None
                    small = 0 < (r.get("cover_px") or 0) < 500
                    if alt and (not r.get("has_cover") or small):
                        ck = f"{it.get('group_id')}|{it.get('edition', '')}|{it.get('release_year')}"
                        if ck not in covers:
                            prog.note(extra="finding cover")
                            covers[ck] = get_cover(st, cfg, alt, it)
                        cover = covers[ck]
                    if cfg.get("lyrics"):
                        prog.note(extra="lyrics")
                    lyr = get_lyrics(st, it, r.get("duration")) if cfg.get("lyrics") else ""
                    removed = write_tags(tmp, it["ext"], it["new_tags"], cover, replace_cover=small, lyrics=lyr)
                    old = r["tags"]
                    diff = [k for k in ("artist", "albumartist", "album", "title", "track", "year", "genre")
                            if it["new_tags"].get(k) and str(it["new_tags"].get(k)) != str(old.get(k, ""))]
                    if diff:
                        changes.append("retagged: " + ",".join(diff))
                    if cover:
                        changes.append("cover replaced" if small else "cover added")
                    if lyr:
                        changes.append("lyrics added")
                    if removed:
                        changes.append("removed junk tags: " + " | ".join(removed))
                elif it.get("dup_tag"):            # V2.0.3: identical extra copy whose other tags stay as they are: only the removable Comment
                    try:
                        if write_dup_comment(tmp, it["ext"]):
                            changes.append("tagged DUPLICATE (Comment, removable)")
                    except Exception as e_:
                        note = f"could not add the DUPLICATE comment: {type(e_).__name__}"
                h = audio_hash(tmp, cfg.get("ffmpeg"))
                if r.get("audio_hash") and h != r["audio_hash"]:
                    # the raw-packet check can shift when tags are rewritten (e.g. old ID3v1/APE tags, padding);
                    # decide by the DECODED sound of the original and the copy: only a real audio change stops
                    da, db = decoded_hash(src, cfg.get("ffmpeg")), decoded_hash(tmp, cfg.get("ffmpeg"))
                    if not da or da != db:
                        fail_item(row, src, "the audio of the copy differed from the original (audio must never change); the copy was set aside in _undone", tmp)
                        continue
                    note = "verified by decoded audio"
                    h = r["audio_hash"]
                if exists(dst):
                    fail_item(row, src, f"the destination appeared while working (never overwritten): {dst}", tmp)
                    continue
                for _t2 in range(6):                  # the renaming can also meet an antivirus scan of the new file
                    try:
                        os.rename(lp(tmp), lp(dst))
                        break
                    except PermissionError:
                        if _t2 == 5:
                            raise
                        time.sleep(1.0 + _t2)
                created.append(dst)
                if relocate:
                    park = os.path.join(undone_root, os.path.relpath(src, cfg["library"]))
                    os.makedirs(lp(os.path.dirname(park)), exist_ok=True)
                    for _t3 in range(6):
                        try:
                            shutil.move(lp(src), lp(park))
                            break
                        except PermissionError:
                            if _t3 == 5:
                                raise
                            time.sleep(1.0 + _t3)
                    changes.append(f"old copy parked in {undone_root}")
                if os.path.basename(dst) != r["filename"]:
                    changes.append("renamed")
                if it.get("dup_name"):
                    changes.append(f"duplicate of {it.get('dup_of', '')}")
                changes += it.get("notes", [])
                nt = it["new_tags"] or {}
                row.update(new_full_path=dst, new_filename=os.path.basename(dst), new_artist=nt.get("artist", ""),
                           new_albumartist=nt.get("albumartist", ""), new_album=nt.get("album", ""),
                           new_title=nt.get("title", ""), new_track=nt.get("track", ""), new_disc=nt.get("disc", ""),
                           new_year=nt.get("year", ""), new_genre=nt.get("genre", ""), changes_made="; ".join(changes),
                           date_processed=now(), data_source=it.get("data_source", ""), confidence=it.get("confidence", ""),
                           status="verified" if (r.get("audio_hash") and h) else "copied",
                           notes=(note or "") + ("" if r.get("audio_hash") else " audio hash unavailable (install ffmpeg)"))
                if row.get("final_original_path"):
                    row["status"] = "original_archived"
            except Exception as e:
                fail_item(row, src, f"{type(e).__name__}: {e}", locals().get("tmp"))
                continue
        save_prov(st, rows)
        st.save("created_files.json", created)
        if hasattr(get_lyrics, "c"):
            save_lyrics()
        if alt:
            alt.save()
        say(f"   batch done: {min(b + BATCH_SIZE, len(todo)):,}/{len(todo):,}  ({time.time() - t0:.0f}s)  - log saved + backup")
        if errors:
            prog.done()
            say("\nSTOPPED.\n " + errors)
            break
    prog.lag = 0
    if Progress.active:
        prog.note(cur="finishing: saving logs and playlists")
        prog.done()
    try:
        done_src = {(it.get("current_path") if it["action"] == "relocate" else inv_by_id[it["file_id"]]["path"]) for it in todo}
        old = [e for e in st.load("copy_failures.json", []) if e.get("src") not in done_src]
        st.save("copy_failures.json", old + fail_log)
    except Exception:
        pass
    made = rebuild_playlists(st, cfg, rows)
    try:
        made += write_split_playlists(st, cfg, rows)
    except Exception as e:
        say(f"   (could not write the compilation playlists: {type(e).__name__}: {e})")
    counts = Counter(r.get("status") or "not copied" for r in rows.values())
    hr("Phase 3 summary")
    for k, v in counts.most_common():
        say(f"   {v:>7,}  {k}")
    if made:
        say(f"   {made:>7,}  playlists recreated in _Playlists")
    if failed:
        say(f"   {len(failed):>7,}  files NOT copied because of an error (the rest were copied). They are listed above, marked needs_review in the provenance log; fix the cause and run Copy & tag again: only these are copied.")
    if busy_skipped:
        say(f"   {len(busy_skipped):>7,}  files NOT copied because another program was using them (playing?). Close it and run Copy & tag again: only these are copied.")
    say(f"\n Provenance log: {st.p('music_provenance.csv')}  (+ .xlsx, + backups\\)")
    waiting = [it for it in plan if not it["approved"] and not it.get("fixed") and not it.get("dup_extra") and it.get("kind") != "skip"]
    if waiting:
        say(f"\n {len(waiting):,} songs still wait for your review and were NOT copied (needs_review.csv).\n"
            "   Run Phase 2 to review just those, then Phase 3 again: it copies only them; nothing done is redone.")
    else:
        say(" Nothing is waiting for review.")
    say(" To undo: menu option 6 moves every copy made here into an _undone folder (nothing is deleted).")
    say(" When you have checked the library, run Phase 4 to archive the originals.")
    notify("Phase 3 finished" + (" - STOPPED on an error" if errors else ""))


# ----------------------------------------------------------------------------- Phase 4: archive

def archive_dest(root, orig):
    drive, rest = os.path.splitdrive(orig)
    if drive.startswith("\\\\"):
        d = "UNC_" + re.sub(r"[\\/]+", "_", drive.strip("\\/"))
    else:
        d = drive.rstrip(":\\/") or "ROOT"
    return os.path.join(root, d, rest.lstrip("\\/"))


def phase4(st, cfg):
    hr("PHASE 4 - Archive originals (MOVE, never delete)")
    rows = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    cand = [r for r in rows.values() if r.get("status") in ("verified", "copied")]
    if not cand:
        say("No copied files found. Finish Phase 3 first.")
        return
    if not ask_yn("Have you finished Phase 3 and reviewed the new library?", "n"):
        say("OK - come back when you have.")
        return
    while True:
        arch = clean_input_path(ask("Where should the originals go? Archive folder\n"
                                    "   (example: C:\\WORKPLACE\\_NEW WORLD ORDER\\EVERY MUSIC ALL AT ONCE)", cfg.get("archive", "")))
        if not arch:
            continue
        if inside(arch, cfg["library"]):
            say("   The archive should not be inside the organized library (it would mix originals with it).")
            if not ask_yn("   Use it anyway?", "n"):
                continue
        if any(inside(arch, s_["path"]) for s_ in (cfg.get("sources") or cfg.get("last_sources") or [])):
            say("   The archive cannot be inside a music source folder (it would be scanned again). Choose another.")
            continue
        break
    cfg["archive"] = arch
    st.save("config.json", cfg)
    say(f"Re-verifying {len(cand):,} copies against their originals (audio-stream hash)...")
    ok, bad = [], []
    prog = Progress("Re-verifying copies", len(cand))
    for i, r in enumerate(cand, 1):
        prog.step(os.path.basename(r["original_full_path"])[:70])
        src, new = r["original_full_path"], r["new_full_path"]
        why = ""
        if not exists(src):
            why = "original not found"
        elif not exists(new):
            why = "copy not found"
        elif not r.get("audio_stream_hash"):
            why = "no audio hash recorded (ffmpeg was missing)"
        else:
            if sha256_file(src) != r["sha256_hash"]:
                why = "original changed since scan"
            elif audio_hash(new, cfg.get("ffmpeg")) != r["audio_stream_hash"]:
                why = "copy audio does not match original"
        (bad if why else ok).append((r, why))
        pass
    prog.done()
    if bad:
        say(f"\n{len(bad):,} originals will NOT be moved:")
        for r, why in bad[:30]:
            say(f"   {why}: {r['original_full_path']}")
        write_csv(st.p(f"archive_excluded_{stamp()}.csv"), ["file_id", "original_full_path", "reason"],
                  [{"file_id": r["file_id"], "original_full_path": r["original_full_path"], "reason": w} for r, w in bad])
    if not ok:
        return
    if cfg.get("archive_flat"):            # app option 'Archive flat': every original straight into one folder
        plan, used = [], set()
        for r, _ in ok:
            name = os.path.basename(r["original_full_path"])
            stem, ext = os.path.splitext(name)
            d = os.path.join(cfg["archive"], name)
            if exists(d) or os.path.normcase(d) in used:          # same name: the artist first, then a number
                art = sanitize(r.get("orig_artist") or r.get("new_artist") or "")
                d = os.path.join(cfg["archive"], f"{art} - {name}" if art and not stem.lower().startswith(art.lower()) else name)
                n = 2
                while exists(d) or os.path.normcase(d) in used:
                    base = f"{art} - {stem}" if art and not stem.lower().startswith(art.lower()) else stem
                    d = os.path.join(cfg["archive"], f"{base} ({n:02d}){ext}")
                    n += 1
            used.add(os.path.normcase(d))
            plan.append((r, d))
    else:
        plan = [(r, archive_dest(cfg["archive"], r["original_full_path"])) for r, _ in ok]
    clash = [d for _, d in plan if exists(d)]
    size = sum(os.path.getsize(lp(r["original_full_path"])) for r, _ in ok)
    folders = Counter(os.path.dirname(r["original_full_path"]) for r, _ in ok)
    write_csv(st.p(f"archive_plan_{stamp()}.csv"), ["file_id", "original_full_path", "archive_path"],
              [{"file_id": r["file_id"], "original_full_path": r["original_full_path"], "archive_path": d} for r, d in plan])
    hr("Archive plan")
    say(f" Originals to move: {len(ok):,}  ({human(size)})\n Source folders: {len(folders):,}")
    for f, n in folders.most_common(15):
        say(f"   {n:>6,}  {f}")
    say(" Examples:")
    for r, d in plan[:5]:
        say(f"   {r['original_full_path']}\n     -> {d}")
    if clash:
        say(f"\nSTOP: {len(clash)} destination paths already exist (never overwritten), e.g.:\n   {clash[0]}")
        say("Decide what to do with those and run Phase 4 again.")
        return
    if not ask_yn(f"\nMove these {len(plan):,} originals into {cfg['archive']} now?", "n"):
        say("Cancelled. No original was touched.")
        return
    moved = 0
    prog = Progress("Archiving originals", len(plan))
    for b in range(0, len(plan), BATCH_SIZE):
        err = None
        for r, dest in plan[b:b + BATCH_SIZE]:
            prog.step(os.path.basename(r["original_full_path"])[:70])
            try:
                if exists(dest):
                    err = f"Destination exists (never overwritten): {dest}"
                    break
                os.makedirs(lp(os.path.dirname(dest)), exist_ok=True)
                shutil.move(lp(r["original_full_path"]), lp(dest))
                row = rows[r["file_id"]]
                row.update(final_original_path=dest, final_original_filename=os.path.basename(dest),
                           status="original_archived")
                moved += 1
            except Exception as e:
                err = f"Move failed, file left where it was: {r['original_full_path']}\n   {type(e).__name__}: {e}"
                break
        save_prov(st, rows)
        say(f"   moved {moved:,}/{len(plan):,} - log saved + backup")
        if err:
            prog.done()
            say("\nSTOPPED.\n " + err)
            break
    if Progress.active:
        prog.done()
    # empty folders left behind (only folders with no files and no subfolders at all, inside the sources)
    roots = [s_["path"] for s_ in (cfg.get("sources") or cfg.get("last_sources") or [])]
    cand = set()
    for r, _ in plan[:moved]:
        d = os.path.dirname(r["original_full_path"])
        while d and any(inside(d, rt) for rt in roots):
            if any(same_path(d, rt) for rt in roots):
                break                         # your music folder itself always stays
            cand.add(d)
            d = os.path.dirname(d)
    removed_dirs = []
    if cand:
        def empty(d):
            try:
                return os.path.isdir(lp(d)) and not os.listdir(lp(d))
            except Exception:
                return False
        todo_dirs = sorted(cand, key=lambda d: -len(d))
        show = [d for d in todo_dirs if empty(d)]
        if show:
            say(f"\n{len(show):,} folders are now completely empty (no files, no subfolders), e.g.:")
            for d in show[:15]:
                say(f"   {d}")
            if ask_yn("Remove these empty folders? (only truly empty ones; files are never deleted)", "n"):
                for d in todo_dirs:          # deepest first, so parents that become empty go too
                    if empty(d):
                        try:
                            os.rmdir(lp(d))
                            removed_dirs.append(d)
                        except Exception:
                            pass
                with open(lp(st.p(f"empty_folders_removed_{stamp()}.txt")), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(removed_dirs))
    hr("Phase 4 summary")
    say(f" Moved {moved:,} originals into {cfg['archive']}")
    if removed_dirs:
        say(f" Removed {len(removed_dirs):,} empty folders (list saved in the logs folder)")
    say(" To restore any file: menu option 5 -> search by name -> restore. Or by hand: the provenance log row\n"
        " gives final_original_path (where it is now) and original_full_path (where it came from).")
    notify(f"Phase 4 finished - {moved:,} originals archived")

# ----------------------------------------------------------------------------- tools: find / restore / undo

def find_restore(st, cfg):
    rows = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    q = ask("Search (part of a file name, path, artist or title)").lower()
    if not q:
        return
    hits = [r for r in rows.values() if any(q in (r.get(k) or "").lower() for k in
                                            ("original_full_path", "new_full_path", "final_original_path", "orig_artist",
                                             "orig_title", "new_title", "new_artist"))]
    for r in hits[:25]:
        say(f"\n {r['file_id']}  [{r['status']}]\n   original : {r['original_full_path']}\n"
            f"   library  : {r.get('new_full_path') or '-'}\n   archived : {r.get('final_original_path') or '-'}")
    if len(hits) > 25:
        say(f"\n ... {len(hits) - 25} more - narrow the search.")
    fid = ask("\nFile id to restore its original to the original location (Enter to skip)").upper()
    r = rows.get(fid)
    if not r:
        return
    if r.get("status") != "original_archived":
        say("That original is not archived; it is still in its original place.")
        return
    if exists(r["original_full_path"]):
        say("Something already exists at the original location; nothing was moved.")
        return
    if ask_yn(f"Move\n   {r['final_original_path']}\n back to\n   {r['original_full_path']} ?", "n"):
        os.makedirs(lp(os.path.dirname(r["original_full_path"])), exist_ok=True)
        shutil.move(lp(r["final_original_path"]), lp(r["original_full_path"]))
        write_restore_log(st, cfg, "Restore original", [{"file_id": fid, "kind": "restore", "from": r["final_original_path"],
                                                         "to": r["original_full_path"], "hash": r.get("audio_stream_hash", ""),
                                                         "time": now()}])
        r.update(status="verified", notes=(r.get("notes", "") + f" original restored {now()}").strip(),
                 final_original_path="", final_original_filename="")
        save_prov(st, rows)
        say("Restored.")


# ----------------------------------------------------------------------------- restore logs
RESTORE_COLS = ["file_id", "kind", "from", "to", "hash", "time"]
RESTORE_WHAT = {"copy": "copy made", "move_copy": "library copy moved", "archive": "original archived",
                "undo": "copy moved to _undone", "restore": "original put back"}


def write_restore_log(st, cfg, action, entries):
    """Every change gets its own restore log (_logs/restore/restore_<time>_<action>.json + .csv): exactly what was
    copied or moved, from where to where. 'Restore from a log' can reverse it later - even after a reinstall or
    from another computer. Nothing in it is ever deleted."""
    if not entries:
        return ""
    folder = os.path.join(st.logs, "restore")
    os.makedirs(lp(folder), exist_ok=True)
    base0 = os.path.join(folder, f"restore_{stamp()}_{re.sub(r'[^a-z0-9]+', '-', action.lower()).strip('-')}")
    base, n = base0, 2
    while exists(base + ".json"):            # never overwrite an earlier log
        base, n = f"{base0}_{n}", n + 1
    data = {"app": "Midnight 00:01 Music Sorter", "version": VERSION, "made": now(), "action": action,
            "library": cfg.get("library", ""), "entries": entries}
    with open(lp(base + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    write_csv(base + ".csv", RESTORE_COLS, entries)
    say(f" Restore log: {base}.json  ({len(entries):,} changes)")
    return base + ".json"


def prov_changes(before, after, kind):
    """What Phase 3 (copies, relocations) or Phase 4 (archive) changed, from two provenance snapshots."""
    out, t = [], now()
    for fid, a in after.items():
        b = before.get(fid) or {}
        if kind == "copy":
            if a.get("status") in ("copied", "verified") and a.get("new_full_path") and \
                    (b.get("status") not in ("copied", "verified") or b.get("new_full_path") != a.get("new_full_path")):
                moved = b.get("status") in ("copied", "verified") and b.get("new_full_path")
                out.append({"file_id": fid, "kind": "move_copy" if moved else "copy",
                            "from": b["new_full_path"] if moved else a.get("original_full_path", ""),
                            "to": a["new_full_path"], "hash": a.get("audio_stream_hash", ""), "time": t})
        elif a.get("final_original_path") and not b.get("final_original_path"):
            out.append({"file_id": fid, "kind": "archive", "from": a.get("original_full_path", ""),
                        "to": a["final_original_path"], "hash": a.get("audio_stream_hash", ""), "time": t})
    return out


def restore_from_log(st, cfg):
    """Load a restore log (from this library's _logs/restore, or any .json you drag in) and reverse it.
    Copies go to _undone (never deleted); moved files go back where they were; nothing is overwritten."""
    folder = os.path.join(st.logs, "restore")
    logs = sorted((os.path.join(folder, f) for f in os.listdir(lp(folder)) if f.endswith(".json")), reverse=True) \
        if os.path.isdir(lp(folder)) else []
    for i, f in enumerate(logs[:15], 1):
        try:
            d = json.load(open(lp(f), encoding="utf-8"))
            say(f" {i:2}) {d.get('made', '')}  {d.get('action', '')}  - {len(d.get('entries') or []):,} changes")
        except Exception:
            say(f" {i:2}) {os.path.basename(f)}  (unreadable)")
    pick = clean_input_path(ask("\nNumber, or drag a restore log (.json) here (Enter to cancel)"))
    if not pick:
        return
    path = logs[int(pick) - 1] if pick.isdigit() and 0 < int(pick) <= min(15, len(logs)) else pick
    try:
        d = json.load(open(lp(path), encoding="utf-8"))
        entries = d["entries"]
    except Exception:
        say("That is not a restore log made by this program. Nothing was changed.")
        return
    kinds = Counter(e.get("kind") for e in entries)
    say(f"\n {d.get('action', '')} - {d.get('made', '')}\n   " +
        " | ".join(f"{RESTORE_WHAT.get(k, k)} {v:,}" for k, v in kinds.items()))
    todo, problems = [], []
    for e in entries:
        src, dst = e.get("to", ""), e.get("from", "")
        if not src or not exists(src):
            problems.append(f"no longer there: {src}")
        elif e.get("kind") != "copy" and exists(dst):
            problems.append(f"something already at: {dst}")
        else:
            todo.append(e)
    say(f"   can be reversed: {len(todo):,}" + (f" | skipped: {len(problems):,} (listed below)" if problems else ""))
    for p_ in problems[:20]:
        say("     - " + p_)
    if not todo:
        return
    undone = os.path.join(cfg["library"], f"_undone_{stamp()}")
    n_copy = sum(1 for e in todo if e.get("kind") == "copy")
    if not ask_yn(f"Reverse {len(todo):,} changes? (moved files go back to where they were"
                  + (f"; {n_copy:,} copies go to {undone}" if n_copy else "") + "; nothing is deleted or overwritten)", "n"):
        say("Cancelled.")
        return
    rows = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))} if exists(st.p("music_provenance.csv")) else {}
    done, t = [], now()
    for e in todo:
        src = e["to"]
        dst = e["from"] if e.get("kind") != "copy" else os.path.join(
            undone, os.path.relpath(src, cfg["library"]) if inside(src, cfg["library"]) else os.path.basename(src))
        if exists(dst):
            continue
        os.makedirs(lp(os.path.dirname(dst)), exist_ok=True)
        shutil.move(lp(src), lp(dst))
        done.append({"file_id": e.get("file_id", ""), "kind": "undo" if e.get("kind") == "copy" else "restore",
                     "from": src, "to": dst, "hash": e.get("hash", ""), "time": t})
        r = rows.get(e.get("file_id", ""))
        if r:
            if e.get("kind") == "archive":
                r.update(status="verified", final_original_path="", final_original_filename="")
            elif e.get("kind") == "copy" and r.get("new_full_path") == src:
                r.update(status="skipped")
            elif e.get("kind") == "move_copy":
                r.update(new_full_path=dst, new_filename=os.path.basename(dst))
            r["notes"] = (r.get("notes", "") + f" reversed from restore log {t}").strip()
    if rows:
        save_prov(st, rows)
    say(f"Done: {len(done):,} reversed.")
    write_restore_log(st, cfg, f"Reverse of {d.get('action', 'log')}", done)


def undo_phase3(st, cfg):
    rows = {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))}
    copies = [r for r in rows.values() if r.get("status") in ("copied", "verified") and r.get("new_full_path")
              and exists(r["new_full_path"])]
    created = [p for p in st.load("created_files.json", []) if p.lower().endswith("cover.jpg") and exists(p)]
    if not copies:
        say("No library copies to undo.")
        return
    dest_root = os.path.join(cfg["library"], f"_undone_{stamp()}")
    say(f"{len(copies):,} copies (+{len(created)} cover.jpg) will be MOVED into\n   {dest_root}\n"
        "Nothing is deleted; originals are not touched. (Originals already archived are not affected.)")
    if not ask_yn("Undo now (copies are moved, nothing is deleted)?", "n"):
        say("Cancelled.")
        return
    by_path = {r["new_full_path"]: r["file_id"] for r in copies}
    moved, t = [], now()
    for p in [r["new_full_path"] for r in copies] + created:
        d = os.path.join(dest_root, os.path.relpath(p, cfg["library"]))
        os.makedirs(lp(os.path.dirname(d)), exist_ok=True)
        shutil.move(lp(p), lp(d))
        moved.append({"file_id": by_path.get(p, ""), "kind": "undo", "from": p, "to": d, "hash": "", "time": t})
    for r in copies:
        r.update(status="skipped", notes=(r.get("notes", "") + f" copy undone {now()} -> {dest_root}").strip())
    save_prov(st, rows)
    say(f"Done. Copies are in {dest_root}")
    write_restore_log(st, cfg, "Undo copy & tag", moved)

# ----------------------------------------------------------------------------- app helpers (desktop app: Review)
# Read-only lookups. They only find candidates; nothing is used until you pick one in the app.

def mb_track_len(tr):
    return round(((tr.get("length") or (tr.get("recording") or {}).get("length") or 0) / 1000), 1)


def length_check(duration, ln):
    """('same length' / '2 s shorter' / 'too long, 1:40 longer', ok?)"""
    if not duration or not ln:
        return "length not known", True
    d = ln - duration
    if abs(d) <= 3:
        return "same length", True
    word = "longer" if d > 0 else "shorter"
    if abs(d) <= 10:
        return f"{abs(d):.0f} s {word}", True
    return f"too {'long' if d > 0 else 'short'}: {int(abs(d)) // 60}:{int(abs(d)) % 60:02d} {word}", False


def candidate(m, duration, ln, how):
    txt, ok = length_check(duration, ln)
    tc = m.get("trk_credit") or {}
    return {"match": m, "title": m.get("title", ""), "artist": tc.get("full") or tc.get("primary") or "",
            "release": m.get("group_title", ""), "year": m.get("year", ""), "rtype": m.get("rtype", ""),
            "track": m.get("track", ""), "disc": m.get("disc", ""), "disctotal": m.get("disctotal", ""),
            "source": m.get("source", ""), "how": how, "length": ln, "len_text": txt, "len_ok": ok,
            "cover_url": m.get("cover_url", ""), "mbid": m.get("mbid", ""), "preview": m.get("preview_url", ""),
            "deezer_track": m.get("deezer_track", "")}


def search_by_artist_length(mb, artist, duration, mine="", limit=5):
    """Dig deeper by artist + length: candidates for a song whose title nobody knows. Sorted by how close the title
    is to what your file says (when it says anything) and by the length difference."""
    out = []
    if not (mb and artist and duration):
        return out
    recs = mb.search_by_length(artist, duration)
    recs.sort(key=lambda r: (-same_song_title(r.get("title"), mine) if mine else 0, abs((r.get("length") or 0) / 1000 - duration)))
    for rec in recs[:limit]:
        best = Resolver.choose_release(None, [rec], "")
        if not best:
            continue
        rel = mb.release(best[1]["id"])
        for m, ln in mb_release_tracks(rel):
            if m.get("recording_id") == rec["id"]:
                out.append(candidate(m, duration, ln, "same artist and length"))
                break
    return out


def mb_release_tracks(rel, source="MusicBrainz"):
    """Every track of a MusicBrainz release as a ready-to-use match (for track slots)."""
    out = []
    for medium in (rel or {}).get("media") or []:
        for tr in medium.get("tracks") or []:
            out.append((mb_match(rel, medium, tr, source), mb_track_len(tr)))
    return out


EDITION_WORDS = re.compile(r"\b(remaster\w*|mono|stereo|deluxe|special edition|anniversary|expanded|collector'?s|bonus tracks?|"
                        r"\d{4} mix|reissue|legacy edition|edition)\b", re.I)


def is_edition(*texts):
    """Remaster / mono / stereo / deluxe / special edition...: Apple Music and Deezer list these editions
    much better than MusicBrainz, so they are asked first for such songs."""
    return any(EDITION_WORDS.search(t or "") for t in texts)


def alt_album_views(alt, artist, album, use_sites, sites=("itunes", "deezer"), per_site=2):
    """Album search on Apple Music / Deezer (only the sites you allowed) -> albums with all their tracks.
    Sent: the artist and album words."""
    views = []
    if not alt or not album:
        return views
    want = strip_edition(album) or album

    def close(a_, coll):
        return (not artist or artist_agrees([a_ or ""], artist)) and ratio(strip_edition(coll) or coll, want) >= 0.6
    for site in sites:
        if site not in use_sites:
            continue
        urls = []
        try:
            if site == "itunes":
                q = urllib.parse.urlencode({"term": f"{artist} {album}".strip(), "entity": "album", "limit": "15"})
                res = (alt._get("itunes", "https://itunes.apple.com/search?" + q, 3.1) or {}).get("results") or []
                hits = [c for c in res if c.get("collectionId") and close(c.get("artistName"), re.sub(r"\s-\s(Single|EP)$", "", c.get("collectionName") or ""))]
                hits.sort(key=lambda c: -ratio(c.get("collectionName") or "", album))
                urls = [f"https://music.apple.com/us/album/{c['collectionId']}" for c in hits[:per_site]]
            elif site == "deezer":
                q = urllib.parse.urlencode({"q": (f'artist:"{artist}" ' if artist else "") + f'album:"{want}"', "limit": "15"})
                res = (alt._get("deezer", "https://api.deezer.com/search/album?" + q, 0.15) or {}).get("data") or []
                hits = [c for c in res if c.get("id") and close((c.get("artist") or {}).get("name"), c.get("title") or "")]
                hits.sort(key=lambda c: -ratio(c.get("title") or "", album))
                urls = [f"https://www.deezer.com/album/{c['id']}" for c in hits[:per_site + 1]]
            elif site == "discogs" and alt.token:
                q = urllib.parse.urlencode({"type": "release", "release_title": want, **({"artist": artist} if artist else {}), "per_page": "10"})
                res = (alt._get("discogs", "https://api.discogs.com/database/search?" + q, 1.1, alt.dhdr) or {}).get("results") or []
                hits = [c for c in res if c.get("id") and ratio(strip_edition(re.sub(r"^.*? - ", "", c.get("title") or "")), want) >= 0.6]
                urls = [f"https://www.discogs.com/release/{c['id']}" for c in hits[:per_site]]
            elif site == "spotify" and alt.spotify_id and alt.spotify_secret:       # v2.0: Spotify album search (names only)
                q = urllib.parse.quote((f'artist:{artist} ' if artist else "") + f'album:{want}', safe="")
                res = ((alt._spget(f"/search?q={q}&type=album&limit=10") or {}).get("albums") or {}).get("items") or []
                hits = [c for c in res if c.get("id") and close(" & ".join(x.get("name", "") for x in c.get("artists") or []) or None, c.get("name") or "")]
                hits.sort(key=lambda c: -ratio(c.get("name") or "", album))
                urls = [f"https://open.spotify.com/album/{c['id']}" for c in hits[:per_site]]
            elif site == "tidal" and alt.tidal_id:
                d = alt._tget(f"/searchResults/{urllib.parse.quote(f'{artist} {want}'.strip(), safe='')}?include=albums") or {}
                inc = alt._incl(d)
                ids = [x.get("id") for x in (((d.get("data") or {}).get("relationships") or {}).get("albums") or {}).get("data") or []]
                ok = [i for i in ids if ratio(strip_edition(((inc.get(("albums", i)) or {}).get("attributes") or {}).get("title", "")), want) >= 0.6]
                urls = [f"https://tidal.com/album/{i}" for i in ok[:per_site]]
        except Exception:
            urls = []
        for u in urls:
            try:
                v = release_from_link(u, None, alt)
            except Exception:
                v = {"error": "x"}
            if not v.get("error") and v.get("tracks"):
                views.append(v)
    return views


_OO_CACHE = {}
CLASSICAL_HINT = re.compile(r"\b(symphon\w*|concert[oi]|sonat[ae]|quartet|quintet|trio|opus|op\.? ?\d+|bwv ?\d+|hwv ?\d+|k\.? ?\d+|"
                            r"nocturne|prelude|fugue|[ée]tude|requiem|adagio|allegro|andante|largo|scherzo|overture|cantata|partita|"
                            r"mazurka|polonaise|movement|in [a-g](?:[- ](?:flat|sharp))? (?:major|minor))\b", re.I)
MOVEMENT_RE = re.compile(r"^(?P<work>.+?)\s*[:\-\u2013\u2014]\s*(?P<num>(?:[IVX]{1,5}|\d{1,2})\.?)\s+(?P<mov>[^:]+)$")


def split_movement(title):
    """'Piano Sonata No. 14: II. Allegretto' -> ('Piano Sonata No. 14', 'II', 'Allegretto'); no movement -> (title, '', '')."""
    m = MOVEMENT_RE.match((title or "").strip())
    if not m:
        return title or "", "", ""
    return m.group("work").strip(), m.group("num").strip(" ."), m.group("mov").strip()


def classical_clean(title):
    """1.1.5: Naxos / Brilliant style titles: 'Work : Composer: Work: No. 5 in G. Moderato' -> 'Work: No. 5 in G. Moderato'
    (the repeated work and the composer's name in front are dropped, so the search words are the work and the movement)."""
    t = (title or "").strip()
    if " : " in t:
        t = t.rsplit(" : ", 1)[1].strip()
    m = re.match(r"^([A-ZÀ-Ž][\w'\u2019.\-]+(?: (?:de|di|von|van|da|du|la|le|[A-ZÀ-Ž][\w'\u2019.\-]+)){0,2}):\s+(.+)$", t)
    if m and len(m.group(2)) > 6 and not re.match(r"^(?:no|op|bwv|k|hwv)\b", m.group(1), re.I) and not re.search(r"\d", m.group(1)):
        t = m.group(2).strip()
    return t


def classical_work(title):
    """'13 Preludes, Op. 32: No. 5 in G. Moderato' -> '13 Preludes, Op. 32' (for the OpenOpus work search)."""
    t = classical_clean(title)
    return re.split(r"\s*[:\-\u2013]\s*(?:No\.?|Nr\.?|[IVX]{1,5}\.|\d{1,2}\.)\s", t, 1)[0].strip() or t


def looks_classical(*texts):
    return any(CLASSICAL_HINT.search(t or "") for t in texts)


def openopus_names(text):
    """v1.1.5: ask OpenOpus (api.openopus.org) for the standard composer + work names. Sends only this text (composer / title words).
    Returns [(composer, work_title), ...] (max 3). Blocked by CACHE_ONLY. Any failure -> [] (silent)."""
    key = (text or "").strip().lower()
    if not key or CACHE_ONLY:
        return []
    if key in _OO_CACHE:
        return _OO_CACHE[key]
    out = []
    try:
        url = "https://api.openopus.org/omnisearch/" + urllib.parse.quote(key[:80], safe="") + "/0.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Midnight-Music-Sorter/1.1.5"})
        with urllib.request.urlopen(req, timeout=12) as f:
            j = json.loads(f.read().decode("utf-8", "replace"))
        for it in (j.get("results") or [])[:3]:
            c = (it.get("composer") or {}).get("complete_name") or (it.get("composer") or {}).get("name")
            w = (it.get("work") or {}).get("title")
            if c and w:
                out.append((c, w))
    except Exception:
        out = []
    _OO_CACHE[key] = out
    return out


def search_again(mb, alt, artist, title, album="", duration=0, use_sites=(), mine="", context="", deep=False, stats=None):
    """'Search again' / 'Find another album': MusicBrainz first (album search when an album is typed, then the
    song), then the other sites you allowed, in your order. Returns candidates with a length check.
    Labels like '(Remastered 2009)' or ': Original Motion Picture Soundtrack' are left out of the search words."""
    out, seen = [], set()
    mine = mine or title
    edition = is_edition(mine, album, context)
    album_typed = album
    title = neutral(title or "").strip() or (title or "")
    album = strip_edition(album or "").strip() or (album or "")

    def add(c):
        k = (c["match"].get("release_id"), str(c["match"].get("disc")), str(c["match"].get("track")))
        if k not in seen:
            seen.add(k)
            c["other_version"] = different_version(mine, c["title"])
            out.append(c)
    artists = artist_parts(artist) or [""]       # 'A, B' / 'A feat. B' / 'A / B': whole, then each artist
    for p_ in re.split(r"\s+(?:&|and|x|×|vs\.?|with)\s+", artist or "", flags=re.I):   # searching only: also 'A & B'
        if p_.strip() and p_.strip() not in artists:
            artists.append(p_.strip())
    def mb_part():
        if not (mb and title):
            return
        if album:
            found = []
            for a_ in artists[:4]:
                found = mb.search_release(a_, album)
                if found:
                    break
            for c in found[:6]:
                if int(c.get("score", 0)) < 60:
                    continue
                rel = mb.release(c["id"])
                best = None
                for m, ln in mb_release_tracks(rel):
                    sim = same_song_title(m["title"], title)
                    if sim >= 0.6 and (best is None or sim > best[0]):
                        best = (sim, m, ln)
                if best:
                    add(candidate(best[1], duration, best[2], "album search on MusicBrainz"))
        recs = []
        for a_ in artists[:4]:
            recs = mb.search_recording(a_, title, duration or 0, False)
            if not recs and base_title(title) != title:
                recs = mb.search_recording(a_, base_title(title), duration or 0, False)
            if recs:
                break
        for rec in recs[:8]:
            if int(rec.get("score", 0)) < 60 or same_song_title(rec.get("title"), title) < 0.6:
                continue
            best = Resolver.choose_release(None, [rec], album)
            if not best:
                continue
            rel = mb.release(best[1]["id"])
            for m, ln in mb_release_tracks(rel):
                if m.get("recording_id") == rec["id"]:
                    add(candidate(m, duration, ln, "song search on MusicBrainz"))
                    break
            if len(out) >= 8:
                break

    def alt_part(order):
        if not (alt and title):
            return
        for name in order:
            if name not in use_sites or (name == "discogs" and not alt.token) or (name == "lastfm" and not alt.lfm_key):
                continue
            m = None
            for a_ in artists[:3]:
                try:
                    m = getattr(alt, name)(a_, title, album, duration)
                except Exception:
                    m = None
                if m:
                    break
            if m and m.get("lfm_mbid") and mb:
                rel = mb.release(m["lfm_mbid"])
                for mm_, ln in mb_release_tracks(rel, "Last.fm > MusicBrainz"):
                    if same_song_title(mm_["title"], title) >= 0.88:
                        m = mm_
                        break
            if m:
                add(candidate(m, duration, 0, f"song search on {m['source']} (length checked ±10 s)"))

    def sure():
        return any(not c["other_version"] and c["len_ok"] for c in out)

    if edition:
        # V2.0.6: a remaster / mono / deluxe / special edition: Spotify and Apple Music FIRST (they list the remasters best), then
        # MusicBrainz and the other sites in their usual order. A normal search stops as soon as a same-version, same-length result is
        # found (keeps it fast); a search by hand (deep) asks every site anyway.
        first = [n for n in ("spotify", "itunes") if n in use_sites]
        for n in first:
            alt_part([n])
            if sure() and not deep:
                break
        if deep or not sure():
            mb_part()
            alt_part([n for n in alt.order if n not in first] if alt else [])
        elif stats is not None:
            stats["more"] = True
    else:
        mb_part()
        alt_part(alt.order if alt else [])
    if not out and not CACHE_ONLY and mb and looks_classical(title, mine, album, artist):
        # v1.1.5 classical: nothing found -> retry once with the standard composer + work names from OpenOpus, and the movement
        # ("II. Adagio") and the performers / conductor / orchestra in your artist text are used to rank the results.
        # Kept SMALL on purpose (a time budget + few lookups): a long classical search must never block the other searches.
        t_end = time.time() + 25
        title_c = classical_clean(title)
        work_, num_, mov_ = split_movement(title_c)
        tries = openopus_names(f"{artist} {classical_work(title)}".strip()) or openopus_names(classical_work(title)) or openopus_names(work_)
        for oc, ow in tries[:2]:
            q_title = f"{ow}: {num_}. {mov_}" if mov_ and num_ else ow
            if time.time() > t_end:
                break
            try:
                recs = mb.search_recording("", q_title, duration or 0, False) or (mb.search_recording("", ow, duration or 0, False) if mov_ else [])
            except RuntimeError:
                recs = []
            n_rel = 0
            for rec in (recs or [])[:5]:
                if time.time() > t_end or n_rel >= 3:
                    break
                if int(rec.get("score", 0)) < 70:
                    continue
                best = Resolver.choose_release(None, [rec], album)
                if not best:
                    continue
                n_rel += 1
                rel = mb.release(best[1]["id"])
                for m, ln in mb_release_tracks(rel):
                    if m.get("recording_id") == rec["id"]:
                        add(candidate(m, duration, ln, f"classical search (OpenOpus: {oc}, {ow})"))
                        break
            if out:
                break
        perf = [norm_key(p) for p in artist_parts(artist) if p]
        for c in out:
            who = norm_key(f"{c.get('artist') or ''} {c.get('credit') or ''}")
            c["performer_match"] = bool(perf) and any(p and p in who for p in perf)
        out.sort(key=lambda c: not c.get("performer_match"))
    if album_typed:
        # the album you typed counts: results on other albums are shown only when none is on that album
        on = [c for c in out if ratio(strip_edition(c.get("release") or "") or c.get("release") or "", album) >= 0.6]
        if on:
            if stats is not None and len(on) < len(out):
                stats["hidden_other_albums"] = len(out) - len(on)
            out[:] = on
        elif stats is not None and out:
            stats["no_album_hit"] = True
    out.sort(key=lambda c: (c["other_version"], not c["len_ok"]))
    if stats is not None:
        stats["edition"] = edition
    return out


def match_group_to_release(view, recs):
    """Album group: which track of this release is each of your songs? Same version only, length within 7 s
    (a song in the same track position with the same length and a similar title also counts)."""
    out = {}
    for r in recs:
        h = hints(r)
        best = None
        for i, t in enumerate(view.get("tracks") or []):
            if different_version(h["title_plain"], t["title"], "", f"{h['album_raw']} {r['filename']}"):
                continue
            ln, dur = t.get("length") or 0, r.get("duration") or 0
            if ln and dur and abs(ln - dur) > 7:
                continue
            sim = same_song_title(h["title_plain"], t["title"])
            if h["track"] and str(t.get("track")) == str(h["track"]).lstrip("0") and ln and dur and abs(ln - dur) <= 3 and \
                    ratio(title_key(neutral(h["title_plain"])), title_key(neutral(t["title"]))) >= 0.6:
                sim = max(sim, 0.9)
            if sim >= 0.88 and (best is None or sim > best[0]):
                best = (sim, i, ln)
        if best:
            txt, ok = length_check(r.get("duration") or 0, best[2])
            out[r["id"]] = {"i": best[1], "len_text": txt, "len_ok": ok}
    return out


def release_view(rel, source="MusicBrainz", focus_recording=""):
    """A MusicBrainz release with all its tracks, for track slots in the app."""
    tracks = mb_release_tracks(rel, source)
    rc = credit_info(rel.get("artist-credit"))
    rg = rel.get("release-group") or {}
    return {"title": rel.get("title", ""), "artist": rc["full"], "source": source, "mbid": rel["id"],
            "year": (rg.get("first-release-date") or rel.get("date") or "")[:4], "rtype": tracks[0][0]["rtype"] if tracks else "",
            "disambiguation": rel.get("disambiguation", ""),
            "tracks": [{"match": m, "title": m["title"], "track": m["track"], "disc": m["disc"], "length": ln,
                        "focus": bool(focus_recording) and m.get("recording_id") == focus_recording} for m, ln in tracks]}


def identify_by_sound(path, cfg, mb, album_hint="", duration=0, info=None):
    """AcoustID: fingerprint made on this PC (numbers, not audio) + length -> recordings -> releases.
    'info' (a dict) receives a plain-words reason when nothing could be found."""
    info = info if info is not None else {}
    fp = cfg.get("fpcalc") or find_tool("fpcalc")
    if fp and not os.path.exists(fp):
        fp = find_tool("fpcalc")
    if not fp:
        info["error"] = "fpcalc.exe was not found."
        return []
    if not cfg.get("acoustid_key"):
        info["error"] = "No AcoustID key (Settings)."
        return []
    if not mb:
        info["error"] = "MusicBrainz is switched off."
        return []
    cp = Chromaprint(fp, cfg["acoustid_key"])
    hits = cp.lookup(path)
    if cp.err:
        info["error"] = cp.err
        return []
    if not hits:
        info["error"] = "AcoustID does not know this recording."
        return []
    out, seen = [], set()
    for score, rid in hits[:6]:
        if score < 0.5 or rid in seen:
            continue
        seen.add(rid)
        rec = mb.recording(rid)
        if not rec:
            continue
        best = Resolver.choose_release(None, [rec], album_hint)
        if not best:              # only on compilations (classical, film...): take its first official release
            rels = [r for r in rec.get("releases") or [] if (r.get("status") or "Official") == "Official"] or rec.get("releases") or []
            best = (None, rels[0], rec) if rels else None
        if not best:
            continue
        rel = mb.release(best[1]["id"])
        for m, ln in mb_release_tracks(rel, "AcoustID + MusicBrainz"):
            if m.get("recording_id") == rid:
                out.append(candidate(m, duration, ln, f"identified by sound ({score * 100:.0f}% sure)"))
                break
    if not out:
        info["error"] = "The sound was recognised, but MusicBrainz has no release for it."
    return out


LINK_RE = [
    ("mb_release", re.compile(r"musicbrainz\.org/release/([0-9a-f-]{36})", re.I)),
    ("mb_group", re.compile(r"musicbrainz\.org/release-group/([0-9a-f-]{36})", re.I)),
    ("discogs_release", re.compile(r"discogs\.com/(?:[^/]+/)?release/(\d+)", re.I)),
    ("discogs_master", re.compile(r"discogs\.com/(?:[^/]+/)?master/(\d+)", re.I)),
    ("mb_recording", re.compile(r"musicbrainz\.org/recording/([0-9a-f-]{36})", re.I)),
    ("mb_track", re.compile(r"musicbrainz\.org/track/([0-9a-f-]{36})", re.I)),
    ("deezer", re.compile(r"deezer\.com/(?:[a-z]{2}/)?album/(\d+)", re.I)),
    ("tidal", re.compile(r"tidal\.com/(?:browse/)?album/(\d+)", re.I)),
    ("spotify_track", re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?track/|spotify:track:)([A-Za-z0-9]{22})", re.I)),
    ("spotify", re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?album/|spotify:album:)([A-Za-z0-9]{22})", re.I)),
    ("deezer_track", re.compile(r"deezer\.com/(?:[a-z]{2}/)?track/(\d+)", re.I)),
    ("apple_song", re.compile(r"(?:music|itunes)\.apple\.com/(?:([a-z]{2})/)?(?:[a-z-]+/)?album/[^?#]*?(?:id)?(\d+)\?(?:[^#]*&)?i=(\d+)", re.I)),
    ("apple", re.compile(r"(?:music|itunes)\.apple\.com/(?:([a-z]{2})/)?(?:[a-z-]+/)?album/(?:[^/?#]+/)?(?:id)?(\d+)", re.I)),
    ("apple_song", re.compile(r"(?:music|itunes)\.apple\.com/(?:([a-z]{2})/)?song/(?:[^/?#]+/)?(?:id)?()(\d+)", re.I)),
]
LINK_SITE = {"tidal": "Tidal", "spotify": "Spotify", "spotify_track": "Spotify", "mb_release": "MusicBrainz", "mb_group": "MusicBrainz", "mb_recording": "MusicBrainz", "mb_track": "MusicBrainz",
             "discogs_release": "Discogs", "discogs_master": "Discogs", "deezer": "Deezer", "deezer_track": "Deezer",
             "apple": "Apple Music", "apple_song": "Apple Music"}


def parse_link(url):
    """-> (kind, id). Apple ids are 'country|album id|song id' (store country from the link, e.g. gb)."""
    for kind, rx in LINK_RE:
        m = rx.search((url or "").strip())
        if m:
            if kind == "apple":
                return kind, f"{(m.group(1) or '').lower()}|{m.group(2)}|"
            if kind == "apple_song":
                return kind, f"{(m.group(1) or '').lower()}|{m.group(2) or ''}|{m.group(3)}"
            return kind, m.group(1)
    return None, None



def spotify_page(kind, sid):
    """v1.1.5: a pasted Spotify link, NO login and no key: the public embed page of that track / album. Only the id in the link is
    sent. Returns {"title","artist","duration","tracks":[(title, artist, seconds)],"album","cover"} or {} (any failure is silent)."""
    if CACHE_ONLY:
        return {}
    try:
        req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{sid}", headers={"User-Agent": "Mozilla/5.0 Midnight-Music-Sorter"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return {}
        ent = (((json.loads(m.group(1)).get("props") or {}).get("pageProps") or {}).get("state") or {}).get("data", {}).get("entity") or {}
        arts = ", ".join(a.get("name", "") for a in ent.get("artists") or [] if a.get("name"))
        out = {"title": ent.get("name") or ent.get("title") or "", "artist": arts, "duration": (ent.get("duration") or 0) / 1000,
               "album": (ent.get("albumName") or ""), "cover": ""}
        covs = ent.get("coverArt", {}).get("sources") or ent.get("visualIdentity", {}).get("image") or []
        if covs:
            out["cover"] = covs[-1].get("url", "") if isinstance(covs[-1], dict) else ""
        out["tracks"] = [(t.get("title", ""), t.get("subtitle", ""), (t.get("duration") or 0) / 1000) for t in ent.get("trackList") or []]
        return out
    except Exception:
        return {}

def _alt_track_match(source, rid, gid, album, album_artist, year, rtype, ntracks, title, artists, pos, disc, genre, cover):
    tcred = [{"name": n, "joinphrase": " & ", "artist": {"name": n, "id": ""}} for n in artists or [album_artist]]
    tcred[-1]["joinphrase"] = ""
    return {"source": source, "verified": True, "release_id": rid, "mbid": "", "group_id": gid,
            "group_title": strip_edition(album), "year": year, "release_year": year, "rtype": rtype, "ntracks": ntracks,
            "is_va": norm_key(album_artist) in VA_NAMES, "remaster": bool(REMASTER_RE.search(album or "")),
            "rel_credit": credit_info(simple_credit(album_artist)), "trk_credit": credit_info(tcred), "title": title,
            "track": str(pos), "disc": str(disc or 1), "disctotal": "", "tracktotal": str(ntracks), "maxtrack": ntracks,
            "genre": genre, "recording_id": "", "cover_url": cover, "hint": 1}


def match_from_tags(r):
    """'Trust my tags' (app): a box set / bootleg no site knows is placed as an album using YOUR tags exactly
    (album, album artist, year, track numbers). Marked 'Your tags' - never chosen automatically."""
    t = r.get("tags") or {}
    h = hints(r)
    album = (t.get("album") or h.get("folder_album") or "").strip() or "Unknown Album"
    aa = (t.get("albumartist") or t.get("artist") or h.get("artist") or "").strip() or "Unknown Artist"
    artist = (t.get("artist") or aa).strip()
    tr = str(t.get("track") or h.get("track") or "").split("/")[0].lstrip("0")
    disc = str(t.get("disc") or h.get("disc") or "1").split("/")[0].lstrip("0") or "1"
    total = str(t.get("tracktotal") or (str(t.get("track") or "").split("/")[1] if "/" in str(t.get("track") or "") else "")).lstrip("0")
    rtype = "Album"                    # kept together in ONE album folder (a box set is not spread over artists)
    if norm_key(aa) in VA_NAMES:
        aa = "Various Artists"
    m = _alt_track_match("Your tags", f"tags:{norm_key(aa)}:{norm_key(album)}", f"tags:{norm_key(aa)}:{norm_key(album)}", album, aa,
                         (t.get("year") or "")[:4], rtype, int(total) if total.isdigit() else 0,
                         (t.get("title") or h.get("title_raw") or "").strip(), [artist], tr, disc, t.get("genre") or "", "")
    m["is_va"] = False
    m["trusted"] = True
    return m


def release_from_link(url, mb, alt):
    """A release page you paste (MusicBrainz, Discogs, Deezer, Apple Music) -> the release with all its tracks.
    Only the id in the link is sent to that one site."""
    kind, rid = parse_link(url)
    if not kind:
        return {"error": "This link was not understood. Paste an album or song page from MusicBrainz, Discogs, Deezer, Apple Music or Spotify."}
    tracks, head = [], {}
    focus_rec = ""
    if kind in ("mb_recording", "mb_track"):
        if not mb:
            return {"error": "MusicBrainz is switched off."}
        if kind == "mb_track":                # a track id: find its recording through a release search
            d = mb.get("release", {"query": f"tid:{rid}", "limit": "1"}) or {}
            rels = d.get("releases") or []
            if not rels:
                return {"error": "MusicBrainz does not know this track."}
            rel = mb.release(rels[0]["id"])
            for medium in (rel or {}).get("media") or []:
                for tr in medium.get("tracks") or []:
                    if tr.get("id") == rid:
                        focus_rec = (tr.get("recording") or {}).get("id", "")
            return dict(release_view(rel, focus_recording=focus_rec), site="MusicBrainz")
        rec = mb.recording(rid)
        if not rec:
            return {"error": "MusicBrainz does not know this song."}
        best = Resolver.choose_release(None, [rec], "")
        if not best:
            return {"error": "This song is on no official release on MusicBrainz."}
        return dict(release_view(mb.release(best[1]["id"]), focus_recording=rid), site="MusicBrainz")
    if kind.startswith("mb"):
        if not mb:
            return {"error": "MusicBrainz is switched off."}
        if kind == "mb_group":
            d = mb.get("release", {"release-group": rid, "status": "official", "limit": "25"}) or {}
            rels = sorted(d.get("releases") or [], key=lambda r: r.get("date") or "9999")
            if not rels:
                return {"error": "No official release found in that release group."}
            rid = rels[0]["id"]
        rel = mb.release(rid)
        if not rel:
            return {"error": "MusicBrainz does not know this release."}
        return dict(release_view(rel), site="MusicBrainz")
    elif kind in ("spotify", "spotify_track"):          # v1.1.5: no login, no key needed for a pasted link
        kk = "track" if kind == "spotify_track" else "album"
        if kind == "spotify" and alt is not None and getattr(alt, "spotify_id", "") and getattr(alt, "spotify_secret", ""):
            v = alt.spotify_album(rid)
            if not v.get("error"):
                tracks, head = v["tracks"], v["head"]
        elif kind == "spotify_track" and alt is not None and getattr(alt, "spotify_id", "") and getattr(alt, "spotify_secret", ""):
            # V2.0.6: a Spotify SONG link: the song's album comes from the Spotify key, then that album is shown with the song marked
            t_ = alt._spget(f"/tracks/{rid}") or {}
            alb_id = (t_.get("album") or {}).get("id")
            if alb_id:
                v = alt.spotify_album(alb_id)
                if not v.get("error"):
                    tracks, head = v["tracks"], v["head"]
                    focus_rec = str(t_.get("name") or "")
        if not tracks:
            info = spotify_page(kk, rid)
            if not info or not (info.get("title") or info.get("tracks")):
                return {"error": "Spotify gave no details for this link (it may be private or the page changed). Paste a MusicBrainz, Deezer or Apple Music link, or search by name."}
            if kind == "spotify_track":
                cands = search_again(mb, alt, info["artist"], info["title"], info.get("album", ""), info.get("duration") or 0,
                                     use_sites=tuple(getattr(alt, "use", ()) or ()) if alt else ()) or []
                for c in cands:
                    r_id = str((c.get("match") or {}).get("release_id") or "")
                    if mb and r_id and ":" not in r_id:
                        rel = mb.release(r_id)
                        if rel:
                            return dict(release_view(rel, focus_recording=(c["match"].get("recording_id") or "")), site="Spotify > MusicBrainz")
                for c in cands:            # V2.0.6: no MusicBrainz album? the album the other sites found for this song is used
                    r_id = str((c.get("match") or {}).get("release_id") or "")
                    pre, _, num = r_id.partition(":")
                    u2 = {"deezer": f"https://www.deezer.com/album/{num}", "itunes": f"https://music.apple.com/us/album/id{num}",
                          "discogs": f"https://www.discogs.com/release/{num}"}.get(pre)
                    if u2 and num.isdigit():
                        v2 = release_from_link(u2, mb, alt)
                        if v2 and not v2.get("error"):
                            for tr_ in v2.get("tracks") or []:
                                if same_song_title(tr_.get("title", ""), info["title"]) >= 0.88:
                                    tr_["focus"] = True
                            v2["site"] = "Spotify > " + str(v2.get("site") or pre)
                            return v2
                return {"error": f"Spotify says this is '{info['artist']} - {info['title']}', but no album was found for it. Try Search again with these words."}
            aa = info["artist"]
            for i, (tt, ta, ln) in enumerate(info["tracks"], 1):
                m = _alt_track_match("Spotify", f"spotify:{rid}", f"spotify:{norm_key(aa)}:{norm_key(strip_edition(info['title']))}",
                                     info["title"], aa, "", "Album", len(info["tracks"]), tt, [ta or aa], i, 1, "", info.get("cover", ""))
                tracks.append((m, ln))
            head = {"title": info["title"], "artist": aa, "year": "", "source": "Spotify", "cover_url": info.get("cover", "")}
    elif alt is None:
        return {"error": "Other sites are not available."}
    elif kind == "tidal":
        v = alt.tidal_album(rid)
        if v.get("error"):
            return v
        tracks, head = v["tracks"], v["head"]
    elif kind in ("deezer", "deezer_track"):
        if kind == "deezer_track":
            trk = alt._get("deezer", f"https://api.deezer.com/track/{rid}", 0.15) or {}
            if not trk or trk.get("error") or not (trk.get("album") or {}).get("id"):
                return {"error": "Deezer does not know this song."}
            focus_rec = str(trk.get("title") or "")
            rid = str(trk["album"]["id"])
        alb = alt._get("deezer", f"https://api.deezer.com/album/{rid}", 0.15) or {}
        if not alb or alb.get("error"):
            return {"error": "Deezer does not know this album."}
        aa = (alb.get("artist") or {}).get("name", "")
        rtype = AltSources.DZ_TYPES.get(alb.get("record_type"), "Album")
        items = (alb.get("tracks") or {}).get("data") or []
        year = (alb.get("release_date") or "")[:4]
        for i, t in enumerate(items, 1):
            m = _alt_track_match("Deezer", f"deezer:{rid}", f"deezer:{norm_key(aa)}:{norm_key(strip_edition(alb.get('title', '')))}",
                                 alb.get("title", ""), aa, year, rtype, len(items), t.get("title", ""),
                                 [(t.get("artist") or {}).get("name") or aa], i, t.get("disk_number") or 1,
                                 (((alb.get("genres") or {}).get("data") or [{}])[0]).get("name", ""), alb.get("cover_xl") or "")
            m["preview_url"], m["deezer_track"] = t.get("preview") or "", t.get("id") or ""
            tracks.append((m, t.get("duration") or 0))
        head = {"title": alb.get("title", ""), "artist": aa, "year": year, "source": "Deezer", "cover_url": alb.get("cover_xl") or ""}
    elif kind in ("apple", "apple_song"):
        cc, alb_id, song_id = rid.split("|")
        stores = [x for x in (cc, "us") if x] or ["us"]
        if not alb_id:                         # a song page: find its album first
            for c_ in stores:
                d = alt._get("itunes", f"https://itunes.apple.com/lookup?id={song_id}&country={c_}", 3.1) or {}
                hit = next((r for r in d.get("results") or [] if r.get("collectionId")), None)
                if hit:
                    alb_id = str(hit["collectionId"])
                    break
            if not alb_id:
                return {"error": "Apple Music does not know this song (in the store of the link)."}
        res, coll = [], None
        for c_ in stores:                      # the store of the link first (an album may exist only there)
            d = alt._get("itunes", f"https://itunes.apple.com/lookup?id={alb_id}&entity=song&country={c_}", 3.1) or {}
            res = d.get("results") or []
            coll = next((r for r in res if r.get("wrapperType") == "collection"), None)
            if coll:
                break
        if not coll:
            return {"error": "Apple Music does not know this album (in the store of the link)."}
        rid = alb_id
        name, aa = coll.get("collectionName", ""), coll.get("artistName", "")
        rtype = "Album"
        mm_ = re.search(r"\s-\s(Single|EP)$", name)
        if mm_:
            rtype, name = mm_.group(1), name[:mm_.start()]
        year = (coll.get("releaseDate") or "")[:4]
        songs = sorted((r for r in res if r.get("wrapperType") == "track"), key=lambda r: (r.get("discNumber") or 1, r.get("trackNumber") or 0))
        cover = (coll.get("artworkUrl100") or "").replace("100x100bb", "1000x1000bb")
        for t in songs:
            m = _alt_track_match("Apple Music", f"itunes:{rid}", f"itunes:{norm_key(aa)}:{norm_key(strip_edition(name))}", name, aa, year,
                                 rtype, coll.get("trackCount") or len(songs), t.get("trackName", ""), [t.get("artistName") or aa],
                                 t.get("trackNumber") or "", t.get("discNumber") or 1, coll.get("primaryGenreName", ""), cover)
            m["focus"] = bool(song_id) and str(t.get("trackId")) == song_id
            m["preview_url"] = t.get("previewUrl") or ""
            tracks.append((m, (t.get("trackTimeMillis") or 0) / 1000))
        head = {"title": name, "artist": aa, "year": year, "source": "Apple Music", "cover_url": cover}
    else:      # Discogs
        if kind == "discogs_master":
            ms = alt._get("discogs", f"https://api.discogs.com/masters/{rid}", 1.1, alt.dhdr) or {}
            rid = ms.get("main_release")
            if not rid:
                return {"error": "Discogs does not know this master release."}
        rel = alt._get("discogs", f"https://api.discogs.com/releases/{rid}", 1.1, alt.dhdr) or {}
        if not rel.get("tracklist"):
            return {"error": "Discogs does not know this release."}
        rcred = AltSources._dg_credit(rel.get("artists"))
        aa = credit_info(rcred)["full"]
        items = [t for t in rel.get("tracklist") or [] if (t.get("type_") or "track") == "track"]
        imgs = rel.get("images") or []
        cover = next((im.get("uri") for im in imgs if im.get("type") == "primary"), imgs[0].get("uri") if imgs else "")
        for i, t in enumerate(items, 1):
            pos = t.get("position") or ""
            mpos = re.match(r"^(?:CD)?(\d+)[-.](\d+)$", pos, re.I)
            disc, num = (int(mpos.group(1)), int(mpos.group(2))) if mpos else (1, i)
            ln = 0
            if re.match(r"^\d+:\d\d$", t.get("duration") or ""):
                a_, b_ = t["duration"].split(":")
                ln = int(a_) * 60 + int(b_)
            names = [x["name"] for x in AltSources._dg_credit(t.get("artists"))] or [x["name"] for x in rcred]
            m = _alt_track_match("Discogs", f"discogs:{rid}", f"discogs-master:{rel['master_id']}" if rel.get("master_id") else f"discogs:{rid}",
                                 rel.get("title", ""), aa, str(rel.get("year") or ""), "Album", len(items), t.get("title", ""), names,
                                 num, disc, (rel.get("genres") or [""])[0], cover)
            tracks.append((m, ln))
        head = {"title": rel.get("title", ""), "artist": aa, "year": str(rel.get("year") or ""), "source": "Discogs", "cover_url": cover}
    head["tracks"] = [{"match": m, "title": m["title"], "track": m["track"], "disc": m["disc"], "length": ln, "preview": m.get("preview_url", ""),
                       "deezer_track": m.get("deezer_track", ""),
                       "focus": bool(m.pop("focus", False)) or (bool(focus_rec) and kind in ("deezer_track", "spotify_track") and m["title"] == focus_rec)}
                      for m, ln in tracks]
    head["site"] = LINK_SITE[kind]
    return head

# ----------------------------------------------------------------------------- main

def keep_awake(on):
    """While the program is open, Windows does not go to sleep (the screen may still turn off)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:
        pass


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if mutagen is None:
        say("Missing library. Open a terminal and run:\n\n    pip install mutagen openpyxl pillow\n")
        sys.exit(1)
    st, cfg = setup(sys.argv)
    keep_awake(True)
    while True:
        hr("Menu")
        say(" 1) Phase 1 - Scan & audit                 (read-only)\n"
            " 2) Phase 2 - Propose changes              (read-only)\n"
            " 3) Phase 3 - Apply: copy + tag            (asks y/n)\n"
            " 4) Phase 4 - Archive the originals        (asks y/n)\n"
            " 5) Find a file / restore an archived original\n"
            " 6) Undo Phase 3 (moves copies to _undone; never deletes)\n"
            " 7) Restore from a restore log (pick one, or drag in a .json)\n"
            " 0) Quit")
        c = ask("Choose", "")
        try:
            if c == "1":
                phase1(st, cfg)
            elif c == "2":
                phase2(st, cfg)
            elif c in ("3", "4"):
                snap = lambda: {r["file_id"]: r for r in read_csv(st.p("music_provenance.csv"))} \
                    if exists(st.p("music_provenance.csv")) else {}
                before = snap()
                try:
                    (phase3 if c == "3" else phase4)(st, cfg)
                finally:      # also after an error or Ctrl+C: whatever was done is in the log
                    write_restore_log(st, cfg, "Copy & tag" if c == "3" else "Archive originals",
                                      prov_changes(before, snap(), "copy" if c == "3" else "archive"))
            elif c == "5":
                find_restore(st, cfg)
            elif c == "6":
                undo_phase3(st, cfg)
            elif c == "7":
                restore_from_log(st, cfg)
            elif c == "0":
                keep_awake(False)
                break
        except KeyboardInterrupt:
            save_lyrics()
            say("\nInterrupted. Logs saved up to the last finished batch; lookup answers and lyrics are kept.")


if __name__ == "__main__":
    main()

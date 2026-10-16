#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Midnight 00:01 · Music Sorter - desktop app
===========================================
A window (pywebview + the HTML in ui/) on top of the engine music_manager.py.
The engine does all the work exactly as in the text menu; this file only:
  - shows its progress and messages on screen,
  - answers its questions from what you chose on screen (online services, layout ...),
  - never approves a copy / move by itself: that only happens after you press a green button.

Run:   python midnight_app.py            (the window)
       python midnight_app.py --browser  (same app in your web browser, for testing)
The text menu still works:  python music_manager.py   (or 'Start Music Manager.bat')
"""
from __future__ import annotations

import io
import itertools
import json
import multiprocessing
import os
import re
import string
import sys
import threading
import time
import traceback
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import music_manager as mm  # noqa: E402

APP_NAME = "Midnight 00:01 · Music Sorter"
APP_VERSION = "2.0.6"
UI_DIR = os.path.join(getattr(sys, "_MEIPASS", HERE), "ui")
KEY_FIELDS = ("acoustid_key", "discogs_token", "lastfm_key", "tidal_id", "tidal_secret", "spotify_id", "spotify_secret", "mb_contact")
MEMO = os.path.join(os.path.expanduser("~"), ".music_library_manager.json")   # shared with the text menu
PROTECTED_NAMES = ["THE MUSIC GOD FOLDER"]         # never touched unless you confirm by typing YES


class StopRequested(RuntimeError):
    """Raised inside the engine's progress line when you press Stop (only during read-only phases)."""
    def __init__(self):
        super().__init__("Stopped by you. Nothing was changed; answers found so far are kept in the cache.")


def is_protected(path):
    p = (path or "").lower()
    return next((n for n in PROTECTED_NAMES if n.lower() in p), "")


_CSV_CACHE = {}


def prov_rows(st):
    """music_provenance.csv, read from disk again only when it changed (read only - do not change the rows)."""
    p = st.p("music_provenance.csv")
    try:
        stt = os.stat(mm.lp(p))
    except OSError:
        return []
    key = (stt.st_mtime_ns, stt.st_size)
    hit = _CSV_CACHE.get(p)
    if hit and hit[0] == key:
        return hit[1]
    rows = mm.read_csv(p)
    _CSV_CACHE[p] = (key, rows)
    return rows


EXTRA_KINDS = {
    "covers": ("Cover pictures", (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")),
    "playlists": ("Playlist files", (".m3u", ".m3u8", ".pls", ".wpl", ".xspf")),
    "cue": ("CD rip files (.cue / .log)", (".cue", ".log", ".accurip", ".ffp", ".md5", ".sfv")),
    "booklets": ("Booklets / scans (PDF and pictures in Scans folders)", (".pdf",)),
    "lyrics": ("Lyrics files (.lrc / .txt)", (".lrc", ".txt")),
}
SCAN_DIRS = {"scans", "scan", "artwork", "art", "covers", "cover", "booklet", "booklets", "images", "pics"}


def extras_found(app):
    """Extra files in the folders your songs come from, with the album folder they would go to."""
    plan = app.st.cached("plan.json", [])
    dest = {}
    for it in plan:
        if (it.get("approved") or it.get("fixed")) and it.get("new_path") and it.get("kind") not in ("skip",) and not it.get("dup_extra"):
            d = dest.setdefault(os.path.normcase(os.path.dirname(it["src"])), Counter())
            d[os.path.dirname(it["new_path"])] += 1
    out = []
    for src_dir, c in dest.items():
        to = c.most_common(1)[0][0]
        if os.path.basename(to).startswith("_") or "_Unverified" in to:
            continue                         # not for _Unverified / _Short Files...
        real = next((os.path.dirname(it["src"]) for it in plan if os.path.normcase(os.path.dirname(it["src"])) == src_dir), src_dir)
        try:
            entries = list(os.scandir(mm.lp(real)))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_dir() and e.name.lower() in SCAN_DIRS:
                    for f in os.scandir(e.path):
                        if f.is_file() and os.path.splitext(f.name)[1].lower() in (".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff", ".webp"):
                            out.append({"kind": "booklets", "src": os.path.join(real, e.name, f.name), "to": os.path.join(to, e.name),
                                        "size": f.stat().st_size})
                    continue
                if not e.is_file():
                    continue
                ext = os.path.splitext(e.name)[1].lower()
                kind = next((k for k, (_, exts) in EXTRA_KINDS.items() if ext in exts), None)
                if kind == "covers" and re.search(r"book|scan|inlay|cd\d|disc|tray", e.name, re.I):
                    kind = "booklets"
                if kind:
                    out.append({"kind": kind, "src": os.path.join(real, e.name), "to": to, "size": e.stat().st_size})
            except OSError:
                continue
    return out


_LIVE_RE = re.compile(r"\b(live|unplugged|in concert|concert|bootleg)\b|\(live|\[live", re.I)


def looks_live(c):
    """v1.1: a copy whose title, album or file name says it is a live version."""
    return bool(_LIVE_RE.search(" ".join(str(c.get(k) or "") for k in ("title", "album", "new_name", "name", "source"))))


def live_mismatch(cs):
    return len({looks_live(c) for c in cs}) > 1


def version_mismatch(cs):
    return len({mm.version_tags(c.get("title") or "") for c in cs}) > 1


def dup_sureness(cs, plan, inv, measured=None):
    """How sure the app is that these copies are the same song (0-100) and why. Sound first:
    identical audio data = 100; a measured fingerprint comparison = that %; otherwise an estimate from the
    MusicBrainz recording, the lengths and the titles."""
    if all(c.get("identical_audio") for c in cs[1:]):
        return 100, "identical audio"
    if measured and measured.get("pct") is not None:
        return int(measured["pct"]), "measured by sound"
    recs = {(plan.get(c["file_id"]) or {}).get("recording_id") for c in cs}
    lens = [(inv.get(c["file_id"]) or {}).get("duration") or c.get("length") or 0 for c in cs]
    spread = (max(lens) - min(lens)) if lens and all(lens) else 99
    base = 95 if len(recs) == 1 and None not in recs and "" not in recs else 85
    pct = base - (0 if spread <= 1 else 5 if spread <= 3 else 15 if spread <= 8 else 35)
    titles = {mm.title_key(mm.neutral(c.get("title") or "")) for c in cs}
    if len(titles) > 1:
        pct -= 10
    if any(c.get("identical_audio") for c in cs):
        pct = max(pct, 90)
    if live_mismatch(cs):                    # a live version next to a studio one is a different recording
        return min(pct, 55), "one copy looks like a live version"
    if version_mismatch(cs):                 # v1.1.5: demo / alternate / mono / remix next to the original = another version
        return min(pct, 60), "the titles name different versions of the song"
    return max(5, min(99, pct)), "estimate (lengths, titles, recording)"


def cache_dir():
    """Where the shared lookup memory is (same rule as the engine, read-only: nothing is created)."""
    for d in mm.up_dirs():
        if os.path.isdir(os.path.join(d, "_cache")):
            return os.path.join(d, "_cache")
    return os.path.join(mm.APP_DIR, "_cache")


def protected_inside(path):
    """Protected folders (e.g. THE MUSIC GOD FOLDER) that sit INSIDE a folder you add: they are skipped."""
    out = []
    try:
        for name in os.listdir(mm.lp(path)):
            if is_protected(name) and os.path.isdir(os.path.join(path, name)):
                out.append(os.path.join(path, name))
    except OSError:
        pass
    return out


# ----------------------------------------------------------------------------- the engine process

class Engine:
    """The engine runs in its own process (midnight_worker.py), so the window never freezes.
    Commands go out on cmd_q; progress, messages and answers come back on evt_q."""
    def __init__(self, app):
        self.app = app
        self.ctx = multiprocessing.get_context("spawn")
        self.ids = itertools.count(1)
        self.waiting = {}                    # call id -> [Event, value]
        self.proc = None
        self.lock = threading.Lock()

    def start(self):
        import midnight_worker
        self.cmd_q, self.evt_q = self.ctx.Queue(), self.ctx.Queue()
        self.stop_ev = self.ctx.Event()
        self.pause_ev = self.ctx.Event()
        self.proc = self.ctx.Process(target=midnight_worker.main, args=(self.cmd_q, self.evt_q, self.stop_ev, HERE, self.pause_ev),
                                     daemon=True, name="Midnight engine")
        self.proc.start()
        threading.Thread(target=self.pump, args=(self.evt_q,), daemon=True).start()

    def ensure(self):
        with self.lock:
            if not self.proc or not self.proc.is_alive():
                if self.proc:
                    self.app.log("(the engine had stopped - started it again)")
                    self.fail_all("The engine stopped unexpectedly and was restarted. Please try again.")
                self.start()

    def fail_all(self, msg):
        for cid, slot in list(self.waiting.items()):
            slot[1] = {"error": msg}
            slot[0].set()
        if self.app.job and not self.app.job.get("done"):
            self.app.finish_job(msg)

    def pump(self, q):
        while True:
            try:
                e = q.get(timeout=2)
            except Exception:
                if self.proc and not self.proc.is_alive():
                    self.fail_all("The engine stopped unexpectedly (out of memory?). Nothing was changed.")
                    return
                continue
            t = e.get("t")
            app = self.app
            if t == "log":
                app.log(e["line"])
            elif t == "progress":
                app.set_progress(e["p"])
            elif t == "stage":
                with app.lock:
                    if app.job:
                        app.job["stage"] = e["stage"]
                        if e.get("files") is not None:
                            app.job["files"] = e["files"]
                    app.progress = None
                    app.rev += 1
            elif t == "confirm":
                with app.lock:
                    app.confirm = {"id": e["id"], "question": e.get("question", ""), "details": e.get("details", [])}
                    app.rev += 1
            elif t == "confirm_done":
                with app.lock:
                    if app.confirm and app.confirm.get("id") == e.get("id"):
                        app.confirm = None
                    app.rev += 1
            elif t == "job_done":
                with app.lock:
                    app.confirm = None
                app.finish_job(e.get("error", ""))
            elif t == "status":
                with app.lock:
                    app.lookups_status = e.get("lookups", "")
                    app.rev += 1
            elif t == "result":
                slot = self.waiting.get(e["id"])
                if slot:
                    slot[1] = e["value"]
                    slot[0].set()

    def call(self, name, *args, timeout=600, wait=True):
        self.ensure()
        cid = next(self.ids)
        slot = [threading.Event(), None]
        if wait:
            self.waiting[cid] = slot
        self.cmd_q.put({"op": "call", "id": cid, "name": name, "args": list(args), "library": self.app.library})
        if not wait:
            return None
        ok = slot[0].wait(timeout)
        self.waiting.pop(cid, None)
        return slot[1] if ok else {"error": "No answer from the engine in time (the website may be slow). Please try again."}

    def job(self, kind, answers):
        self.ensure()
        self.stop_ev.clear()
        self.pause_ev.clear()
        self.cmd_q.put({"op": "job", "kind": kind, "library": self.app.library, "answers": answers, "id": next(self.ids)})

    def stop(self):
        if self.proc:
            self.pause_ev.clear()
            self.stop_ev.set()

    def answer(self, cid, yes):
        if self.proc:
            self.cmd_q.put({"op": "answer", "id": cid, "value": bool(yes)})

    def pause(self, on):
        if self.proc:
            (self.pause_ev.set if on else self.pause_ev.clear)()

    def quit(self):
        try:
            if self.proc and self.proc.is_alive():
                self.cmd_q.put({"op": "quit"})
                self.proc.join(8)
        except Exception:
            pass


# ----------------------------------------------------------------------------- the app's state + jobs

class App:
    def __init__(self):
        self.lock = threading.Lock()
        self.rev = 0
        self.approved_questions = set()
        self.engine = Engine(self)
        self.lookups_status = ""
        self.window = None
        self.job = None                       # {"kind","started","done","error","phases":[...]}
        self.progress = None
        self.lines = []
        self.memo = self._load_memo()
        self.last_library = self.memo.get("library", "")      # V2.0.5: remembered, but NO project opens by itself at start
        self.library = ""
        self.st, self.cfg = None, {}
        self.counts = {}                      # source path -> {"files": n, "counting": bool}
        self.whole = None                     # whole-computer search
        self.dropped = None                   # folders dropped from Explorer (desktop window)
        self.prep = None                      # 'Prepare Review' / 'Dig deeper': background searches
        self.vprep = None                     # V2.0.5 (#10): 'Verify with other sites' runs in its own lane, so it can run together with Prepare Previews
        self.confirm = None                   # an "Are you sure?" waiting for your answer
        self.pcindex = None                   # v1.1: PcIndex (every audio file on this PC, names only), made on first use
        self.phase_times = {}
        self.pending = []                     # v1.1: folders added while a job was running
        # V2.0.5: the app starts with no project open (Sources, empty). "Load session" brings a project back; choosing a
        # destination folder opens one too. The last project's folder is only remembered (memo) so it can be offered.

    # -- helpers
    def bump(self):
        with self.lock:
            self.rev += 1

    def log(self, line):
        with self.lock:
            self.lines.append(line)
            if len(self.lines) > 400:
                self.lines = self.lines[-400:]
            self.rev += 1

    def set_progress(self, p):
        with self.lock:
            self.progress = p
            lab = (p or {}).get("label") if isinstance(p, dict) else None
            if lab and lab != getattr(self, "_phase_label", None):      # v1.1: how long each part took (written to app_jobs.json)
                now_t = time.time()
                if getattr(self, "_phase_label", None):
                    self.phase_times[self._phase_label] = self.phase_times.get(self._phase_label, 0) + now_t - self._phase_t0
                self._phase_label, self._phase_t0 = lab, now_t
            self.rev += 1

    @staticmethod
    def _load_memo():
        try:
            with open(MEMO, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_memo(self):
        try:
            with open(MEMO, "w", encoding="utf-8") as f:
                json.dump(self.memo, f)
        except Exception:
            pass

    def _open_library(self, lib):
        """Same as the text menu's start: logs are always <library>\\_logs; config.json lives there."""
        logs = os.path.join(lib, "_logs")
        self.library = lib
        self.st = None
        self.cfg = {}
        if os.path.isdir(logs):               # read only; the folder is created when a scan starts
            self.st = mm.Store(logs)
            self.cfg = self.st.load("config.json", {})
        self.cfg["library"] = lib
        mm.SKIP_NESTED = bool(self.cfg.get("skip_nested"))
        if "alt_use" not in self.cfg:           # v1.1: services that need no key start ON (you still approve them in the scan dialog)
            self.cfg["alt_use"] = ["deezer", "itunes"]
            self.cfg.setdefault("alt_order", ["deezer", "itunes", "tidal", "discogs", "lastfm"])
            self.cfg.setdefault("covers", True)
            self.cfg.setdefault("lyrics", True)
        # v2.0: keys are remembered between sessions and between libraries (kept in your home folder, next to the library memo)
        saved = (self.memo.get("keys") or {}) if isinstance(self.memo.get("keys"), dict) else {}
        for k in KEY_FIELDS:
            if not (self.cfg.get(k) or "").strip() and (saved.get(k) or "").strip():
                self.cfg[k] = saved[k]
        if not self.cfg.get("sources_v203_done"):         # V2.0.3 decision 11: every source with a saved key is ON once (you can still turn it off), lyrics + covers ON
            self.cfg["sources_v203_done"] = True
            use = list(self.cfg.get("alt_use") or [])
            order = list(self.cfg.get("alt_order") or [])
            for key_, needs_ in (("spotify", ("spotify_id", "spotify_secret")), ("discogs", ("discogs_token",)), ("tidal", ("tidal_id", "tidal_secret")),
                                 ("lastfm", ("lastfm_key",)), ("deezer", ()), ("itunes", ())):
                if all((self.cfg.get(n_) or "").strip() for n_ in needs_):
                    if key_ not in use:
                        use.append(key_)
                    if key_ not in order:
                        order.append(key_)
            self.cfg["alt_use"], self.cfg["alt_order"] = use, order
            self.cfg["lyrics"], self.cfg["covers"] = True, True
        if not self.cfg.get("spotify_default_done"):     # v2.0: Spotify is on by default (only when its key is there; you can still turn it off)
            self.cfg["spotify_default_done"] = True
            if self.cfg.get("spotify_id") and self.cfg.get("spotify_secret"):
                use = list(self.cfg.get("alt_use") or [])
                if "spotify" not in use:
                    use.append("spotify")
                self.cfg["alt_use"] = use
                order = [x for x in (self.cfg.get("alt_order") or []) if x != "spotify"]
                if "lastfm" in order:
                    order.insert(order.index("lastfm"), "spotify")
                else:
                    order.append("spotify")
                self.cfg["alt_order"] = order

    def remember_keys(self):
        """Copies every key you typed into the home-folder memo so the next session / library does not ask again."""
        try:
            keys = dict(self.memo.get("keys") or {})
            for k in KEY_FIELDS:
                if (self.cfg.get(k) or "").strip():
                    keys[k] = self.cfg[k]
            if keys != self.memo.get("keys"):
                self.memo["keys"] = keys
                self._save_memo()
        except Exception:
            pass

    def _ensure_store(self):
        logs = os.path.join(self.library, "_logs")
        os.makedirs(mm.lp(logs), exist_ok=True)
        if not self.st:
            self.st = mm.Store(logs)
            old = self.st.load("config.json", {})
            old.update(self.cfg)
            self.cfg = old
        self.cfg["library"] = self.library
        for t in ("ffmpeg", "fpcalc"):            # v1.1: an empty or stale path is looked for again (a hand-picked file wins)
            cur = self.cfg.get(t) or ""
            ch = mm._chosen_tool(t)
            if ch:
                self.cfg[t] = ch
            elif not cur or (not os.path.isfile(cur) and not mm.shutil.which(cur)):
                self.cfg[t] = mm.find_tool(t)
        self.st.save("config.json", self.cfg)
        self.memo.update(logs=self.st.logs, library=self.library)
        self._save_memo()

    def busy(self):
        return bool(self.job and not self.job.get("done"))

    # -- sources
    def sources(self):
        return [dict(s) for s in self.cfg.get("sources", [])]

    def excludes(self):
        return list(self.cfg.get("excludes", []))

    def _count_source(self, path):
        def run():
            n = 0
            ex = self.excludes() + mm.protected_dirs(self.cfg)
            try:
                for _ in mm.walk_music(path, True, ex):
                    n += 1
                    if n % 200 == 0:
                        with self.lock:
                            self.counts[path] = {"files": n, "counting": True}
                            self.rev += 1
            except Exception:
                pass
            with self.lock:
                self.counts[path] = {"files": n, "counting": False}
                self.rev += 1
        with self.lock:
            self.counts[path] = {"files": 0, "counting": True}
        threading.Thread(target=run, daemon=True).start()

    def save_cfg(self):
        if self.st:
            self.st.save("config.json", self.cfg)
        self.remember_keys()

    # -- Review decisions: <library>\_logs\app_decisions.json (one entry per song, your own choices)
    def inv_map(self):
        """The scan (inventory) by file id, kept in memory until the file changes."""
        if not self.st:
            return {}
        try:
            mt = os.path.getmtime(self.st.p("inventory.json"))
        except OSError:
            return {}
        c = getattr(self, "_inv_cache", None)
        if not c or c[0] != (self.st.logs, mt):
            self._inv_cache = c = ((self.st.logs, mt), {r["id"]: r for r in self.st.cached("inventory.json", [])})
        return c[1]

    def decisions(self):
        """Batch 01 speed: your choices are read from disk only when the file changed (it used to be read on every click)."""
        if not self.st:
            return {}
        path = self.st.p("app_decisions.json")
        try:
            stt = os.stat(mm.lp(path))
        except OSError:
            self._dec_cache = None
            return {}
        key = (path, stt.st_mtime_ns, stt.st_size)
        c = getattr(self, "_dec_cache", None)
        if c and c[0] == key:
            return dict(c[1])
        val = self.st.load("app_decisions.json", {})
        self._dec_cache = (key, val)
        return dict(val)

    def save_decisions(self, d):
        if self.st:
            with self.lock:
                path = self.st.p("app_decisions.json")
                tmp = self.st.p(f"app_decisions.json.{threading.get_ident()}.tmp")
                with open(mm.lp(tmp), "w", encoding="utf-8") as f:           # compact: several times faster than the indented file
                    json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(mm.lp(tmp), mm.lp(path))
                try:
                    stt = os.stat(mm.lp(path))
                    self._dec_cache = ((path, stt.st_mtime_ns, stt.st_size), dict(d))
                except OSError:
                    self._dec_cache = None

    # -- 'Not one album': folders / album tags whose songs are matched one by one
    def mixed(self):
        return set(self.st.load("app_mixed.json", [])) if self.st else set()

    def save_mixed(self, ids):
        if self.st:
            self.st.save("app_mixed.json", sorted(ids))

    # -- Prepare Review: results of the background searches, <library>\_logs\review_prep.json
    def prep_results(self):
        if not self.st:
            return {}
        c = getattr(self, "_prep_cache", None)
        if c is None or c[0] != self.st.logs:
            self._prep_cache = c = (self.st.logs, self.st.load("review_prep.json", {}))
        return c[1]

    def verify_results(self):
        """V2.0.3: second-source checks, <library>\\_logs\\review_verify.json  {file id: {n, sources, differ, t}}"""
        if not self.st:
            return {}
        c = getattr(self, "_ver_cache", None)
        if c is None or c[0] != self.st.logs:
            self._ver_cache = c = (self.st.logs, self.st.load("review_verify.json", {}))
        return c[1]

    def finish_job(self, error=""):
        if self.st:                           # the engine may have saved settings (e.g. sources): read them again
            self.cfg = self.st.load("config.json", self.cfg)
            self.cfg["library"] = self.library
        with self.lock:
            if self.job:
                self.job["done"], self.job["error"], self.job["finished"] = True, error, time.time()
            self.rev += 1
            job = dict(self.job) if self.job else None
        if job and self.st:
            try:
                nm = self.JOB_NAMES.get(job["kind"], job["kind"])
                secs = round(job["finished"] - job.get("started", job["finished"]))
                if error:
                    low = error.lower()
                    stopped = any(w in low for w in ("stop", "cancel", "interrupt", "engine"))
                    self.activity("job", f"{nm} {'interrupted' if stopped else 'failed'}: {error.splitlines()[0][:160]}",
                                  "interrupted" if stopped else "failed", job["kind"])
                else:
                    extra = ""
                    if job["kind"] == "copy":
                        nf = len([e for e in self.st.load("copy_failures.json", []) if e.get("src")])
                        extra = f", {nf} not copied" if nf else ""
                    self.activity("job", f"{nm} finished in {secs // 60}m{secs % 60:02d}s{extra}", "ok" if not extra else "attention", job["kind"])
            except Exception:
                pass
        if job and not error and job.get("kind") in ("scan", "update") and job.get("speed") == "complete" and self.cfg.get("auto_search", True):
            self.auto_search()                # V2.0.3: Complete scan = Prepare Previews, then Dig deeper, started on their own
        if job and self.st:                   # how long it took (shown on the Dashboard, also after a restart)
            try:
                lj = self.st.load("app_jobs.json", {})
                if getattr(self, "_phase_label", None):
                    self.phase_times[self._phase_label] = self.phase_times.get(self._phase_label, 0) + time.time() - self._phase_t0
                lj[job["kind"]] = {"finished": job["finished"], "seconds": round(job["finished"] - job.get("started", job["finished"])),
                                   "error": error, "parts": {k: round(v) for k, v in self.phase_times.items()}}
                self.phase_times, self._phase_label = {}, None
                self.st.save("app_jobs.json", lj)
            except Exception:
                pass

    def auto_search(self):
        """After a Complete scan: Prepare Previews and then Dig deeper start by themselves (one after the other, in the background,
        the same read-only searches as the buttons). Cancel on the Review page stops the chain."""
        def run():
            # V2.0.5 (#12): the activity line now says what REALLY happened (searched / nothing to do / stopped / error), not just "ran"
            outcomes, problem = [], False
            try:
                time.sleep(3)
                api = Api()
                for label, fn in (("Prepare Previews", api.prep_start), ("Dig deeper", api.dig_start)):
                    r = fn()
                    if isinstance(r, dict) and r.get("error"):
                        outcomes.append(f"{label}: not run ({r['error']})")
                        continue
                    p_ = self.prep
                    while p_ and not p_.finished:
                        time.sleep(2)
                    st_ = p_.state() if p_ else {}
                    err_ = getattr(p_, "error", "") if p_ else ""
                    if p_ and p_.cancel.is_set():
                        outcomes.append(f"{label}: stopped by you after {st_.get('done', 0)} of {st_.get('total', 0)} songs")
                        problem = True
                        break
                    outcomes.append(f"{label}: searched {st_.get('done', 0)} of {st_.get('total', 0)} songs, {st_.get('found', 0)} with results"
                                    + (f" (stopped by an error: {err_})" if err_ else ""))
                    problem = problem or bool(err_)
                self.activity("job", "After the Complete scan: " + " · ".join(outcomes or ["nothing to do"]), "needs a look" if problem else "ok", "scan")
            except Exception as e:
                self.log(f"Automatic search stopped: {type(e).__name__}: {e}")
                self.activity("job", "After the Complete scan the automatic search stopped: " + f"{type(e).__name__}: {e}", "error", "scan")
        threading.Thread(target=run, daemon=True).start()

    JOB_NAMES = {"scan": "Scan", "update": "Update", "fastupdate": "Quick update", "copy": "Copy & tag", "archive": "Archive",
                 "loonybin": "Duplicate copies", "neat": "Neat Picky", "analyze": "Analyze"}

    def activity(self, kind, text, result="ok", where=""):
        """1.1.7: one line in the Activity log (time, what happened, result). Best effort: never stops anything."""
        if not self.st:
            return
        try:
            with self.lock:
                log = self.st.load("app_activity.json", [])
                log.append({"t": time.time(), "kind": kind, "text": text, "result": result, "where": where, "seen": False})
                self.st.save("app_activity.json", log[-2000:])
        except Exception:
            pass

    def preload(self):
        """Load the lookup memory in the engine process in the background (the window stays usable)."""
        if self.st and self.cfg.get("use_mb", True) and self.st.cached("inventory.json", None) is not None:
            self.lookups_status = "loading"
            self.engine.call("preload", wait=False)



APP = App()


# ----------------------------------------------------------------------------- whole-computer search

JUNK_APP = re.compile(r"(^|[\\/])(steam|steamapps|steamlibrary|epic games|games?|riot games|ubisoft|origin|gog galaxy|battle\.net|"
                      r"cache|caches|logs?|drivers?|android|sdk|unity|unreal|resources|assets|sounds?|sfx|"
                      r"notifications?|ringtones?|alarms?|ui|plugins?|vst\d*|samples?|soundbanks?|\.cache)([\\/]|$)", re.I)
JUNK_VOICE = re.compile(r"(whatsapp|telegram|viber|signal|voice ?(memos?|notes?|recorder|messages?)|recordings?|recorder|"
                        r"call ?recordings?|voicemail|podcasts?|audiobooks?|audible|lectures?|dictation)", re.I)
VOICE_EXTS = {".amr", ".opus", ".m4b", ".3gp", ".aa", ".aax"}


def junk_reason(dirpath, files):
    """Why a folder with audio files is probably not music (it is still listed, set to Skip)."""
    if JUNK_VOICE.search(dirpath):
        return "voice / podcast / audiobook"
    exts = [os.path.splitext(f)[1].lower() for f, _ in files]
    if exts and sum(e in VOICE_EXTS for e in exts) * 2 > len(exts):
        return "voice / podcast / audiobook"
    if JUNK_APP.search(dirpath):
        return "app / game / system sounds"
    sizes = sorted(sz for _, sz in files)
    if sizes and sizes[len(sizes) // 2] < 500_000:
        return "sound effects (short files)"
    if sum(1 for sz in sizes if sz >= 1_000_000) < 5 and len(sizes) < 5:
        return "fewer than 5 songs"
    return ""


class WholeScan:
    """Walks every drive (read-only), skipping system folders, the library and the archive. Folders that hold
    music are reported as they are found, with the folders above them, so the tree grows live."""
    def __init__(self, app):
        self.app = app
        self.nodes, self.index = [], {}
        self.done = False
        self.cancel = threading.Event()
        self.folder = ""
        self.seen_dirs = 0
        self.songs = 0
        self.junk = 0
        self.roots = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if mm.IS_WIN else ["/"]
        if not mm.IS_WIN and os.environ.get("MIDNIGHT_TEST_ROOT"):
            self.roots = [os.environ["MIDNIGHT_TEST_ROOT"]]
        self.root_i = 0
        threading.Thread(target=self.run, daemon=True).start()

    @staticmethod
    def top_of(path):
        drive, rest = os.path.splitdrive(path)
        parts = [p for p in re.split(r"[\\/]", rest) if p]
        k = 3 if len(parts) >= 3 and parts[0].lower() in ("users", "home") else 2
        if not mm.IS_WIN and os.environ.get("MIDNIGHT_TEST_ROOT"):
            base = os.environ["MIDNIGHT_TEST_ROOT"].rstrip("/")
            rel = [p for p in path[len(base):].split("/") if p]
            return base + "/" + "/".join(rel[:1]) if rel else base
        return os.path.join(drive + os.sep, *parts[:k]) if parts else drive + os.sep

    def _node(self, path, own=0, top=False):
        key = os.path.normcase(path)
        if key in self.index:
            return self.index[key]
        parent = None if top else os.path.dirname(path)
        n = {"id": path, "name": os.path.basename(path.rstrip("\\/")) or path, "parent": parent, "own": own,
             "top": top, "protected": bool(is_protected(path))}
        self.index[key] = n
        self.nodes.append(n)
        return n

    def add_music_dir(self, path, n):
        top = self.top_of(path)
        chain, p = [], path
        while os.path.normcase(p) != os.path.normcase(top) and len(p) > len(top):
            chain.append(p)
            p = os.path.dirname(p)
        self._node(top, n if os.path.normcase(path) == os.path.normcase(top) else 0, top=True)
        for p in reversed(chain):
            self._node(p, n if p == path else 0)

    def run(self):
        ex = mm.protected_dirs(self.app.cfg)
        for i, r in enumerate(self.roots):
            self.root_i = i
            for dirpath, dirnames, filenames in os.walk(r):
                if self.cancel.is_set():
                    break
                dirnames[:] = sorted(d for d in dirnames if not mm.is_skipped_dir(os.path.join(dirpath, d), d, ex))
                self.seen_dirs += 1
                self.folder = dirpath
                aud = [fn for fn in filenames if os.path.splitext(fn)[1].lower() in mm.AUDIO_EXTS]
                n = len(aud)
                if n:
                    files = []
                    for fn in aud[:200]:
                        try:
                            files.append((fn, os.path.getsize(os.path.join(dirpath, fn))))
                        except OSError:
                            pass
                    why = junk_reason(dirpath, files)
                    with self.app.lock:
                        self.add_music_dir(dirpath, n)
                        self.index[os.path.normcase(dirpath)]["junk"] = why
                        if not why:
                            self.songs += n
                        else:
                            self.junk += n
                if self.seen_dirs % 50 == 0 or n:
                    self.app.bump()
        self.done = True
        self.app.bump()

    def state(self, since):
        with self.app.lock:
            new = self.nodes[since:]
            return {"nodes": new, "count": len(self.nodes), "done": self.done, "cancelled": self.cancel.is_set(),
                    "folder": self.folder, "dirs": self.seen_dirs, "songs": self.songs, "junk": self.junk,
                    "pct": round(100 * (self.root_i + (1 if self.done else 0.5)) / max(1, len(self.roots))),
                    "roots": self.roots}


# ----------------------------------------------------------------------------- scan & identify (Phase 1 + 2)

SERVICE_INFO = [
    {"key": "mb", "name": "MusicBrainz", "site": "musicbrainz.org", "needs": "",
     "sends": "artist, album and song names and song length (text only). About 1 question per second; answers are cached."},
    {"key": "acoustid", "name": "Identify by sound (AcoustID)", "site": "api.acoustid.org", "needs": "acoustid_key",
     "sends": "a fingerprint computed on your PC (a list of numbers, not the audio) and the song length, only for songs not found by name."},
    {"key": "discogs", "name": "Discogs", "site": "api.discogs.com", "needs": "discogs_token",
     "sends": "artist, album and song names, only for songs MusicBrainz cannot identify."},
    {"key": "deezer", "name": "Deezer", "site": "api.deezer.com", "needs": "",
     "sends": "artist, album and song names, only for songs MusicBrainz cannot identify."},
    {"key": "itunes", "name": "Apple Music / iTunes", "site": "itunes.apple.com", "needs": "",
     "sends": "artist and song names, only for songs MusicBrainz cannot identify (about 20 per minute)."},
    {"key": "tidal", "name": "Tidal (beta)", "site": "openapi.tidal.com", "needs": "tidal_id",
     "sends": "artist, album and song names, only for songs MusicBrainz cannot identify. Needs a Client ID + Secret."},
    {"key": "spotify", "name": "Spotify (search)", "site": "api.spotify.com", "needs": "spotify_id",
     "sends": "artist and song names, only for songs MusicBrainz cannot identify. Needs a free Client ID + Secret (no Spotify login). Pasting a Spotify link needs nothing."},
    {"key": "lastfm", "name": "Last.fm", "site": "ws.audioscrobbler.com", "needs": "lastfm_key",
     "sends": "artist, album and song names, asked last, only for songs no other site found."},
    {"key": "covers", "name": "Cover art", "site": "Deezer, Apple Music, Cover Art Archive, Discogs", "needs": "",
     "sends": "artist and album names (same release only). Covers are fetched later, during Copy & tag."},
    {"key": "lyrics", "name": "Lyrics (LRCLIB)", "site": "lrclib.net", "needs": "",
     "sends": "artist, song and album names and length. Fetched later, during Copy & tag."},
]


def services_from_cfg(cfg):
    use = cfg.get("alt_use", [])
    return {"mb": cfg.get("use_mb", True), "contact": cfg.get("mb_contact", ""),
            "acoustid": bool(cfg.get("acoustid_key")) and not cfg.get("acoustid_off"),
            "acoustid_key": cfg.get("acoustid_key", ""),
            "discogs": "discogs" in use, "discogs_token": cfg.get("discogs_token", ""),
            "deezer": "deezer" in use, "itunes": "itunes" in use,
            "lastfm": "lastfm" in use, "lastfm_key": cfg.get("lastfm_key", ""),
            "tidal": "tidal" in use, "tidal_id": cfg.get("tidal_id", ""), "tidal_secret": cfg.get("tidal_secret", ""),
            "spotify": "spotify" in use, "spotify_id": cfg.get("spotify_id", ""), "spotify_secret": cfg.get("spotify_secret", ""),
            "covers": cfg.get("covers", False), "lyrics": cfg.get("lyrics", False),
            "analyze": cfg.get("analyze", True), "sort_mode": cfg.get("sort_mode", "simple")}


def start_job(opts, update=False):
    """Scan & identify (Phase 1 + 2), or only 'update the plan' (Phase 2 again, with your Review choices;
    every answer is cached, so it is quick). Both are read-only. The work runs in the engine process."""
    app = APP
    with app.lock:
        app.job = {"kind": "update" if update else "scan", "started": time.time(), "done": False, "error": "",
                   "stage": "identify" if update else "read",
                   "mode": app.cfg.get("scan_mode", "simple") if update else opts.get("mode", "simple")}
        app.progress = None
        app.lines = []
        app.job["speed"] = (opts.get("services") or {}).get("speed") or "complete"     # V2.0.3: a Complete scan also searches on its own afterwards
        app.rev += 1
    try:
        app._ensure_store()
        if not update:
            app.cfg["scan_mode"] = opts.get("mode", "simple")
            # your Review choices are kept for the same files (a file keeps its id by its path);
            # songs no longer in your sources simply do not appear in the new Review list
        if not update and app.cfg.get("sources"):
            app.cfg["last_sources"] = [dict(x) for x in app.cfg["sources"]]
        app.save_cfg()
        app.engine.job("update" if update else "scan", dict(opts.get("services") or services_from_cfg(app.cfg)))
    except Exception as e:
        app.log(f"Error: {type(e).__name__}: {e}")
        app.finish_job(f"{type(e).__name__}: {e}")


# ----------------------------------------------------------------------------- ONE definition of every count (V2.0.5, #2)

COPIED_STATES = ("copied", "verified", "original_archived")


def copied_ids(app):
    """file ids whose copy already exists in the library (from the provenance log)."""
    if not app.st:
        return set()
    return {r["file_id"] for r in prov_rows(app.st) if r.get("status") in COPIED_STATES}


def song_state(it, dec, copied):
    """The single place that says what a planned song is. Every screen (Dashboard, Review sidebar, Plan, Copy & tag,
    Check tags, Library) must use this and nothing else:
      skip     - not music we sort (kept out of every count)
      copied   - already copied into the library
      extra    - extra copy left out on purpose (duplicate)
      ready    - approved in the plan, will be copied
      decided  - you decided it in Review; it joins the plan at the next Update plan
      later    - you left it for later (still needs you)
      waiting  - still needs you (not decided, or "Not this")"""
    if it.get("kind") == "skip" or it.get("action") in ("keep", "skip"):
        return "skip"
    if it["file_id"] in copied:
        return "copied"
    if it.get("dup_extra"):
        return "extra"
    if it.get("approved") or it.get("fixed"):
        return "ready"
    act = (dec.get(it["file_id"]) or {}).get("action")
    if act == "later":
        return "later"
    if act and act != "reject":
        return "decided"
    return "waiting"


def song_counts(app, plan=None):
    """All the numbers in one pass. waiting = songs that still need you (waiting + later)."""
    if not app.st:
        return {}
    plan = app.st.cached("plan.json", []) if plan is None else plan
    dec, cp = app.decisions(), copied_ids(app)
    c = Counter()
    kinds = Counter()
    for it in plan:
        s_ = song_state(it, dec, cp)
        c[s_] += 1
        if s_ in ("waiting", "later"):
            kinds["check" if it.get("verified") else "place" if it.get("kind") == "artist_unverified" else "none"] += 1
    out = {k: c[k] for k in ("skip", "copied", "extra", "ready", "decided", "later", "waiting")}
    out["needs_you"] = c["waiting"] + c["later"]
    out["songs"] = len(plan) - c["skip"]
    out["check"], out["place"], out["none"] = kinds["check"], kinds["place"], kinds["none"]
    return out


# ----------------------------------------------------------------------------- dashboard numbers

TIER_ORDER = [mm.TIER_GOLD, mm.TIER_GETTO, mm.TIER_START, mm.TIER_SCAT, mm.TIER_UNK, mm.TIER_CLASSICAL]


def dashboard():
    app = APP
    out = {"library": app.library, "has_scan": False}
    if not app.st:
        return out
    st = app.st
    inv = st.cached("inventory.json", [])
    plan = st.cached("plan.json", [])
    out.update(scanned=len(inv), has_scan=bool(inv), has_plan=bool(plan))
    try:
        out["last_run"] = time.strftime("%d %b %Y %H:%M", time.localtime(os.path.getmtime(st.p("plan.json" if plan else "inventory.json"))))
    except OSError:
        out["last_run"] = ""
    dec = app.decisions()
    cp = copied_ids(app)
    waiting = [it for it in plan if song_state(it, dec, cp) in ("waiting", "later")]       # V2.0.5 (#2): the one shared definition
    out["counts"] = song_counts(app, plan)
    out.update(confirmed=sum(1 for it in plan if it.get("verified")),
               waiting=len(waiting),
               unverified=sum(1 for it in plan if it.get("kind") in ("unverified", "artist_unverified")),
               approved=sum(1 for it in plan if it["approved"] and it.get("action") not in ("keep", "skip")),
               dup_extra=sum(1 for it in plan if it.get("dup_extra")),
               skipped=sum(1 for it in plan if it.get("kind") == "skip"),
               sort_mode=app.cfg.get("sort_mode", "simple"), scan_mode=app.cfg.get("scan_mode", "simple"))
    prov = prov_rows(st)
    pc = Counter(r.get("status") for r in prov)
    songs = [it for it in plan if it.get("kind") != "skip"]
    out["songs"] = len(songs)
    out["last_jobs"] = st.load("app_jobs.json", {})
    out["sorted_pct"] = round(100 * (len(songs) - len(waiting)) / len(songs)) if songs else 0
    # honest numbers: extra copies (left out on purpose) are not failures
    real = [it for it in songs if not it.get("dup_extra")]
    kinds = Counter()
    for it in waiting:
        kinds["check" if it.get("verified") else "place" if it.get("kind") == "artist_unverified" else "none"] += 1
    out["breakdown"] = {"songs": len(real), "found": sum(1 for it in real if it.get("verified") or it.get("kind") == "artist_unverified"),
                        "placed": sum(1 for it in real if it.get("approved")), "check": kinds["check"], "place": kinds["place"],
                        "none": kinds["none"], "left_out": sum(1 for it in real if (dec.get(it["file_id"]) or {}).get("action") == "leave"),
                        "later": sum(1 for it in real if (dec.get(it["file_id"]) or {}).get("action") == "later"),
                        "extra_copies": out["dup_extra"]}
    out["confirmed_pct"] = round(100 * out["confirmed"] / len(songs)) if songs else 0
    try:                                    # the scan read new files but the plan is from an older run
        out["plan_stale"] = bool(plan) and os.path.getmtime(st.p("plan.json")) < os.path.getmtime(st.p("inventory.json")) - 1
    except OSError:
        out["plan_stale"] = False
    out["copied"] = pc["verified"] + pc["copied"] + pc["original_archived"]
    out["archived"] = pc["original_archived"]
    an = st.cached("analysis.json", {})
    if an:
        tc = Counter()
        for a in an.get("artists", []):
            tc[a.get("tier", "")] += 1
        tiers = []
        for t in TIER_ORDER:
            short = t.split(" ", 1)[1]
            tiers.append({"name": t, "short": short, "count": tc.get(short, 0)})
        out["tiers"] = tiers
        out["summary"] = an.get("summary", {})
        arts = sorted(an.get("artists", []), key=lambda r: -(r.get("songs") or 0))
        real = {(r["artist"], r["album"]) for r in an.get("albums", []) if r.get("type") not in ("Comp", "Box", "Single")}
        out["top_artists"] = [{"artist": r["artist"], "songs": r.get("songs", 0), "releases": r.get("releases", 0),
                               "complete": r.get("complete_releases", 0), "tier": r.get("tier", ""),
                               "studio": f"{r['studio_complete']} of {r['studio_total']}" if r.get("studio_total") else ""}
                              for r in arts[:10]]
        # 1.1.5: "Top albums" (Almost complete lives only in Analyze): complete albums first, then the biggest ones
        tops = sorted([x for x in an.get("albums", []) if (x["artist"], x["album"]) in real and x.get("tracks_owned")],
                      key=lambda x: (not x.get("complete"), -(x.get("tracks_owned") or 0), -(x.get("percent") or 0)))
        out["top_albums"] = [{"artist": r["artist"], "album": r["album"], "have": r.get("tracks_owned", 0), "total": r.get("tracks_total", 0),
                              "percent": r.get("percent", 0), "complete": bool(r.get("complete")), "year": r.get("year", "")} for r in tops[:8]]
    return out


# ----------------------------------------------------------------------------- Review

def _tags(r):
    t = r.get("tags") or {}
    return {k: t.get(k, "") for k in ("artist", "albumartist", "album", "title", "track", "year", "genre")}


def review_kind(it):
    if it.get("kind") in ("release", "singles") and it.get("verified"):
        return "match"
    if it.get("kind") == "artist_unverified":
        return "place"
    if it.get("kind") == "unverified":
        return "none"
    return ""


def _is_classical_row(it, h, tags):
    """V2.0.5: for the Review's Classical filter (a filter, not a separate tab): the plan says classical, or the tags / genre / title say so."""
    if it.get("classical"):
        return True
    try:
        return bool(mm.classical_by_words(h, (it.get("genre") or tags.get("genre") or ""), tags.get("album") or ""))
    except Exception:
        return "classic" in str(tags.get("genre") or "").lower()


def _review_row(app, it, k, r):
    """One Review row from the plan (the slow part: hints, 'sure'); kept in memory until the song changes."""
    fid = it["file_id"]
    h = mm.hints(r) if r else {}
    tags = _tags(r)
    x = {"id": fid, "kind": k, "file": os.path.basename(it["src"]), "folder": os.path.dirname(it["src"]),
         "duration": round(r.get("duration") or it.get("duration") or 0), "tags": tags, "reason": it.get("reason", ""),
         "ext": it.get("ext", ""), "bitrate": r.get("bitrate", 0),
         "q": [h.get("artist") or tags["artist"], h.get("title_plain") or tags["title"] or os.path.splitext(os.path.basename(it["src"]))[0],
               h.get("album") or h.get("folder_album") or ""],
         "dest": it.get("new_path", ""), "match_pct": it.get("match_percent"),
         "dup_possible": it.get("dup_possible", ""),
         "classical": _is_classical_row(it, h, tags),
         "composer": it.get("composer", "") or (h.get("composer") or ""),
         "g_album": (tags["album"] or h.get("folder_album") or "").strip(),
         "g_artist": (tags["albumartist"] or h.get("artist") or tags["artist"] or "").strip()}
    if k == "match":
        x["suggest"] = {"title": it.get("title", ""), "artist": it.get("display_artist") or it.get("credited", ""),
                        "release": it.get("album", ""), "rtype": it.get("rtype", ""), "year": it.get("year", ""),
                        "track": it.get("track", ""), "disc": it.get("disc", ""), "disctotal": it.get("disctotal", ""),
                        "tracktotal": it.get("tracktotal", ""), "source": it.get("data_source", ""), "mbid": it.get("mbid", ""),
                        "cover_url": it.get("cover_url", ""), "genre": it.get("genre", "")}
        x["rel_key"] = it.get("release_id") or f"{it.get('album', '')}|{it.get('credited', '')}"
        x["warn"] = next((n_ for n_ in it.get("notes") or [] if "missing in the match" in n_), "")
        x["classical"] = bool(it.get("classical"))
        x["composer"] = it.get("composer", "")
        mine_t = tags["title"] or h.get("title_plain") or ""
        # 'sure': same song title, same version, same artist -> 'Accept if' may take it
        x["sure"] = bool(mine_t) and mm.same_song_title(mine_t, it.get("title", "")) >= 0.88 and \
            not mm.different_version(mine_t, it.get("title", ""), "", r.get("filename", "")) and \
            (not tags["artist"] or mm.artist_agrees([x["suggest"]["artist"] or ""], tags["artist"]))
        # V2.0.4: an edition / version word of the file (Remaster, Deluxe, Original Version, Version 2 ...) that the match lost is never 'sure'
        lost = mm.edition_words_of(f"{tags['album']} {mine_t}") - mm.edition_words_of(f"{x['suggest']['release']} {x['suggest']['title']}") - {"stereo"}
        if lost:
            x["sure"] = False
            x["warn"] = x["warn"] or "edition / version word of your file is missing in the match: " + ", ".join(sorted(lost))
    elif k == "place":
        x["artist_found"] = it.get("entity") or it.get("credited", "")
        x["artist_id"] = it.get("artist_id", "")
        x["source"] = it.get("data_source", "")
        x["release_found"] = it.get("album", "") if it.get("verified") else ""
    else:
        no_tags = not any(tags[f] for f in ("artist", "title", "album"))
        x["why"] = ("No tags and a plain file name, so there was nothing to search with." if no_tags and not h.get("artist")
                    else "Not found on MusicBrainz" + (" or the other sites you allowed." if app.cfg.get("alt_use") else "."))
    return x


def review_list():
    app = APP
    if not app.st:
        return {"items": [], "plan_time": 0}
    st = app.st
    plan = st.cached("plan.json", [])
    inv = app.inv_map()
    dec = app.decisions()
    try:
        plan_time = os.path.getmtime(st.p("plan.json"))
    except OSError:
        plan_time = 0
    out, by_folder = [], Counter()
    memo = getattr(app, "_rl_memo", None)
    ikey = getattr(app, "_inv_cache", (None,))[0]
    if not memo or memo[0] != ikey:
        memo = app._rl_memo = (ikey, {})
    memo = memo[1]
    for it in plan:
        fid = it["file_id"]
        d = dec.get(fid)
        needs = not it["approved"] and not it.get("fixed") and not it.get("dup_extra") and it.get("kind") != "skip"
        if not needs and not d:
            continue
        k = (d or {}).get("kind0") or review_kind(it)
        if not k:
            continue
        key = (k, it.get("title"), it.get("album"), it.get("display_artist"), it.get("credited"), it.get("match_percent"),
               it.get("data_source"), it.get("release_id"), it.get("reason"), it.get("new_path"), it.get("entity"), it.get("year"), it.get("track"), it.get("dup_possible"))
        hit = memo.get(fid)
        if hit and hit[0] == key:
            x = dict(hit[1])
        else:
            x = _review_row(app, it, k, inv.get(fid) or {})
            memo[fid] = (key, x)
            x = dict(x)
        x["decision"] = d
        if k == "none":
            by_folder[x["folder"]] += 1
        out.append(x)
    for x in out:
        if x["kind"] == "none":
            x["same_folder"] = by_folder[x["folder"]] - 1
    prep = app.prep_results()
    mixed = app.mixed()
    for x in out:
        pr = prep.get(x["id"])
        if pr:
            x["prep"] = len(pr.get("results") or [])
            x["dig"] = bool(pr.get("dig"))
            top = (pr.get("results") or [None])[0]
            if prep_sure(x, top):
                x["prep_sure"] = top
        x["mixed"] = x["id"] in mixed
        vr = app.verify_results().get(x["id"])
        if vr:
            x["verify"] = {"n": vr.get("n", 0), "sources": vr.get("sources") or [], "differ": vr.get("differ") or []}
        x["safe"] = bool(x["kind"] == "match" and x.get("sure") and vr and vr.get("n", 0) >= 2 and not x.get("warn"))
    decided_after = max([d.get("t", 0) for d in dec.values()] + [0])
    return {"items": out, "plan_time": plan_time, "stale": decided_after > plan_time,
            "acoustid": bool(app.cfg.get("acoustid_key")) and bool(mm.find_tool("fpcalc")),
            "sites": (["MusicBrainz"] if app.cfg.get("use_mb", True) else []) +
                     [mm.ALT_NAMES[k] for k in mm.full_alt_order(app.cfg) if k in app.cfg.get("alt_use", [])],
            "covers": bool(app.cfg.get("covers")), "cover_base": AUDIO.base + "cover/" if AUDIO else ""}


class Prep:
    """'Prepare Review': searches every Place, No album and set-aside song in the background (one at a time,
    through the same engine queue as your own searches, so the sites' speed limits are kept). Read-only."""
    def __init__(self, app, ids, mode="prep"):
        self.app, self.ids, self.mode = app, ids, mode       # mode 'dig' = Dig deeper for songs nobody recognized
        self.done, self.found, self.sure, self.cur = 0, 0, 0, ""
        self.paused, self.cancel, self.finished = threading.Event(), threading.Event(), False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        """v2.0: whatever happens (an engine timeout, an error), what was found so far is saved and the run ends cleanly, so Prepare Review can be started again later."""
        try:
            self._run()
        except Exception as e:
            app = self.app
            try:
                app.st.save("review_verify.json" if self.mode == "verify" else "review_prep.json",
                            getattr(self, "res", None) or (app.verify_results() if self.mode == "verify" else app.prep_results()))
            except Exception:
                pass
            self.error = f"{type(e).__name__}: {e}"
        finally:
            self.finished = True
            self.app.bump()

    def _run(self):
        """V2.0.3 decision 17: up to 4 songs at once (each site keeps its own speed limit; MusicBrainz max 1 request per second)."""
        app = self.app
        items = {x["id"]: x for x in review_list()["items"]}
        verify = self.mode == "verify"
        res = self.res = app.verify_results() if verify else app.prep_results()
        fname = "review_verify.json" if verify else "review_prep.json"
        lock = threading.Lock()
        state = {"last_save": time.time()}

        def work(fid):
            while self.paused.is_set() and not self.cancel.is_set():
                time.sleep(0.3)
            if self.cancel.is_set():
                return
            x = items.get(fid)
            if not x:
                return
            q = x["q"]
            self.cur = f"{q[0]} - {q[1]}" if q[0] else q[1]
            try:
                if verify:
                    r = app.engine.call("verify_bg", fid, timeout=900)
                    if r and not r.get("error"):
                        with lock:
                            res[fid] = r
                            if r.get("n", 0) >= 2:
                                self.sure += 1
                            self.found += 1
                elif self.mode == "dig":
                    r = app.engine.call("dig_bg", fid, None, timeout=1800)
                    found = (r or {}).get("results") or []
                    with lock:
                        res[fid] = {"results": found[:12], "t": time.time(), "dig": True, "steps": (r or {}).get("steps") or []}
                        if found:
                            self.found += 1
                            if prep_sure(x, found[0]):
                                self.sure += 1
                elif (q[1] or "").strip():
                    r = app.engine.call("search_bg", fid, q[0], q[1], q[2], False, timeout=900)
                    found = (r or {}).get("results") or []
                    if not found and app.cfg.get("acoustid_key") and not app.cfg.get("acoustid_off") and mm.find_tool("fpcalc"):
                        try:                          # v1.1.4: nothing by name -> identify by sound (a fingerprint + the length go to AcoustID)
                            r2 = app.engine.call("sound_bg", fid, timeout=300)
                            found = [dict(c, how=("identified by sound" + (f" ({c['how']})" if c.get("how") else ""))) for c in ((r2 or {}).get("results") or [])]
                        except Exception:
                            found = []
                    with lock:
                        res[fid] = {"results": found[:8], "t": time.time()}
                        if found:
                            self.found += 1
                            if prep_sure(x, found[0]):
                                self.sure += 1
            finally:
                with lock:
                    self.done += 1
                    if time.time() - state["last_save"] > 20:
                        app.st.save(fname, res)
                        state["last_save"] = time.time()
                app.bump()

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6 if self.mode == "prep" else 4) as ex:          # V2.0.5 (#10): Prepare Previews uses 6 lanes (each site still keeps its own speed limit)
            list(ex.map(work, list(self.ids)))
        app.st.save(fname, res)
        self.finished = True
        app.bump()

    def state(self):
        return {"mode": self.mode, "total": len(self.ids), "done": self.done, "found": self.found, "sure": self.sure, "cur": self.cur,
                "paused": self.paused.is_set(), "running": not self.finished, "cancelled": self.cancel.is_set()}


def prep_sure(x, c):
    """A background result you may accept in one go: same version, same length (±3 s), 90%+ alike."""
    return bool(c) and not c.get("other_version") and c.get("len_ok") and c.get("length") \
        and abs((c.get("length") or 0) - (x.get("duration") or 0)) <= 3 and (c.get("match_pct") or 0) >= 90


def owned_slots(release_id):
    plan = APP.st.cached("plan.json", []) if APP.st else []
    out = {}
    for it in plan:
        if it.get("release_id") == release_id and (it.get("approved") or it.get("fixed")):
            out.setdefault(f"{it.get('disc') or 1}-{it.get('track')}", os.path.basename(it.get("src", "")))
    return out


# ----------------------------------------------------------------------------- song preview (local only)

class AudioServer:
    """Plays a scanned song in the app: http://127.0.0.1:<port>/<token>/<file id>. Only files that are in the
    scan (inventory) can be played, only from this PC, and only read."""
    def __init__(self):
        import http.server
        import secrets
        import socketserver
        self.token = secrets.token_hex(12)
        token = self.token

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                parts = self.path.strip("/").split("/")
                if len(parts) == 3 and parts[0] == token and parts[1] == "cover" and APP.st:
                    data, mime = embedded_cover(parts[2])
                    if not data:
                        self.send_response(404)
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "max-age=3600")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    try:
                        self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                if len(parts) != 2 or parts[0] != token or not APP.st:
                    self.send_response(404)
                    self.end_headers()
                    return
                r = APP.inv_map().get(parts[1])
                path = r and r.get("path")
                if not path or not os.path.isfile(mm.lp(path)):
                    self.send_response(404)
                    self.end_headers()
                    return
                size = os.path.getsize(mm.lp(path))
                start, end = 0, size - 1
                rng = self.headers.get("Range")
                if rng and rng.startswith("bytes="):
                    a, _, b = rng[6:].partition("-")
                    start = int(a) if a else 0
                    end = int(b) if b else size - 1
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                else:
                    self.send_response(200)
                types = {".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".m4b": "audio/mp4", ".aac": "audio/aac",
                         ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".wma": "audio/x-ms-wma",
                         ".aiff": "audio/aiff", ".aif": "audio/aiff"}
                self.send_header("Content-Type", types.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    pos, left = start, end - start + 1
                    while left > 0:                          # 1.1.7: the file is opened only for each 1 MB piece, so a paused
                        with open(mm.lp(path), "rb") as f:   # or finished player never keeps it locked (WinError 32 in Copy)
                            f.seek(pos)
                            b_ = f.read(min(1 << 20, left))
                        if not b_:
                            break
                        self.wfile.write(b_)
                        pos += len(b_)
                        left -= len(b_)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
        self.srv = S(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}/{self.token}/"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


AUDIO = None
_COVERS = {}


def file_paths(fid):
    """Where a song is now: the original (if still there), its library copy, or its archived original."""
    out = []
    r = APP.inv_map().get(fid)
    if r:
        out.append(r["path"])
    pm = getattr(APP, "_prov_paths", None)
    try:
        mt = os.path.getmtime(APP.st.p("music_provenance.csv"))
    except OSError:
        mt = 0
    if not pm or pm[0] != mt:
        rows = prov_rows(APP.st) if mt else []
        APP._prov_paths = pm = (mt, {x["file_id"]: [x.get("new_full_path", ""), x.get("final_original_path", "")] for x in rows})
    out += [p_ for p_ in pm[1].get(fid, []) if p_]
    return [p_ for p_ in out if p_ and os.path.isfile(mm.lp(p_))]


def embedded_cover(fid):
    """The cover picture inside a song file (read only), for the Analyze screen."""
    if fid in _COVERS:
        return _COVERS[fid]
    data, mime = None, "image/jpeg"
    for path in file_paths(fid)[:2]:
        try:
            f = mm.mutagen.File(mm.lp(path))
            _, pics = mm.extract_tags(f) if f is not None else ({}, [])
            pics = [x for x in pics if x and x != b"ASF"]
            if pics:
                data = pics[0]
                mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
                break
        except Exception:
            continue
    if len(_COVERS) > 3000:
        _COVERS.clear()
    _COVERS[fid] = (data, mime)
    return data, mime



# ----------------------------------------------------------------------------- find a song on this PC (v1.1)
class PcIndex:
    """Every audio file on every drive, listed once in the background (file names only, read only) and kept in
    <library>\\_logs\\app_pcindex.json. Searches then answer in a blink, several can run at the same time, and
    nothing waits for the engine process. The index refreshes itself in the background when it is old."""
    MAX_AGE = 3 * 24 * 3600

    def __init__(self, app):
        self.app, self.files, self.built, self.building = app, [], 0, False
        self.dirs, self.status, self.searches = 0, "", {}
        self.cancel = threading.Event()
        self.lock = threading.Lock()

    def _path(self):
        return os.path.join(self.app.library, "_logs", "app_pcindex.json") if self.app.library else ""

    def _load(self):
        p = self._path()
        try:
            with open(mm.lp(p), encoding="utf-8") as f:
                d = json.load(f)
            self.files, self.built = d.get("files", []), d.get("built", 0)
        except Exception:
            pass

    def ensure(self, force=False):
        with self.lock:
            if not self.files and not self.built:
                self._load()
            old = time.time() - self.built > self.MAX_AGE
            if self.building or (self.built and not old and not force):
                return
            self.building = True
        threading.Thread(target=self._build, daemon=True).start()

    def _build(self):
        files, dirs = [], 0
        try:
            roots = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if mm.IS_WIN else \
                [os.environ.get("MIDNIGHT_TEST_ROOT") or os.path.expanduser("~")]
            ex = mm.protected_dirs(self.app.cfg) if self.app.cfg else []
            stack = list(roots)
            while stack:
                d = stack.pop()
                dirs += 1
                self.status, self.dirs = d, dirs
                try:
                    with os.scandir(mm.lp(d) if mm.IS_WIN else d) as it:
                        for e in it:
                            try:
                                if e.is_dir(follow_symlinks=False):
                                    if not mm.is_skipped_dir(os.path.join(d, e.name), e.name, ex):
                                        stack.append(os.path.join(d, e.name))
                                elif os.path.splitext(e.name)[1].lower() in mm.AUDIO_EXTS:
                                    files.append(os.path.join(d, e.name))
                            except OSError:
                                pass
                except OSError:
                    pass
                if dirs % 500 == 0:
                    with self.lock:
                        self.files = files if not self.built else self.files
        finally:
            with self.lock:
                self.files, self.built, self.building = files, time.time(), False
            p = self._path()
            if p and os.path.isdir(mm.lp(os.path.dirname(p))):
                try:
                    with open(mm.lp(p), "w", encoding="utf-8") as f:
                        json.dump({"built": self.built, "files": files}, f)
                except Exception:
                    pass
            self.app.bump()

    def _match(self, artist, title):
        words_t = [w for w in mm.norm_key(mm.neutral(title)).split() if len(w) > 1] or mm.norm_key(title).split()
        words_a = [w for w in mm.norm_key(artist).split() if len(w) > 1]
        hits, seen = [], {}
        for p in list(self.files):
            if len(hits) >= 20:
                break
            k = mm.norm_key(os.path.join(os.path.basename(os.path.dirname(p)), os.path.basename(p)))
            if not all(w in k for w in words_t):
                continue
            if not os.path.exists(mm.lp(p)):
                continue
            info = {}
            try:
                info = mm.read_audio(p)
            except Exception:
                pass
            tg = info.get("tags") or {}
            if not words_a or all(w in k for w in words_a) or mm.artist_agrees([tg.get("artist", "")], artist):
                dkey = (os.path.basename(p).lower(), round(info.get("duration") or 0))
                if dkey in seen:                       # v1.1: the same file in several folders is listed once
                    seen[dkey]["copies"] = seen[dkey].get("copies", 1) + 1
                    continue
                ext = os.path.splitext(p)[1].lower()
                try:
                    size = os.path.getsize(mm.lp(p))
                except OSError:
                    size = 0
                hits.append({"path": p, "duration": round(info.get("duration") or 0), "artist": tg.get("artist", ""),
                             "title": tg.get("title", ""), "album": tg.get("album", ""), "copies": 1,
                             "ext": ext.lstrip("."), "size": size, "bitrate": info.get("bitrate") or 0,
                             "lossless": ext in (".flac", ".wav", ".aiff", ".aif", ".ape", ".wv")})
                seen[dkey] = hits[-1]
        # v1.1.4: suggest the best quality; when there is a lossless one AND a lossy one, suggest both (FLAC + MP3 are both kept)
        qual = lambda h: (h.get("bitrate") or 0, h.get("size") or 0)
        lossless = sorted([h for h in hits if h["lossless"]], key=qual, reverse=True)
        lossy = sorted([h for h in hits if not h["lossless"]], key=qual, reverse=True)
        if len(hits) > 1:
            for h in (lossless[:1] + lossy[:1]):
                h["suggest"] = True
        return hits

    def match_artist(self, artist):
        """Folders on this PC whose path holds the artist's name, with ONLY the matching songs of each folder.
        1.1.7: songs already in Sources, or already scanned, are left out of the list (so 'added' items disappear)."""
        words = [w for w in mm.norm_key(artist).split() if len(w) > 1] or mm.norm_key(artist).split()
        srcs = list(self.app.cfg.get("sources", []))
        try:
            scanned = {os.path.normcase(r.get("path", "")) for r in self.app.inv_map().values()}
        except Exception:
            scanned = set()

        def covered(p):
            if os.path.normcase(p) in scanned:
                return True
            return any(mm.same_path(p, s_["path"]) or (s_.get("recursive") and not s_.get("file") and mm.inside(p, s_["path"])) for s_ in srcs)
        folders, files = Counter(), {}
        for p in list(self.files):
            k = mm.norm_key(os.path.dirname(p) + " " + os.path.basename(p))
            if words and all(w in k for w in words) and not covered(p):
                d = os.path.dirname(p)
                folders[d] += 1
                files.setdefault(d, []).append(p)
        return [{"folder": f, "songs": n, "files": files[f]} for f, n in folders.most_common(60)]

    def start(self, key, artist, title):
        self.ensure()
        self.searches[key] = {"loading": True}

        def run():
            while self.building and not self.files and not self.built:      # first ever index: wait for it
                time.sleep(0.5)
            try:
                if title is None:                                      # v1.1: "find this artist's music": folders, not songs
                    self.searches[key] = {"folders": self.match_artist(artist), "hits": [], "loading": False}
                    return
                hits = self._match(artist, title)
                self.searches[key] = {"hits": hits, "folders": self.dirs, "loading": False}
            except Exception as e:
                self.searches[key] = {"hits": [], "error": f"{type(e).__name__}: {e}", "loading": False}
        threading.Thread(target=run, daemon=True).start()

    def state(self, keys):
        return {"searches": {k: self.searches.get(k) for k in keys}, "building": self.building, "dirs": self.dirs,
                "folder": self.status, "files": len(self.files), "built": self.built}


# ----------------------------------------------------------------------------- the API the page calls

class Api:
    # ---- start / settings
    def save_session(self, d):
        """v2.0: keeps your keys, your settings and the page you were on, so the next start picks up where you stopped."""
        app = APP
        d = d if isinstance(d, dict) else {}
        app.remember_keys()
        app.memo["session"] = {"screen": str(d.get("screen") or "")[:30], "theme": d.get("theme") if d.get("theme") in ("dark", "light") else "",
                               "speed": d.get("speed") if d.get("speed") in ("fast", "complete") else "", "saved": mm.now()}
        app._save_memo()
        if app.st:
            app.save_cfg()
        return {"ok": True, "saved": app.memo["session"]["saved"]}

    def _logs_start(self):
        """2.0.2: the file dialogs of Save / Load session open in <library>\\_logs (when it exists).
        V2.0.6: once you saved (or loaded) a session somewhere else, they open THERE from then on."""
        last = (APP.memo or {}).get("session_dir") or ""
        if last and os.path.isdir(last):
            return last
        d = os.path.join(APP.library, "_logs") if APP.library else ""
        return d if d and os.path.isdir(d) else ""

    def _remember_session_dir(self, path):
        try:
            d = os.path.dirname(path)
            if d and os.path.isdir(d):
                APP.memo["session_dir"] = d
                APP._save_memo()
        except Exception:
            pass

    def save_session_file(self, d):
        """2.0.1: Save session also writes your settings and the page you are on into a file you choose. Keys and secrets are NOT written."""
        res = self.save_session(d)
        if APP.window is None:
            return {"error": "Saving to a file needs the desktop window. The session was kept inside the app."}
        import webview
        r = APP.window.create_file_dialog(webview.SAVE_DIALOG, directory=self._logs_start(), save_filename="midnight_session.json", file_types=("Midnight session (*.json)",))
        path = (r if isinstance(r, str) else (r[0] if r else None)) if r else None
        if not path:
            return {"cancelled": True}
        if not path.lower().endswith(".json"):
            path += ".json"
        data = {"app": APP_NAME, "version": APP_VERSION, "saved": mm.now(), "session": APP.memo.get("session") or {},
                "settings": {k: v for k, v in (APP.cfg or {}).items() if k not in KEY_FIELDS and not re.search(r"(key|secret|token|password)", k, re.I)}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        self._remember_session_dir(path)
        return {"ok": True, "path": path, "saved": res.get("saved")}

    def load_session_file(self):
        """2.0.1: Load a session file saved above: restores the settings and the page. Keys already in the app are left as they are."""
        if APP.window is None:
            return {"error": "Loading a file needs the desktop window."}
        import webview
        t0 = time.time()
        r = APP.window.create_file_dialog(webview.OPEN_DIALOG, directory=self._logs_start(), file_types=("Midnight session (*.json)",))
        t1 = time.time()
        path = (r[0] if isinstance(r, (list, tuple)) else r) if r else None
        if not path:
            return {"cancelled": True}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            return {"error": "That file could not be read: " + str(e)}
        self._remember_session_dir(path)
        if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
            return {"error": "That is not a Midnight session file."}
        lib = str(data["settings"].get("library") or "")
        if lib and os.path.isdir(lib) and os.path.normcase(lib) != os.path.normcase(APP.library or ""):
            rr = self.set_library(lib, True)          # V2.0.5: the session's project opens again (the app starts with none)
            if isinstance(rr, dict) and rr.get("error"):
                return rr
        elif lib and not os.path.isdir(lib):
            return {"error": "The project folder of this session is not there any more: " + lib}
        n = 0
        for k, v in data["settings"].items():
            if k in KEY_FIELDS or re.search(r"(key|secret|token|password)", k, re.I):
                continue
            APP.cfg[k] = v
            n += 1
        sess = data.get("session") if isinstance(data.get("session"), dict) else {}
        APP.memo["session"] = {"screen": str(sess.get("screen") or "")[:30], "theme": sess.get("theme") if sess.get("theme") in ("dark", "light") else "",
                               "speed": sess.get("speed") if sess.get("speed") in ("fast", "complete") else "", "saved": mm.now()}
        APP._save_memo()
        t2 = time.time()
        if APP.st:
            APP.save_cfg()
        t3 = time.time()
        APP.log(f"Load session: file window {t1 - t0:.1f}s (this includes the time you took to choose), read + apply {t2 - t1:.1f}s, save {t3 - t2:.1f}s")
        return {"ok": True, "applied": n, "screen": APP.memo["session"]["screen"], "t_dialog": round(t1 - t0, 1), "t_apply": round(t2 - t1, 1), "t_save": round(t3 - t2, 1)}

    def init(self):
        app = APP
        self.recount()                         # song counts for the folders chosen last time
        return {"session": app.memo.get("session") or {}, "app": APP_NAME, "version": APP_VERSION, "app_dir": HERE, "library": app.library, "last_library": app.last_library if app.last_library and os.path.isdir(app.last_library) else "", "titlebar": os.path.exists(os.path.join(HERE, "_titlebar_on.txt")),
                "logs": os.path.join(app.library, "_logs") if app.library else "",
                "suggest_library": os.path.join(os.path.dirname(mm.APP_DIR), "TEST 01"),
                "sources": app.sources(), "excludes": app.excludes(),
                "scan_mode": app.cfg.get("scan_mode", "simple"), "services": services_from_cfg(app.cfg), "set_once": bool(app.cfg.get("services_saved")),
                "service_info": SERVICE_INFO, "ffmpeg": mm.find_tool("ffmpeg"), "fpcalc": mm.find_tool("fpcalc"),
                "cache_dir": cache_dir(),
                "desktop": APP.window is not None, "protected": PROTECTED_NAMES,
                "audio": AUDIO.base if AUDIO else "", "explorer": mm.IS_WIN}

    def poll(self, since_rev=-1):
        app = APP
        with app.lock:
            if since_rev == app.rev:
                return {"rev": app.rev, "same": True}
            return {"rev": app.rev, "job": dict(app.job) if app.job else None, "progress": app.progress,
                    "lines": app.lines[-120:], "counts": dict(app.counts), "sources": app.sources(),
                    "excludes": app.excludes(), "library": app.library, "dropped": app.dropped,
                    "lookups": app.lookups_status, "prep": app.prep.state() if app.prep else None, "vprep": app.vprep.state() if app.vprep else None, "confirm": app.confirm,
                    "pending": list(app.pending)}

    def _start_dir(self):
        """V2.0.5 (#4): where a folder dialog opens: the folder you picked last time, else your Music folder - never a _logs folder."""
        d = (APP.memo.get("pick_dir") or "").strip()
        bad = lambda x: (not x) or (not os.path.isdir(x)) or any(part.lower() == "_logs" for part in re.split(r"[\\/]", x))
        if bad(d):
            d = os.path.join(os.path.expanduser("~"), "Music")
        if bad(d):
            d = os.path.expanduser("~")
        return d

    def _remember_dir(self, path):
        try:
            par = os.path.dirname(path.rstrip("\\/")) or path
            if os.path.isdir(par):
                APP.memo["pick_dir"] = par
                APP._save_memo()
        except Exception:
            pass

    def pick_folder(self, title="Choose a folder"):
        if APP.window is None:
            return None
        import webview
        try:
            r = APP.window.create_file_dialog(webview.FOLDER_DIALOG, directory=self._start_dir())
        except TypeError:                                    # older pywebview without 'directory'
            r = APP.window.create_file_dialog(webview.FOLDER_DIALOG)
        if r:
            self._remember_dir(r[0])
        return r[0] if r else None

    def list_dirs(self, path=""):
        """V2.0.5 (#4): the in-app folder picker (used in browser mode, where there is no Windows dialog). Folders only, read only."""
        out = {"path": "", "parent": "", "dirs": [], "drives": [], "start": self._start_dir(), "error": ""}
        if mm.IS_WIN:
            out["drives"] = [f"{c}:\\" for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
        path = mm.clean_input_path(path or "") if path else ""
        if not path:
            out["dirs"] = [{"name": d, "path": d} for d in out["drives"]] if mm.IS_WIN else []
            if not mm.IS_WIN:
                path = "/"
            else:
                return out
        path = os.path.abspath(path)
        if not os.path.isdir(mm.lp(path)):
            out["error"] = "That folder does not exist."
            out["path"] = path
            return out
        out["path"] = path
        par = os.path.dirname(path.rstrip("\\/"))
        out["parent"] = par if par and par != path else ""
        try:
            names = sorted((n for n in os.listdir(mm.lp(path)) if os.path.isdir(os.path.join(path, n))), key=lambda n: n.lower())
        except OSError as e:
            out["error"] = f"Cannot open this folder ({e.strerror or e})."
            return out
        out["dirs"] = [{"name": n, "path": os.path.join(path, n)} for n in names if not n.startswith("$")][:2000]
        return out

    def note_pick(self, path):
        """The in-app picker tells us what was chosen so the next dialog opens nearby."""
        self._remember_dir(path or "")
        return True

    def pick_file(self, title="Choose a file", kinds=("Restore log (*.json)",)):
        if APP.window is None:
            return None
        import webview
        r = APP.window.create_file_dialog(webview.OPEN_DIALOG, file_types=tuple(kinds))
        return (r[0] if isinstance(r, (list, tuple)) else r) if r else None

    def pick_songs(self):
        """v1.1.4: choose single songs (instead of a whole folder) to scan."""
        if APP.window is None:
            return []
        import webview
        exts = ";".join("*" + e for e in sorted(mm.AUDIO_EXTS))
        r = APP.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                          file_types=(f"Music files ({exts})", "All files (*.*)"))
        return list(r) if r else []

    def add_source_files(self, paths):
        """Songs found on this PC become sources one by one (only those songs are scanned, not their folder)."""
        return self.add_sources(list(paths or []), False)

    def remove_all_sources(self):
        app = APP
        if app.busy():
            return {"error": "Please wait until the scan has finished."}
        app.cfg["sources"] = []
        app.cfg["excludes"] = []
        app.counts.clear()
        app.save_cfg()
        app.bump()
        return {"sources": app.sources()}

    def check_path(self, path):
        path = mm.clean_input_path(path or "")
        return {"path": path, "exists": bool(path) and os.path.isdir(path), "protected": is_protected(path)}

    # ---- sources
    def add_sources(self, paths, confirmed_protected=False):
        app = APP
        if app.busy():                         # v1.1: do not lose the folder: it waits until you add it
            queued = []
            for p in paths or []:
                p = mm.clean_input_path(p if isinstance(p, str) else (p or {}).get("path", ""))
                if p and (os.path.isdir(p) or os.path.isfile(p)) and not any(mm.same_path(p, q) for q in app.pending + [s["path"] for s in app.sources()]):
                    app.pending.append(p)
                    queued.append(p)
            app.bump()
            return {"added": [], "queued": queued, "problems": [], "sources": app.sources()}
        added, problems, already = [], [], []
        srcs = app.cfg.setdefault("sources", [])
        for p in paths or []:
            p = mm.clean_input_path(p or "")
            if not p:
                continue
            if os.path.isfile(p):             # v1.1.4: one song as a source: only this song is scanned
                if os.path.splitext(p)[1].lower() not in mm.AUDIO_EXTS:
                    problems.append(f"Not a music file: {p}")
                elif any(mm.same_path(p, s["path"]) or (s["recursive"] and mm.inside(p, s["path"])) for s in srcs):
                    already.append(p)                 # v1.1.5: not an error: it is in your sources already
                else:
                    srcs.append({"path": p, "recursive": False, "file": True})
                    added.append(p)
                continue
            if not os.path.isdir(p):
                problems.append(f"Not a folder: {p}" if os.path.exists(p) else f"Folder not found: {p}")
                continue
            if is_protected(p) and not confirmed_protected:
                return {"needs_confirm": is_protected(p), "path": p}
            if app.library and mm.inside(p, app.library):
                problems.append(f"This is the organized library itself (it is skipped automatically): {p}")
                continue
            if any(mm.same_path(p, s["path"]) for s in srcs):
                already.append(p)
                continue
            if any(s["recursive"] and mm.inside(p, s["path"]) for s in srcs):
                already.append(p)
                continue
            srcs.append({"path": p, "recursive": True})
            added.append(p)
            ex = app.cfg.setdefault("excludes", [])
            for prot in protected_inside(p):
                if not any(mm.same_path(prot, e) for e in ex):
                    ex.append(prot)
                    problems.append(f"Skipped automatically (protected): {prot}")
        app.save_cfg()
        for p in added:
            app._count_source(p)
        if added:
            fl = [x for x in added if os.path.isfile(x)]
            app.activity("sources", (f"Added {len(fl)} song(s) to sources" if fl and len(fl) == len(added) else
                                     f"Added {len(added)} folder(s) to sources") + ": " + ", ".join(os.path.basename(x) for x in added[:3]) + (" …" if len(added) > 3 else ""))
        app.bump()
        return {"added": added, "already": already, "problems": problems, "sources": app.sources()}

    def take_pending(self):
        app = APP
        if app.busy():
            return {"error": "Please wait until the running job has finished."}
        paths, app.pending = list(app.pending), []
        return self.add_sources(paths, True)

    def new_project(self):
        """v1.1: empties the music folders list (nothing on disk is touched); the destination stays."""
        app = APP
        if app.busy():
            return {"error": "Please wait until the running job has finished."}
        app.cfg["sources"], app.cfg["excludes"] = [], []
        app.cfg.pop("last_sources", None)
        app.pending, app.counts = [], {}                   # the destination (library) stays
        if app.st:
            app.save_cfg()
        app.bump()
        return {"ok": True}

    def speeds(self):
        """Measured answer times per site (seconds) + the order 'fastest first' (MusicBrainz stays first)."""
        sp = APP.st.load("app_speeds.json", {}) if APP.st else {}
        base = ["deezer", "itunes", "tidal", "discogs", "lastfm"]          # the usual order when nothing is measured yet
        known = sorted([k for k in base if k in sp], key=lambda k: sp[k]["avg"])
        order = known + [k for k in base if k not in sp]
        return {"speeds": sp, "fastest": order, "measured": bool(known)}

    def measure_speeds(self):
        app = APP
        if not app.st:
            return {"error": "Choose the library first."}
        use = [k for k in (["mb"] if app.cfg.get("use_mb", True) else []) + list(app.cfg.get("alt_use") or [])]
        r = app.engine.call("speed_test", use, timeout=180)
        return {"speeds": r, **self.speeds()}

    def set_tool(self, name):
        """Choose ffmpeg.exe / fpcalc.exe by hand when they are not found next to the app."""
        if name not in ("ffmpeg", "fpcalc"):
            return {"error": "Unknown tool."}
        p = self.pick_file(f"Choose {name}.exe", (f"{name} (*.exe)", "All files (*.*)"))
        if not p:
            return {"path": ""}
        if not os.path.isfile(p):
            return {"error": "That file was not found."}
        APP.memo.setdefault("tools", {})[name] = p
        APP._save_memo()
        APP.cfg[name] = p
        if APP.st:
            APP.save_cfg()
        APP.bump()
        return {"path": p}

    def set_tree_sources(self, sources, excludes, confirmed_protected=False):
        """From the whole-computer tree: each 'Use' folder (whose folder above is skipped) + the skipped
        folders inside them."""
        app = APP
        if not confirmed_protected:
            hit = next((p for p in sources if is_protected(p)), "")
            if hit:
                return {"needs_confirm": is_protected(hit), "path": hit}
        app.cfg["sources"] = [s for s in app.cfg.get("sources", []) if not any(mm.same_path(s["path"], x) for x in sources)]
        app.cfg["sources"] += [{"path": p, "recursive": True} for p in sources]
        ex = app.cfg.setdefault("excludes", [])
        ex += [e for e in excludes if not any(mm.same_path(e, x) for x in ex)]
        app.save_cfg()
        for p in sources:
            app._count_source(p)
        app.bump()
        return {"sources": app.sources()}

    def remove_source(self, path):
        app = APP
        if app.busy():
            return {"error": "Please wait until the scan has finished."}
        app.cfg["sources"] = [s for s in app.cfg.get("sources", []) if not mm.same_path(s["path"], path)]
        app.cfg["excludes"] = [e for e in app.cfg.get("excludes", []) if not mm.inside(e, path)]
        app.counts.pop(path, None)
        app.save_cfg()
        app.activity("sources", "Removed from sources: " + os.path.basename(path.rstrip("\\/")) )
        app.bump()
        return {"sources": app.sources()}

    def recount(self):
        for s in APP.sources():
            if s["path"] not in APP.counts:
                APP._count_source(s["path"])
        return True

    def set_library(self, path, confirmed_protected=False):
        app = APP
        if app.busy():
            return {"error": "Please wait until the scan has finished."}
        path = mm.clean_input_path(path or "")
        if not path:
            return {"error": "Choose a folder."}
        if is_protected(path) and not confirmed_protected:
            return {"needs_confirm": is_protected(path), "path": path}
        for s in app.sources():
            if mm.inside(path, s["path"]):
                return {"error": "The library folder must not be inside a music folder you are scanning."}
        keep_sources, keep_ex = app.sources(), app.excludes()
        app._open_library(path)
        if not app.cfg.get("sources"):          # a new library: keep the folders you already chose
            app.cfg["sources"], app.cfg["excludes"] = keep_sources, keep_ex
        app.memo.update(library=path, logs=os.path.join(path, "_logs"))
        app._save_memo()
        app.counts = {}
        for s in app.sources():
            app._count_source(s["path"])
        app.lookups_status = ""
        app.preload()
        app.bump()
        return {"library": path, "logs": os.path.join(path, "_logs"), "sources": app.sources(),
                "services": services_from_cfg(app.cfg), "scan_mode": app.cfg.get("scan_mode", "simple"),
                "exists": os.path.isdir(path)}

    # ---- whole computer
    def whole_start(self):
        if APP.whole and not APP.whole.done:
            return True
        APP.whole = WholeScan(APP)
        return True

    def whole_poll(self, since=0):
        return APP.whole.state(since) if APP.whole else None

    def whole_cancel(self):
        if APP.whole:
            APP.whole.cancel.set()
        return True

    def folder_songs(self, path):
        try:
            names = sorted(f for f in os.listdir(mm.lp(path)) if os.path.splitext(f)[1].lower() in mm.AUDIO_EXTS)
        except OSError:
            names = []
        return {"songs": names[:200], "count": len(names)}

    # ---- scan
    def start_scan(self, opts):
        app = APP
        if app.busy():
            return {"error": "A scan is already running."}
        if not app.library:
            return {"error": "Choose where the organized library should go (step 2)."}
        if not app.sources():
            return {"error": "Add at least one music folder (step 1)."}
        for s in app.sources():
            if mm.inside(app.library, s["path"]):
                return {"error": "The library folder is inside a music folder. Choose another library folder."}
        sv = dict(opts.get("services") or {})
        for k, need in (("acoustid", "acoustid_key"), ("discogs", "discogs_token"), ("lastfm", "lastfm_key"), ("tidal", "tidal_id"), ("tidal", "tidal_secret"), ("spotify", "spotify_id"), ("spotify", "spotify_secret")):
            if sv.get(k) and not (sv.get(need) or "").strip():
                sv[k] = False
        opts["services"] = sv
        start_job(opts)
        return {"ok": True}

    def stop(self):
        """Cancel: the scan ends; the last finished plan stays as it was. Nothing is changed."""
        APP.engine.stop()
        with APP.lock:
            if APP.job:
                APP.job["paused"] = False
            APP.rev += 1
        APP.log("Cancelling... (finishing the current song; the last finished results stay)")
        return True

    def prep_start(self, ids=None):
        """Search every Place, No album and set-aside song now (or the songs given), in the background."""
        app = APP
        if app.prep and not app.prep.finished:
            return {"error": "Prepare Review is already running."}
        if not ids:
            dec = app.decisions()
            have = app.prep_results()
            ids = [x["id"] for x in review_list()["items"]
                   if (x["kind"] in ("place", "none") or (dec.get(x["id"]) or {}).get("action") == "reject")
                   and (dec.get(x["id"]) or {}).get("action") in (None, "reject", "later") and x["id"] not in have]
        if not ids:
            return {"error": "Nothing left to prepare: every Place, No album and set-aside song has been searched."}
        app.prep = Prep(app, list(ids))
        app.bump()
        return {"ok": True, "total": len(ids)}

    def nested_info(self):
        """V2.0.3 decision 8: sub-folders inside your sources whose name starts with "_" (e.g. _Full Collection, _Sorted). They often hold
        a second copy of the same songs. Returns [{source, folder, path, songs}] and whether the setting already skips them."""
        app = APP
        out = []
        for src in app.sources():
            path = src.get("path")
            if not path or not os.path.isdir(mm.lp(path)):
                continue
            try:
                for e in os.scandir(mm.lp(path)):
                    if e.is_dir() and e.name.startswith("_") and e.name.lower() not in ("_loonybin", "_leftout", "_duplicates", "_logs"):
                        n = 0
                        for _dp, _dn, fn in os.walk(e.path):
                            n += sum(1 for f in fn if os.path.splitext(f)[1].lower() in mm.AUDIO_EXTS)
                        if n:
                            out.append({"source": path, "folder": e.name, "path": e.path.replace("\\\\?\\", ""), "songs": n})
            except OSError:
                pass
        return {"nested": out, "skipping": bool(app.cfg.get("skip_nested"))}

    def auto_list(self):
        """V2.0.3 decision 2: songs placed on their own because their tags were already identical (with an Undo)."""
        app = APP
        if not app.st:
            return {"items": []}
        dec = app.decisions()
        return {"items": [dict(x, undone=bool((dec.get(x["file_id"]) or {}).get("action") == "later")) for x in app.st.cached("auto_accepted.json", [])]}

    def auto_undo(self, ids):
        app = APP
        dec = app.decisions()
        for i in ids or []:
            dec[i] = {"action": "later", "label": "automatic accept undone", "t": time.time(), "kind0": "match"}
        app.save_decisions(dec)
        app.bump()
        return {"ok": True, "ids": list(ids or [])}

    def verify_start(self, ids=None):
        """V2.0.3: ask the other allowed sites whether they agree with each waiting match (up to 4 songs at a time). Read-only."""
        app = APP
        if app.vprep and not app.vprep.finished:
            return {"error": "Verify with other sites is already running."}
        have = app.verify_results()
        if not ids:
            ids = [x["id"] for x in review_list()["items"] if x["kind"] == "match" and not x.get("decision") and x["id"] not in have]
        if not ids:
            return {"error": "Nothing left to verify."}
        app.vprep = Prep(app, list(ids), "verify")
        app.bump()
        return {"ok": True, "total": len(ids)}

    def verify_flags(self):
        return {fid: [v.get("n", 0), v.get("sources") or [], v.get("differ") or []] for fid, v in APP.verify_results().items()}

    def dig_start(self, ids=None, again=False):
        """Dig deeper (in the background) for every song nobody recognized (No album / not found), or the songs given."""
        app = APP
        if app.prep and not app.prep.finished:
            return {"error": "Prepare Review or Dig deeper is already running."}
        if not ids:
            dec = app.decisions()
            have = set() if again else {k for k, v in app.prep_results().items() if v.get("dig")}   # V2.0.5: again = search the still-unidentified songs once more
            ids = [x["id"] for x in review_list()["items"] if x["kind"] == "none"
                   and (dec.get(x["id"]) or {}).get("action") in (None, "reject", "later") and x["id"] not in have]
        if not ids:
            return {"error": "Nothing left to dig: every song nobody recognized has been dug already."}
        app.prep = Prep(app, list(ids), "dig")
        app.bump()
        return {"ok": True, "total": len(ids)}

    def review_dig(self, fid):
        """Dig deeper for one song now (all steps)."""
        r = APP.engine.call("dig", fid, None, timeout=1800)
        if r and r.get("results") is not None and APP.st:
            res = APP.prep_results()
            res[fid] = {"results": r["results"][:12], "t": time.time(), "dig": True, "steps": r.get("steps") or []}
            APP.st.save("review_prep.json", res)
        return r

    def _preps(self, which=""):
        """V2.0.5 (#10): the background lanes: 'main' = Prepare Previews / Dig deeper, 'verify' = Verify with other sites; '' = both."""
        return [p_ for p_ in ((APP.prep if which in ("", "main") else None), (APP.vprep if which in ("", "verify") else None)) if p_]

    def prep_pause(self, on=True, which=""):
        for p_ in self._preps(which):
            (p_.paused.set if on else p_.paused.clear)()
        APP.bump()
        return {"ok": True}

    def prep_cancel(self, which=""):
        for p_ in self._preps(which):
            p_.cancel.set()
            p_.paused.clear()
        APP.bump()
        return {"ok": True}

    def prep_flags(self):
        """Small update for the Review list while Prepare Review / Dig deeper runs: {id: [results, sure result, dig]}."""
        app = APP
        inv = app.inv_map()
        out = {}
        for fid, pr in app.prep_results().items():
            res = pr.get("results") or []
            top = res[0] if res else None
            x = {"duration": round((inv.get(fid) or {}).get("duration") or 0)}
            out[fid] = [len(res), top if prep_sure(x, top) else None, bool(pr.get("dig"))]
        return out

    def prep_get(self, fid):
        return APP.prep_results().get(fid) or {"results": []}

    def album_mixed(self, ids, on=True):
        """'Not one album': these songs are matched one by one (the album is not looked up as a whole)."""
        app = APP
        m = app.mixed()
        m = (m | set(ids)) if on else (m - set(ids))
        app.save_mixed(m)
        app.bump()
        return {"ok": True, "count": len(ids)}

    def artist_albums(self, fid):
        return APP.engine.call("artist_albums", fid)

    def copy_info(self):
        """What Copy & tag would do: counts, size, artists (nothing is changed here)."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        plan = app.st.cached("plan.json", [])
        if not plan:
            return {"error": "Scan first."}
        inv = app.inv_map()
        prov = {r["file_id"]: r for r in prov_rows(app.st)}
        done_ids = {fid for fid, r in prov.items() if r.get("status") in ("copied", "verified", "original_archived")}
        dec = app.decisions()
        ready, waiting = [], []
        for it in plan:
            if it.get("kind") == "skip" or it.get("action") in ("keep", "skip") or it["file_id"] in done_ids:
                continue
            if it["approved"]:
                ready.append(it)
            elif not it.get("dup_extra") and not it.get("fixed"):
                waiting.append(it)
        arts = {}
        for it in ready:
            a = it.get("artist_folder") or "_Unverified"
            d = arts.setdefault(a, {"artist": a, "songs": 0, "size": 0})
            d["songs"] += 1
            d["size"] += (inv.get(it["file_id"]) or {}).get("size", 0)
        size = lambda its: sum((inv.get(it["file_id"]) or {}).get("size", 0) for it in its)
        recog = [it for it in waiting if review_kind(it) == "match"]      # found by a music site, only waiting for your check
        try:
            stale = max([d.get("t", 0) for d in dec.values()] + [0]) > os.path.getmtime(app.st.p("plan.json"))
        except OSError:
            stale = False
        recent = sorted((r for r in prov.values() if r.get("status") in ("copied", "verified", "original_archived")),
                        key=lambda r: r.get("date_processed") or "", reverse=True)[:300]
        recent = [{"path": r.get("new_full_path", ""), "from": r.get("original_path") or r.get("original_full_path") or "",
                   "changes": r.get("changes_made", ""), "status": r.get("status", ""), "when": r.get("date_processed", "")} for r in recent]
        extra = [r for r in app.st.load("app_extra_copies.json", []) if not r.get("done")]
        failures = [e for e in app.st.load("copy_failures.json", []) if e.get("src")]
        cnt = song_counts(app, plan)           # V2.0.5 (#2): the same numbers as the Dashboard / Review / Plan
        return {"failures": failures, "extra": extra, "recent": recent, "library": app.library, "ready": len(ready), "ready_size": size(ready), "waiting": cnt.get("needs_you", len(waiting)),
                "waiting_all": len(waiting), "decided": cnt.get("decided", 0), "counts": cnt,
                "waiting_size": size(waiting), "recog": len(recog), "recog_size": size(recog), "copied": len(done_ids), "dup_extra": sum(1 for it in plan if it.get("dup_extra")),
                "artists": sorted(arts.values(), key=lambda d: d["artist"].lower()), "stale": stale,
                "covers": [mm.COVER_NAMES[k] for k in (app.cfg.get("cover_order") or mm.COVER_ORDER) if k in mm.COVER_NAMES]}

    def activity_list(self, limit=400):
        """The Activity log, newest first (1.1.7)."""
        st = APP.st
        if not st:
            return {"items": [], "unseen": 0}
        log = st.load("app_activity.json", [])
        return {"items": list(reversed(log))[:limit], "unseen": sum(1 for e in log if not e.get("seen"))}

    def activity_seen(self):
        st = APP.st
        if st:
            with APP.lock:
                log = st.load("app_activity.json", [])
                for e in log:
                    e["seen"] = True
                st.save("app_activity.json", log)
        return True

    def activity_unseen(self):
        st = APP.st
        return sum(1 for e in st.load("app_activity.json", []) if not e.get("seen")) if st else 0

    def copy_extras_scan(self):
        """Before Copy & tag: other files next to your songs (covers, playlists, .cue/.log, booklets, lyrics) that could be
        copied into the album folders too. Read only - you tick which kinds."""
        app = APP
        if not app.st:
            return {"kinds": {}}
        ex = extras_found(app)
        out = {}
        for e in ex:
            k = out.setdefault(e["kind"], {"count": 0, "size": 0, "examples": []})
            k["count"] += 1
            k["size"] += e["size"]
            if len(k["examples"]) < 6:
                k["examples"].append(e["src"])
        return {"kinds": out, "left_out": sum(1 for d in app.decisions().values() if d.get("action") == "leave")}

    def start_copy(self, mode, artists=None, extras=None, left_out=False):
        """Copy & tag, approved with one click: update the plan with your Review choices, then copy.
        mode: 'confirmed' (decided songs), 'all' (also the songs still waiting: copied with THEIR OWN tags into
        _Unverified), 'custom' (only the artists you ticked). Originals are never changed; nothing is overwritten."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        if not app.st or not app.st.cached("plan.json", []):
            return {"error": "Scan first."}
        if mode == "all":                    # waiting songs: keep their own tags (recorded as your choice)
            dec = app.decisions()
            t = time.time()
            for x in review_list()["items"]:
                if not dec.get(x["id"]) or (dec[x["id"]].get("action") in ("reject", "later")):
                    dec[x["id"]] = {"action": "unverified", "label": "kept as it is (Copy: All)", "kind0": x["kind"], "t": t}
            app.save_decisions(dec)
        if mode == "recognized":             # v1.1.4: accept every song a music site found (waiting for your check), then copy
            dec = app.decisions()
            t = time.time()
            for x in review_list()["items"]:
                if x["kind"] == "match" and (not dec.get(x["id"]) or dec[x["id"]].get("action") in ("later", "reject")):
                    dec[x["id"]] = {"action": "accept", "label": "accepted (Copy: Recognized)", "kind0": "match", "t": t}
            app.save_decisions(dec)
        ids = None
        if mode == "custom":
            want = set(artists or [])
            if not want:
                return {"error": "Tick at least one artist."}
            ids = [it["file_id"] for it in app.st.cached("plan.json", []) if (it.get("artist_folder") or "_Unverified") in want]
        services = services_from_cfg(app.cfg)
        services.update(covers=True, lyrics=True)        # you chose: embedded cover + lyrics
        app.cfg.update(covers=True, lyrics=True)
        app.save_cfg()
        if ids:
            services["copy_ids"] = ids
        kinds = [k for k in (extras or []) if k in EXTRA_KINDS]
        if kinds:
            services["extras"] = [e for e in extras_found(app) if e["kind"] in kinds]
        if left_out:
            services["left_out"] = True
        with app.lock:
            app.job = {"kind": "copy", "started": time.time(), "done": False, "error": "", "stage": "identify",
                       "mode": app.cfg.get("scan_mode", "simple"), "copy_mode": mode}
            app.progress = None
            app.lines = []
            app.rev += 1
        try:
            app.engine.job("copy", services)
        except Exception as e:
            app.finish_job(f"{type(e).__name__}: {e}")
        app.log(f"Copy & tag approved ({mode}). Originals are never changed; existing files are never overwritten.")
        return {"ok": True}

    def answer(self, cid, yes):
        """Your answer to an on-screen "Are you sure?" (archive, empty folders)."""
        APP.engine.answer(cid, yes)
        APP.log(("Yes: " if yes else "No: ") + ((APP.confirm or {}).get("question") or "").splitlines()[0][:120])
        return {"ok": True}

    # -- 2.0.2 (item 75): copy the verified songs of the library into another folder (the library itself is never changed)
    def _export_walk(self):
        """Yield (full path, path relative to the library) for every song in the library that is not in a '_' folder (_Unverified, _Short Files, _LoonyBin, _logs ...)."""
        lib = APP.library
        if not lib or not os.path.isdir(lib):
            return
        for root, dirs, files in os.walk(lib):
            dirs[:] = [d for d in dirs if not d.startswith("_")]
            for fn in files:
                if os.path.splitext(fn)[1].lower() in mm.AUDIO_EXTS:
                    full = os.path.join(root, fn)
                    yield full, os.path.relpath(full, lib)

    def export_info(self):
        n = size = 0
        for full, _rel in self._export_walk():
            n += 1
            try:
                size += os.path.getsize(full)
            except OSError:
                pass
        return {"library": APP.library or "", "songs": n, "size": size, "state": self.export_status()}

    def export_check(self, dest):
        dest = mm.clean_input_path(dest or "")
        if not dest:
            return {"error": "Choose a folder."}
        if not APP.library:
            return {"error": "Open your library first."}
        if mm.inside(dest, APP.library) or mm.inside(APP.library, dest):
            return {"error": "Choose a folder outside your library (and not one that contains it)."}
        for src in APP.sources():
            if mm.inside(dest, src["path"]) or mm.inside(src["path"], dest):
                return {"error": "Choose a folder that is not one of your music folders."}
        return {"ok": True, "dest": dest}

    def export_start(self, dest):
        r = self.export_check(dest)
        if r.get("error"):
            return r
        dest = r["dest"]
        st = getattr(APP, "export", None)
        if st and st.get("running"):
            return {"error": "An export is already running."}
        files = list(self._export_walk())
        APP.export = st = {"running": True, "done": False, "total": len(files), "copied": 0, "skipped": 0, "failed": 0, "dest": dest, "cancel": False, "last": "", "errors": []}

        def run():
            import shutil
            for full, rel in files:
                if st["cancel"]:
                    break
                target = os.path.join(dest, rel)
                st["last"] = rel
                try:
                    if os.path.exists(mm.lp(target)):
                        st["skipped"] += 1          # never overwrite anything
                        continue
                    os.makedirs(mm.lp(os.path.dirname(target)), exist_ok=True)
                    part = target + ".part"
                    shutil.copy2(mm.lp(full), mm.lp(part))
                    if os.path.getsize(mm.lp(part)) != os.path.getsize(mm.lp(full)):
                        os.remove(mm.lp(part))
                        raise OSError("the copy has a different size")
                    os.replace(mm.lp(part), mm.lp(target))
                    st["copied"] += 1
                except Exception as e:
                    st["failed"] += 1
                    if len(st["errors"]) < 20:
                        st["errors"].append(f"{rel}: {e}")
            st["running"], st["done"] = False, True
            APP.log(f"Export verified songs to {dest}: {st['copied']} copied, {st['skipped']} already there (left as they are), {st['failed']} failed" + (" (stopped)" if st["cancel"] else ""))
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    def export_status(self):
        st = getattr(APP, "export", None)
        return {k: v for k, v in st.items() if k != "cancel"} if st else None

    def export_cancel(self):
        st = getattr(APP, "export", None)
        if st:
            st["cancel"] = True
        return {"ok": True}

    def archive_info(self):
        """Originals that can be archived now (their copy exists and is verified), already archived, archive folder."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        prov = prov_rows(app.st)
        ready = [r for r in prov if r.get("status") in ("verified", "copied")]
        arch = [r for r in prov if r.get("status") == "original_archived"]
        size = 0
        for r in ready[:20000]:
            try:
                size += os.path.getsize(mm.lp(r["original_full_path"]))
            except OSError:
                pass
        folders = Counter(os.path.dirname(r["original_full_path"]) for r in ready)
        return {"archive_on": bool(app.cfg.get("archive_on")), "ready": len(ready), "ready_size": size, "no_hash": sum(1 for r in ready if not r.get("audio_stream_hash")),
                "archived": len(arch), "archive": app.cfg.get("archive", ""), "library": app.library,
                "sources": [x["path"] for x in app.sources()],
                "folders": [{"folder": f, "songs": n} for f, n in folders.most_common(12)],
                "recent": [{"from": r["original_full_path"], "to": r.get("final_original_path", "")} for r in arch[-50:]][::-1]}

    def check_archive_folder(self, path):
        app = APP
        path = (path or "").strip().strip('"')
        if not path:
            return {"error": "Choose a folder."}
        if not os.path.isabs(path):
            return {"error": "Use a full path, e.g. C:\\Music Archive."}
        if any(mm.inside(path, s_["path"]) for s_ in app.sources()):
            return {"error": "The archive cannot be inside a music folder you scan (it would be scanned again)."}
        if app.library and mm.inside(path, app.library):
            return {"error": "The archive should not be inside the organized library (it would mix originals with it)."}
        prot = is_protected(path)
        if prot:
            return {"error": f"{prot} is protected: the app never writes there unless you say so."}
        return {"ok": True, "path": path, "exists": os.path.isdir(path)}

    def start_archive(self, folder, empty_folders=False, flat=False):
        if not APP.cfg.get("archive_on"):
            return {"error": "Archive is switched off in Settings (it moves your original files)."}
        """Archive originals (Phase 4): moves originals whose copies are verified into the folder you chose.
        Nothing is deleted. You confirm again on screen after the check ("Are you sure?")."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        chk = self.check_archive_folder(folder)
        if chk.get("error"):
            return chk
        app.cfg["archive"] = chk["path"]
        app.cfg["archive_flat"] = bool(flat)
        app.save_cfg()
        with app.lock:
            app.job = {"kind": "archive", "started": time.time(), "done": False, "error": "", "stage": "archive",
                       "mode": app.cfg.get("scan_mode", "simple")}
            app.progress = None
            app.lines = []
            app.rev += 1
        app.engine.job("archive", {"archive": chk["path"], "empty_folders": bool(empty_folders)})
        app.log(f"Archive approved: originals go to {chk['path']} after one more check on screen.")
        return {"ok": True}

    # ------------------------------------------------------------- Find & restore
    def find_search(self, q):
        """Search every song (where it came from, where its copy is, where the original was archived). Read only."""
        app = APP
        if not app.st:
            return {"error": "Scan first.", "rows": []}
        q = (q or "").strip().lower()
        if len(q) < 2:
            return {"rows": []}
        prov = {r["file_id"]: r for r in mm.read_csv(app.st.p("music_provenance.csv"))} if mm.exists(app.st.p("music_provenance.csv")) else {}
        plan = {it["file_id"]: it for it in app.st.cached("plan.json", [])}
        inv = app.inv_map()
        out = []
        for fid, r in inv.items():
            pr, it = prov.get(fid) or {}, plan.get(fid) or {}
            tg = r.get("tags") or {}
            hay = " ".join([r.get("path", ""), tg.get("artist", ""), tg.get("title", ""), tg.get("album", ""), pr.get("new_full_path", ""),
                            pr.get("final_original_path", ""), it.get("title", ""), it.get("display_artist", ""), it.get("album", ""), fid]).lower()
            if q not in hay:
                continue
            st_ = pr.get("status") or ("planned" if it.get("approved") else "not copied")
            out.append({"id": fid, "status": st_, "title": it.get("title") or tg.get("title") or os.path.basename(r.get("path", "")),
                        "artist": it.get("display_artist") or tg.get("artist", ""), "album": it.get("album") or tg.get("album", ""),
                        "original": pr.get("original_full_path") or r.get("path", ""), "original_there": mm.exists(r.get("path", "")),
                        "copy": pr.get("new_full_path") or "", "copy_there": bool(pr.get("new_full_path")) and mm.exists(pr["new_full_path"]),
                        "planned": it.get("new_path", "") if not pr.get("new_full_path") else "",
                        "archived": pr.get("final_original_path") or "", "archived_there": bool(pr.get("final_original_path")) and mm.exists(pr["final_original_path"]),
                        "changes": pr.get("changes_made", ""), "notes": pr.get("notes", "")})
            if len(out) >= 200:
                break
        out.sort(key=lambda x: (x["artist"].lower(), x["title"].lower()))
        return {"rows": out, "more": len(out) >= 200}

    def restore_logs(self):
        """Every restore log of this library, newest first, with what can be reversed now. Read only."""
        app = APP
        if not app.st:
            return {"logs": []}
        folder = os.path.join(app.st.logs, "restore")
        files = sorted((os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".json")), reverse=True) if os.path.isdir(folder) else []
        return {"logs": [self.restore_log_info(f) for f in files[:200]], "folder": folder}

    def restore_log_info(self, path):
        """What a restore log did and what reversing it would do (nothing is changed here)."""
        path = (path or "").strip().strip('"')
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            entries = d["entries"]
        except Exception:
            return {"path": path, "error": "That is not a restore log made by this program."}
        kinds = Counter(e.get("kind") for e in entries)
        can, skipped = [], []
        for e in entries:
            src, dst = e.get("to", ""), e.get("from", "")
            if not src or not mm.exists(src):
                skipped.append({"why": "no longer there", "path": src})
            elif e.get("kind") != "copy" and mm.exists(dst):
                skipped.append({"why": "something already at the old place", "path": dst})
            else:
                can.append(e)
        return {"path": path, "name": os.path.basename(path), "action": d.get("action", ""), "made": d.get("made", ""),
                "library": d.get("library", ""), "total": len(entries),
                "kinds": {mm.RESTORE_WHAT.get(k, k): v for k, v in kinds.items()},
                "can": len(can), "copies": sum(1 for e in can if e.get("kind") == "copy"), "skipped": skipped[:50],
                "n_skipped": len(skipped), "sample": [{"kind": mm.RESTORE_WHAT.get(e.get("kind"), e.get("kind")), "from": e.get("from", ""),
                                                       "to": e.get("to", "")} for e in entries[:30]]}

    def _restore_job(self, kind, answers):
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        with app.lock:
            app.job = {"kind": kind, "started": time.time(), "done": False, "error": "", "stage": "restore",
                       "mode": app.cfg.get("scan_mode", "simple")}
            app.progress = None
            app.lines = []
            app.rev += 1
        app.engine.job(kind, answers)
        return {"ok": True}

    def restore_original(self, fid):
        """Put one archived original back where it came from (you confirm on screen; nothing is overwritten)."""
        app = APP
        prov = {r["file_id"]: r for r in mm.read_csv(app.st.p("music_provenance.csv"))} if app.st and mm.exists(app.st.p("music_provenance.csv")) else {}
        r = prov.get(fid)
        if not r or r.get("status") != "original_archived":
            return {"error": "That original is not archived; it is still in its original place."}
        if mm.exists(r["original_full_path"]):
            return {"error": "Something already exists at the original place; nothing was moved."}
        return self._restore_job("restore_one", {"query": r["original_full_path"].lower(), "file_id": fid})

    def reverse_log(self, path):
        info = self.restore_log_info(path)
        if info.get("error"):
            return info
        if not info["can"]:
            return {"error": "Nothing in this log can be reversed now."}
        return self._restore_job("reverse_log", {"log": info["path"]})

    # ------------------------------------------------------------- Playlist manager
    def playlist_data(self):
        """Box sets / compilations found in your music (one page to decide each), and your existing playlist files."""
        app = APP
        if not app.st:
            return {"boxes": [], "playlists": []}
        plan = app.st.cached("plan.json", [])
        inv = app.inv_map()
        dec = app.decisions()
        ch = app.st.load("app_boxsets.json", {})
        groups = {}
        for it in plan:
            r = inv.get(it["file_id"]) or {}
            t = r.get("tags") or {}
            alb = (t.get("album") or "").strip()
            if not alb or it.get("kind") == "skip":
                continue
            aa = (t.get("albumartist") or "").strip()
            key = mm.norm_key(alb) + "|" + mm.norm_key(aa if aa else os.path.dirname(it["src"]))
            g = groups.setdefault(key, {"key": key, "album": alb, "albumartist": aa, "ids": [], "artists": set(), "folders": Counter(),
                                        "placed": 0, "elsewhere": 0, "trusted": 0})
            g["ids"].append(it["file_id"])
            g.setdefault("list", []).append(f"{(t.get('track') or '').split('/')[0]} {t.get('artist') or '?'} - {t.get('title') or os.path.basename(it['src'])}".strip())
            g["artists"].add(mm.norm_key(t.get("artist") or ""))
            g["folders"][os.path.dirname(it["src"])] += 1
            d = (dec.get(it["file_id"]) or {}).get("action")
            if d == "trust" or it.get("trusted"):
                g["trusted"] += 1
            elif it.get("approved") and it.get("verified") and mm.norm_key(it.get("album") or "") != mm.norm_key(alb):
                g["elsewhere"] += 1             # sorted onto its real album (not this box set)
            if it.get("approved"):
                g["placed"] += 1
        boxes = []
        for g in groups.values():
            n = len(g["ids"])
            va = mm.norm_key(g["albumartist"]) in mm.VA_NAMES
            many = len(g["artists"] - {""}) >= 4
            words = bool(re.search(r"\b(box|collection|encyclopedia|anthology|complete|essential|greatest|hits|best of|cd ?\d|disc ?\d)\b", g["album"], re.I))
            folder = g["folders"].most_common(1)[0][0]
            fname = os.path.basename(folder)
            cdfold = bool(re.search(r"\b(cd|disc|disk)\s*\d+", fname, re.I))
            if n < 3 or not (va or many or words or cdfold):
                continue
            same = mm.norm_key(re.sub(r"^\d{4}\s*[-.]?\s*", "", fname)) == mm.norm_key(g["album"])
            boxes.append({"key": g["key"], "album": g["album"], "albumartist": g["albumartist"] or ("Various Artists" if va else ""),
                          "songs": n, "artists": len(g["artists"] - {""}), "folder": folder, "same_name": same,
                          "placed": g["placed"], "elsewhere": g["elsewhere"], "trusted": g["trusted"],
                          "why": ", ".join(w for w, c in (("Various Artists", va), (f"{len(g['artists'] - {''})} artists", many),
                                                          ("box/collection name", words), ("CD folder", cdfold)) if c),
                          "choice": (ch.get(g["key"]) or {}).get("mode", ""), "ids": g["ids"], "list": sorted(g.get("list", []), key=lambda x: x.lower())[:300], "explorer": g["folders"].most_common(1)[0][0] if g.get("folders") else ""})
        boxes.sort(key=lambda b: (bool(b["choice"]), b["same_name"], -b["songs"]))
        # existing playlist files
        prov = {os.path.normcase(r.get("original_full_path") or ""): r for r in prov_rows(app.st)}
        by_src = {os.path.normcase(it["src"]): it for it in plan}
        pls = []
        for pth in app.st.load("playlists.json", []):
            entries, inlib, planned = 0, 0, 0
            try:
                for line in mm.read_text_any(pth).splitlines():
                    x = line.strip()
                    if not x or x.startswith("#"):
                        continue
                    entries += 1
                    full = os.path.normcase(os.path.abspath(x if os.path.isabs(x) else os.path.join(os.path.dirname(pth), x)))
                    pr = prov.get(full)
                    if pr and pr.get("new_full_path"):
                        inlib += 1
                    elif (by_src.get(full) or {}).get("approved"):
                        planned += 1
                ok = True
            except Exception:
                ok = False
            pls.append({"path": pth, "name": os.path.basename(pth), "entries": entries, "in_library": inlib, "planned": planned, "readable": ok})
        return {"boxes": boxes, "playlists": pls, "library": app.library}

    def box_choose(self, key, mode, ids=None, album=""):
        """'together' = keep the box set as ONE album with your own tags (Trust my tags for its songs);
        'playlist' = its songs are sorted onto their real albums and the box set is saved as a playlist (at Copy & tag);
        '' = undo. Nothing is copied here."""
        app = APP
        ch = app.st.load("app_boxsets.json", {})
        dec = app.decisions()
        t = time.time()
        old = ch.pop(key, None)
        if old and old.get("mode") == "together":            # undo the Trust my tags it set
            for fid in old.get("ids") or []:
                if (dec.get(fid) or {}).get("src") == "box":
                    dec.pop(fid, None)
        if mode in ("together", "playlist", "skip"):      # 'skip' (v1.1): leave this one alone, nothing changes
            ch[key] = {"mode": mode, "ids": list(ids or []), "album": album, "t": t}
            if mode == "together":
                for fid in ids or []:
                    if not dec.get(fid) or dec[fid].get("action") in ("later", "reject"):
                        dec[fid] = {"action": "trust", "label": "box set kept together: " + album, "src": "box", "t": t}
        app.st.save("app_boxsets.json", ch)
        app.save_decisions(dec)
        app.bump()
        return {"ok": True}

    def restore_all_archive(self):
        """Put everything back: every archived original to its old place (you confirm on screen; nothing overwritten)."""
        return self._restore_job("restore_all", {})

    def undo_copy(self):
        return self._restore_job("undo_copy", {})

    # ------------------------------------------------------------- Settings
    def get_settings(self):
        app = APP
        c = app.cfg
        return {"services": services_from_cfg(c), "service_info": SERVICE_INFO,
                "alt_order": mm.full_alt_order(c),
                "alt_names": mm.ALT_NAMES,
                "cover_order": [k for k in (c.get("cover_order") or mm.COVER_ORDER) if k in mm.COVER_ORDER] + [k for k in mm.COVER_ORDER if k not in (c.get("cover_order") or mm.COVER_ORDER)],
                "cover_names": mm.COVER_NAMES, "sort_mode": c.get("sort_mode", "simple"), "analyze": c.get("analyze", True), "neat": c.get("scan_mode") == "neat",
                "classical_mode": c.get("classical_mode", "performer"), "skip_nested": bool(c.get("skip_nested")), "archive_on": bool(c.get("archive_on")), "dup_place": c.get("dup_place", "album"), "tier_style": (c.get("layout") or {}).get("tier_style", "folder"), "tier_name": (c.get("layout") or {}).get("tier_name", "bracket"),
                "ffmpeg": (c.get("ffmpeg") if c.get("ffmpeg") and os.path.isfile(c["ffmpeg"]) else mm.find_tool("ffmpeg")) or "",
                "fpcalc": (c.get("fpcalc") if c.get("fpcalc") and os.path.isfile(c["fpcalc"]) else mm.find_tool("fpcalc")) or "", "cache_dir": cache_dir(),
                "speeds": self.speeds(),
                "library": app.library, "logs": os.path.join(app.library, "_logs") if app.library else "", "version": APP_VERSION}

    # ---- 1.1.7 (beta): round yellow Minimize / red Close buttons instead of the Windows title bar. Needs a restart; off by default.
    def titlebar_set(self, on):
        flag = os.path.join(HERE, "_titlebar_on.txt")
        try:
            if on:
                with open(flag, "w", encoding="utf-8") as f:
                    f.write("Delete this file (or turn the option off in Settings) to get the normal Windows title bar back.\n")
            elif os.path.exists(flag):
                os.remove(flag)
        except OSError as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"ok": True, "on": bool(on)}

    def win_minimize(self):
        try:
            APP.window.minimize()
        except Exception:
            pass
        return True

    def win_close(self):
        try:
            APP.window.destroy()
        except Exception:
            pass
        return True

    # -- 2.0.2: Settings > "Check one track": asks every site you turned on about ONE song and shows what each one answered
    def site_check_pick(self):
        """Choose a song file; returns its artist / title / album / length (read only, nothing is sent anywhere)."""
        if APP.window is None:
            return {"error": "Choosing a song needs the desktop window. Type the artist and title instead."}
        import webview
        r = APP.window.create_file_dialog(webview.OPEN_DIALOG, file_types=("Music (*.mp3;*.flac;*.m4a;*.ogg;*.opus;*.wav;*.wma;*.aiff;*.aif;*.aac)",))
        path = (r[0] if isinstance(r, (list, tuple)) else r) if r else None
        if not path:
            return {"cancelled": True}
        a = mm.read_audio(path)
        t = a.get("tags") or {}
        return {"path": path, "artist": t.get("artist") or t.get("albumartist") or "", "title": t.get("title") or "", "album": t.get("album") or "",
                "duration": int(a.get("duration") or 0), "error": a.get("error") or ""}

    def site_check(self, artist, title, album="", duration=0, path=""):
        """Sends the artist, title, album and length (and, for AcoustID only, the audio fingerprint of the picked file) to every site that is turned on.
        Nothing is saved: the shared lookup memory (_cache) is only read, never changed."""
        c = APP.cfg
        artist, title, album = (artist or "").strip(), (title or "").strip(), (album or "").strip()
        try:
            duration = int(float(duration or 0))
        except Exception:
            duration = 0
        if not title:
            return {"error": "Type at least a title (or pick a song)."}
        use = list(c.get("alt_use") or [])
        try:
            alt = mm.AltSources(APP.st, use, c.get("discogs_token", ""), c.get("lastfm_key", ""), c.get("tidal_id", ""), c.get("tidal_secret", ""),
                                c.get("spotify_id", ""), c.get("spotify_secret", ""))
            mbc = mm.MusicBrainz(APP.st, c.get("mb_contact", ""))
        except Exception as e:
            return {"error": f"Could not start the check: {e}"}
        for o in (alt, mbc):                        # a clean test: ignore the saved answers, and save nothing
            o.cache = {}
            o.save = lambda: None
            try:
                mm.LIVE_CACHES.remove(o)
            except ValueError:
                pass
        names = {"mb": "MusicBrainz", "deezer": "Deezer", "itunes": "Apple Music", "discogs": "Discogs", "tidal": "Tidal", "spotify": "Spotify", "lastfm": "Last.fm", "acoustid": "AcoustID (by sound)"}
        needs = {"discogs": ("discogs_token",), "tidal": ("tidal_id", "tidal_secret"), "spotify": ("spotify_id", "spotify_secret"), "lastfm": ("lastfm_key",)}
        out, lock = {}, threading.Lock()

        def alt_text(m):
            return " · ".join(x for x in (m.get("group_title") or m.get("title") or "", str(m.get("year") or ""), m.get("rtype") or "") if x)

        def run(key):
            t0 = time.time()
            state, detail = "none", ""
            try:
                if key == "mb":
                    rec = mbc.search_recording(artist, title, duration)
                    if rec:
                        r0 = rec[0]
                        cred = " & ".join(x.get("name", "") for x in (r0.get("artist-credit") or []) if isinstance(x, dict))
                        rel = ((r0.get("releases") or [{}])[0]).get("title", "")
                        state, detail = "found", f"{len(rec)} recordings. First: {cred} - {r0.get('title', '')}" + (f" · {rel}" if rel else "")
                elif key == "acoustid":
                    cp = mm.Chromaprint(mm.find_tool("fpcalc"), c.get("acoustid_key", ""))
                    res = cp.lookup(path)
                    if res:
                        state, detail = "found", f"{len(res)} recordings, best score {res[0][0]:.2f}"
                    else:
                        state, detail = ("error", cp.err) if cp.err else ("none", "No recording matched this audio.")
                else:
                    before = (alt.errs.get(key) or [0, ""])[0]
                    m = getattr(alt, key)(artist, title, album, duration)
                    if m:
                        state, detail = "found", alt_text(m)
                    else:
                        e = alt.errs.get(key)
                        if e and e[0] > before:
                            state, detail = "error", f"The site answered with a problem: {e[1]}"
                        else:
                            detail = "No song matched (artist, title and length must all agree)."
            except Exception as e:
                state, detail = "error", f"{type(e).__name__}: {e}"
            with lock:
                out[key] = {"key": key, "name": names[key], "state": state, "detail": detail, "secs": round(time.time() - t0, 1)}

        keys, rows, ths = [], [], []
        if c.get("use_mb", True):
            keys.append("mb")
        for k in (c.get("alt_order") or ["deezer", "itunes", "discogs", "tidal", "spotify", "lastfm"]):
            if k in names and k not in keys and k != "acoustid":
                keys.append(k)
        keys.append("acoustid")
        for k in keys:
            if k in needs and k in use and not all((c.get(n) or "").strip() for n in needs[k]):
                rows.append({"key": k, "name": names[k], "state": "off", "detail": "On, but the key is not saved yet (Settings).", "secs": 0})
            elif k == "acoustid":
                if not path:
                    rows.append({"key": k, "name": names[k], "state": "off", "detail": "Needs a song file: use Pick a song."})
                elif not (c.get("acoustid_key") and mm.find_tool("fpcalc")):
                    rows.append({"key": k, "name": names[k], "state": "off", "detail": "Needs the AcoustID key and fpcalc.exe (Settings)."})
                else:
                    th = threading.Thread(target=run, args=(k,), daemon=True)
                    ths.append(th)
            elif k != "mb" and k not in use:
                rows.append({"key": k, "name": names[k], "state": "off", "detail": "Turned off in Settings.", "secs": 0})
            else:
                ths.append(threading.Thread(target=run, args=(k,), daemon=True))
                ths[-1].name = k
        for th in ths:
            th.start()
        t_end = time.time() + 90
        for th in ths:
            th.join(max(0.1, t_end - time.time()))
        waiting = [th.name for th in ths if th.is_alive()]
        for k in keys:
            if k in out:
                rows.append(out[k])
        done = {r["key"] for r in rows}
        for k in keys:
            if k not in done:
                rows.append({"key": k, "name": names[k], "state": "error", "detail": "No answer after 90 seconds (the site is slow or not reachable).", "secs": 90})
        order = {k: i for i, k in enumerate(keys)}
        rows.sort(key=lambda r: order.get(r["key"], 99))
        return {"ok": True, "rows": rows, "artist": artist, "title": title, "album": album, "duration": duration}

    def test_spotify(self):
        """1.1.7: Settings > Spotify > Test. Sends ONLY your Spotify key and one test search ("Hey Jude" by The Beatles). Says what is wrong."""
        import base64
        import urllib.error
        import urllib.parse
        import urllib.request
        c = APP.cfg
        cid, sec = (c.get("spotify_id") or "").strip(), (c.get("spotify_secret") or "").strip()
        on = "spotify" in (c.get("alt_use") or [])
        if not (cid and sec):
            return {"ok": False, "on": on, "message": "The Spotify Client ID and Client Secret are not both saved yet. Paste them, press Save, then test again."}
        try:
            req = urllib.request.Request("https://accounts.spotify.com/api/token", data=b"grant_type=client_credentials",
                                         headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=20) as r:
                tok = json.load(r).get("access_token")
        except urllib.error.HTTPError as e:
            return {"ok": False, "on": on, "message": f"Spotify refused the key (HTTP {e.code}). " + ("The Client ID or Secret is wrong: copy both again from your app page at developer.spotify.com/dashboard." if e.code in (400, 401) else "Try again later.")}
        except Exception as e:
            return {"ok": False, "on": on, "message": f"Could not reach Spotify: {type(e).__name__}: {e}"}
        try:
            rq = urllib.request.Request("https://api.spotify.com/v1/search?q=" + urllib.parse.quote("track:Hey Jude artist:The Beatles") + "&type=track&limit=3",
                                        headers={"Authorization": "Bearer " + str(tok)})
            with urllib.request.urlopen(rq, timeout=20) as r:
                items = ((json.load(r).get("tracks") or {}).get("items") or [])
        except urllib.error.HTTPError as e:
            why = {403: "Spotify answered 403: the app owner may need an active Spotify Premium account for apps in development mode, or the app must have your account added under User Management.",
                   429: "Spotify says too many requests right now: wait a few minutes."}.get(e.code, f"Spotify answered HTTP {e.code} to the search.")
            return {"ok": False, "on": on, "message": why}
        except Exception as e:
            return {"ok": False, "on": on, "message": f"The search failed: {type(e).__name__}: {e}"}
        if not items:
            return {"ok": False, "on": on, "message": "The key works but the test search found nothing."}
        msg = f"Spotify works: found '{items[0].get('name', '')}'."
        if not on:
            msg += " But the Spotify switch is OFF, so scans do not use it: turn it on and press Save."
        return {"ok": True, "on": on, "message": msg}

    def save_settings(self, d):
        """Saves your choices into the library's config.json (the same file the text menu uses). Nothing is sent anywhere."""
        app = APP
        if app.busy():
            return {"error": "Please wait until the running job is finished."}
        c, sv = app.cfg, d.get("services") or {}
        c["services_saved"] = True       # v1.1.4: you chose the services in Settings -> the scan does not ask again when all keys are there
        if "mb" in sv:
            c["use_mb"] = bool(sv["mb"])
        for k_sv, k_cfg in (("contact", "mb_contact"), ("acoustid_key", "acoustid_key"), ("discogs_token", "discogs_token"), ("lastfm_key", "lastfm_key"),
                            ("tidal_id", "tidal_id"), ("tidal_secret", "tidal_secret"),
                            ("spotify_id", "spotify_id"), ("spotify_secret", "spotify_secret")):
            if k_sv in sv:
                c[k_cfg] = (sv[k_sv] or "").strip()
        if "acoustid" in sv:
            c["acoustid_off"] = not sv["acoustid"]
        if any(k in sv for k in ("discogs", "deezer", "itunes", "lastfm", "tidal", "spotify")):
            need = {"discogs": ("discogs_token",), "lastfm": ("lastfm_key",), "tidal": ("tidal_id", "tidal_secret"), "spotify": ("spotify_id", "spotify_secret")}
            c["alt_use"] = [k for k in mm.ALT_ORDER if sv.get(k) and all(c.get(n) for n in need.get(k, ()))]
        for k in ("covers", "lyrics"):
            if k in sv:
                c[k] = bool(sv[k])
        if d.get("alt_order"):
            c["alt_order"] = [k for k in d["alt_order"] if k in mm.ALT_ORDER]
        if d.get("cover_order"):
            c["cover_order"] = [k for k in d["cover_order"] if k in mm.COVER_ORDER]
        if d.get("sort_mode") in ("simple", "collection"):
            c["sort_mode"] = d["sort_mode"]
        if d.get("classical_mode") in ("skip", "composer", "performer"):
            c["classical_mode"] = d["classical_mode"]
        if d.get("dup_place") in ("album", "flat"):
            c["dup_place"] = d["dup_place"]
        if "skip_nested" in d:
            c["skip_nested"] = bool(d["skip_nested"])
            mm.SKIP_NESTED = c["skip_nested"]
        if "archive_on" in d:
            c["archive_on"] = bool(d["archive_on"])
        if "neat" in d:
            c["scan_mode"] = "neat" if d["neat"] else "simple"
        if "analyze" in d:
            c["analyze"] = bool(d["analyze"])
        if d.get("tier_style") in ("folder", "name"):
            lay = dict(mm.DEFAULT_LAYOUT, **(c.get("layout") or {}))
            lay["tier_style"] = d["tier_style"]
            if d.get("tier_name") in ("bracket", "dash", "suffix"):
                lay["tier_name"] = d["tier_name"]
            if lay["tier_style"] == "name" and "tier" not in lay["levels"]:
                lay["levels"] = ["tier"] + list(lay["levels"])
            c["layout"] = lay
        app.save_cfg()
        app.bump()
        return {"ok": True, "saved_to": app.st.p("config.json") if app.st else ""}

    # ------------------------------------------------------------- Neat Picky
    def neat_list(self):
        """Every confirmed song: the tags it has now and the tags it will get, field by field, with how alike they are."""
        app = APP
        if not app.st:
            return {"rows": []}
        plan = app.st.cached("plan.json", [])
        inv = app.inv_map()
        neat = app.st.load("app_neat.json", {})
        dec = app.decisions()
        try:
            plan_time = os.path.getmtime(app.st.p("plan.json"))
        except OSError:
            plan_time = 0
        F = ("artist", "title", "album", "albumartist", "year", "track", "disc", "genre")
        memo = getattr(app, "_neat_memo", None)
        if memo is None:
            memo = app._neat_memo = {}
        rows = []
        for it in plan:
            fid = it["file_id"]
            new = it.get("proposed_tags") or it.get("new_tags") or {}
            if not new or it.get("kind") == "skip" or it.get("dup_extra"):
                continue
            if not (it.get("approved") or it.get("fixed") or fid in neat or fid in dec):
                continue
            r = inv.get(fid) or {}
            old = r.get("tags") or {}
            mk = (id(r), tuple(str(new.get(k) or "") for k in F))
            hit = memo.get(fid)
            if hit and hit[0] == mk:
                per, pct = hit[1]
            else:
                per, pct = mm.tag_match(old, new)
                memo[fid] = (mk, (per, pct))
            n = neat.get(fid) or {}
            d = dec.get(fid) or {}
            state = n.get("action") or ({"later": "later", "reject": "find"}.get(d.get("action")) or "")
            rows.append({"id": fid, "pct": pct, "per": per, "file": os.path.basename(it.get("src", "")), "folder": os.path.dirname(it.get("src", "")),
                         "old": {k: str(old.get(k) or "") for k in F},
                         "new": {k: ("/".join(new[k]) if isinstance(new.get(k), list) else str(new.get(k) or "")) for k in F},
                         "dest": it.get("new_path", ""), "source": it.get("data_source", ""), "rtype": it.get("rtype", ""),
                         "group": it.get("album") or "", "artist": it.get("display_artist") or "", "state": state,
                         "t": n.get("t") or d.get("t") or 0, "duration": round(r.get("duration") or 0)})
        last = max([v.get("t", 0) for v in neat.values()] + [0])
        return {"rows": rows, "stale": last > plan_time}

    def neat_decide(self, ids, action):
        """'accept' (new tags), 'keep' (my tags; still placed in the library), 'later' (not copied for now),
        'find' (another match: the song goes to Review > Not this). Used when the plan is updated."""
        app = APP
        neat = app.st.load("app_neat.json", {})
        dec = app.decisions()
        t = time.time()
        for fid in ids:
            neat.pop(fid, None)
            if (dec.get(fid) or {}).get("src") == "neat":
                dec.pop(fid, None)
            if action == "keep":
                neat[fid] = {"action": "keep", "t": t}
            elif action == "accept":
                neat[fid] = {"action": "accept", "t": t}
            elif action == "accept_nogenre":          # V2.0.3: take the match, keep the file's own genre
                neat[fid] = {"action": "accept", "t": t, "keep_fields": ["genre"]}
            elif action in ("later", "find"):
                dec[fid] = {"action": "later" if action == "later" else "reject", "kind0": "match", "src": "neat", "t": t}
        app.st.save("app_neat.json", neat)
        app.save_decisions(dec)
        app.bump()
        return {"ok": True}

    def analyze_data(self, basis="new", scope="all"):
        """Everything for the Analyze screen (read only): tiers, artists with their albums, almost complete albums.
        basis 'old' (v1.1): the same view built from the tags your files have now (before any Copy & tag)."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        if scope == "sources":                      # v1.1.4: only the songs that are in your Sources (single songs too)
            return self._analyze_old(scope=True, new=(basis != "old"))
        if basis == "old":
            return self._analyze_old()
        an = app.st.cached("analysis.json", {})
        if not an:
            return {"error": "No analysis yet: run Scan & identify (Complete scan for tiers)."}
        plan = app.st.cached("plan.json", [])
        first, conf = {}, {}
        for it in plan:
            if it.get("release_id") and it.get("artist_folder"):
                k = (it["artist_folder"], it.get("album") or "")
                conf[k] = conf.get(k, True) and bool(it.get("approved") or it.get("verified"))      # 1.1.5: new cover only for confirmed albums
                inv = app.inv_map().get(it["file_id"]) or {}
                if k not in first or (inv.get("has_cover") and not first[k][1]):
                    first[k] = (it["file_id"], bool(inv.get("has_cover")))
        albums = {}
        for al in an.get("albums", []):
            fc = first.get((al["artist"], al["album"]))
            albums.setdefault(al["artist"], []).append(dict(al, fid=fc[0] if fc and fc[1] else "", confirmed=bool(conf.get((al["artist"], al["album"])))))
        arts = []
        for a in an.get("artists", []):
            als = sorted(albums.get(a["artist"], []), key=lambda x: (str(x.get("year") or "9999"), x["album"].lower()))
            arts.append(dict(a, albums=als))
        tiers = Counter(a.get("tier", "") for a in arts)
        return {"summary": an.get("summary", {}), "made": an.get("made", ""), "artists": arts,
                "tiers": [{"name": t, "short": t.split(" ", 1)[1], "count": tiers.get(t.split(" ", 1)[1], 0)} for t in TIER_ORDER],
                "almost": an.get("almost", []), "covers": AUDIO.base + "cover/" if AUDIO else "",
                "pics": "deezer" in (app.cfg.get("alt_use") or [])}

    def _analyze_old(self, scope=False, new=False):
        app = APP
        inv = app.st.cached("inventory.json", [])
        if not inv:
            return {"error": "No scan yet."}
        if scope:
            srcs = app.cfg.get("sources") or app.cfg.get("last_sources") or []
            inv = [r for r in inv if any(mm.same_path(r["path"], s["path"]) or (s.get("recursive") and mm.inside(r["path"], s["path"])) for s in srcs)]
            if not inv:
                return {"error": "None of the songs in your Sources has been scanned yet. Add songs or folders in Sources and press Scan & identify."}
        plan = {it["file_id"]: it for it in app.st.cached("plan.json", [])} if new else {}
        arts = {}
        for r in inv:
            tg = dict(r.get("tags") or {})
            it = plan.get(r["id"])
            if it and it.get("album") and (it.get("verified") or it.get("approved")):       # the new (matched) tags
                tg.update(albumartist=it.get("artist_folder") or it.get("display_artist") or tg.get("albumartist"), album=it.get("album"),
                          year=it.get("year") or tg.get("year"), track=it.get("track") or tg.get("track"), disc=it.get("disc") or tg.get("disc"),
                          tracktotal=it.get("tracktotal") or tg.get("tracktotal"))
            a = (tg.get("albumartist") or tg.get("artist") or "").strip() or "(no artist tag)"
            al = (tg.get("album") or "").strip() or "(no album tag)"
            d = arts.setdefault(a, {"songs": set(), "albums": {}})
            d["songs"].add(r["id"])
            x = d["albums"].setdefault(al, {"album": al, "year": str(tg.get("year") or "")[:4], "type": "", "have": set(), "total": 0, "n": 0})
            x["n"] += 1
            try:
                x["have"].add((str(tg.get("disc") or "1"), int(str(tg.get("track") or "").split("/")[0])))
            except ValueError:
                pass
            try:
                x["total"] = max(x["total"], int(str(tg.get("tracktotal") or "0").split("/")[0]))
            except ValueError:
                pass
        out_arts = []
        for a, d in arts.items():
            als = []
            for al, x in d["albums"].items():
                owned = len(x["have"]) or x["n"]
                tot = x["total"] if x["total"] >= owned else 0
                pct = round(100 * owned / tot) if tot else 0
                als.append({"artist": a, "album": al, "release_id": "", "year": x["year"], "type": "", "tracks_owned": owned,
                            "tracks_total": tot, "percent": pct, "complete": bool(tot and owned >= tot), "missing": "", "fid": ""})
            als.sort(key=lambda x: (str(x["year"] or "9999"), x["album"].lower()))
            out_arts.append({"artist": a, "tier": "", "songs": len(d["songs"]), "releases": len(als),
                             "complete_releases": sum(1 for x in als if x["complete"]), "studio_total": 0, "studio_complete": 0,
                             "percent": 0, "albums": als})
        out_arts.sort(key=lambda r: -r["songs"])
        alls = [x for r in out_arts for x in r["albums"]]
        part = [x for x in alls if x["tracks_total"]]
        summary = {"artists": len(out_arts), "songs": sum(r["songs"] for r in out_arts), "releases": len(alls),
                   "complete_releases": sum(1 for x in alls if x["complete"]),
                   "almost_complete": sum(1 for x in part if not x["complete"] and x["tracks_total"] - x["tracks_owned"] <= 2),
                   "average_release_percent": round(sum(x["percent"] for x in part) / len(part)) if part else 0, "tiers_known": False}
        return {"summary": summary, "made": ("only the songs in your Sources" + (", with the new tags" if new else ", from your files' own tags")) if scope else "from your files' own tags (before Copy & tag)", "artists": out_arts, "tiers": [],
                "almost": [], "covers": "", "pics": False, "basis": "old"}

    def artist_pictures(self, names):
        """Artist photos from Deezer (only if you allowed Deezer; sends the artist names)."""
        if "deezer" not in (APP.cfg.get("alt_use") or []):
            return {}
        return APP.engine.call("artist_pics", list(names or [])[:40], timeout=150)

    def analyze_report(self, fmt, artist=""):
        """Analyze › Report: PDF, Excel or an image card for one artist, saved in <library>\\_Reports (never overwritten)."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        an = app.st.cached("analysis.json", {})
        if not an:
            return {"error": "No analysis yet: run Scan & identify."}
        import midnight_report as rep
        try:
            p = rep.excel(an, app.library) if fmt == "excel" else rep.pdf(an, app.library) if fmt == "pdf" else \
                rep.collection_card(an, app.library) if fmt == "collection" else rep.artist_card(an, app.library, artist)
        except Exception as e:
            self.report_error("analyze_report " + str(fmt), traceback.format_exc())      # v1.1: the details go to app_errors.txt
            return {"error": f"The report could not be made ({type(e).__name__}: {e})."}
        if mm.IS_WIN:
            try:
                os.startfile(p)
            except Exception:
                pass
        return {"ok": True, "path": p}

    def final_report(self):
        """V2.0.5 (#13): the final Excel report (Tagged, Before and after, _Unverified, Duplicates, Not found) in <library>\\_logs. Read only."""
        app = APP
        if not app.st or not app.st.cached("plan.json", []):
            return {"error": "Scan first."}
        import midnight_report as rep
        try:
            p = rep.final_report(app.st, app.library, APP_VERSION, app.decisions())
        except Exception:
            self.report_error("final_report", traceback.format_exc())
            return {"error": "The report could not be made. The details are in app_errors.txt."}
        app.activity("job", "Final Excel report made: " + os.path.basename(p), "ok", "report")
        if mm.IS_WIN:
            try:
                os.startfile(p)
            except Exception:
                pass
        return {"ok": True, "path": p}

    def album_tracks(self, release_id):
        """Analyze › open an album: every track, which ones you have (and the file), which are missing."""
        app = APP
        own = {}
        for it in app.st.cached("plan.json", []) if app.st else []:
            if it.get("release_id") == release_id and (it.get("approved") or it.get("fixed")) and not it.get("dup_extra"):
                own[(str(it.get("disc") or "1"), str(it.get("track") or ""))] = {"file": os.path.basename(it.get("src", "")), "fid": it["file_id"],
                                                                                  "path": it.get("new_path", "")}
        v = app.engine.call("release_view", release_id, timeout=300) or {}
        tracks = []
        for t in v.get("tracks") or []:
            k = (str(t.get("disc") or "1"), str(t.get("track") or ""))
            o = own.pop(k, None)
            tracks.append({"disc": k[0], "track": k[1], "title": t.get("title", ""), "length": t.get("length") or 0,
                           "have": bool(o), "file": (o or {}).get("file", ""), "fid": (o or {}).get("fid", ""),
                           "label": f"{k[0] + '-' if str(v.get('disctotal') or '1') not in ('', '1') else ''}{k[1].zfill(2)} {t.get('title', '')}"})
        for k, o in own.items():           # yours, but not on the track list (e.g. placed with your own tags)
            tracks.append({"disc": k[0], "track": k[1], "title": o["file"], "length": 0, "have": True, "file": o["file"], "fid": o["fid"], "label": o["file"]})
        return {"tracks": tracks, "error": v.get("error", "") if not tracks else "", "title": v.get("title", ""), "source": v.get("source", "")}

    def pick_audio(self):
        """Browse for one music file (Analyze › missing song)."""
        if APP.window is None:
            return None
        import webview
        r = APP.window.create_file_dialog(webview.OPEN_DIALOG, file_types=("Music files (*.mp3;*.flac;*.m4a;*.ogg;*.opus;*.wav;*.wma;*.aiff;*.aif)",))
        return (r[0] if isinstance(r, (list, tuple)) else r) if r else None

    def extra_copy(self, src, release_id, disc, track, title, artist, album, on=True, src_path=""):
        """'Copy it into this album': remembered now, done in the next Copy & tag (after your approval)."""
        app = APP
        reqs = app.st.load("app_extra_copies.json", [])
        key = (release_id, str(disc), str(track))
        reqs = [r for r in reqs if (r["release_id"], str(r["disc"]), str(r["track"])) != key or r.get("done")]
        if on:
            if src_path and not os.path.isfile(src_path):
                return {"error": "That file was not found."}
            reqs.append({"src": src, "release_id": release_id, "disc": str(disc), "track": str(track), "title": title,
                         "artist": artist, "album": album, "t": time.time(), **({"src_path": src_path} if src_path else {})})
        app.st.save("app_extra_copies.json", reqs)
        app.bump()
        return {"ok": True, "pending": sum(1 for r in reqs if not r.get("done"))}

    def extra_copies(self):
        return APP.st.load("app_extra_copies.json", []) if APP.st else []

    def open_url(self, url):
        """Opens a music site search in your browser (Apple Music, Deezer, YouTube Music, Bandcamp, Discogs)."""
        ok = re.match(r"^https://(music\.apple\.com|www\.deezer\.com|music\.youtube\.com|bandcamp\.com|www\.discogs\.com|musicbrainz\.org|acoustid\.org|www\.last\.fm|lrclib\.net)/", url or "")
        if not ok:
            return {"error": "Only music sites can be opened."}
        import webbrowser
        webbrowser.open(url)
        return {"ok": True}

    def find_on_pc(self, artist, title):
        """Looks for a song on every drive by file name and tags (read only; nothing is moved)."""
        return APP.engine.call("find_on_pc", artist, title, timeout=300)

    def pc_find_start(self, key, artist, title):
        """v1.1: starts a search in the background (read only); poll with pc_find_poll. Several can run at once."""
        APP.pcindex = APP.pcindex or PcIndex(APP)
        APP.pcindex.start(key, artist, title)
        return True

    def pc_find_artist(self, key, artist):
        APP.pcindex = APP.pcindex or PcIndex(APP)
        APP.pcindex.start(key, artist, None)
        return True

    def pc_find_poll(self, keys):
        APP.pcindex = APP.pcindex or PcIndex(APP)
        return APP.pcindex.state(list(keys or []))

    def pc_reindex(self):
        APP.pcindex = APP.pcindex or PcIndex(APP)
        APP.pcindex.ensure(force=True)
        return True

    def add_source_folder(self, path):
        """'Add to next scan': the folder of a file found on this PC becomes a music folder (Sources)."""
        return self.add_sources([os.path.dirname(path)], False)

    def plan_tree(self, folder=""):
        """Plan preview: the folders of the new library, one level at a time (read only)."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        try:
            mt = os.path.getmtime(app.st.p("plan.json"))
        except OSError:
            return {"error": "Scan first."}
        app.decisions()                                    # refreshes the decisions cache key used below
        dkey = (getattr(app, "_dec_cache", None) or (None,))[0]
        c = getattr(app, "_tree", None)
        if not c or c[0] != (app.st.logs, mt, dkey):
            plan = app.st.cached("plan.json", [])
            decs, cps = app.decisions(), copied_ids(app)
            prov = {r["file_id"]: r.get("status") for r in prov_rows(app.st)} \
                if mm.exists(app.st.p("music_provenance.csv")) else {}
            dirs, files = {}, {}
            lib = app.library.rstrip("\\/")
            stats = Counter()
            for it in plan:
                if it.get("kind") == "skip" or not it.get("new_path"):
                    continue
                rel = os.path.relpath(it["new_path"], lib) if mm.inside(it["new_path"], lib) else it["new_path"]
                parts = re.split(r"[\\/]", rel)
                st_ = song_state(it, decs, cps)                        # V2.0.5 (#2)
                st_ = "waiting" if st_ in ("later", "waiting") else "ready" if st_ == "decided" else st_
                stats[st_] += 1
                for i in range(len(parts) - 1):
                    key = "/".join(parts[:i])
                    d = dirs.setdefault(key, {})
                    e = d.setdefault(parts[i], {"songs": 0, "waiting": 0, "low": 0, "dups": 0, "nt": 0})
                    e["songs"] += 1
                    e["waiting"] += st_ == "waiting"
                    e["low"] += bool(it.get("match_percent") not in (None, "") and float(it.get("match_percent") or 100) < 90)   # v1.1.5 Library review
                    e["dups"] += bool(it.get("dup_extra"))
                    if i == len(parts) - 2:                         # the album folder: which release it is, how many tracks it should have
                        e["album"] = True
                        e["rid"] = e.get("rid") or it.get("release_id") or ""
                        e["nt"] = max(e["nt"], int(it.get("ntracks") or 0))
                files.setdefault("/".join(parts[:-1]), []).append({"name": parts[-1], "state": st_, "id": it["file_id"],
                                                                     "from": os.path.basename(it["src"]), "rid": it.get("release_id") or "",
                                                                     "pct": it.get("match_percent"), "dup": bool(it.get("dup_extra"))})
            app._tree = c = ((app.st.logs, mt, dkey), dirs, files, stats)
        _, dirs, files, stats = c
        sub = sorted(({"name": k, **v} for k, v in dirs.get(folder, {}).items()), key=lambda x: (not x["name"].startswith("_"), x["name"].lower()))
        fl = sorted(files.get(folder, []), key=lambda x: x["name"].lower())
        lay = dict(mm.DEFAULT_LAYOUT, **(app.cfg.get("layout") or {}))
        sample = next((it for it in app.st.cached("plan.json", []) if it.get("kind") == "release" and it.get("track")), None) if not folder else None
        return {"folder": folder, "dirs": sub, "files": fl[:500], "more_files": max(0, len(fl) - 500), "stats": dict(stats),
                "layout": lay, "sort_mode": app.cfg.get("sort_mode", "simple"), "library": app.library,
                "sample": {k: (sample or {}).get(k, "") for k in ("artist_folder", "credit_text", "album", "year", "track", "title",
                                                               "genre", "rtype", "tier", "disc", "ext")} if sample else None}

    def suggest_music(self, kind):
        """Analyze › Suggestions. 'upgrade' is local (songs worth replacing with a better file); 'similar' / 'gems' ask Last.fm (artist names only)."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        inv = app.st.cached("inventory.json", [])
        if kind == "upgrade":
            rows = []
            for r in inv:
                if r.get("error") or r.get("lossless"):
                    continue
                br = int(r.get("bitrate") or 0)
                if 0 < br < 192:
                    t = r.get("tags") or {}
                    rows.append({"artist": t.get("artist") or "", "title": t.get("title") or r.get("filename", ""), "album": t.get("album") or "",
                                 "kbps": br, "ext": r.get("ext", ""), "id": r.get("id", "")})
            rows.sort(key=lambda x: (x["kbps"], x["artist"].lower()))
            return {"items": rows[:300], "total": len(rows)}
        if kind in ("mixups", "renames"):
            return self._checks(kind, inv)
        an = app.st.cached("analysis.json", {})
        arts = an.get("artists", [])
        names = [a["artist"] for a in arts]
        top = [a["artist"] for a in sorted(arts, key=lambda a: -(a.get("songs") or 0))[:10]]
        few = [a["artist"] for a in arts if 0 < (a.get("songs") or 0) <= 2 and a.get("tier") != "Classical (not measured)"]
        return APP.engine.call("suggest_music", kind, {"all": names, "top": top, "few": few}, timeout=600)

    def song_artists(self, q):
        """Analyze search: which artists (folders) hold a song with this title? Local, read only."""
        app = APP
        q = mm.norm_key(q or "")
        if not app.st or len(q) < 3:
            return {}
        plan = app.st.cached("plan.json", [])
        key = (id(plan), len(plan))
        idx = getattr(app, "_song_idx", None)
        if not idx or idx[0] != key:
            rows = [(mm.norm_key(it.get("title") or ""), it.get("artist_folder") or it.get("display_artist") or "", it.get("title") or "")
                    for it in plan if it.get("title") and not it.get("dup_extra")]
            app._song_idx = idx = (key, rows)
        out = {}
        for nk, art, title in idx[1]:
            if art and q in nk:
                out.setdefault(art, [])
                if len(out[art]) < 3 and title not in out[art]:
                    out[art].append(title)
            if len(out) >= 300:
                break
        return out

    def artist_songs(self, artist):
        """Analyze > open an artist: the songs you have by this artist, album by album (local, read only)."""
        app = APP
        if not app.st or not artist:
            return []
        out = []
        for it in app.st.cached("plan.json", []):
            if it.get("dup_extra") or not it.get("title"):
                continue
            if (it.get("artist_folder") or it.get("display_artist") or "") != artist:
                continue
            try:
                tr = int(str(it.get("track") or 0).split("/")[0] or 0)
            except ValueError:
                tr = 0
            out.append({"id": it.get("file_id", ""), "title": it.get("title", ""), "album": it.get("album", "") or "",
                        "year": str(it.get("year") or ""), "track": tr, "disc": str(it.get("disc") or "1")})
            if len(out) >= 3000:
                break
        out.sort(key=lambda r: (r["year"] or "9999", r["album"].lower(), r["disc"], r["track"], r["title"].lower()))
        return out

    _SFX_RE = re.compile(r"\b(sfx|sound ?effects?|foley|whoosh|swoosh|explosion|footsteps?|door (?:open|close|slam)|beep|ringtone|jingle|stinger|ambience|ambient loop|impact|glitch|riser)\b", re.I)

    def _checks(self, kind, inv):
        """Analyze › Suggestions › two local checks (nothing is sent anywhere, nothing is changed):
        'mixups' = sound effects that were matched to a real song (and short real songs that look like effects),
        'renames' = artist names that the scan wants to change into a clearly different name."""
        app = APP
        plan = app.st.cached("plan.json", [])
        byid = {r.get("id"): r for r in inv}
        if kind == "mixups":
            rows = []
            for it in plan:
                r = byid.get(it.get("file_id")) or {}
                dur = it.get("duration") or r.get("duration") or 0
                t = r.get("tags") or {}
                name = f"{r.get('filename', '')} {os.path.basename(r.get('folder', ''))} {t.get('title', '')}"
                sfx = bool(self._SFX_RE.search(name))
                matched = bool(it.get("verified") and it.get("release_id"))
                why = ""
                if matched and 0 < dur < 25:
                    why = f"only {int(dur)} s long, but matched to a real album track"
                elif matched and sfx:
                    why = "the name looks like a sound effect, but it was matched to a real album track"
                elif sfx and dur >= 25 and not matched:
                    why = "looks like a sound effect (kept with your own tags)"
                if why:
                    rows.append({"id": it.get("file_id"), "artist": it.get("display_artist") or t.get("artist") or "", "title": it.get("title") or t.get("title") or r.get("filename", ""),
                                 "album": it.get("album") or t.get("album") or "", "why": why, "sec": int(dur), "to": it.get("name") or ""})
            for r in inv:             # short files that carry full tags and were not matched: maybe a real intro / skit, not an effect
                t = r.get("tags") or {}
                dur = r.get("duration") or 0
                if not r.get("error") and 0 < dur < 25 and t.get("artist") and t.get("album") and t.get("title") and not self._SFX_RE.search(r.get("filename", "")) \
                        and not any(x["id"] == r.get("id") for x in rows) and not any(it.get("file_id") == r.get("id") and it.get("verified") for it in plan):
                    rows.append({"id": r.get("id"), "artist": t["artist"], "title": t["title"], "album": t["album"], "sec": int(dur),
                                 "why": f"only {int(dur)} s, but it has full artist/album/title tags: a real intro or skit, not an effect?", "to": ""})
            rows.sort(key=lambda x: (x["sec"], x["artist"].lower()))
            return {"items": rows[:300], "total": len(rows)}
        cnt = {}
        for it in plan:
            r = byid.get(it.get("file_id")) or {}
            a0 = ((r.get("tags") or {}).get("artist") or "").strip()
            a1 = (it.get("display_artist") or it.get("entity") or "").strip()
            if not a0 or not a1 or it.get("dup_extra"):
                continue
            if sorted(re.findall(r"\w+", a0.lower())) == sorted(re.findall(r"\w+", a1.lower())) or mm.artist_agrees([a0], a1) or mm.ratio(a0, a1) >= 0.7:
                continue
            cnt.setdefault((a0, a1), []).append(it.get("title") or r.get("filename", ""))
        rows = [{"artist": a0, "to": a1, "n": len(ts), "songs": ts[:3]} for (a0, a1), ts in cnt.items()]
        rows.sort(key=lambda x: (-x["n"], x["artist"].lower()))
        return {"items": rows[:300], "total": len(rows)}

    def song_info(self, fid):
        """v2.0: one song of the library that is not in Review: the tags in your file next to the tags it gets (local, read only)."""
        app = APP
        if not app.st or not fid:
            return {"error": "Scan first."}
        r = app.inv_map().get(fid) or {}
        it = next((x for x in app.st.cached("plan.json", []) if x.get("file_id") == fid), None) or {}
        t = r.get("tags") or {}
        dec = (app.decisions() or {}).get(fid) if hasattr(app, "decisions") else None
        return {"id": fid, "file": r.get("filename") or it.get("name") or "", "path": r.get("path") or it.get("current_path") or "",
                "old": {"artist": t.get("artist", ""), "title": t.get("title", ""), "album": t.get("album", ""), "year": str(t.get("year") or ""), "track": str(t.get("track") or "")},
                "new": {"artist": it.get("display_artist") or "", "title": it.get("title") or "", "album": it.get("album") or "", "year": str(it.get("year") or ""), "track": str(it.get("track") or "")},
                "new_name": it.get("name") or "", "verified": bool(it.get("verified")), "kind": it.get("kind") or "",
                "duration": int(r.get("duration") or it.get("duration") or 0), "kbps": int(r.get("bitrate") or 0), "ext": r.get("ext", ""),
                "decided": bool(dec)}

    # ---- Library review (v1.1.5): the library next to Quick mode
    def lib_disk(self, folder=""):
        """The library folder as it is ON DISK, one level at a time (read only)."""
        app = APP
        if not app.library:
            return {"error": "No library folder."}
        base = os.path.join(app.library, *[p for p in re.split(r"[\\/]", folder or "") if p and p != ".."])
        if not mm.inside(base, app.library) and os.path.normcase(base) != os.path.normcase(app.library):
            return {"error": "Outside the library."}
        dirs, files = [], []
        try:
            for e in sorted(os.scandir(mm.lp(base)), key=lambda e: e.name.lower()):
                if e.is_dir(follow_symlinks=False):
                    dirs.append({"name": e.name, "songs": 0})
                elif os.path.splitext(e.name)[1].lower() in mm.AUDIO_EXTS:
                    files.append({"name": e.name, "state": "copied", "id": "", "from": ""})
        except OSError as ex:
            return {"error": f"{type(ex).__name__}: {ex}"}
        return {"folder": folder, "dirs": dirs, "files": files[:500], "more_files": max(0, len(files) - 500), "library": app.library}

    def lib_all(self, limit=30000):
        """Every planned song as one flat list (for the table and for searching). Capped."""
        app = APP
        if not app.st:
            return {"error": "Scan first."}
        lib = app.library.rstrip("\\/")
        rows = []
        _dec, _cp = app.decisions(), copied_ids(app)
        for it in app.st.cached("plan.json", []):
            if it.get("kind") == "skip" or not it.get("new_path"):
                continue
            rel = os.path.relpath(it["new_path"], lib) if mm.inside(it["new_path"], lib) else it["new_path"]
            _s = song_state(it, _dec, _cp)
            rows.append({"path": rel.replace("\\", "/"), "state": "waiting" if _s in ("later", "waiting") else "ready" if _s == "decided" else _s,
                         "id": it["file_id"], "pct": it.get("match_percent"), "rid": it.get("release_id") or "", "title": it.get("title") or "",
                         "artist": it.get("credit_text") or "", "album": it.get("album") or ""})
            if len(rows) >= limit:
                break
        return {"rows": rows, "capped": len(rows) >= limit}

    def lib_find(self, artist="", album="", release_id=""):
        """Where a song would land: albums of the planned library with the same release, or a similar name (for the jump + highlight)."""
        app = APP
        if not app.st:
            return {"hits": []}
        lib = app.library.rstrip("\\/")
        seen, hits = {}, []
        for it in app.st.cached("plan.json", []):
            if it.get("kind") == "skip" or not it.get("new_path"):
                continue
            rel = os.path.relpath(it["new_path"], lib) if mm.inside(it["new_path"], lib) else it["new_path"]
            folder = "/".join(re.split(r"[\\/]", rel)[:-1])
            if not folder or folder in seen:
                continue
            same = bool(release_id) and it.get("release_id") == release_id
            sim_a = mm.ratio(mm.norm_key(it.get("album") or ""), mm.norm_key(album or "")) if album else 0
            sim_r = mm.ratio(mm.norm_key(it.get("credit_text") or ""), mm.norm_key(artist or "")) if artist else 0
            score = 3 if same else (sim_a * 0.7 + sim_r * 0.3 if sim_a >= 0.6 else (0.4 if sim_r >= 0.9 and not album else 0))
            if score >= 0.4:
                seen[folder] = 1
                hits.append({"folder": folder, "score": round(score, 2), "why": "same album" if same else "similar album" if sim_a >= 0.6 else "same artist",
                             "rid": it.get("release_id") or "", "album": it.get("album") or ""})
        hits.sort(key=lambda h: -h["score"])
        return {"hits": hits[:8]}

    def set_layout(self, layout, sort_mode=None):
        """Customize folders: saved, then the plan is updated (nothing is copied)."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        lv = [x for x in (layout.get("levels") or []) if x in mm.LEVEL_NAMES]
        def pattern(p_):
            out = [x for x in (p_ or []) if isinstance(x, str) and (x in mm.PATTERN_TOKENS or (len(x) <= 5 and not re.search(r'[\\/:*?"<>|{}]', x)))]
            return out[:20]
        lay = {"levels": lv or ["artist"],
               "release": layout.get("release") if layout.get("release") in ("year_album", "album_year", "album", "custom") else "year_album",
               "file": layout.get("file") if layout.get("file") in ("full", "track_title", "artist_track_title", "custom") else "full",
               "release_pattern": pattern(layout.get("release_pattern")), "file_pattern": pattern(layout.get("file_pattern")),
               "tier_style": "name" if layout.get("tier_style") == "name" else "folder",
               "tier_name": layout.get("tier_name") if layout.get("tier_name") in ("bracket", "dash", "suffix") else "bracket"}
        if lay["tier_style"] == "name" and "tier" not in lay["levels"]:
            lay["levels"] = ["tier"] + lay["levels"]          # the tier is still worked out; it just goes into the name
        if lay["release"] == "custom" and not any(x in mm.PATTERN_TOKENS for x in lay["release_pattern"]):
            lay["release"] = "year_album"
        if lay["file"] == "custom" and "{title}" not in lay["file_pattern"]:
            return {"error": "The file name needs the Title block."}
        app.cfg["layout"] = lay
        if sort_mode in ("simple", "collection"):
            app.cfg["sort_mode"] = sort_mode
        app.save_cfg()
        start_job({}, True)
        return {"ok": True}

    def fullscreen(self):
        """F11: full screen on / off (desktop window only)."""
        try:
            if APP.window:
                APP.window.toggle_fullscreen()
                return {"ok": True}
        except Exception as e:
            return {"error": f"Full screen is not available ({e})."}
        return {"error": "Full screen works in the desktop window only."}

    def pause(self, on=True):
        """Pause / resume the running scan (it waits right where it is)."""
        if not APP.busy():
            return {"error": "No scan is running."}
        APP.engine.pause(bool(on))
        with APP.lock:
            APP.job["paused"] = bool(on)
            APP.rev += 1
        APP.log("Paused." if on else "Resumed.")
        return {"ok": True}

    def dashboard(self):
        return dashboard()

    def stamp(self):
        """1.1.5: a tiny 'did anything change?' answer (file times of the plan, the scan and your choices), so screens that are already
        loaded are not rebuilt (and re-sent, which took seconds on big libraries) every time you switch to them."""
        st = APP.st
        if not st:
            return ""
        out = []
        for n in ("plan.json", "inventory.json", "app_decisions.json", "analysis.json", "app_neat.json"):
            try:
                out.append(str(int(os.path.getmtime(st.p(n)) * 1000)))
            except OSError:
                out.append("0")
        return "-".join(out)

    def report_error(self, where, message):
        """Errors from the screens are written to <library>/_logs/app_errors.txt (or next to the app)."""
        for folder in {APP.st.logs if APP.st else mm.APP_DIR, mm.APP_DIR}:     # also next to the app, always
            try:
                with open(mm.lp(os.path.join(folder, "app_errors.txt")), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  v{APP_VERSION}  [{where}]  library: {APP.library}\n{message}\n\n")
            except OSError:
                pass
        APP.log(f"Screen error ({where}): {str(message).splitlines()[0][:200]}")
        return True

    # ---- review
    def review_list(self):
        return review_list()

    def dup_list(self):
        """Duplicates: every song found more than once, best copy first, with your choices."""
        app = APP
        if not app.st:
            return {"groups": []}
        rows = app.st.cached("duplicates.json", [])
        plan = {it["file_id"]: it for it in app.st.cached("plan.json", [])}
        inv = app.inv_map()
        ch = app.st.load("app_dups.json", {})
        qual = {k.split("|")[0]: v for k, v in app.st.load("dup_quality.json", {}).items()}
        groups = {}
        for r in rows:
            it = plan.get(r["file_id"]) or {}
            iv = inv.get(r["file_id"]) or {}
            r = dict(r, extra=bool(it.get("dup_extra")), kind=it.get("dup_kind", ""), bits=iv.get("bits") or "",
                     codec=iv.get("codec", ""), quality=qual.get(r["file_id"]), dup_of=it.get("dup_of", ""),
                     flat=bool(it.get("dup_flat")), tag=bool(it.get("dup_tag")), dup_name=it.get("dup_name", ""))
            groups.setdefault(r.get("group"), []).append(r)
        out = []
        cmp_ = app.st.load("app_dupcmp.json", {})
        for gid, cs in groups.items():
            cs.sort(key=lambda c: c.get("rank") or 99)
            kinds = {c.get("kind") for c in cs if not c["extra"]}
            sure, how = dup_sureness(cs, plan, inv, cmp_.get(gid))
            out.append({"group": gid, "copies": cs, "identical": any(c.get("identical_audio") for c in cs),
                        "pair": "lossless" in kinds and "compressed" in kinds, "lower": any(c["extra"] and not c.get("identical_audio") for c in cs),
                        "choice": ch.get(gid), "sure": sure, "sure_how": how, "live": live_mismatch(cs) or version_mismatch(cs)})
        # the least sure first: those are the ones worth a listen (Artist order is a choice on the page)
        out.sort(key=lambda g: (g["sure"], (g["copies"][0].get("artist") or "~").lower(), (g["copies"][0].get("title") or "").lower()))
        loony = os.path.join(app.library, "_LoonyBin") if app.library else ""
        dec_ = app.decisions()
        pend = [i_ for i_ in plan.values() if i_.get("dup_possible") and not i_.get("approved") and not i_.get("dup_extra")
                and (dec_.get(i_["file_id"]) or {}).get("action") in (None, "reject", "later")]
        return {"groups": out, "possible": len(pend), "possible_ids": [i_["file_id"] for i_ in pend][:500],
                "covers": AUDIO.base + "cover/" if AUDIO else "", "loony": loony,
                "loony_count": len([f for f in os.listdir(mm.lp(loony)) if not f.endswith(".csv")]) if loony and os.path.isdir(mm.lp(loony)) else 0,
                "stale": bool(ch) and max([c.get("t", 0) for c in ch.values()] + [0]) > (os.path.getmtime(app.st.p("plan.json")) if mm.exists(app.st.p("plan.json")) else 0)}

    def dup_choose(self, group, mode, include=None, leave=None):
        """Your choice for one song: 'best' (best of each kind), 'all' (every copy), 'custom' (ticks), or 'undo'.
        Used when the plan is updated; nothing is copied here."""
        app = APP
        ch = app.st.load("app_dups.json", {})
        if mode == "undo":
            ch.pop(group, None)
        else:
            ch[group] = {"mode": mode, "include": list(include or []), "leave": list(leave or []), "t": time.time()}
        app.st.save("app_dups.json", ch)
        app.bump()
        return {"ok": True}

    def dup_best_everywhere(self):
        app = APP
        ch = app.st.load("app_dups.json", {})
        t = time.time()
        skipped = 0
        for g in self.dup_list().get("groups", []):        # v1.1: only where the app is at least 90% sure it is the same song
            if g["sure"] >= 90:
                ch.setdefault(g["group"], {"mode": "best", "include": [], "leave": [], "t": t})
            elif not g.get("choice"):
                skipped += 1
        app.st.save("app_dups.json", ch)
        app.bump()
        return {"ok": True, "skipped": skipped}

    def dup_quality(self, fids):
        return APP.engine.call("dup_quality", list(fids), timeout=900)

    def dup_compare(self, fids, group=""):
        r = APP.engine.call("dup_compare", list(fids), timeout=600)
        if group and r and r.get("pairs") and APP.st:        # remember it: it decides how sure the page is
            pcts = [p_["pct"] for p_ in r["pairs"] if p_.get("pct") is not None]
            if pcts:
                c = APP.st.load("app_dupcmp.json", {})
                c[group] = {"pct": min(pcts), "t": time.time()}
                APP.st.save("app_dupcmp.json", c)
        return r

    def start_loonybin(self, mode="copy"):
        """DupCop: COPY every extra copy into <library>\\Loony Bin (one folder). Originals are only read."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        with app.lock:
            app.job = {"kind": "loonybin", "started": time.time(), "done": False, "error": "", "stage": "loonybin",
                       "mode": app.cfg.get("scan_mode", "simple")}
            app.progress = None
            app.lines = []
            app.rev += 1
        app.engine.job("loonybin", {"loony_mode": mode if mode in ("copy", "C01", "C02", "C03", "C04") else "copy"})
        return {"ok": True}

    def review_decide(self, fid, d):
        """Save your choice for one song (applied to the plan by 'Update the plan'). Nothing is copied here."""
        app = APP
        dec = app.decisions()
        same = d.pop("same_folder", False)
        d["t"] = time.time()
        ids = [fid]
        if same and d.get("action") in ("unverified", "later"):
            items = review_list()["items"]
            me = next((x for x in items if x["id"] == fid), None)
            if me:
                ids += [x["id"] for x in items if x["kind"] == "none" and x["folder"] == me["folder"]
                        and x["id"] != fid and not dec.get(x["id"])]
        for i in ids:
            if d.get("action") == "undo":
                dec.pop(i, None)
            else:
                dec[i] = dict(d)
        app.save_decisions(dec)
        app.bump()
        return {"ok": True, "ids": ids}

    def review_decide_many(self, ids, d):
        """The same choice for several songs at once (group select). Nothing is copied here."""
        app = APP
        dec = app.decisions()
        kinds = {x["id"]: x["kind"] for x in review_list()["items"]}
        d = dict(d, t=time.time())
        done = []
        for i in ids or []:
            if i not in kinds:
                continue
            if d.get("action") == "undo":
                dec.pop(i, None)
            else:
                dec[i] = dict(d, kind0=kinds[i])
            done.append(i)
        app.save_decisions(dec)
        app.bump()
        return {"ok": True, "ids": done}

    def review_search(self, fid, artist, title, album, deep=False):
        return APP.engine.call("search", fid, artist, title, album, bool(deep))

    def review_sound(self, fid):
        return APP.engine.call("sound", fid)

    def review_link(self, url):
        rel = APP.engine.call("link", url)
        if rel and rel.get("tracks"):
            rel["owned"] = owned_slots(rel["tracks"][0]["match"].get("release_id"))
        return rel

    def review_suggest(self, fid):
        """PLACE: the release(s) your tags or folder name point to, with their track slots (MusicBrainz)."""
        r = APP.engine.call("suggest", fid)
        for rel in (r or {}).get("releases") or []:
            if rel.get("mbid"):
                rel["owned"] = owned_slots(rel["mbid"])
        return r or {"releases": []}

    def review_group(self, fids, artist, album, url=""):
        r = APP.engine.call("group", fids, artist, album, url or "")
        for rel in (r or {}).get("releases") or []:
            if rel.get("tracks"):
                rel["owned"] = owned_slots(rel["tracks"][0]["match"].get("release_id"))
        return r

    def preview_url(self, deezer_track):
        return APP.engine.call("preview", deezer_track, timeout=30)

    def review_decide_each(self, pairs):
        """Several songs, each with its own choice (an album group). Nothing is copied here."""
        app = APP
        dec = app.decisions()
        kinds = {x["id"]: x["kind"] for x in review_list()["items"]}
        done = []
        for fid, d in pairs or []:
            if fid in kinds:
                dec[fid] = dict(d, t=time.time(), kind0=kinds[fid])
                done.append(fid)
        app.save_decisions(dec)
        app.bump()
        return {"ok": True, "ids": done}

    def reveal(self, fid):
        """Show the song in Windows Explorer (selected). Opens Explorer only; nothing is changed."""
        r = APP.inv_map().get(fid)
        path = r and r.get("path")
        if not path or not os.path.exists(mm.lp(path)):
            return {"error": "The file is not there any more."}
        if mm.IS_WIN:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return {"ok": True}
        return {"error": "Only on Windows.", "path": path}

    def update_plan(self, mode="fast"):
        """'fast' (default): only the songs whose choice changed are worked out again - seconds, no searching.
        'full': the whole plan again (every answer is cached, but it takes longer on big libraries)."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        if not app.st or not app.st.cached("inventory.json", []):
            return {"error": "Scan first."}
        if mode == "fast" and app.st.cached("plan.json", []):
            with app.lock:
                app.job = {"kind": "fastupdate", "started": time.time(), "done": False, "error": "", "stage": "identify",
                           "mode": app.cfg.get("scan_mode", "simple")}
                app.progress = None
                app.lines = []
                app.rev += 1
            app.engine.job("fastupdate", {})
            return {"ok": True}
        start_job({}, True)
        return {"ok": True}

    def use_cached(self, mode="use"):
        """After you cancelled a scan: 'use' = build the plan from what was already looked up (no internet),
        'add' = the same, but only the FOUND songs are added to the plan you already have."""
        app = APP
        if app.busy():
            return {"error": "Please wait: something is already running."}
        if not app.st or not app.st.cached("inventory.json", []):
            return {"error": "Nothing was read yet, so there is nothing to use."}
        sv = dict(services_from_cfg(app.cfg), cache_only=True, merge=(mode == "add"))
        start_job({"services": sv}, True)
        return {"ok": True}

    @staticmethod
    def _inv(fid):
        return APP.inv_map().get(fid)

    def open_folder(self, path):
        if path and os.path.isdir(path) and mm.IS_WIN:
            os.startfile(path)      # opens Explorer; nothing is changed
            return True
        return False


# ----------------------------------------------------------------------------- start

def _windows_icon_id():
    """2.0.2 (item 82): Windows groups the taskbar button by app id. Without our own id it uses Python's, with Python's icon."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Midnight.MusicSorter.2")
    except Exception:
        pass


def _windows_icon_set():
    """Puts midnight.ico on the window and the taskbar button (needs midnight.ico next to the app; if it is missing nothing changes)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ico = os.path.join(HERE, "midnight.ico")
        if not os.path.isfile(ico):
            ico = os.path.join(getattr(sys, "_MEIPASS", HERE), "midnight.ico")
        if not os.path.isfile(ico):
            return
        u = ctypes.windll.user32
        hwnd = 0
        for _ in range(40):                                  # the window may need a moment to exist
            hwnd = u.FindWindowW(None, APP_NAME)
            if hwnd:
                break
            time.sleep(0.25)
        if not hwnd:
            return
        for which, metric in ((0, 49), (1, 11)):             # ICON_SMALL / ICON_BIG at the sizes Windows wants
            px = u.GetSystemMetrics(metric)
            h = u.LoadImageW(0, ico, 1, px, px, 0x10)
            if h:
                u.SendMessageW(hwnd, 0x80, which, h)
    except Exception:
        pass


def run_desktop():
    import webview
    _windows_icon_id()
    api = Api()
    custom_bar = os.path.exists(os.path.join(HERE, "_titlebar_on.txt"))          # 1.1.7 beta: own round Minimize / Close buttons
    try:          # 2.0.2: the window opens maximized (fills the screen); older pywebview versions fall back to the normal size
        win = webview.create_window(APP_NAME, os.path.join(UI_DIR, "index.html"), js_api=api, maximized=True,
                                    width=1360, height=900, min_size=(980, 640), background_color="#111214", frameless=custom_bar)
    except TypeError:
        win = webview.create_window(APP_NAME, os.path.join(UI_DIR, "index.html"), js_api=api,
                                    width=1360, height=900, min_size=(980, 640), background_color="#111214", frameless=custom_bar)
    APP.window = win

    def on_loaded():
        try:
            from webview.dom import DOMEventHandler

            def on_drop(e):
                files = (e.get("dataTransfer") or {}).get("files") or []
                paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
                folders = [p for p in paths if os.path.isdir(p)]
                with APP.lock:
                    APP.dropped = {"folders": folders, "files": [p for p in paths if not os.path.isdir(p)], "t": time.time()}
                    APP.rev += 1
            win.dom.document.events.drop += DOMEventHandler(on_drop, True, True)     # only the drop reaches Python
        except Exception as ex:          # older pywebview: Browse… still works
            APP.log(f"(drag & drop not available: {ex})")
    win.events.loaded += on_loaded
    threading.Thread(target=_windows_icon_set, daemon=True).start()
    # remember the window's own settings (last Review spot, look, sort choices...) between starts
    store = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Midnight 00-01", "window")
    try:
        os.makedirs(store, exist_ok=True)
        webview.start(debug="--debug" in sys.argv, private_mode=False, storage_path=store)
    except TypeError:                                        # older pywebview
        webview.start(debug="--debug" in sys.argv)


def run_browser(port=8765):
    """The same app in a normal browser (for testing): http://127.0.0.1:8765"""
    import http.server
    import socketserver
    api = Api()

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=UI_DIR, **k)

        def end_headers(self):          # V2.0.5: the browser view never keeps an old copy of the screens (an edited file showed the old behaviour)
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass

        def do_POST(self):
            origin = self.headers.get("Origin") or ""
            if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                self.send_response(403)
                self.end_headers()
                return
            name = self.path.strip("/").split("/")[-1]
            ln = int(self.headers.get("Content-Length") or 0)
            args = json.loads(self.rfile.read(ln) or b"[]")
            fn = getattr(api, name, None)
            try:
                res = fn(*args) if fn and not name.startswith("_") else {"error": "unknown call"}
                body = json.dumps(res, ensure_ascii=False).encode()
                self.send_response(200)
            except Exception as e:
                body = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
                self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
    print(f"Midnight 00:01 running at http://127.0.0.1:{port}  (Ctrl+C to quit)")
    S(("127.0.0.1", port), H).serve_forever()


def main():
    if sys.stdout is None:          # packaged app has no console: keep the engine's prints harmless
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    if mm.mutagen is None:
        print("Missing library: pip install mutagen openpyxl pillow pywebview")
        sys.exit(1)
    try:                            # 1.1.6: which folder and version really started (so a wrong shortcut is easy to spot)
        with open(os.path.join(HERE, "_last_run.txt"), "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  v{APP_VERSION}\n{HERE}\n")
    except OSError:
        pass
    global AUDIO
    AUDIO = AudioServer()
    APP.engine.start()              # the engine works in its own process: the window never freezes
    APP.preload()
    mm.keep_awake(True)
    try:
        if "--browser" in sys.argv:
            run_browser(int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765)
        else:
            run_desktop()
    finally:
        APP.engine.quit()
        mm.keep_awake(False)


if __name__ == "__main__":
    multiprocessing.freeze_support()          # needed for the packaged .exe
    main()

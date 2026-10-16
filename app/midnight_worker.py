# -*- coding: utf-8 -*-
"""
Midnight 00:01 · Music Sorter - engine worker
=============================================
Runs the engine (music_manager.py) in its OWN process, next to the app window, so the window never freezes
- not even while the 270 MB lookup memory (_cache) is loaded or while thousands of files are read.

The window process sends commands; this process answers with events:
    commands: {"op": "job", ...}  scan / update (read-only phases)
              {"op": "call", ...} Review lookups (search again, identify by sound, link, suggested album)
              {"op": "preload"}   load the lookup memory in the background
              {"op": "quit"}
    events:   log / progress / stage / job_done / result / status
Safety rules are the engine's own: this file adds no file operations.
"""
from __future__ import annotations

import io
import os
import re
import sys
import threading
import time
import traceback


class StopRequested(RuntimeError):
    def __init__(self):
        super().__init__("Cancelled by you. Nothing was changed; the last finished results stay, and answers found so far are kept in the cache.")


def strip_site_words(text):
    """v1.1.5: site names / URLs / 'downloaded from' words are left out of the deep search words (engine function)."""
    import music_manager as mm          # V2.0.3: was a bare 'mm' (NameError in Dig deeper)
    return mm.strip_site_words(text)


def openopus_names(text):
    """Kept for Dig deeper: the engine function (blocked by CACHE_ONLY, silent on failure)."""
    import music_manager as mm          # V2.0.3
    return mm.openopus_names(text)



CLASSICAL_WORDS = re.compile(r"\b(symphon\w*|concert[oi]|sonat[ae]|quartet|quintet|opus|op\.? ?\d+|bwv ?\d+|hwv ?\d+|kv?\. ?\d+|"
                             r"nocturne|prelude|fugue|[ée]tude|requiem|adagio|allegro|andante|largo|scherzo|overture|cantata|"
                             r"partita|mazurka|polonaise|movement|in [a-g](?:[- ](?:flat|sharp))? (?:major|minor))\b", re.I)

ANSWER_RULES = [
    (r"^use the same sources again", lambda a: "y"),
    (r"^musicbrainz \(main source", lambda a: "y" if a.get("mb") else "n"),
    (r"^musicbrainz asks for a contact", lambda a: a.get("contact", "")),
    (r"^use identify by sound", lambda a: "y" if a.get("acoustid") else "n"),
    (r"acoustid api key", lambda a: a.get("acoustid_key", "")),
    (r"^discogs\?", lambda a: "y" if a.get("discogs") else "n"),
    (r"discogs personal token", lambda a: a.get("discogs_token", "")),
    (r"^deezer\?", lambda a: "y" if a.get("deezer") else "n"),
    (r"^apple music / itunes\?", lambda a: "y" if a.get("itunes") else "n"),
    (r"^tidal\?", lambda a: "y" if a.get("tidal") else "n"),
    (r"tidal client id", lambda a: a.get("tidal_id", "")),
    (r"tidal client secret", lambda a: a.get("tidal_secret", "")),
    (r"^spotify\?", lambda a: "y" if a.get("spotify") else "n"),
    (r"spotify client id", lambda a: a.get("spotify_id", "")),
    (r"spotify client secret", lambda a: a.get("spotify_secret", "")),
    (r"^last\.fm\?", lambda a: "y" if a.get("lastfm") else "n"),
    (r"last\.fm api key", lambda a: a.get("lastfm_key", "")),
    (r"new order \(numbers", None),               # None = keep the engine's default (order saved in config)
    (r"^sort mode", lambda a: "c" if a.get("sort_mode") == "collection" else "s"),
    (r"layout \(enter = keep\)", None),
    (r"^analyze the collection", lambda a: "y" if a.get("analyze", True) else "n"),
    (r"^cover art for confirmed songs", lambda a: "y" if a.get("covers") else "n"),
    (r"^lyrics for confirmed songs", lambda a: "y" if a.get("lyrics") else "n"),
    (r"^reuse your earlier review answers", lambda a: "y"),
    (r"^re-check the .* already organized", lambda a: "n"),
    (r"^where should the originals go", lambda a: a.get("archive", "")),
    (r"^\s*use it anyway", lambda a: "n"),
]


def recycle(path):
    """Windows Recycle Bin (can be restored from there). Raises if it did not work - nothing else is tried."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI = 3, 0x40, 0x10, 0x4, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, os.path.abspath(path) + "\0", None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc or op.fAnyOperationsAborted or os.path.exists(path):
        raise OSError(f"the Recycle Bin did not take it (code {rc})")


class Worker:
    defer_review = True          # the engine leaves grouped review questions to the app's Review screen

    def __init__(self, cmd_q, evt_q, stop_ev, pause_ev=None):
        self.cmd_q, self.evt_q, self.stop_ev, self.pause_ev = cmd_q, evt_q, stop_ev, pause_ev
        self.answers, self.approvals, self.confirms = {}, [], []
        self.answer_slots, self.recent_lines = {}, []
        self.copy_ids = None
        self.st = None
        self.look = {}            # library -> (mb, alt)
        self.look_lock = threading.Lock()
        self.job_running = False
        import music_manager as mm
        self.mm = mm
        mm.UI = self

    # ---------------------------------------------------------------- events to the window
    def emit(self, **e):
        try:
            self.evt_q.put(e)
        except Exception:
            pass

    # ---------------------------------------------------------------- engine hooks (music_manager.UI)
    def say(self, text):
        for line in str(text).splitlines():
            if line.strip() and not re.fullmatch(r"[=\-\s]+", line):
                self.emit(t="log", line=line.rstrip())
                self.recent_lines.append("".join(ch for ch in line.rstrip() if ch.isprintable() or ch == "\t"))
                del self.recent_lines[:-60]

    def cancelled(self):
        return bool(self.job_running and self.stop_ev.is_set())

    def progress(self, p):
        if self.job_running and self.stop_ev.is_set() and not p.finished:
            raise StopRequested()
        if self.job_running and self.pause_ev is not None and self.pause_ev.is_set() and not p.finished:
            t_pause = time.time()
            while self.pause_ev.is_set() and not self.stop_ev.is_set():      # paused: wait right here
                time.sleep(0.3)
            if self.stop_ev.is_set():
                raise StopRequested()
            p.t0 += time.time() - t_pause            # the pause does not count as working time
            w_ = getattr(self, "_rate", None)
            if w_:
                w_["pts"].clear()
        el = time.time() - p.t0
        now = time.time()
        if not p.finished and now - getattr(self, "_last_p", 0) < 0.25:
            return
        self._last_p = now
        # time left from the RECENT speed (last ~3 minutes), not the average since the start: songs found in the
        # lookup memory go very fast at first, new or messy ones are slower, so the old average was far too low
        w = getattr(self, "_rate", None)
        if w is None or w["label"] != p.label or w["t0"] != p.t0:
            w = self._rate = {"label": p.label, "t0": p.t0, "pts": []}
        pts = w["pts"]
        if not pts or now - pts[-1][0] >= 2:
            pts.append((now, p.n))
            while len(pts) > 2 and now - pts[0][0] > 180:
                pts.pop(0)
        left = None
        if p.total and p.n:
            t_a, n_a = pts[0]
            if now - t_a >= 20 and p.n > n_a:
                rate = (p.n - n_a) / (now - t_a)
                avg = p.n / max(el, 1e-6)
                rate = min(rate, avg * 3) if el > 60 else rate
                left = (p.total - p.n) / rate
            elif el >= 20:
                left = el / p.n * (p.total - p.n)
        self.emit(t="progress", p={"label": p.label, "n": p.n, "total": p.total or 0, "cur": p.cur or "",
                                   "extra": p.extra or "", "elapsed": round(el), "finished": p.finished,
                                   "left": None if left is None else round(left)})

    def ask(self, q, default=""):
        """Answers from your on-screen choices. Unknown questions get the engine's safe default (No for every
        'go ahead?' question). A copy / move is only approved when the window sent that exact approval."""
        ql = q.strip().lower()
        for i, (pat, ans) in enumerate(list(getattr(self, "script", []) or [])):   # Find & restore: answers given on screen
            if re.search(pat, ql):
                self.script.pop(i)
                return ans
        for pat, fn in ANSWER_RULES:
            if re.search(pat, ql):
                return default if fn is None else fn(self.answers)
        for pat in list(self.approvals):
            if re.search(pat, ql):
                self.approvals.remove(pat)          # one approval = one answer
                return "y"
        for pat in list(self.confirms):            # asked on screen: "Are you sure?" with the details
            if re.search(pat, ql):
                return self.confirm_on_screen(q)
        self.emit(t="log", line=f"(asked: {q.strip().splitlines()[0][:90]} -> {default or 'no answer'})")
        return default

    def confirm_on_screen(self, q):
        """Shows the question (and the summary the engine just printed) in the window and waits for your
        answer. Cancel / Stop = No."""
        cid = f"q{time.time():.3f}"
        ev = threading.Event()
        self.answer_slots[cid] = [ev, "n"]
        self.emit(t="confirm", id=cid, question=q.strip(), details=list(self.recent_lines[-40:]))
        while not ev.wait(0.5):
            if self.stop_ev.is_set():
                break
        self.emit(t="confirm_done", id=cid)
        return self.answer_slots.pop(cid, [None, "n"])[1]

    def decisions(self):
        return self.st.load("app_decisions.json", {}) if self.st else {}

    def dup_choices(self, dup_groups):
        """Duplicates page: copies you included are copied too (named (02), (03)...); copies you left out are not."""
        ch = self.st.load("app_dups.json", {}) if self.st else {}
        live_re = re.compile(r"\b(live|unplugged|in concert|concert|bootleg)\b|\(live|\[live", re.I)
        for g in dup_groups:
            c = ch.get(g[0]["file_id"])
            if not c:                                      # v1.1: a live version next to a studio one is not a duplicate
                flags = {bool(live_re.search(" ".join(str(it.get(k) or "") for k in ("title", "album", "new_name", "name", "source")))) for it in g}
                inv_ = {r["id"]: r for r in self.st.cached("inventory.json", [])} if self.st else {}
                lens = [(inv_.get(it["file_id"]) or {}).get("duration") or 0 for it in g]
                vers = {tuple(sorted(self.mm.version_tags(it.get("title") or it.get("name") or ""))) if hasattr(self.mm, "version_tags") else () for it in g}
                if len(flags) > 1 or (lens and all(lens) and max(lens) - min(lens) > 3) or len(vers) > 1:
                    c = {"mode": "all"}          # V2.0.3 decision 7: another version / length is never left out
                else:
                    continue
            inc, leave = set(c.get("include") or []), set(c.get("leave") or [])
            if c.get("mode") == "all":
                inc = {it["file_id"] for it in g}
            for it in g:
                fid = it["file_id"]
                if fid in inc and (it.get("dup_extra") or it.get("dup_flat")):
                    # you chose to keep it: it stays in its own album (a second file of the same kind is numbered "(2)" there), no DUPLICATE tag
                    it.update(approved=True, dup_extra=False, dup_keep=True, dup_flat=False, dup_tag=False, dup_user_keep=True, reason="")
                    if it.get("dup_orig_folder"):
                        it["folder"] = it.pop("dup_orig_folder")
                    it.pop("dup_name", None)
                elif fid not in inc and it.get("dup_user_keep"):
                    it.pop("dup_user_keep", None)      # you undid "keep": the next duplicate check sends it back to _Duplicates
                if fid in leave and not it.get("dup_extra"):
                    it.update(approved=False, dup_extra=True, reason="left out by you (Duplicates)", review=None)

    def keep_tags_ids(self):
        """Neat Picky 'Keep my tags': these songs are placed in the library, but their tags are not changed."""
        return {k for k, v in (self.st.load("app_neat.json", {}) if self.st else {}).items() if v.get("action") == "keep"}

    def mixed_ids(self):
        return set(self.st.load("app_mixed.json", [])) if self.st else set()

    def review_results(self, results, res, inv_by_id):
        for fid, d in self.decisions().items():
            if fid not in results:
                continue
            a = d.get("action")
            if a == "pick" and d.get("match"):
                results[fid] = (d["match"], "high")
            elif a in ("unverified", "reject"):
                results[fid] = (None, "low")
            elif a == "trust" and inv_by_id.get(fid):
                results[fid] = (self.mm.match_from_tags(inv_by_id[fid]), "high")
            elif a == "edit" and inv_by_id.get(fid):          # V2.0.3: the tag editor - exactly the tags you typed
                results[fid] = (self.mm.match_from_tags(self.edited(inv_by_id[fid], d)), "high")

    @staticmethod
    def edited(r, d):
        """A copy of the song's record whose tags are the ones typed in the tag editor."""
        r2 = dict(r)
        t = dict(r.get("tags") or {})
        for k, v in (d.get("fields") or {}).items():
            if v is not None:
                t[k] = str(v).strip()
        if t.get("artist") and not (d.get("fields") or {}).get("albumartist"):
            t["albumartist"] = t["artist"] if not (r.get("tags") or {}).get("albumartist") else t.get("albumartist", "")
        r2["tags"] = t
        return r2

    def review_approvals(self, items):
        dec = self.decisions()
        for fid, it in items.items():
            d = dec.get(fid)
            if not d or it.get("kind") == "skip":
                continue
            if d.get("action") in ("accept", "pick", "unverified", "trust", "edit"):
                it["approved"], it["reason"] = True, ""
            elif d.get("action") == "later":
                it["approved"], it["reason"] = False, "left for later (Review)"
            elif d.get("action") == "leave":
                it["approved"], it["reason"], it["left_out"] = False, "left out by you (Review)", True

    # ---------------------------------------------------------------- library + lookups
    def store(self, library):
        logs = os.path.join(library, "_logs")
        os.makedirs(self.mm.lp(logs), exist_ok=True)
        st = self.mm.Store(logs)
        return st, st.load("config.json", {})

    def lookups(self, library):
        mm = self.mm
        with self.look_lock:
            st, cfg = self.store(library)
            if library not in self.look:
                self.emit(t="status", lookups="loading")
                mb = mm.MusicBrainz(st, cfg.get("mb_contact", "")) if cfg.get("use_mb", True) else None
                alt = mm.AltSources(st, cfg.get("alt_use", []), cfg.get("discogs_token", ""), cfg.get("lastfm_key", ""), cfg.get("tidal_id", ""), cfg.get("tidal_secret", ""), cfg.get("spotify_id", ""), cfg.get("spotify_secret", ""))
                self.look[library] = (mb, alt)
                self.emit(t="status", lookups="ready")
            mb, alt = self.look[library]
            if mb is None and cfg.get("use_mb", True):
                mb = mm.MusicBrainz(st, cfg.get("mb_contact", ""))
                self.look[library] = (mb, alt)
            if alt:
                alt.use, alt.token, alt.lfm_key = cfg.get("alt_use", []), cfg.get("discogs_token", ""), cfg.get("lastfm_key", "")
                alt.tidal_id, alt.tidal_secret = cfg.get("tidal_id", ""), cfg.get("tidal_secret", "")
                alt.spotify_id, alt.spotify_secret = cfg.get("spotify_id", ""), cfg.get("spotify_secret", "")
                alt.order = mm.full_alt_order(cfg)          # v1.1: the order from Settings is used by Review searches too
                alt.order = mm.full_alt_order(cfg)
                alt.cover_order = list(cfg.get("cover_order") or mm.COVER_ORDER)
            return (mb if cfg.get("use_mb", True) else None), alt, st, cfg

    def save_caches(self):
        mm = self.mm
        keep = {id(x) for pair in self.look.values() for x in pair if x}
        for c in list(mm.LIVE_CACHES):
            try:
                c.save()
            except Exception:
                pass
        mm.LIVE_CACHES[:] = [c for c in mm.LIVE_CACHES if id(c) in keep]
        try:
            mm.save_lyrics()
        except Exception:
            pass

    # ---------------------------------------------------------------- jobs
    def run_job(self, cmd):
        mm = self.mm
        err = ""
        keep = None
        self.stop_ev.clear()
        self.job_running = True
        try:
            self.st, cfg = self.store(cmd["library"])
            mm.CLASSICAL_MODE = cfg.get("classical_mode") if cfg.get("classical_mode") in ("skip", "composer", "performer") else "performer"
            mm.SKIP_NESTED = bool(cfg.get("skip_nested"))
            self.answers = dict(cmd.get("answers") or {})
            self.approvals = list(cmd.get("approvals") or [])
            self.confirms = []
            self.script = []
            self.recent_lines = []
            fast = self.answers.get("speed") == "fast"
            mm.FAST_SCAN = fast
            mm.CACHE_ONLY = bool(self.answers.get("cache_only"))
            old_plan = self.st.load("plan.json", []) if self.answers.get("merge") else None
            keep = {k: cfg.get(k) for k in ("analyze", "lyrics", "acoustid_off")} if fast else None
            if fast:          # Fast scan: by name only, no sound / discography check / lyrics (settings restored after)
                self.answers.update(acoustid=False, analyze=False, lyrics=False)
            if cmd["kind"] == "loonybin":         # DupCop: copies (never moves) the extra copies into one folder
                self.emit(t="stage", stage="loonybin")
                self.loony_bin(cfg, self.answers.get("loony_mode") or "copy")
                return
            if cmd["kind"] == "fastupdate":      # quick update: only the songs whose choice changed
                self.emit(t="stage", stage="identify")
                self.fast_update(cfg)
                return
            if cmd["kind"] == "restore_one":     # Find & restore: put one archived original back (asked on screen)
                a = self.answers
                self.script = [(r"^search \(part of", a.get("query", "")), (r"file id to restore", a.get("file_id", ""))]
                self.confirms = [r"^move\b"]
                self.emit(t="stage", stage="restore")
                mm.find_restore(self.st, cfg)
                return
            if cmd["kind"] == "reverse_log":     # Reverse a restore log (copies go to _undone, moved files go back)
                self.script = [(r"drag a restore log", self.answers.get("log", ""))]
                self.confirms = [r"^reverse [\d,]+ changes"]
                self.emit(t="stage", stage="restore")
                mm.restore_from_log(self.st, cfg)
                return
            if cmd["kind"] == "restore_all":     # Put everything back: every archived original to where it came from
                self.emit(t="stage", stage="restore")
                self.restore_all(cfg)
                return
            if cmd["kind"] == "undo_copy":       # Undo copy & tag: every library copy moved to _undone (nothing deleted)
                self.confirms = [r"^undo now"]
                self.emit(t="stage", stage="restore")
                mm.undo_phase3(self.st, cfg)
                return
            if cmd["kind"] == "archive":         # Archive originals: Approve, folder, then "Are you sure?" on screen
                self.approvals = [r"^have you finished phase 3"]
                self.confirms = [r"^\s*move these"] + ([r"^remove these empty folders"] if self.answers.get("empty_folders") else [])
                self.emit(t="stage", stage="archive")
                self.with_restore_log(lambda: mm.phase4(self.st, cfg), "Archive originals", "archive")
                return
            if cmd["kind"] == "scan":
                self.emit(t="stage", stage="read")
                mm.phase1(self.st, cfg)
                if self.stop_ev.is_set():
                    raise StopRequested()
            try:
                nfiles = len(self.st.load("inventory.json", [])) if cmd["kind"] == "scan" else None
            except Exception:
                nfiles = None
            self.emit(t="stage", stage="identify", files=nfiles)
            old_an = self.st.load("analysis.json", {}) if fast else {}
            if cmd["kind"] == "copy" and self.st.load("plan.json", []):
                # v1.1.2: the plan already exists (Scan did the searching): only apply your newest Review choices, no new searches
                self.emit(t="log", line="Copy & tag: using the existing plan (only your new Review choices are applied; no new scan).")
                self.fast_update(cfg)
            else:
                keep_old = self.keep_decided_ids(cfg) if cmd["kind"] == "scan" else {}
                mm.SKIP_IDS = set(keep_old)
                try:
                    mm.phase2(self.st, cfg)
                finally:
                    mm.SKIP_IDS = set()
                if keep_old:
                    self.restore_decided(keep_old)
                if self.answers.get("merge"):        # v1.1.4 "add the found songs": keep the old plan, add only what was found
                    self.merge_found(old_plan)
            if self.stop_ev.is_set():
                raise StopRequested()
            if cmd["kind"] == "copy":            # Copy & tag: approved with one click in the app
                self.copy_ids = set(self.answers.get("copy_ids") or []) or None
                self.approvals = [r"^start now"]
                self.emit(t="stage", stage="copy")
                self.with_restore_log(lambda: mm.phase3(self.st, self.st.load("config.json", cfg)), "Copy & tag", "copy")
                self.copy_ids = None
                self.run_extra_copies()
                if self.answers.get("extras"):
                    self.copy_extra_files(cfg, self.answers["extras"])
                if self.answers.get("left_out"):
                    self.copy_left_out(cfg)
                self.write_box_playlists(cfg)
            if fast and old_an:
                self.keep_tiers(old_an)
        except (StopRequested, mm.Cancelled) as e:
            e = StopRequested() if isinstance(e, mm.Cancelled) else e
            err = str(e)
            self.emit(t="log", line=err)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            self.emit(t="log", line="Error: " + err)
            self.emit(t="log", line=traceback.format_exc(limit=4))
        finally:
            mm.CACHE_ONLY = False
            if keep is not None and self.st:      # a Fast scan does not change your saved settings
                try:
                    c2 = self.st.load("config.json", {})
                    for k, v in keep.items():
                        if v is None:
                            c2.pop(k, None)
                        else:
                            c2[k] = v
                    self.st.save("config.json", c2)
                except Exception:
                    pass
            self.save_caches()
            mm.Progress.active = None
            self.job_running = False
            self.stop_ev.clear()
            self.emit(t="job_done", id=cmd.get("id"), error=err)

    def keep_decided_ids(self, cfg):
        """V2.0.6: a new scan searches everything again EXCEPT songs you already decided in Review (or that the plan already approved):
        those keep their old plan entry exactly. Returns {file id: old plan item}. Switch off with "rescan_keep_decided": false in config.json."""
        if cfg.get("rescan_keep_decided", True) is False and self.answers.get("keep_decided") is not True:
            return {}
        try:
            old = self.st.load("plan.json", [])
            if not old:
                return {}
            dec = self.decisions()
            inv = {r["id"]: r for r in self.st.load("inventory.json", [])}
            keep = {}
            for it in old:
                fid = it.get("file_id")
                r = inv.get(fid)
                if not r or it.get("kind") not in ("release", "singles") or os.path.normcase(r.get("path", "")) != os.path.normcase(it.get("src", "")):
                    continue                                   # moved or renamed: it has a new identity, search it again
                a = (dec.get(fid) or {}).get("action")
                if (a and a not in ("reject", "later")) or it.get("approved") or it.get("fixed"):
                    keep[fid] = it
            if keep:
                self.emit(t="log", line=f"Re-scan: {len(keep):,} songs you already decided (or the plan approved) are kept as they are and not searched again.")
            return keep
        except Exception as e:
            self.emit(t="log", line=f"(could not work out which songs to keep: {e}; searching everything)")
            return {}

    def restore_decided(self, keep):
        new = self.st.load("plan.json", [])
        done = set()
        for i, it in enumerate(new):
            if it.get("file_id") in keep:
                new[i] = keep[it["file_id"]]
                done.add(it["file_id"])
        self.st.save("plan.json", new)
        self.emit(t="log", line=f"Kept {len(done):,} decided songs exactly as they were.")

    def merge_found(self, old_plan):
        new = self.st.load("plan.json", [])
        old = {it["file_id"]: it for it in (old_plan or [])}
        out = dict(old)
        added = 0
        for it in new:
            fid = it["file_id"]
            found = it.get("kind") in ("release", "singles") and it.get("verified")
            if found and (fid not in old or not old[fid].get("approved")):
                out[fid] = it
                added += 1
        self.st.save("plan.json", list(out.values()))
        self.emit(t="log", line=f"Added {added:,} found songs to the plan (the rest of the plan is as it was).")

    def fast_update(self, cfg):
        """Quick 'Update the plan': only the songs whose Review / Neat Picky choice changed are worked out again
        (no new searches, the rest of the plan stays as it is). 'Full update' (and Copy & tag) still redo everything.
        Read-only: only plan.json changes."""
        mm, st = self.mm, self.st
        plan = st.load("plan.json", [])
        if not plan:
            raise RuntimeError("No plan yet: run Scan & identify first.")
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        dec = st.load("app_decisions.json", {})
        neat = st.load("app_neat.json", {})
        lib = cfg["library"]
        mm.CLASSICAL_MODE = cfg.get("classical_mode") if cfg.get("classical_mode") in ("skip", "composer", "performer") else "performer"
        mm.LAYOUT.clear()
        mm.LAYOUT.update(mm.DEFAULT_LAYOUT, **(cfg.get("layout") or {}))
        if cfg.get("sort_mode") != "collection":
            mm.LAYOUT["levels"] = [lv for lv in mm.LAYOUT["levels"] if lv != "tier"]
        by_id = {it["file_id"]: it for it in plan}
        KEYS = ("kind", "approved", "review", "reason", "verified", "new_tags", "proposed_tags", "folder", "name", "new_path",
                "action", "title", "album", "year", "track", "disc", "disctotal", "tracktotal", "release_id", "rtype", "group_id",
                "artist_id", "entity", "credited", "credit_text", "display_artist", "artists", "data_source", "confidence",
                "artist_folder", "edition", "album_suffix", "notes", "tag_match", "match_percent", "dup_name", "left_out",
                "composer", "classical", "held", "auto_ok", "file_artist", "dup_flat", "dup_keep", "dup_user_keep", "dup_tag", "dup_of", "dup_group", "dup_rank", "dup_kind", "dup_identical")

        def want(it):
            d = dec.get(it["file_id"])
            n = neat.get(it["file_id"])
            return max((d or {}).get("t", 0), (n or {}).get("t", 0))
        todo = [it for it in plan if want(it) > (it.get("dec_t") or 0) or (it.get("dec_t") and not dec.get(it["file_id"])
                                                                              and not neat.get(it["file_id"]))]
        prog = mm.Progress("Updating your choices", len(todo))
        used = {os.path.normcase(it["new_path"]) for it in plan if it.get("new_path")}
        art_folder, tiers = {}, {}
        for it in plan:
            k = it.get("artist_id") or mm.norm_key(it.get("entity") or it.get("credited") or "")
            if k and it.get("artist_folder"):
                art_folder.setdefault(k, it["artist_folder"])
            if k and it.get("tier"):
                tiers.setdefault(k, it["tier"])
        changed = 0
        for it in todo:
            mm.check_cancel()
            fid = it["file_id"]
            r = inv.get(fid)
            prog.step(os.path.basename(it.get("src", "")))
            if not r:
                continue
            if "_orig" not in it:                       # what the full update made, to go back to on Undo
                it["_orig"] = {k: it.get(k) for k in KEYS}
            base = dict(it["_orig"])
            d = dec.get(fid) or {}
            a = d.get("action")
            h = mm.hints(r)
            new = None
            if a == "pick" and d.get("match"):
                new = mm.make_item(r, h, d["match"], "high")
            elif a in ("unverified", "reject"):
                new = mm.make_item(r, h, None, "low")
            elif a == "trust":
                new = mm.make_item(r, h, mm.match_from_tags(r), "high")
            elif a == "edit":
                r_e = self.edited(r, d)
                new = mm.make_item(r_e, mm.hints(r_e), mm.match_from_tags(r_e), "high")
            if new is not None:
                new.pop("notes", None)
                k = new.get("artist_id") or mm.norm_key(new.get("entity") or new.get("credited") or "")
                if new["kind"] in ("release", "singles", "artist_unverified"):
                    if k in art_folder:
                        new["artist_folder"] = art_folder[k]
                    else:
                        tmp = {fid: new}
                        mm.name_artist_folders(tmp)
                        art_folder[k] = new.get("artist_folder") or new.get("credited") or "Unknown Artist"
                        new["artist_folder"] = art_folder[k]
                    if k in tiers:
                        new["tier"] = tiers[k]
                cur = {kk: it.get(kk) for kk in KEYS}
                for kk in KEYS:
                    it.pop(kk, None)
                it.update(new)
                it["notes"] = list(base.get("notes") or [])
                tmp = {fid: it}
                mm.build_paths(tmp, lib)
                mm.cap_path_lengths(tmp)
                old_path = os.path.normcase(cur.get("new_path") or "")
                used.discard(old_path)
                name = it.get("name") or os.path.basename(it.get("src", ""))
                stem, ext = os.path.splitext(name)
                n = 2
                while os.path.normcase(os.path.join(it["folder"], name)) in used:
                    name = f"{stem} ({n:02d}){ext}"
                    n += 1
                it["new_path"] = os.path.join(it["folder"], name)
                used.add(os.path.normcase(it["new_path"]))
                it["new_tags"] = mm.plan_tags(it)
                it["action"] = "copy" if os.path.basename(it["new_path"]) == r["filename"] else "rename"
            else:
                for kk in KEYS:
                    it.pop(kk, None)
                it.update({kk: v for kk, v in base.items() if v is not None})
            if a in ("accept", "pick", "unverified", "trust", "edit"):
                it["approved"], it["reason"], it["review"] = True, "", None
                it.pop("held", None)
            elif a == "later":
                it["approved"], it["reason"] = False, "left for later (Review)"
            elif a == "leave":
                it["approved"], it["reason"], it["left_out"] = False, "left out by you (Review)", True
            elif a == "reject":
                it["approved"], it["reason"] = False, "not this - search again (Review)"
            n_ = neat.get(fid) or {}
            if n_.get("action") == "keep" and it.get("new_tags"):
                it["proposed_tags"], it["new_tags"] = it["new_tags"], {}
            elif n_.get("keep_fields") and it.get("new_tags"):          # V2.0.3: per-field choice (keep my genre)
                it["proposed_tags"] = dict(it["new_tags"])
                for kf in n_["keep_fields"]:
                    it["new_tags"][kf] = ""
            it["tag_match"], it["match_percent"] = mm.tag_match(r.get("tags") or {}, it.get("new_tags") or {}, r.get("filename", ""))
            it["dec_t"] = want(it) or time.time()
            if not dec.get(fid) and not neat.get(fid):
                it.pop("dec_t", None)
                it.pop("_orig", None)
            changed += 1
        if changed:
            # V2.0.3: songs accepted in Review after the scan were never checked for extra copies of the same song (they were not approved
            # when the scan looked), so a second identical file was copied as "Title (02)". Check again now that they are approved.
            try:
                items_ = {it["file_id"]: it for it in plan}
                dup_groups, _coll = mm.mark_duplicates(items_, inv, None)
                used_ = {os.path.normcase(it["new_path"]) for it in plan if it.get("new_path") and (it.get("fixed") or not it.get("approved"))}
                for it in plan:
                    if it.get("dup_flat") and it.get("approved") and not it.get("fixed") and it.get("kind") != "skip":
                        it.setdefault("dup_orig_folder", it["folder"])
                        it["folder"] = os.path.join(lib, "_Duplicates")
                        if it.get("verified"):
                            it["new_tags"] = mm.plan_tags(it)
                for it in sorted(plan, key=lambda x: x["file_id"]):
                    if it.get("approved") and not it.get("fixed") and it.get("kind") != "skip" and it.get("folder") and it.get("name"):
                        nm = it.get("dup_name") or it["name"]
                        stem_, ext_ = os.path.splitext(nm)
                        n_ = 2
                        while os.path.normcase(os.path.join(it["folder"], nm)) in used_:
                            nm = f"{stem_} ({n_}){ext_}"
                            n_ += 1
                        it["new_path"] = os.path.join(it["folder"], nm)
                        used_.add(os.path.normcase(it["new_path"]))
                mm.write_duplicates(st, dup_groups, inv)
            except Exception as e_:
                mm.say(f" (extra-copy check skipped: {type(e_).__name__}: {e_})")
        st.save("plan.json", plan)
        mm.say(f" Plan updated: {changed:,} songs with new choices (the rest of the plan is unchanged).")

    def with_restore_log(self, fn, action, kind):
        """Like the text menu: whatever Copy & tag / Archive did gets its own restore log (also after a stop)."""
        mm = self.mm
        snap = lambda: {r["file_id"]: r for r in mm.read_csv(self.st.p("music_provenance.csv"))} \
            if mm.exists(self.st.p("music_provenance.csv")) else {}
        before = snap()
        try:
            fn()
        finally:
            try:
                mm.write_restore_log(self.st, self.st.load("config.json", {}), action, mm.prov_changes(before, snap(), kind))
            except Exception as e:
                self.emit(t="log", line=f"(restore log could not be written: {e})")

    def loony_bin(self, cfg, mode="copy"):
        """DupCop / Loony Bin - what happens to the EXTRA copies (left out on the Duplicates page), one choice per run:
          copy : COPY into <library>\\_LoonyBin (originals only read)                          - the safe default
          C01  : MOVE the originals into a _LoonyBin inside their own music folder (your sources)
          C02  : MOVE the originals into <library>\\_LoonyBin
          C03  : MOVE into the music folder's _LoonyBin AND copy into <library>\\_LoonyBin
          C04  : delete - only copies with exactly the same audio as the copy you keep, into the Windows Recycle Bin
        Every move/delete is asked on screen first ("Are you sure?"); a report and a restore log are written."""
        mm, st = self.mm, self.st
        rows = st.cached("duplicates.json", [])
        plan = {it["file_id"]: it for it in st.cached("plan.json", [])}
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        extra = [r for r in rows if (plan.get(r["file_id"]) or {}).get("dup_extra")]
        if mode == "C04":
            extra = [r for r in extra if self.same_audio_as_kept(r, plan, inv)]
        lib_bin = os.path.join(cfg["library"], "_LoonyBin")
        roots = [s_["path"] for s_ in (cfg.get("sources") or cfg.get("last_sources") or [])]

        def src_bin(path):
            root = next((rt for rt in sorted(roots, key=len, reverse=True) if mm.inside(path, rt)), os.path.dirname(path))
            return os.path.join(root, "_LoonyBin")
        if not extra:
            mm.say(" Nothing to do: no extra copies" + (" with exactly the same audio as the kept copy." if mode == "C04" else "."))
            return
        what = {"copy": f"COPY {len(extra):,} extra copies into {lib_bin}",
                "C01": f"MOVE {len(extra):,} extra copies (the original files) into a _LoonyBin folder inside your music folder",
                "C02": f"MOVE {len(extra):,} extra copies (the original files) into {lib_bin}",
                "C03": f"MOVE {len(extra):,} extra copies into a _LoonyBin inside your music folder and COPY them into {lib_bin}",
                "C04": f"DELETE {len(extra):,} extra copies that have exactly the same audio as the copy you keep (they go to the Windows Recycle Bin)"}[mode]
        mm.say(f" Loony Bin: {what}.")
        for r in extra[:12]:
            mm.say(f"   {r['source']}")
        if mode != "copy":
            ans = self.confirm_on_screen(f"{what} now?\n   [Y]es / [N]o")
            if (ans or "n").lower()[:1] != "y":
                mm.say(" Cancelled - nothing was moved or deleted.")
                return
        if mode == "C04" and not mm.IS_WIN:
            mm.say(" Deleting to the Recycle Bin works on Windows only. Nothing was deleted.")
            return
        log, rep, t = [], [], mm.now()
        prog = mm.Progress("Loony Bin", len(extra))

        def free(folder, src, ext):
            base = mm.sanitize(f"{r.get('artist') or 'Unknown'} - {r.get('title') or os.path.splitext(os.path.basename(src))[0]}")[:150]
            n = 1
            dst = os.path.join(folder, f"{base} (copy {n}){ext}")
            while mm.exists(dst):
                n += 1
                dst = os.path.join(folder, f"{base} (copy {n}){ext}")
            return dst
        for r in extra:
            prog.step(os.path.basename(r["source"]))
            src = r["source"]
            if not mm.exists(src):
                rep.append(dict(r, loony_path="", note="original not found"))
                continue
            ext = os.path.splitext(src)[1].lower()
            try:
                if mode == "C04":
                    recycle(src)
                    log.append({"file_id": r["file_id"], "kind": "recycled", "from": src, "to": "Recycle Bin", "hash": "", "time": t})
                    rep.append(dict(r, loony_path="Recycle Bin", note="sent to the Recycle Bin (same audio as the kept copy)"))
                    continue
                if mode in ("copy", "C03"):
                    os.makedirs(mm.lp(lib_bin), exist_ok=True)
                    dst = free(lib_bin, src, ext)
                    mm.shutil.copy2(mm.lp(src), mm.lp(dst))
                    log.append({"file_id": r["file_id"], "kind": "copy", "from": src, "to": dst, "hash": "", "time": t})
                    rep.append(dict(r, loony_path=dst, note="copied"))
                if mode in ("C01", "C02", "C03"):
                    folder = lib_bin if mode == "C02" else src_bin(src)
                    os.makedirs(mm.lp(folder), exist_ok=True)
                    dst = free(folder, src, ext)
                    mm.shutil.move(mm.lp(src), mm.lp(dst))
                    log.append({"file_id": r["file_id"], "kind": "loony_move", "from": src, "to": dst, "hash": "", "time": t})
                    rep.append(dict(r, loony_path=dst, note="moved"))
            except Exception as e:
                rep.append(dict(r, loony_path="", note=f"{type(e).__name__}: {e}"))
        prog.done()
        if rep:
            os.makedirs(mm.lp(lib_bin), exist_ok=True)
            mm.write_csv(os.path.join(lib_bin, f"Loony Bin report {mm.stamp()}.csv"), list(rep[0]), rep)
        mm.write_restore_log(st, cfg, f"Loony Bin ({mode})", [e for e in log if e["kind"] != "recycled"] or log)
        mm.say(f" Loony Bin: {len(log):,} done. Report saved in {lib_bin}.")

    def restore_all(self, cfg):
        """Every archived original goes back to its old place (asked on screen first). Nothing is overwritten:
        if something already sits at the old place, that original stays in the archive and is listed."""
        mm, st = self.mm, self.st
        rows = {r["file_id"]: r for r in mm.read_csv(st.p("music_provenance.csv"))} if mm.exists(st.p("music_provenance.csv")) else {}
        arch = [r for r in rows.values() if r.get("status") == "original_archived" and r.get("final_original_path")]
        todo, skip = [], []
        for r in arch:
            if not mm.exists(r["final_original_path"]):
                skip.append(f"not in the archive any more: {r['final_original_path']}")
            elif mm.exists(r["original_full_path"]):
                skip.append(f"something already at: {r['original_full_path']}")
            else:
                todo.append(r)
        mm.say(f" Archived originals: {len(arch):,} · can go back now: {len(todo):,}" + (f" · stay (listed below): {len(skip):,}" if skip else ""))
        for x in skip[:20]:
            mm.say("   - " + x)
        for r in todo[:8]:
            mm.say(f"   {r['final_original_path']}\n     -> {r['original_full_path']}")
        if not todo:
            return
        if (self.confirm_on_screen(f"Put {len(todo):,} archived originals back where they came from?\n   [Y]es / [N]o") or "n").lower()[:1] != "y":
            mm.say(" Cancelled - nothing was moved.")
            return
        prog = mm.Progress("Putting originals back", len(todo))
        log, t = [], mm.now()
        for r in todo:
            prog.step(os.path.basename(r["original_full_path"]))
            try:
                if mm.exists(r["original_full_path"]):
                    continue
                os.makedirs(mm.lp(os.path.dirname(r["original_full_path"])), exist_ok=True)
                mm.shutil.move(mm.lp(r["final_original_path"]), mm.lp(r["original_full_path"]))
                log.append({"file_id": r["file_id"], "kind": "restore", "from": r["final_original_path"], "to": r["original_full_path"],
                            "hash": r.get("audio_stream_hash", ""), "time": t})
                r.update(status="verified", final_original_path="", final_original_filename="",
                         notes=(r.get("notes", "") + f" original put back {t}").strip())
            except Exception as e:
                self.emit(t="log", line=f"(not put back: {r['final_original_path']} - {e})")
        prog.done()
        mm.save_prov(st, rows)
        mm.write_restore_log(st, cfg, "Put everything back from the archive", log)
        mm.say(f" Done: {len(log):,} originals are back where they came from.")

    def same_audio_as_kept(self, r, plan, inv):
        """C04 safety: only a copy whose audio data is exactly the same as a copy you keep may be deleted."""
        it = plan.get(r["file_id"]) or {}
        a = inv.get(r["file_id"]) or {}
        if not a.get("audio_hash"):
            return False
        kept = [k for k, p_ in plan.items() if p_.get("dup_group") == it.get("dup_group") and not p_.get("dup_extra") and k != r["file_id"]]
        return any((inv.get(k) or {}).get("audio_hash") == a["audio_hash"] for k in kept)

    def run_extra_copies(self):
        """'Copy it into this album' (Analyze): an extra, tagged copy of a song you already have, placed on the
        album where it is missing. The source file is only read; nothing is overwritten; a restore log is written."""
        mm, st = self.mm, self.st
        reqs = st.load("app_extra_copies.json", [])
        todo = [r for r in reqs if not r.get("done")]
        if not todo:
            return
        cfg = st.load("config.json", {})
        plan = st.load("plan.json", [])
        prov = {r["file_id"]: r for r in mm.read_csv(st.p("music_provenance.csv"))} if mm.exists(st.p("music_provenance.csv")) else {}
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        log, t = [], mm.now()
        prog = mm.Progress("Copying songs into albums", len(todo))
        for rq in todo:
            prog.step(rq.get("title", ""))
            sib = next((it for it in plan if it.get("release_id") == rq["release_id"] and it.get("new_path")), None)
            pr = prov.get(rq["src"]) or {}
            src = next((p_ for p_ in (rq.get("src_path"), pr.get("new_full_path"), (inv.get(rq["src"]) or {}).get("path"), pr.get("final_original_path"))
                        if p_ and mm.exists(p_)), None)
            if not sib or not src:
                rq["error"] = "the album or the song is not in the library plan any more"
                continue
            ext = os.path.splitext(src)[1].lower()
            num = (f"{rq['disc']}-" if str(sib.get("disctotal") or "1") not in ("", "1") else "") + f"{int(rq['track']):02d}" \
                if str(rq.get("track", "")).isdigit() else ""
            base = os.path.basename(sib["new_path"])
            m = re.search(r"(?:\d+-)?\d{2} .*$", os.path.splitext(base)[0])
            stem = (os.path.splitext(base)[0][:m.start()] if m else "") + (f"{num} " if num else "") + mm.sanitize(rq["title"])
            dst = os.path.join(sib["folder"], stem + ext)
            n = 2
            while mm.exists(dst):
                dst = os.path.join(sib["folder"], f"{stem} ({n:02d}){ext}")
                n += 1
            nt = dict(sib.get("new_tags") or {})
            nt.update(title=rq["title"], track=str(rq.get("track", "")), disc=str(rq.get("disc", "1")))
            tmp = os.path.join(sib["folder"], f"~mlm_tmp_extra_{re.sub(r'[^A-Za-z0-9]+', '_', str(rq['src']))[:40]}{ext}")
            try:
                os.makedirs(mm.lp(sib["folder"]), exist_ok=True)
                if mm.exists(tmp):
                    rq["error"] = "a temporary file from an earlier try is in the way"
                    continue
                mm.shutil.copy2(mm.lp(src), mm.lp(tmp))
                os.chmod(mm.lp(tmp), mm.stat.S_IREAD | mm.stat.S_IWRITE)
                if nt:
                    mm.write_tags(tmp, ext, nt)
                h0, h1 = mm.audio_hash(src, cfg.get("ffmpeg")), mm.audio_hash(tmp, cfg.get("ffmpeg"))
                if h0 and h1 and h0 != h1:
                    da, db = mm.decoded_hash(src, cfg.get("ffmpeg")), mm.decoded_hash(tmp, cfg.get("ffmpeg"))
                    if not da or da != db:
                        rq["error"] = "the audio of the copy differed from the source; the copy was parked, not used"
                        park = os.path.join(cfg["library"], f"_undone_{mm.stamp()}", os.path.basename(tmp))
                        os.makedirs(mm.lp(os.path.dirname(park)), exist_ok=True)
                        mm.shutil.move(mm.lp(tmp), mm.lp(park))
                        continue
                os.rename(mm.lp(tmp), mm.lp(dst))
                rq.update(done=True, path=dst, when=t, error="")
                log.append({"file_id": rq["src"], "kind": "copy", "from": src, "to": dst, "hash": h1 or "", "time": t})
                mm.say(f"   copied into the album: {dst}")
            except Exception as e:
                rq["error"] = f"{type(e).__name__}: {e}"
        prog.done()
        st.save("app_extra_copies.json", reqs)
        if log:
            mm.write_restore_log(st, cfg, "Copy into album", log)

    def copy_extra_files(self, cfg, extras):
        """Covers / playlists / .cue / booklets / lyrics you ticked: COPIED into the album folders (originals only read,
        nothing overwritten - a second file with the same name gets (2)). A restore log is written."""
        mm = self.mm
        prog = mm.Progress("Copying extra files", len(extras))
        log, t = [], mm.now()
        for e in extras:
            prog.step(os.path.basename(e["src"]))
            try:
                if not mm.exists(e["src"]) or not os.path.isdir(mm.lp(os.path.dirname(e["to"]) if os.path.basename(e["to"]).lower() in ("scans", "scan", "artwork", "art", "covers", "cover", "booklet", "booklets", "images", "pics") else e["to"])):
                    continue                          # only into album folders that exist (their songs were copied)
                os.makedirs(mm.lp(e["to"]), exist_ok=True)
                stem, ext = os.path.splitext(os.path.basename(e["src"]))
                dst, n, same = os.path.join(e["to"], stem + ext), 2, False
                while mm.exists(dst):
                    if os.path.getsize(mm.lp(dst)) == os.path.getsize(mm.lp(e["src"])):
                        same = True                   # already there (an earlier Copy & tag)
                        break
                    dst = os.path.join(e["to"], f"{stem} ({n}){ext}")
                    n += 1
                if same:
                    continue
                mm.shutil.copy2(mm.lp(e["src"]), mm.lp(dst))
                log.append({"file_id": "", "kind": "copy", "from": e["src"], "to": dst, "hash": "", "time": t})
            except Exception as ex:
                self.emit(t="log", line=f"(extra file not copied: {e['src']} - {ex})")
        prog.done()
        if log:
            mm.write_restore_log(self.st, cfg, "Extra files (covers, playlists...)", log)
            mm.say(f" Extra files copied into the album folders: {len(log):,}")

    def write_box_playlists(self, cfg):
        """Playlist manager › 'sort + playlist': the box set's songs went to their real albums; this writes one
        playlist with them in the box set's order into <library>\\_Playlists (a new file; never overwritten)."""
        mm, st = self.mm, self.st
        ch = {k: v for k, v in st.load("app_boxsets.json", {}).items() if v.get("mode") == "playlist"}
        if not ch:
            return
        rows = {r["file_id"]: r for r in mm.read_csv(st.p("music_provenance.csv"))} if mm.exists(st.p("music_provenance.csv")) else {}
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        out = os.path.join(cfg["library"], "_Playlists")
        os.makedirs(mm.lp(out), exist_ok=True)
        made = 0
        for key, b in ch.items():
            def order(fid):
                t = (inv.get(fid) or {}).get("tags") or {}
                d, n = str(t.get("disc") or "1").split("/")[0], str(t.get("track") or "0").split("/")[0]
                return (int(d) if d.isdigit() else 1, int(n) if n.isdigit() else 0, (inv.get(fid) or {}).get("path", ""))
            lines = ["#EXTM3U"]
            for fid in sorted(b.get("ids") or [], key=order):
                r = rows.get(fid) or {}
                p_ = r.get("new_full_path")
                t = (inv.get(fid) or {}).get("tags") or {}
                if p_ and r.get("status") in ("copied", "verified", "original_archived"):
                    lines.append(f"#EXTINF:{int((inv.get(fid) or {}).get('duration') or 0)},{t.get('artist', '')} - {t.get('title', '')}")
                    lines.append(p_)
                elif (inv.get(fid) or {}).get("path") and mm.exists(inv[fid]["path"]):
                    # v1.1.5: a song that was not copied (not accepted yet) is listed at its ORIGINAL place, so the playlist is not empty
                    lines.append(f"#EXTINF:{int((inv.get(fid) or {}).get('duration') or 0)},{t.get('artist', '')} - {t.get('title', '')}")
                    lines.append(inv[fid]["path"])
            if len(lines) < 3:
                continue
            body = "\n".join(lines) + "\n"
            name = mm.sanitize(b.get("album") or "Box set") + ".m3u8"
            dst, n = os.path.join(out, name), 2
            while mm.exists(dst):
                if mm.read_text_any(dst) == body:
                    break
                dst = os.path.join(out, mm.suffixed(name, n))
                n += 1
            else:
                with open(mm.lp(dst), "w", encoding="utf-8") as fh:
                    fh.write(body)
                made += 1
        if made:
            mm.say(f" Box-set playlists written into {out}: {made}")

    def copy_left_out(self, cfg):
        """Songs you left out: COPIED into <library>\\_LeftOut, flat, as 'Artist - Title' - to listen and delete yourself.
        The originals stay where they are."""
        mm, st = self.mm, self.st
        dec = st.load("app_decisions.json", {})
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        ids = [fid for fid, d in dec.items() if d.get("action") == "leave" and fid in inv]
        if not ids:
            return
        root = os.path.join(cfg["library"], "_LeftOut")
        os.makedirs(mm.lp(root), exist_ok=True)
        prog = mm.Progress("Copying left-out songs", len(ids))
        log, t = [], mm.now()
        for fid in ids:
            r = inv[fid]
            prog.step(r.get("filename", ""))
            src = r["path"]
            if not mm.exists(src):
                continue
            tg = r.get("tags") or {}
            name = mm.sanitize(f"{tg.get('artist') or 'Unknown'} - {tg.get('title') or os.path.splitext(r['filename'])[0]}") or fid
            ext = os.path.splitext(src)[1]
            dst, n = os.path.join(root, name + ext), 2
            if any(e_["from"] == src for e_ in log):
                continue
            same = False
            while mm.exists(dst):
                if os.path.getsize(mm.lp(dst)) == os.path.getsize(mm.lp(src)):
                    same = True                       # copied on an earlier run
                    break
                dst = os.path.join(root, f"{name} ({n}){ext}")
                n += 1
            if same:
                continue
            try:
                mm.shutil.copy2(mm.lp(src), mm.lp(dst))
                log.append({"file_id": fid, "kind": "copy", "from": src, "to": dst, "hash": "", "time": t})
            except Exception as ex:
                self.emit(t="log", line=f"(left-out song not copied: {src} - {ex})")
        prog.done()
        if log:
            mm.write_restore_log(st, cfg, "Left-out songs copied to _LeftOut", log)
            mm.say(f" {len(log):,} left-out songs copied into {root} (originals untouched).")

    def keep_tiers(self, old):
        """A Fast scan skips the discography check: keep each artist's tier from the last Complete scan."""
        try:
            new = self.st.load("analysis.json", {})
            prev = {r["artist"]: r for r in old.get("artists", []) if r.get("studio_total")}
            if not new or not prev:
                return
            for r in new.get("artists", []):
                o = prev.get(r["artist"])
                if o:
                    for k in ("tier", "studio_complete", "studio_total", "percent"):
                        r[k] = o.get(k, r.get(k))
            new.setdefault("summary", {})["tiers_known"] = True
            new["summary"]["tiers_from"] = old.get("made", "")
            self.st.save("analysis.json", new)
        except Exception as e:
            self.emit(t="log", line=f"(could not keep the earlier tiers: {e})")

    # ---------------------------------------------------------------- Review lookups
    def call(self, cmd):
        name, args, lib = cmd["name"], cmd.get("args") or [], cmd["library"]
        try:
            value = getattr(self, "c_" + name)(lib, *args)
        except Exception as e:
            value = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=4)}
        self.emit(t="result", id=cmd["id"], value=value)

    def _inv(self, st, fid):
        """V2.0.5 (#10): one lookup table per inventory (it used to walk the whole list for every single search)."""
        inv = st.cached("inventory.json", [])
        c = getattr(self, "_invmap", None)
        if not c or c[0] is not inv or c[1] != len(inv):
            self._invmap = c = (inv, len(inv), {r["id"]: r for r in inv})
        return c[2].get(fid)

    def _bg(self, fn, *a):
        """v2.0: runs a call in the background lane of the website queues (see LANE in music_manager)."""
        self.mm.LANE.bg = True
        try:
            return fn(*a)
        finally:
            self.mm.LANE.bg = False

    def c_search_bg(self, lib, *a):
        return self._bg(self.c_search, lib, *a)

    def c_verify_bg(self, lib, *a):
        return self._bg(self.c_verify, lib, *a)

    def _plan_map(self, st):
        pm = getattr(self, "_pm", None)
        try:
            mt = os.path.getmtime(st.p("plan.json"))
        except OSError:
            mt = 0
        if not pm or pm[0] != mt or pm[1] is not st:
            pm = self._pm = (mt, st, {it["file_id"]: it for it in st.load("plan.json", [])}, {r["id"]: r for r in st.cached("inventory.json", [])})
        return pm

    def c_verify(self, lib, fid):
        """V2.0.3 decisions 2 + 18: a second, independent source must agree on artist, title, album and length before a song
        counts as 'verified'. MusicBrainz (or whichever site made the match) is source 1; the other allowed sites are asked one by
        one until two agree. Read-only; answers are cached like every lookup."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        _, _, plan, inv = self._plan_map(st)
        it, r = plan.get(fid), inv.get(fid)
        if not it or not r:
            return {"error": "song not found"}
        artist = it.get("display_artist") or it.get("credited") or ""
        title, album, dur = it.get("title") or "", it.get("album") or "", r.get("duration") or 0
        own = it.get("data_source") or ""
        if alt is None:
            return {"n": 1 if it.get("verified") else 0, "sources": [own] if it.get("verified") else [], "checked": [], "differ": [], "t": time.time()}
        agree, checked, differ = ([own] if (it.get("verified") and own) else []), [], []
        want = ("deezer", "spotify", "tidal", "discogs", "itunes", "lastfm")
        use = [k for k in want if k in (cfg.get("alt_use") or [])]
        for k in use:
            if len(agree) >= 2:
                break
            if mm.ALT_NAMES.get(k, k) == own:
                continue
            if (k == "discogs" and not alt.token) or (k == "lastfm" and not alt.lfm_key):
                continue
            checked.append(k)
            try:
                m = getattr(alt, k)(artist, title, album, dur)
            except mm.Cancelled:
                raise
            except Exception:
                m = None
            if not m:
                continue
            names = (m.get("trk_credit") or {}).get("names") or [(m.get("trk_credit") or {}).get("primary", "")]
            same_album = mm.ratio(mm.norm_key(mm.strip_edition(m.get("group_title") or "")), mm.norm_key(mm.strip_edition(album))) >= 0.85 \
                or mm.ratio(mm.title_key(m.get("group_title") or ""), mm.title_key(album)) >= 0.85
            ok = mm.artist_agrees(names, artist) and mm.same_song_title(m.get("title") or "", title) >= 0.88 \
                and not mm.different_version(title, m.get("title") or "") and same_album
            (agree if ok else differ).append(mm.ALT_NAMES.get(k, k) if ok else f"{mm.ALT_NAMES.get(k, k)}: {m.get('group_title', '')} ({m.get('year', '')})")
        return {"n": len(agree), "sources": agree, "checked": checked, "differ": differ, "t": time.time()}

    def c_dig_bg(self, lib, *a):
        return self._bg(self.c_dig, lib, *a)

    def c_sound_bg(self, lib, *a):
        return self._bg(self.c_sound, lib, *a)

    def c_search(self, lib, fid, artist, title, album, deep=False):
        mb, alt, st, cfg = self.lookups(lib)
        r = self._inv(st, fid) or {}
        tg = r.get("tags") or {}
        stats = {}
        res = self.mm.search_again(mb, alt, (artist or "").strip(), (title or "").strip(), (album or "").strip(),
                                   r.get("duration") or 0, cfg.get("alt_use", []), mine=title,
                                   context=f"{tg.get('title', '')} {tg.get('album', '')} {r.get('filename', '')}", deep=True, stats=stats)   # V2.0.5: a search by hand always asks EVERY site you allowed
        for c in res:          # how close each result is to the tags your file has now (like Neat Picky)
            c["match_pct"] = self.mm.tag_match(r.get("tags") or {}, {"artist": c["artist"], "title": c["title"], "album": c["release"],
                                                                      "year": c["year"], "track": c["track"]}, r.get("filename", ""))[1]
        res.sort(key=lambda c: (c["other_version"], not c["len_ok"], -(c.get("match_pct") or 0)))   # closest first
        return {"results": res, "stats": stats}

    def c_dig(self, lib, fid, steps=None):
        """'Dig deeper' for a song nobody recognized. Four steps, in order, stopping at the first sure result:
        1 MusicBrainz IDs already in your tags, 2 classical search (composer + work), 3 deep text search (title only,
        no album, then the names in the file and folder names), 4 identify by sound, the last level (only when the levels before it found nothing sure, and AcoustID is set up).
        Uses only the sites you allowed; sends names, lengths (and for step 4 a fingerprint)."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        r = self._inv(st, fid)
        if not r:
            return {"error": "Song not found in the scan."}
        steps = list(steps or ["ids", "classical", "deep", "length", "sound"])
        h = mm.hints(r)
        tg = r.get("tags") or {}
        dur = r.get("duration") or 0
        out, seen, log = [], set(), []

        def add(cands, how):
            n = 0
            for c in cands or []:
                m = c.get("match") or {}
                k = (m.get("release_id"), str(m.get("disc")), str(m.get("track")))
                if k in seen:
                    continue
                seen.add(k)
                c = dict(c, how=f"dig deeper · {how}" + (f" ({c['how']})" if c.get("how") else ""), dig=how)
                c.setdefault("other_version", mm.different_version(h["title_plain"], c.get("title", "")))
                out.append(c)
                n += 1
            return n

        def sure():
            return any(not c.get("other_version") and c.get("len_ok") for c in out)

        def search(artist, title, album=""):
            return mm.search_again(mb, alt, artist or "", title or "", album or "", dur, cfg.get("alt_use", []), mine=h["title_plain"],
                                   context=f"{tg.get('title', '')} {r.get('filename', '')}", deep=True)
        for step in steps:
            mm.check_cancel()
            if sure():      # V2.0.3: identify by sound is the LAST level: only tried when the levels before it found nothing sure
                continue
            n, note = 0, ""
            try:
                if step == "ids":
                    rid, aid = (tg.get("mb_trackid") or "").strip(), (tg.get("mb_albumid") or "").strip()
                    if not (rid or aid):
                        note = "no MusicBrainz IDs in the tags"
                    elif not mb:
                        note = "MusicBrainz is off"
                    else:
                        cands = []
                        if aid:
                            for m, ln in mm.mb_release_tracks(mb.release(aid)):
                                if (rid and m.get("recording_id") == rid) or (not rid and mm.same_song_title(m["title"], h["title_plain"]) >= 0.8):
                                    cands.append(mm.candidate(m, dur, ln, "release ID in your tags"))
                        if rid and not cands:
                            rec = mb.recording(rid)
                            for rel in ((rec or {}).get("releases") or [])[:6]:
                                for m, ln in mm.mb_release_tracks(mb.release(rel["id"])):
                                    if m.get("recording_id") == rid:
                                        cands.append(mm.candidate(m, dur, ln, "recording ID in your tags"))
                                        break
                        n = add(cands, "MusicBrainz ID in tags")
                        note = "" if n else "the IDs in your tags were not found"
                elif step == "classical":
                    comp = (tg.get("composer") or "").strip()
                    text = " ".join([tg.get("title", ""), tg.get("album", ""), r.get("filename", ""), os.path.basename(r.get("folder", ""))])
                    if not (comp or CLASSICAL_WORDS.search(text) or "classic" in (tg.get("genre") or "").lower()):
                        note = "does not look like classical music"
                    else:
                        work = re.sub(r"\b(op\.?|no\.?|bwv|k\.)\s*\d+\w*", " ", h["title_plain"], flags=re.I)
                        work = re.sub(r"\s+", " ", re.sub(r"[:,/()\[\]-]", " ", work)).strip()
                        for oc, ow in openopus_names(f"{comp} {work}".strip()):
                            n += add(search(oc, ow), f"classical (OpenOpus): {oc}")
                            if sure():
                                break
                        for who in ([] if n else [comp, h.get("artist"), tg.get("conductor", "")]):
                            if who and work:
                                n += add(search(who, work), f"classical: {who}")
                            if n:
                                break
                        if not n and h["title_plain"]:
                            n = add(search(comp, h["title_plain"]), "classical")
                        note = "" if n else "no composer/work match"
                elif step == "deep":
                    fn = mm.parse_filename(os.path.splitext(r.get("filename", ""))[0])
                    fy, falb, fart = mm.parse_folder(os.path.basename(r.get("folder", "")))
                    tries = [(h.get("artist"), strip_site_words(h["title_plain"])), ("", strip_site_words(h["title_plain"])),
                             (strip_site_words(fn.get("artist") or fart), strip_site_words(fn.get("title"))), ("", strip_site_words(fn.get("title")))]
                    done = set()
                    for a_, t_ in tries:
                        t_ = (t_ or "").strip()
                        key = ((a_ or "").lower(), t_.lower())
                        if not t_ or key in done:
                            continue
                        done.add(key)
                        n += add(search(a_, t_), "title only" if not a_ else "names from file/folder" if a_ != h.get("artist") else "no album")
                        if sure():
                            break
                    note = "" if n else "nothing found by title"
                elif step == "length":
                    fn2 = mm.parse_filename(os.path.splitext(r.get("filename", ""))[0])
                    fy2, falb2, fart2 = mm.parse_folder(os.path.basename(r.get("folder", "")))
                    who = (h.get("artist") or strip_site_words(fn2.get("artist") or fart2) or "").strip()
                    if not who:
                        note = "the artist is not known"
                    elif not mb:
                        note = "MusicBrainz is off"
                    elif not dur:
                        note = "the file's length is unknown"
                    else:
                        n = add(mm.search_by_artist_length(mb, who, dur, h["title_plain"]), "artist + length")
                        note = "" if n else f"no recording by {who} with this length"
                elif step == "sound":
                    if not (cfg.get("acoustid_key") and (cfg.get("fpcalc") or mm.find_tool("fpcalc"))):
                        note = "identify by sound is not set up (AcoustID key in Settings)"
                    else:
                        info = {}
                        res = mm.identify_by_sound(r["path"], cfg, mb, h.get("album") or h.get("folder_album"), dur, info)
                        n = add(res, "identify by sound")
                        note = "" if n else (info.get("error") or "no recording with this fingerprint")
            except mm.Cancelled:
                raise
            except Exception as e:
                note = f"{type(e).__name__}: {e}"
            log.append({"step": step, "found": n, "note": note})
        for c in out:
            c["match_pct"] = mm.tag_match(tg, {"artist": c["artist"], "title": c["title"], "album": c["release"],
                                               "year": c["year"], "track": c["track"]}, r.get("filename", ""))[1]
        out.sort(key=lambda c: (c["other_version"], not c["len_ok"], -(c.get("match_pct") or 0)))
        return {"results": out[:12], "steps": log}

    def c_release_view(self, lib, release_id):
        """Every track of one album (for Analyze: what you have and what is missing). Read from the lookup memory."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        rid = release_id or ""
        try:
            if re.fullmatch(r"[0-9a-f-]{36}", rid) and mb:
                rel = mb.release(rid)
                return mm.release_view(rel) if rel else {"error": "MusicBrainz does not know this album."}
            kind, _, num = rid.partition(":")
            url = {"deezer": f"https://www.deezer.com/album/{num}", "itunes": f"https://music.apple.com/us/album/{num}",
                   "discogs": f"https://www.discogs.com/release/{num}", "tidal": f"https://tidal.com/album/{num}"}.get(kind)
            if url:
                return mm.release_from_link(url, mb, alt)
        except mm.Cancelled:
            raise
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"error": "The full track list is not known for this album (it was placed with your own tags)."}

    def c_sound(self, lib, fid):
        mb, alt, st, cfg = self.lookups(lib)
        r = self._inv(st, fid)
        if not r:
            return {"error": "Song not found in the scan."}
        h = self.mm.hints(r)
        info = {}
        res = self.mm.identify_by_sound(r["path"], cfg, mb, h.get("album") or h.get("folder_album"), r.get("duration") or 0, info)
        return {"results": res, "error": "" if res else info.get("error", "")}

    def c_link(self, lib, url):
        mb, alt, st, cfg = self.lookups(lib)
        return self.mm.release_from_link((url or "").strip(), mb, alt)

    def c_suggest(self, lib, fid):
        """PLACE ("Check track"): the albums your tags or folder name point to. 2.0.1: several spellings of the album and of the
        artist, MusicBrainz first then the other allowed sites, and the albums that really contain this song come first."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        r = self._inv(st, fid)
        if not r:
            return {"releases": []}
        h = mm.hints(r)
        album = h.get("album") or h.get("folder_album")
        if not album:
            return {"releases": []}
        artist = h.get("albumartist") or h.get("artist") or ""
        title = (r.get("tags") or {}).get("title") or h.get("title") or ""
        names = []
        for n_ in (album, mm.strip_edition(mm.neutral(album)) or "", mm.neutral(album) or ""):
            if n_ and n_.lower() not in [x.lower() for x in names]:
                names.append(n_)
        views, seen = [], set()
        if mb:
            for a_ in (mm.artist_parts(artist) or [artist])[:3]:
                for n_ in names:
                    try:
                        cands = mb.search_release(a_, n_)[:6]
                    except Exception:
                        cands = []
                    for c in cands:
                        if c["id"] in seen or int(c.get("score", 0)) < 60 or len(views) >= 6:
                            continue
                        seen.add(c["id"])
                        rel = mb.release(c["id"])
                        if rel:
                            views.append(mm.release_view(rel))
                    if views:
                        break
                if views:
                    break
        if len(views) < 2:
            try:
                views += mm.alt_album_views(alt, artist, album, cfg.get("alt_use", []), ("deezer", "itunes"))
            except Exception:
                pass
        key = lambda t: mm.neutral(t or "").lower()
        want = key(title)

        def has_song(v):
            return bool(want) and any(key(t.get("title")) == want or (len(want) >= 4 and want in key(t.get("title"))) for t in (v.get("tracks") or []))
        views.sort(key=lambda v: (not has_song(v), -(len(v.get("tracks") or []) > 0)))
        return {"releases": views[:3]}

    def c_group(self, lib, fids, artist, album, url=""):
        """Album group: find the album and match every song of the group to its track."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        recs = [inv[f] for f in fids if f in inv]
        if not recs:
            return {"error": "These songs are not in the scan any more."}
        views = []
        if url:
            v = mm.release_from_link(url, mb, alt)
            if v.get("error"):
                return v
            views.append(v)
        else:
            q = mm.strip_edition(mm.neutral(album or "")) or album
            use = cfg.get("alt_use", [])
            ctx = " ".join(f"{(r.get('tags') or {}).get('title', '')} {r.get('filename', '')}" for r in recs)
            edition = mm.is_edition(album, ctx)

            def mb_views():
                if not mb:
                    return []
                vs, seen = [], set()
                for a_ in (mm.artist_parts(artist) or [""])[:3]:
                    for c in mb.search_release(a_, q)[:6]:
                        if c["id"] in seen or int(c.get("score", 0)) < 60:
                            continue
                        seen.add(c["id"])
                        rel = mb.release(c["id"])
                        if rel:
                            vs.append(mm.release_view(rel))
                    if vs:
                        break
                return vs

            def apple():
                return mm.alt_album_views(alt, artist, album, use, ("itunes",))

            def deezer():
                return mm.alt_album_views(alt, artist, album, use, ("deezer",))
            # remaster / mono / deluxe / special edition: Spotify, Apple Music, Deezer, then MusicBrainz; otherwise MusicBrainz first.
            # Stops as soon as one album has every song of the group.
            def spotify():
                return mm.alt_album_views(alt, artist, album, use, ("spotify",))
            order = [spotify, apple, deezer, mb_views] if edition else [mb_views, apple, deezer]      # V2.0.6: remasters: Spotify and Apple Music first
            for fn in order:
                try:
                    got = fn()
                except Exception:
                    got = []
                views.extend(got)
                if any(len(mm.match_group_to_release(v, recs)) == len(recs) for v in got):
                    break
            if not views and not mb and not alt:
                return {"error": "No music site is switched on."}
        out = []
        for v in views:
            mp = mm.match_group_to_release(v, recs)
            ntr = len(v.get("tracks") or [])
            out.append(dict(v, map=mp, matched=len(mp), key=(len(mp), -abs(ntr - len(recs)))))
        out.sort(key=lambda v: v["key"], reverse=True)
        for v in out:
            v.pop("key", None)
        for v in out:
            v["checks_out"] = v["matched"] == len(recs)
        return {"releases": out[:5], "searched": album, "count": len(recs)}

    def c_artist_albums(self, lib, fid):
        """The confirmed artist's releases (studio albums first, then EPs, singles, live, soundtracks...)."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        if not mb:
            return {"error": "MusicBrainz is switched off."}
        plan = {it["file_id"]: it for it in st.cached("plan.json", [])}
        it = plan.get(fid) or {}
        aid = it.get("artist_id") or it.get("mb_artist") or ""
        name = it.get("entity") or it.get("credited") or ""
        if not aid and name:
            d = mb.get("artist", {"query": f'artist:"{name}"', "limit": "3"}) or {}
            hit = next((a for a in d.get("artists") or [] if mm.ratio(a.get("name"), name) >= 0.9), None)
            aid = hit["id"] if hit else ""
        if not aid:
            return {"error": "The artist is not known on MusicBrainz.", "albums": []}
        out, offset = [], 0
        while offset < 300:
            d = mb.get("release-group", {"artist": aid, "limit": "100", "offset": str(offset)}) or {}
            rgs = d.get("release-groups") or []
            for g in rgs:
                sec = g.get("secondary-types") or []
                prim = g.get("primary-type") or "Other"
                kind = "Studio album" if prim == "Album" and not sec else ("Soundtrack" if "Soundtrack" in sec else
                       "Live" if "Live" in sec else "Compilation" if "Compilation" in sec else prim if not sec else f"{prim} ({', '.join(sec)})")
                rank = {"Studio album": 0, "EP": 1, "Single": 2, "Live": 3, "Soundtrack": 4, "Compilation": 5}.get(kind, 6)
                out.append({"id": g["id"], "title": g.get("title", ""), "year": (g.get("first-release-date") or "")[:4],
                            "kind": kind, "rank": rank})
            offset += 100
            if len(rgs) < 100 or offset >= int(d.get("release-group-count") or 0):
                break
        out.sort(key=lambda g: (g["rank"], g["year"] or "9999", g["title"].lower()))
        return {"artist": name, "albums": out}

    def c_suggest_music(self, lib, kind, artists):
        """v1.1.5 Analyze › Suggestions that need Last.fm (only artist names are sent):
        'similar' = artists you do not own that are like the ones you do; 'gems' = artists you own only 1-2 songs of, ranked by how well
        known they are, with their top albums."""
        mb, alt, st, cfg = self.lookups(lib)
        if not (alt and cfg.get("lastfm_key")):
            return {"error": "Suggestions like this need a Last.fm key (Settings › Last.fm, free)."}
        mm = self.mm
        alt.lfm_key = cfg.get("lastfm_key", "")
        owned = {mm.norm_key(a) for a in (artists or {}).get("all", [])}
        try:
            if kind in ("similar", "albums"):
                agg = {}
                for a in (artists or {}).get("top", [])[:10]:
                    for name, score in alt.lfm_similar(a, 12):
                        k = mm.norm_key(name)
                        if not k or k in owned:
                            continue
                        e = agg.setdefault(k, {"artist": name, "score": 0.0, "because": []})
                        e["score"] += score
                        if a not in e["because"]:
                            e["because"].append(a)
                out = sorted(agg.values(), key=lambda e: -e["score"])[:30]
                items = [dict(e, score=round(e["score"], 2)) for e in out]
                if kind == "similar":
                    pics = self.c_artist_pics(lib, [e["artist"] for e in items])
                    for e in items:
                        e["img"] = pics.get(e["artist"], "")
                    return {"items": items}
                # v2.0 'albums': one well-known album from each artist like yours, with its cover (Deezer)
                res = []
                for e in items[:18]:
                    al = alt.lfm_top_albums(e["artist"], 1)
                    if not al:
                        continue
                    img = ""
                    try:
                        q = mm.urllib.parse.urlencode({"q": f'artist:"{e["artist"]}" album:"{al[0]}"', "limit": "3"})
                        d = alt._get("deezer", "https://api.deezer.com/search/album?" + q, 0.15) or {}
                        hit = next((x for x in d.get("data") or [] if mm.ratio((x.get("artist") or {}).get("name"), e["artist"]) >= 0.8), None)
                        img = (hit or {}).get("cover_medium", "")
                    except mm.Cancelled:
                        raise
                    except Exception:
                        pass
                    res.append({"artist": e["artist"], "album": al[0], "img": img, "because": e["because"]})
                return {"items": res}
            if kind == "gems":
                rows = []
                for a in (artists or {}).get("few", [])[:40]:
                    info = alt.lfm_artist(a)
                    if info:
                        rows.append({"artist": info.get("name") or a, "listeners": info["listeners"], "plays": info["plays"]})
                rows.sort(key=lambda r: -r["listeners"])
                rows = rows[:20]
                for r in rows[:10]:
                    r["albums"] = alt.lfm_top_albums(r["artist"], 3)
                pics = self.c_artist_pics(lib, [r["artist"] for r in rows])
                for r in rows:
                    r["img"] = pics.get(r["artist"], "")
                return {"items": rows}
        except mm.Cancelled:
            raise
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}
        return {"error": "Unknown kind."}

    def c_artist_pics(self, lib, names):
        """Deezer artist pictures (cached). Sent: the artist names."""
        mm = self.mm
        mb, alt, st, cfg = self.lookups(lib)
        out = {}
        if not alt:
            return out
        pics = st.load("app_artist_pics.json", {})             # 1.1.5: remembered, so each artist is asked once
        t0, dirty = time.time(), False
        for n in names:
            if n in pics:
                if pics[n]:
                    out[n] = pics[n]
                continue
            if time.time() - t0 > 40:                          # never hold the screen: the rest comes next time
                break
            q = mm.urllib.parse.urlencode({"q": n, "limit": "3"})
            d = alt._get("deezer", "https://api.deezer.com/search/artist?" + q, 0.15) or {}
            hit = next((a for a in d.get("data") or [] if mm.ratio(a.get("name"), n) >= 0.85), None)
            ok = bool(hit and hit.get("picture_medium") and "/artist//" not in hit["picture_medium"])
            pics[n] = hit["picture_medium"] if ok else ""
            dirty = True
            if ok:
                out[n] = pics[n]
        if dirty:
            st.save("app_artist_pics.json", pics)
        return out

    def c_speed_test(self, lib, services):
        """Settings > Measure speed: one tiny request (the single word 'queen') to each site that is turned on.
        Read only. Takes the median of 3 answers. Saved in _logs\\app_speeds.json."""
        import urllib.parse as up
        import urllib.request as ur
        st, cfg = self.store(lib)
        tests = {"mb": "https://musicbrainz.org/ws/2/artist/?query=queen&fmt=json&limit=1",
                 "deezer": "https://api.deezer.com/search?q=queen&limit=1",
                 "itunes": "https://itunes.apple.com/search?term=queen&limit=1&entity=song"}
        hdr = {"User-Agent": f"MusicLibraryManager/{self.mm.VERSION}", "Accept": "application/json"}
        heads = {}
        if cfg.get("discogs_token"):
            tests["discogs"] = "https://api.discogs.com/database/search?q=queen&per_page=1&type=artist"
            heads["discogs"] = {"Authorization": f"Discogs token={cfg['discogs_token']}"}
        if cfg.get("lastfm_key"):
            tests["lastfm"] = "https://ws.audioscrobbler.com/2.0/?method=artist.search&artist=queen&limit=1&format=json&api_key=" + up.quote(cfg["lastfm_key"])
        out = {}
        for k in services or []:
            if k not in tests:
                continue
            times = []
            for _ in range(3):
                t0 = time.time()
                try:
                    with ur.urlopen(ur.Request(tests[k], headers={**hdr, **heads.get(k, {})}), timeout=15) as r:
                        r.read(2000)
                    times.append(time.time() - t0)
                except Exception:
                    pass
                time.sleep(1.1 if k == "mb" else 0.3)
            if times:
                times.sort()
                out[k] = {"avg": round(times[len(times) // 2], 3), "n": len(times), "probe": True}
        old = st.load("app_speeds.json", {})
        old.update(out)
        st.save("app_speeds.json", old)
        return out

    def c_find_on_pc(self, lib, artist, title):
        """Every drive: file names (and the tags of likely files) containing artist + title. Read only."""
        mm = self.mm
        import string as _s
        roots = [f"{d}:\\" for d in _s.ascii_uppercase if os.path.exists(f"{d}:\\")] if mm.IS_WIN else \
            [os.environ.get("MIDNIGHT_TEST_ROOT") or os.path.expanduser("~")]
        st, cfg = self.store(lib)
        ex = mm.protected_dirs(cfg)
        words_t = [w for w in mm.norm_key(mm.neutral(title)).split() if len(w) > 1] or mm.norm_key(title).split()
        words_a = [w for w in mm.norm_key(artist).split() if len(w) > 1]
        hits, t0, seen = [], time.time(), 0
        for r in roots:
            for dp, dns, fns in os.walk(r):
                dns[:] = [d for d in dns if not mm.is_skipped_dir(os.path.join(dp, d), d, ex)]
                seen += 1
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() not in mm.AUDIO_EXTS:
                        continue
                    k = mm.norm_key(os.path.join(os.path.basename(dp), fn))
                    if all(w in k for w in words_t):
                        p = os.path.join(dp, fn)
                        info = {}
                        try:
                            info = mm.read_audio(p)
                        except Exception:
                            pass
                        tg = info.get("tags") or {}
                        a_ok = not words_a or all(w in k for w in words_a) or mm.artist_agrees([tg.get("artist", "")], artist)
                        if a_ok:
                            hits.append({"path": p, "duration": round(info.get("duration") or 0), "artist": tg.get("artist", ""),
                                         "title": tg.get("title", ""), "album": tg.get("album", "")})
                if len(hits) >= 20 or time.time() - t0 > 240:
                    break
            if len(hits) >= 20 or time.time() - t0 > 240:
                break
        return {"hits": hits, "folders": seen, "timeout": time.time() - t0 > 240}

    def c_dup_quality(self, lib, fids):
        """Quality details per copy, measured on this PC with ffmpeg (read only, cached):
        real lossless? (energy above 16.5 kHz), peak / mean level, clipping."""
        mm = self.mm
        st, cfg = self.store(lib)
        cache = st.load("dup_quality.json", {})
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        ff = cfg.get("ffmpeg") or mm.find_tool("ffmpeg")
        out = {}
        import subprocess
        for fid in fids[:30]:
            r = inv.get(fid)
            if not r:
                continue
            key = f"{fid}|{r.get('sha256', '')}"
            if key in cache:
                out[fid] = cache[key]
                continue
            q = {}
            if ff and mm.exists(r["path"]):
                def vol(af):
                    try:
                        p_ = subprocess.run([ff, "-hide_banner", "-nostats", "-t", "90", "-i", mm.lp(r["path"]), "-af", af, "-f", "null", "-"],
                                            capture_output=True, text=True, timeout=120,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        mean = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)", p_.stderr)
                        mx = re.search(r"max_volume:\s*(-?[\d.]+|-inf)", p_.stderr)
                        f_ = lambda m_: (-999.0 if m_.group(1) == "-inf" else float(m_.group(1))) if m_ else None
                        return f_(mean), f_(mx)
                    except Exception:
                        return None, None
                mean, mx = vol("volumedetect")
                hi, _ = vol("highpass=f=16500,highpass=f=16500,volumedetect")
                q = {"mean_db": mean, "peak_db": mx, "hf_db": hi,
                     "clipped": mx is not None and mx >= -0.05,
                     "fake_lossless": bool(r.get("lossless")) and hi is not None and mean is not None and hi < mean - 55,
                     "bandwidth": "full (above 16.5 kHz)" if hi is not None and mean is not None and hi > mean - 45 else
                                  "cut near 16 kHz (MP3-like)" if hi is not None else ""}
            out[fid] = cache[key] = q
        st.save("dup_quality.json", cache)
        return out

    def c_dup_compare(self, lib, fids):
        """How alike the copies sound, pair by pair: same audio data = 100 %; else the AcoustID fingerprints
        made on this PC are compared (nothing is sent)."""
        mm = self.mm
        st, cfg = self.store(lib)
        inv = {r["id"]: r for r in st.cached("inventory.json", [])}
        fp = cfg.get("fpcalc") or mm.find_tool("fpcalc")
        cp = mm.Chromaprint(fp) if fp else None
        out = []
        ids = [f for f in fids if f in inv][:8]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = inv[ids[i]], inv[ids[j]]
                if a.get("audio_hash") and a["audio_hash"] == b.get("audio_hash"):
                    pct, how = 100, "same audio data"
                elif cp:
                    sim = cp.similarity(cp.raw(a["path"]), cp.raw(b["path"]))
                    pct, how = (round(sim * 100) if sim is not None else None), "sound fingerprints"
                else:
                    pct, how = None, "fpcalc missing"
                out.append({"a": ids[i], "b": ids[j], "pct": pct, "how": how})
        return {"pairs": out}

    def c_preview(self, lib, deezer_track):
        """A fresh 30-second preview address from Deezer (their links expire after a while)."""
        import json as _j
        import urllib.request as _u
        try:
            with _u.urlopen(_u.Request(f"https://api.deezer.com/track/{int(deezer_track)}",
                                       headers={"User-Agent": "MusicLibraryManager/2.0"}), timeout=15) as r:
                d = _j.load(r)
            return {"url": d.get("preview") or ""}
        except Exception as e:
            return {"error": f"Deezer did not answer ({type(e).__name__})."}

    def c_preload(self, lib):
        self.lookups(lib)
        return {"ok": True}

    # ---------------------------------------------------------------- main loop
    def loop(self):
        while True:
            cmd = self.cmd_q.get()
            op = cmd.get("op")
            if op == "quit":
                self.save_caches()
                break
            if op == "answer":                     # your answer to an on-screen "Are you sure?"
                slot = self.answer_slots.get(cmd.get("id"))
                if slot:
                    slot[1] = "y" if cmd.get("value") else "n"
                    slot[0].set()
                continue
            if op == "job":
                threading.Thread(target=self.run_job, args=(cmd,), daemon=True).start()
            elif op == "call":
                threading.Thread(target=self.call, args=(cmd,), daemon=True).start()


def main(cmd_q, evt_q, stop_ev, here, pause_ev=None):
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    sys.path.insert(0, here)
    patch = os.environ.get("MIDNIGHT_TEST_PATCH")      # test harness only (fake MusicBrainz); never set by the app
    if patch:
        import importlib.util
        spec = importlib.util.spec_from_file_location("midnight_test_patch", patch)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    try:
        Worker(cmd_q, evt_q, stop_ev, pause_ev).loop()
    except KeyboardInterrupt:
        pass

"""Midnight 00:01 - Analyze reports (read only).

Excel (all artists, albums, almost complete), PDF (summary, tiers, top artists, almost complete) and an image card
for one artist. Everything is made from analysis.json + plan.json; new files go into <library>\\_Reports and an
existing file is never overwritten.
"""
from __future__ import annotations

import os
import time

W_BG, W_PANEL, W_TEXT, W_SUB, W_AMBER, W_GREEN, W_LINE = "#111214", "#1A1C20", "#ECE8E1", "#A9A59D", "#E8A33D", "#5CC0A7", "#30343B"
TIER_COL = {"Golden Full Collection": "#E8A33D", "Get To Collection": "#5CC0A7", "Starter Collection": "#8FA3C0",
            "Scattered Collection": "#C08FA3", "Unknown Discography": "#8C8880"}


def _font(size, bold=False):
    from PIL import ImageFont
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    dirs = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"), "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"]
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _out(library, name, ext):
    folder = os.path.join(library, "_Reports")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"{name} {time.strftime('%Y-%m-%d %H%M')}")
    p, n = base + ext, 2
    while os.path.exists(p):                     # never overwrite
        p, n = f"{base} ({n}){ext}", n + 1
    return p


def _safe(s):
    return "".join(c for c in (s or "") if c not in '\\/:*?"<>|').strip() or "Artist"


def excel(an, library):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="1A1C20")

    def sheet(ws, cols, rows):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = head, fill
        for r in rows:
            ws.append([r.get(k, "") for k in cols])
        for i, k in enumerate(cols, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(10, min(50, max([len(str(k))] + [len(str(r.get(k, ""))) for r in rows[:500]]) + 2))
        ws.freeze_panes = "A2"
    ws = wb.active
    ws.title = "Summary"
    sm = an.get("summary") or {}
    for k, v in sm.items():
        ws.append([k.replace("_", " "), v])
    sheet(wb.create_sheet("Artists"), ["artist", "tier", "songs", "releases", "complete_releases", "studio_complete", "studio_total", "percent"],
          sorted(an.get("artists") or [], key=lambda r: -(r.get("songs") or 0)))
    sheet(wb.create_sheet("Albums"), ["artist", "album", "year", "type", "tracks_owned", "tracks_total", "percent", "complete", "missing"],
          sorted(an.get("albums") or [], key=lambda r: (r.get("artist") or "", str(r.get("year") or ""))))
    sheet(wb.create_sheet("Almost complete"), ["artist", "album", "have", "total", "missing", "you_have_it_on"], an.get("almost") or [])
    p = _out(library, "Collection report", ".xlsx")
    wb.save(p)
    return p


def _page():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1240, 1754), W_BG)            # A4 at 150 dpi
    return img, ImageDraw.Draw(img)


def _bar(d, x, y, w, h, pct, col):
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=W_LINE)
    if pct:
        d.rounded_rectangle([x, y, x + max(h, int(w * min(100, pct) / 100)), y + h], radius=h // 2, fill=col)


def _clip(d, text, font, width):
    text = str(text or "")
    while text and d.textlength(text, font=font) > width:
        text = text[:-2] + "…" if len(text) > 2 else ""
    return text


def pdf(an, library):
    sm, pages = an.get("summary") or {}, []
    f_h, f_b, f_t, f_s = _font(54, True), _font(28, True), _font(24), _font(20)
    img, d = _page()
    y = 90
    d.text((80, y), "Midnight 00:01 · Collection report", font=f_h, fill=W_TEXT)
    y += 80
    d.text((80, y), time.strftime("%d %B %Y") + "  ·  " + library, font=f_s, fill=W_SUB)
    y += 70
    tiles = [("artists", sm.get("artists")), ("different songs", sm.get("songs")), ("albums", sm.get("releases")),
             ("complete albums", sm.get("complete_releases")), ("almost complete", sm.get("almost_complete")),
             ("avg. complete", f"{sm.get('average_release_percent', 0)}%")]
    for i, (k, v) in enumerate(tiles):
        x0, y0 = 80 + (i % 3) * 370, y + (i // 3) * 150
        d.rounded_rectangle([x0, y0, x0 + 345, y0 + 130], radius=18, fill=W_PANEL)
        d.text((x0 + 24, y0 + 18), f"{v:,}" if isinstance(v, int) else str(v or 0), font=f_h, fill=W_AMBER)
        d.text((x0 + 24, y0 + 88), k, font=f_s, fill=W_SUB)
    y += 330
    tc = {}
    for a in an.get("artists") or []:
        tc[a.get("tier") or "Unknown Discography"] = tc.get(a.get("tier") or "Unknown Discography", 0) + 1
    if tc:
        d.text((80, y), "Collection tiers", font=f_b, fill=W_TEXT)
        y += 50
        mx = max(tc.values())
        for t in ["Golden Full Collection", "Get To Collection", "Starter Collection", "Scattered Collection", "Unknown Discography"]:
            d.text((80, y), t, font=f_t, fill=W_TEXT)
            _bar(d, 470, y + 8, 560, 16, tc.get(t, 0) / mx * 100, TIER_COL[t])
            d.text((1060, y), f"{tc.get(t, 0):,}", font=f_t, fill=W_SUB)
            y += 44
    y += 30
    d.text((80, y), "Top artists", font=f_b, fill=W_TEXT)
    y += 50
    for a in sorted(an.get("artists") or [], key=lambda r: -(r.get("songs") or 0))[:15]:
        d.text((80, y), _clip(d, a["artist"], f_t, 520), font=f_t, fill=W_TEXT)
        d.text((620, y), f"{a.get('songs', 0)} songs · {a.get('releases', 0)} albums · {a.get('complete_releases', 0)} complete", font=f_s, fill=W_SUB)
        y += 40
    pages.append(img)
    almost = an.get("almost") or []
    while almost:
        img, d = _page()
        y = 90
        d.text((80, y), "Almost complete albums", font=f_h, fill=W_TEXT)
        y += 90
        while almost and y < 1640:
            x = almost.pop(0)
            d.text((80, y), _clip(d, f"{x['artist']} — {x['album']}", f_b, 1080), font=f_b, fill=W_TEXT)
            y += 42
            _bar(d, 80, y + 6, 300, 14, x["have"] / max(1, x["total"]) * 100, W_AMBER)
            d.text((400, y), _clip(d, f"{x['have']} of {x['total']} · missing: {x.get('missing', '')}", f_s, 760), font=f_s, fill=W_SUB)
            y += 56
        pages.append(img)
    p = _out(library, "Collection report", ".pdf")
    pages[0].save(p, "PDF", resolution=150, save_all=True, append_images=pages[1:])
    return p


def artist_card(an, library, artist, cover_paths=None):
    """One artist as a picture (like the Analyze screen): tier, numbers, every album with how complete it is."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:                          # v1.1: no Pillow on this PC -> a picture file that needs nothing extra
        return _artist_svg(an, library, artist)
    a = next((r for r in an.get("artists") or [] if r.get("artist") == artist), None)
    if not a:
        raise ValueError("Artist not found in the analysis.")
    als = sorted([r for r in an.get("albums") or [] if r.get("artist") == artist], key=lambda r: str(r.get("year") or "9999"))
    h = 420 + 92 * max(1, len(als))
    img = Image.new("RGB", (1200, h), W_BG)
    d = ImageDraw.Draw(img)
    f_h, f_b, f_t, f_s = _font(64, True), _font(30, True), _font(26), _font(21)
    col = TIER_COL.get(a.get("tier") or "", "#8C8880")
    d.ellipse([70, 70, 230, 230], fill=W_PANEL, outline=col, width=8)
    ini = "".join(w[0] for w in artist.replace("The ", "").split()[:2]).upper() or "?"
    d.text((150 - d.textlength(ini, font=f_h) / 2, 112), ini, font=f_h, fill=W_TEXT)
    d.text((270, 80), _clip(d, artist, f_h, 880), font=f_h, fill=W_TEXT)
    d.text((272, 168), a.get("tier") or "", font=f_b, fill=col)
    stats = [f"{a.get('songs', 0)} songs", f"{a.get('releases', 0)} albums", f"{a.get('complete_releases', 0)} complete"]
    if a.get("studio_total"):
        stats.append(f"{a.get('studio_complete')} of {a.get('studio_total')} studio albums")
    d.text((272, 216), "  ·  ".join(stats), font=f_t, fill=W_SUB)
    y = 320
    d.line([70, y - 24, 1130, y - 24], fill=W_LINE, width=2)
    for al in als:
        pct = float(al.get("percent") or 0)
        c = W_GREEN if al.get("complete") else W_AMBER
        d.rounded_rectangle([70, y, 1130, y + 76], radius=14, fill=W_PANEL)
        d.text((96, y + 10), _clip(d, al.get("album", ""), f_b, 760), font=f_b, fill=W_TEXT)
        d.text((96, y + 46), " · ".join(str(x) for x in (al.get("year"), al.get("type")) if x), font=f_s, fill=W_SUB)
        _bar(d, 880, y + 22, 220, 14, pct, c)
        owned = f"{al.get('tracks_owned')} of {al.get('tracks_total')}" if al.get("tracks_total") else f"{al.get('tracks_owned')} songs"
        d.text((880, y + 44), owned, font=f_s, fill=W_SUB)
        y += 92
    d.text((70, h - 50), "Midnight 00:01 · " + time.strftime("%d %B %Y"), font=f_s, fill=W_SUB)
    p = _out(library, f"Artist card - {_safe(artist)}", ".png")
    img.save(p)
    return p


def _artist_svg(an, library, artist):
    """Same picture as an SVG (opens in any browser; no extra library needed)."""
    from xml.sax.saxutils import escape as x
    a = next((r for r in an.get("artists") or [] if r.get("artist") == artist), None)
    if not a:
        raise ValueError("Artist not found in the analysis.")
    als = sorted([r for r in an.get("albums") or [] if r.get("artist") == artist], key=lambda r: str(r.get("year") or "9999"))
    h = 420 + 92 * max(1, len(als))
    col = TIER_COL.get(a.get("tier") or "", "#8C8880")
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{h}" font-family="Segoe UI,Arial,sans-serif">',
         f'<rect width="1200" height="{h}" fill="{W_BG}"/>',
         f'<circle cx="150" cy="150" r="76" fill="{W_PANEL}" stroke="{col}" stroke-width="8"/>',
         f'<text x="270" y="130" font-size="60" font-weight="700" fill="{W_TEXT}">{x(artist)}</text>',
         f'<text x="272" y="190" font-size="30" font-weight="700" fill="{col}">{x(a.get("tier") or "")}</text>',
         f'<text x="272" y="236" font-size="26" fill="{W_SUB}">{x(str(a.get("songs", 0)) + " songs · " + str(a.get("releases", 0)) + " albums · " + str(a.get("complete_releases", 0)) + " complete")}</text>']
    y = 320
    for al in als:
        pct = max(0.0, min(100.0, float(al.get("percent") or 0)))
        c = W_GREEN if al.get("complete") else W_AMBER
        owned = f"{al.get('tracks_owned')} of {al.get('tracks_total')}" if al.get("tracks_total") else f"{al.get('tracks_owned')} songs"
        o += [f'<rect x="70" y="{y}" width="1060" height="76" rx="14" fill="{W_PANEL}"/>',
              f'<text x="96" y="{y + 34}" font-size="28" font-weight="700" fill="{W_TEXT}">{x(str(al.get("album", ""))[:48])}</text>',
              f'<text x="96" y="{y + 62}" font-size="21" fill="{W_SUB}">{x(" · ".join(str(v) for v in (al.get("year"), al.get("type")) if v))}</text>',
              f'<rect x="880" y="{y + 22}" width="220" height="14" rx="7" fill="{W_LINE}"/><rect x="880" y="{y + 22}" width="{2.2 * pct:.0f}" height="14" rx="7" fill="{c}"/>',
              f'<text x="880" y="{y + 62}" font-size="21" fill="{W_SUB}">{x(owned)}</text>']
        y += 92
    o += [f'<text x="70" y="{h - 30}" font-size="21" fill="{W_SUB}">Midnight 00:01 · {time.strftime("%d %B %Y")}</text></svg>']
    p = _out(library, f"Artist card - {_safe(artist)}", ".svg")
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(o))
    return p


def collection_card(an, library, top=14):
    """The whole collection as one picture: the numbers and the most complete artists. PNG (Pillow) or SVG."""
    sm = an.get("summary") or {}
    arts = sorted(an.get("artists") or [], key=lambda a: -(a.get("songs") or 0))[:top]
    lines = [f"{sm.get('artists', 0)} artists", f"{sm.get('songs', 0)} different songs", f"{sm.get('releases', 0)} albums",
             f"{sm.get('complete_releases', 0)} complete", f"{sm.get('average_release_percent', 0)}% average"]
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        from xml.sax.saxutils import escape as x
        h = 300 + 70 * max(1, len(arts))
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{h}" font-family="Segoe UI,Arial,sans-serif"><rect width="1200" height="{h}" fill="{W_BG}"/>',
             f'<text x="70" y="110" font-size="58" font-weight="700" fill="{W_TEXT}">My music collection</text>',
             f'<text x="70" y="170" font-size="26" fill="{W_SUB}">{x("  ·  ".join(lines))}</text>']
        y = 260
        for a in arts:
            o += [f'<rect x="70" y="{y}" width="1060" height="56" rx="12" fill="{W_PANEL}"/>',
                  f'<text x="94" y="{y + 36}" font-size="26" fill="{W_TEXT}">{x(str(a.get("artist", ""))[:44])}</text>',
                  f'<text x="900" y="{y + 36}" font-size="22" fill="{W_SUB}">{x(str(a.get("songs", 0)) + " songs · " + str(a.get("releases", 0)) + " albums")}</text>']
            y += 70
        o.append(f'<text x="70" y="{h - 30}" font-size="21" fill="{W_SUB}">Midnight 00:01 · {time.strftime("%d %B %Y")}</text></svg>')
        p = _out(library, "Collection card", ".svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(o))
        return p
    h = 300 + 70 * max(1, len(arts))
    img = Image.new("RGB", (1200, h), W_BG)
    d = ImageDraw.Draw(img)
    f_h, f_t, f_s = _font(58, True), _font(26), _font(21)
    d.text((70, 70), "My music collection", font=f_h, fill=W_TEXT)
    d.text((70, 150), "  ·  ".join(lines), font=f_t, fill=W_SUB)
    y = 260
    for a in arts:
        d.rounded_rectangle([70, y, 1130, y + 56], radius=12, fill=W_PANEL)
        d.text((94, y + 12), _clip(d, a.get("artist", ""), f_t, 760), font=f_t, fill=W_TEXT)
        d.text((900, y + 15), f"{a.get('songs', 0)} songs · {a.get('releases', 0)} albums", font=f_s, fill=W_SUB)
        y += 70
    d.text((70, h - 50), "Midnight 00:01 · " + time.strftime("%d %B %Y"), font=f_s, fill=W_SUB)
    p = _out(library, "Collection card", ".png")
    img.save(p)
    return p


# ----------------------------------------------------------------------------- V2.0.5 (#13): the final Excel report
def final_report(st, library, version="", decisions=None):
    """One workbook for the whole sort (decision 27), saved in <library>\\_logs and never overwritten.
    Sheets: Summary, Tagged (what each song became), Before and after (every changed tag), _Unverified, Duplicates, Not found.
    Read only: made from plan.json, inventory.json, music_provenance.csv, duplicates.json and your Review choices."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    import csv
    decisions = decisions or {}
    plan = st.load("plan.json", [])
    inv = {r["id"]: r for r in st.load("inventory.json", [])}
    dups = st.load("duplicates.json", [])
    prov = {}
    try:
        with open(st.p("music_provenance.csv"), encoding="utf-8-sig", newline="") as f:
            prov = {r["file_id"]: r for r in csv.DictReader(f)}
    except OSError:
        pass
    wb = Workbook()
    head, fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1A1C20")

    def sheet(name, cols, rows):
        ws = wb.create_sheet(name[:31])
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = head, fill
        for r in rows:
            ws.append([("" if r.get(k) is None else r.get(k)) for k in cols])
        for i, k in enumerate(cols, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(10, min(55, max([len(str(k))] + [len(str(r.get(k, ""))) for r in rows[:400]]) + 2))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        return ws

    tagged, changes, unver, notfound, left = [], [], [], [], []
    for it in plan:
        if it.get("kind") == "skip":
            continue
        fid = it["file_id"]
        r = inv.get(fid) or {}
        tg = r.get("tags") or {}
        pv = prov.get(fid) or {}
        dec = decisions.get(fid) or {}
        status = pv.get("status") or ("ready to copy" if it.get("approved") else "waiting for review")
        if dec.get("action") == "leave":
            left.append({"file": r.get("path") or it.get("src", ""), "artist": tg.get("artist", ""), "title": tg.get("title", ""), "album": tg.get("album", "")})
            continue
        before = {"artist": pv.get("orig_artist") or tg.get("artist", ""), "album": pv.get("orig_album") or tg.get("album", ""),
                  "title": pv.get("orig_title") or tg.get("title", ""), "track": pv.get("orig_track") or tg.get("track", ""),
                  "year": pv.get("orig_year") or tg.get("year", ""), "genre": tg.get("genre", "")}
        nt = it.get("new_tags") or {}
        after = {f: (pv.get("new_" + f) or nt.get(f) or "") for f in ("artist", "album", "title", "track", "year", "genre")}
        after = {f: (after[f] or before[f]) for f in after}      # a field the plan leaves empty keeps what the file had
        base = {"status": status, "original_path": r.get("path") or it.get("src", ""), "new_path": pv.get("new_full_path") or it.get("new_path", ""),
                "match_percent": it.get("match_percent"), "source": pv.get("data_source") or it.get("data_source", ""), "confidence": pv.get("confidence", "")}
        k = it.get("kind")
        if k == "unverified" and not it.get("approved"):
            notfound.append(dict(base, artist=tg.get("artist", ""), title=tg.get("title", ""), album=tg.get("album", ""), reason=it.get("reason", ""),
                                 your_choice=dec.get("action", "")))
            continue
        if k in ("unverified", "artist_unverified", "short", "long") or "_Unverified" in (base["new_path"] or "") or "_Sound Effects" in (base["new_path"] or ""):
            unver.append(dict(base, artist=before["artist"], title=before["title"], album=before["album"], reason=it.get("reason", ""), your_choice=dec.get("action", "")))
            continue
        if it.get("dup_extra"):
            continue
        tagged.append(dict(base, **{f"before_{f}": before[f] for f in before}, **{f"after_{f}": after[f] for f in after}))
        for f in before:
            if str(before[f] or "").strip() != str(after[f] or "").strip():
                changes.append({"song": after["title"] or before["title"], "artist": after["artist"] or before["artist"], "field": f,
                                "before": before[f], "after": after[f], "status": status, "original_path": base["original_path"]})
    ws = wb.active
    ws.title = "Summary"
    n_copied = sum(1 for p in prov.values() if p.get("status") in ("copied", "verified", "original_archived"))
    rows = [("Report made", time.strftime("%Y-%m-%d %H:%M")), ("App version", version), ("Library", library),
            ("Songs in the plan", sum(1 for it in plan if it.get("kind") != "skip")), ("Copied into the library", n_copied),
            ("Tagged songs (sheet Tagged)", len(tagged)), ("Changed tag fields (sheet Before and after)", len(changes)),
            ("In _Unverified (kept with their own tags)", len(unver)), ("Not found anywhere", len(notfound)),
            ("Extra copies / duplicates", len({d.get("group") for d in dups})), ("Left out by you", len(left))]
    for a, b in rows:
        ws.append([a, b])
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 60
    base_cols = ["status", "match_percent", "source", "confidence", "original_path", "new_path"]
    sheet("Tagged", ["status"] + [f"{p}_{f}" for p in ("before", "after") for f in ("artist", "album", "title", "track", "year", "genre")] + base_cols[1:], tagged)
    sheet("Before and after", ["song", "artist", "field", "before", "after", "status", "original_path"], changes)
    sheet("_Unverified", ["artist", "title", "album", "reason", "your_choice", "status", "original_path", "new_path"], unver)
    sheet("Duplicates", ["group", "rank", "decision", "why", "identical_audio", "format", "bitrate_kbps", "length", "size_mb", "artist", "title", "album", "source", "new_name"], dups)
    sheet("Not found", ["artist", "title", "album", "reason", "your_choice", "original_path"], notfound)
    if left:
        sheet("Left out", ["artist", "title", "album", "file"], left)
    folder = st.logs
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, f"final_report {time.strftime('%Y-%m-%d %H%M')}")
    p, n = base + ".xlsx", 2
    while os.path.exists(p):                     # never overwrite
        p, n = f"{base} ({n}).xlsx", n + 1
    wb.save(p)
    return p

/* Midnight 00:01 · Archive screen (part of the screens, loaded in order by index.html) */
'use strict';
function archiveScreen() {
  const C = S.arch, job = S.B.job, running = job && !job.done;
  if (!C) { if (!S.archLoading) { S.archLoading = true; call('archive_info').then(r => { S.arch = r || {}; S.archLoading = false; if (S.archDir == null) S.archDir = (r && r.archive) || ''; render(); }); }
    return `<header class="bighead"><h1>Archive</h1><p><span class="spin"></span> Loading…</p></header>`; }
  if (C.error) return `<header class="bighead"><h1>Archive</h1><p>${esc(C.error)}</p></header>`;
  const ok = (S.archDir || '').trim() && !S.archErr;
  if (!C.archive_on && !S.archForce) return `<header class="bighead"><h1>Archive</h1><p>Archive is switched off.</p></header>
    <section class="warnbar"><b style="color:var(--amber-text)">Archive MOVES your original songs.</b><span class="grow">Everything else in this app only copies. The originals are moved out of your music folders into an archive folder (nothing is deleted, and it can be undone from Find &amp; restore). It is switched off so it cannot be started by accident.</span>
      <button class="btn amber" onclick="A.go('settings')">Open the setting</button></section>`;
  return `<header class="bighead"><h1>Archive</h1><p>The last step: your ORIGINAL files are moved into an archive folder, keeping their old folders, so your music folders end up empty and the organized library is what you use. Nothing is ever deleted, and everything can be put back.</p></header>
    <section class="grid4"><div class="stat"><span class="si">${svg('M5 4h14v4H5zM6 8v12h12V8M10 12h4', 18)}</span><div class="srow"><div class="k">originals ready to archive (their copy is verified)</div><div class="v" style="color:var(--green-text)">${fmt(C.ready)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 3v12M7 10l5 5 5-5M5 20h14', 18)}</span><div class="srow"><div class="k">to move</div><div class="v">${human(C.ready_size)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', 18)}</span><div class="srow"><div class="k">already archived</div><div class="v">${fmt(C.archived)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 9v4M12 17h0M10.3 4.2L2.8 17a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z', 18)}</span><div class="srow"><div class="k">without an audio check (they stay)</div><div class="v" style="color:${C.no_hash ? 'var(--amber-text)' : 'var(--text)'}">${fmt(C.no_hash)}</div></div></div></section>
    ${!C.ready ? `<div class="panel empty">${C.archived ? '<b style="color:var(--green-text)">Every copied song\'s original is archived.</b> ' : ''}Nothing to archive right now. Copy songs into your library first (Copy &amp; tag), then check the library.<div style="margin-top:10px"><button class="btn amber small" onclick="A.go('apply')">Go to Copy &amp; tag</button></div></div>` : `
    <h2 class="step"><span class="num">1</span>Check your new library first</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:8px"><span>Open the library and listen to a few songs. Only originals whose copy exists and has the same audio are moved; every other original stays where it is.</span>
      <div class="row"><button class="btn outline small" onclick="A.openLib()">Open the library folder</button></div>
      <span class="sub" style="font-size:13px">Biggest source folders: ${(C.folders || []).map(f => esc(f.folder.split(/[\\/]/).slice(-2).join('\\')) + ' (' + f.songs + ')').join(' · ')}</span></section>
    <h2 class="step"><span class="num">2</span>Choose the archive folder</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:10px">
      <div class="row" style="gap:8px"><input class="text mono grow" id="archdir" placeholder="e.g. C:\\WORKPLACE\\_NEW WORLD ORDER\\EVERY MUSIC ALL AT ONCE" value="${esc(S.archDir || '')}" oninput="S.archDir=this.value;S.archErr=''" onchange="A.archCheck()">
        <button class="btn" onclick="A.archBrowse()">Browse…</button></div>
      ${S.archErr ? `<span style="color:var(--clay);font-size:13px">${esc(S.archErr)}</span>` : '<span class="sub" style="font-size:13px">Not inside your music folders or the library.</span>'}
      <div class="modes" style="grid-template-columns:1fr 1fr">${[['keep', 'Keep the old folders', 'Each original keeps its old path inside the archive (e.g. Archive\\C\\Music\\Album\\Song.mp3). Easiest to put back by hand.'],
        ['flat', 'Archive flat', 'Every original straight into the archive folder, no folders. Same names get the artist first ("Artist - Song.mp3"), then a number.']].map(o =>
        `<button class="mode" aria-pressed="${(S.archFlat ? 'flat' : 'keep') === o[0]}" onclick="S.archFlat=${o[0] === 'flat'};render()"><span class="t"><span class="radio"></span>${o[1]}</span><span class="sub" style="font-size:13px">${o[2]}</span></button>`).join('')}</div>
      <label style="display:flex;gap:8px;align-items:center;font-size:13px;cursor:pointer"><input type="checkbox" ${S.archEmpty ? 'checked' : ''} onchange="S.archEmpty=this.checked" style="width:18px;height:18px;accent-color:var(--amber)">
        Afterwards, offer to remove folders that are left completely empty (you see the list and answer; files are never deleted)</label></section>
    <h2 class="step"><span class="num">3</span>Approve</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:10px">
      <span>The app first checks every copy against its original again. Then it shows you exactly what will move and asks <b>Are you sure?</b> before anything is moved.</span>
      <div class="row"><button class="btn green" style="min-height:48px;padding:0 24px;font-size:15px" onclick="A.archGo()" ${!ok || running ? 'disabled' : ''}>Approve: check and archive ${plural(C.ready, 'original')}</button>
        ${running ? '<span class="sub">Something is running — <button class="btn small outline" onclick="A.go(\'dash\')">See progress</button></span>' : ''}</div></section>`}
    ${(C.recent || []).length ? `<details class="panel" style="padding:12px 16px"><summary><b>Archived originals</b> <span class="sub">· newest first · put any back on Find &amp; restore</span></summary>
      <div class="copylist" style="margin-top:8px">${C.recent.map(r => `<div class="copyrow" style="flex-direction:column;align-items:flex-start;cursor:default"><span class="mono wrap" style="font-size:12px">${esc(r.to)}</span><span class="sub" style="font-size:12px">was: ${esc(r.from)}</span></div>`).join('')}</div></details>` : ''}`;
}

// ---- Copy & tag

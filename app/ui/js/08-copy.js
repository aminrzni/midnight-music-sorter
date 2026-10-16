/* Midnight 00:01 · Copy & tag screen (part of the screens, loaded in order by index.html) */
'use strict';
const human = b => b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? Math.round(b / 1e6) + ' MB' : Math.round((b || 0) / 1e3) + ' KB';
function copyScreen() {
  const C = S.copy, job = S.B.job, running = job && !job.done;
  if (!C) { if (!S.copyLoading) { S.copyLoading = true; call('copy_info').then(r => { S.copy = r || {}; S.copyLoading = false; render(); }); }
    return `<header class="head"><div><h1>Copy &amp; tag</h1><p><span class="spin"></span> Loading…</p></div></header>`; }
  if (C.error) return `<header class="head"><div><h1>Copy &amp; tag</h1><p>${esc(C.error)}</p></div></header>`;
  const mode = S.copyMode || 'confirmed', pick = S.copyPick || (S.copyPick = {});
  const WA = C.waiting_all != null ? C.waiting_all : C.waiting;            // V2.0.5 (#2): C.waiting is the shared 'needs you' number; WA = every song not ready yet
  const picked = (C.artists || []).filter(a => pick[a.artist]);
  const n = mode === 'all' ? C.ready + WA : mode === 'recognized' ? C.ready + (C.recog || 0) : mode === 'custom' ? picked.reduce((t, a) => t + a.songs, 0) : C.ready;
  const size = mode === 'all' ? C.ready_size + C.waiting_size : mode === 'recognized' ? C.ready_size + (C.recog_size || 0) : mode === 'custom' ? picked.reduce((t, a) => t + a.size, 0) : C.ready_size;
  const opts = [['confirmed', 'Confirmed', `${fmt(C.ready)} songs (${human(C.ready_size)}): every song a music site confirmed or you decided in Review. Songs still waiting are not copied yet.`],
    ['recognized', 'Recognized', `${fmt(C.ready + (C.recog || 0))} songs: the confirmed ones plus ${fmt(C.recog || 0)} found by a music site. They are accepted for you.`],
    ['all', 'All', `${fmt(C.ready + WA)} songs (${human(C.ready_size + C.waiting_size)}): also the ${fmt(WA)} songs not ready yet (${fmt(C.waiting)} still need you in Review${C.decided ? ', ' + fmt(C.decided) + ' decided but not in the plan yet' : ''}) — they are copied with their OWN tags into _Unverified (you can fix them later).`],
    ['custom', 'Custom pick', 'Only the artists you tick below.']];
  const q = (S.copyQ || '').toLowerCase();
  const list = mode === 'custom' ? `<section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:8px">
      <div class="row" style="gap:8px"><input class="text grow" id="copyq" placeholder="Find an artist" value="${esc(S.copyQ || '')}" oninput="S.copyQ=this.value;render()">
        <button class="btn small" onclick="A.copyPickAll(true)">Tick all shown</button><button class="btn small ghost" onclick="A.copyPickAll(false)">Clear</button></div>
      <div class="copylist" data-ks="copylist">${(C.artists || []).filter(a => !q || a.artist.toLowerCase().includes(q)).map(a =>
        `<label class="copyrow"><input type="checkbox" ${pick[a.artist] ? 'checked' : ''} onchange="S.copyPick[${arg(a.artist)}]=this.checked;render()"><span class="grow">${esc(a.artist)}</span><span class="sub">${plural(a.songs, 'song')} · ${human(a.size)}</span></label>`).join('')}</div></section>` : '';
  const copyProg = job && job.kind === 'copy' ? progPanel(S.dash || {}, S.B, job, stageInfo(job, S.B.progress), running) : '';
  return `${copyProg}${notCopiedPanel(C, running)}<header class="head"><div><h1>Copy &amp; tag</h1><p>Makes tagged copies in your library. Your originals are never changed, and existing files are never overwritten.</p></div></header>
    ${C.stale ? '<div class="banner">Your newest Review choices are not in the plan yet — they are added automatically before copying.</div>' : ''}
    ${C.copied ? `<details id="copiedbox" class="panel" style="padding:12px 16px" ${S.copyOpen ? 'open' : ''} ontoggle="S.copyOpen=this.open"><summary><b>${plural(C.copied, 'song')} already in the library</b> <span class="sub">(not copied again) · newest first</span></summary>
      <div class="copylist" style="margin-top:8px">${(C.recent || []).map(r => `<div class="copyrow" style="flex-direction:column;align-items:flex-start;cursor:default">
        <span class="mono wrap" style="font-size:12px">${esc(r.path)}</span><span class="sub" style="font-size:12px">${esc([r.status === 'verified' ? 'verified: same audio as the original' : r.status, r.changes, r.when].filter(Boolean).join(' · '))}</span></div>`).join('')}</div></details>` : ''}
    <h2 class="step"><span class="num">1</span>What should be copied?</h2>
    <section class="modes" aria-label="What to copy">${opts.map(o => `<button class="mode" aria-pressed="${mode === o[0]}" onclick="S.copyMode=${arg(o[0])};render()"><span class="t"><span class="radio"></span><span class="mico">${svg(({ confirmed: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', recognized: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5', all: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', custom: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12' })[o[0]], 18)}</span>${o[1]}</span><span class="sub" style="font-size:13px">${o[2]}</span></button>`).join('')}</section>
    ${list}
    <h2 class="step"><span class="num">2</span>Extras (optional)</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:10px">${copyExtras()}</section>
    <h2 class="step"><span class="num">3</span>Approve</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:10px">
      <div style="font-size:16px"><b>${plural(n, 'song')}</b> · ${human(size)} → <span class="mono">${esc(C.library)}</span></div>
      ${(C.extra || []).length ? `<div class="note">Also: ${plural(C.extra.length, 'song')} copied into albums where they are missing (from Analyze): ${C.extra.slice(0, 6).map(e => esc(e.title + ' → ' + e.album)).join(' · ')}${C.extra.length > 6 ? ' …' : ''}</div>` : ''}
      <span class="sub" style="font-size:13px">Covers and lyrics are embedded in the copies. Cover art: ${esc((C.covers || []).join(' → '))} (sent: artist and album names). Lyrics: LRCLIB, lrclib.net (sent: artist, song and album names and length). Covers are added only where a song has none or a small one.</span>
      <span class="sub" style="font-size:13px">First your newest Review choices go into the plan, then the copies are made. You can pause or cancel any time; an undo log is written.${C.dup_extra ? ' ' + plural(C.dup_extra, 'extra copy', 'extra copies') + ' of songs you already have ' + (C.dup_extra === 1 ? 'is' : 'are') + ' not copied (see Duplicates).' : ''}</span>
      <div class="row"><button class="btn green" style="min-height:48px;padding:0 24px;font-size:15px" onclick="A.copyGo()" ${(!n && !(C.extra || []).length) || running ? 'disabled' : ''}>Approve: copy ${plural(n + (C.extra || []).length, 'song')}</button>
        <button class="btn outline" onclick="A.finalReport()" data-tip="An Excel file with every tagged song (before and after), _Unverified, duplicates and songs not found. Saved in the library's _logs folder. Nothing is changed.">Final Excel report</button>
        ${running ? '<span class="sub">Something is running — <button class="btn small outline" onclick="A.go(\'dash\')">See progress</button></span>' : ''}</div></section>${exportPanel()}`;
}

// ---- 2.0.2 (item 75): copy the verified songs of the library into another folder
function exportPanel() {
  const I = S.expInfo, st = S.expSt || (I && I.state);
  if (!I) { if (!S.expLoading) { S.expLoading = true; call('export_info').then(r => { S.expInfo = r || {}; S.expSt = r && r.state; S.expLoading = false; render(); }); } return `<h2 class="step"><span class="num">4</span>Export verified songs</h2><section class="panel pad"><span class="spin"></span> Counting…</section>`; }
  const running = st && st.running, ok = (S.expDir || '').trim() && !S.expErr;
  const prog = st ? `<div class="note"><b>${fmt(st.copied)}</b> copied · ${fmt(st.skipped)} already there (left as they are) · ${fmt(st.failed)} failed · of ${fmt(st.total)}${running ? ' <span class="spin"></span>' : (st.done ? ' · <b style="color:var(--green-text)">done</b>' : '')}
    ${running ? `<div class="sub mono wrap" style="font-size:12px">${esc(st.last || '')}</div><div class="row"><button class="btn small outline" onclick="A.expCancel()">Stop</button></div>` : ''}
    ${(st.errors || []).length ? `<details><summary>Problems (${st.errors.length})</summary><div class="mono wrap" style="font-size:12px">${st.errors.map(esc).join('<br>')}</div></details>` : ''}</div>` : '';
  return `<h2 class="step"><span class="num">4</span>Export verified songs (optional)</h2>
    <section class="panel pad" style="display:flex;flex-direction:column;gap:10px">
      <span><b>${plural(I.songs || 0, 'song')}</b> · ${human(I.size || 0)} in your library are verified (everything except the <span class="mono">_Unverified</span> and other <span class="mono">_</span> folders). This copies them, with their folders, into another folder, for example for a phone or a backup. Your library is not changed and nothing is overwritten.</span>
      <div class="row" style="gap:8px"><input class="text mono grow" id="expdir" placeholder="e.g. D:\\Phone music" value="${esc(S.expDir || '')}" oninput="S.expDir=this.value;S.expErr=''"><button class="btn" onclick="A.expBrowse()">Browse…</button></div>
      ${S.expErr ? `<span style="color:var(--clay);font-size:13px">${esc(S.expErr)}</span>` : ''}
      <div class="row"><button class="btn green" onclick="A.expAsk()" ${!(S.expDir || '').trim() || running || !(I.songs) ? 'disabled' : ''}>Copy the verified songs…</button></div>${prog}</section>`;
}


function copyExtras() {
  const E = S.copyScan;
  const lo = (E && E.left_out) || (S.rv ? S.rv.items.filter(x => x.decision && x.decision.action === 'leave').length : 0);
  const left = `<label class="row" style="gap:8px;cursor:pointer;font-size:14px"><input type="checkbox" ${S.copyLeft ? 'checked' : ''} onchange="S.copyLeft=this.checked;render()" style="width:18px;height:18px;accent-color:var(--amber)">
    Also copy the songs you left out${lo ? ' (' + fmt(lo) + ')' : ''} into <span class="mono">_LeftOut</span> — one flat folder, "Artist - Title", to listen and delete yourself. The originals stay where they are.</label>`;
  if (!E) return `<div class="row" style="gap:8px"><button class="btn outline" onclick="A.copyScan()" ${S.copyScanning ? 'disabled' : ''}>${S.copyScanning ? '<span class="spin"></span> Looking…' : 'Scan for extra files'}</button>
    <span class="sub" style="font-size:13px">Looks next to your songs for cover pictures, playlists, .cue / .log files, booklets and lyrics files that could be copied into the album folders too. Nothing is copied unless you tick it.</span></div>${left}`;
  const names = { covers: 'Cover pictures', playlists: 'Playlist files', cue: 'CD rip files (.cue / .log)', booklets: 'Booklets / scans', lyrics: 'Lyrics files (.lrc / .txt)' };
  const kinds = Object.keys(E.kinds || {});
  return (kinds.length ? `<span class="sub" style="font-size:13px">Found next to your songs. Tick what should be COPIED into the album folders (originals are only read; nothing is overwritten):</span>
    ${kinds.map(k => { const v = E.kinds[k]; return `<label class="exrow"><input type="checkbox" ${(S.copyEx || {})[k] ? 'checked' : ''} onchange="S.copyEx=S.copyEx||{};S.copyEx[${arg(k)}]=this.checked;render()">
      <span class="grow"><b>${esc(names[k] || k)}</b> <span class="sub">· ${plural(v.count, 'file')} · ${human(v.size)}</span><span class="sub mono" style="display:block;font-size:11px;overflow-wrap:anywhere">${v.examples.map(e => esc(e.split(/[\\/]/).slice(-2).join('\\'))).join(' · ')}</span></span></label>`; }).join('')}`
    : '<span class="sub">No extra files found next to your songs.</span>') + left;
}
// ---- Duplicates: every song found more than once, ranked best -> worst; your choice per copy

// ---- 1.1.7: songs that were NOT copied, with the reason and what to do about each
function notCopiedPanel(C, running) {
  const F = C.failures || []; if (!F.length) return '';
  const by = {}; F.forEach(f => (by[f.code] = by[f.code] || []).push(f));
  const titles = { in_use: 'Another program had the file open', exists: 'Already in the library', changed: 'Original changed after the scan',
    audio_diff: 'The copy did not match the audio', disk_full: 'The drive is full', path: 'Path problem', other: 'Other' };
  return `<section class="panel" style="padding:14px 16px;border-color:var(--amber)"><div class="row" style="gap:10px;flex-wrap:wrap">
      <b class="grow">${plural(F.length, 'song')} not copied</b>
      <button class="btn small green" onclick="A.copyGo()" ${running ? 'disabled' : ''} title="Copies only the songs that are still missing">Retry these</button></div>
    ${Object.keys(by).map(k => `<details style="margin-top:8px" ${S.ncOpen === k ? 'open' : ''} ontoggle="if(this.open)S.ncOpen=${arg(k)}"><summary><b>${esc(titles[k] || k)}</b> <span class="sub">· ${plural(by[k].length, 'song')}</span></summary>
      <div class="note" style="margin:6px 0">${esc(by[k][0].reason)}<br><b>What to do:</b> ${esc(by[k][0].guide)}</div>
      <div class="copylist">${by[k].slice(0, 200).map(f => `<div class="copyrow" style="flex-direction:column;align-items:flex-start;cursor:default"><span class="mono wrap" style="font-size:12px">${esc(f.src)}</span><span class="sub" style="font-size:12px">${esc(f.detail || '')}</span></div>`).join('')}</div></details>`).join('')}</section>`;
}


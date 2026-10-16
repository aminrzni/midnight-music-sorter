/* Midnight 00:01 · Dashboard screen (part of the screens, loaded in order by index.html) */
'use strict';
function stageInfo(job, p) {
  if (!job) return null;
  const label = p && p.label || '';
  let pct = 0, title = '', line = '', step = 1;
  const n = p && p.n || 0, t = p && p.total || 0, f = t ? Math.min(1, n / t) : 0;
  if (job.stage === 'read') {
    step = 1; pct = 30 * f; title = 'Step 1 · Reading files';
    line = t ? `${fmt(n)} of ${fmt(t)} files read${p.cur ? ' · ' + p.cur : ''}` : 'finding your music files…';
  } else {
    step = 2;
    const parts = { 'Identifying': [30, 55, 'Identifying songs'], 'Looking for original albums': [85, 4, 'Looking for original albums'],
      'Checking other sites': [89, 6, 'Checking other sites'], 'Checking discographies': [95, 5, 'Checking discographies'] };
    const [a, b, name] = parts[label] || [30, 0, 'Identifying songs'];
    pct = a + b * f; title = 'Step 2 · ' + name;
    line = t ? `${fmt(n)} of ${fmt(t)}${p.cur ? ' · ' + p.cur : ''}${p.extra ? ' · ' + p.extra : ''}` : 'getting ready…';
  }
  // v1.1: Scan and Identify each get their own 0-100% (the old single bar mixed them)
  let scanPct = null, idPct = null;
  if (job.kind === 'scan' || job.kind === 'update') {
    if (job.stage === 'read') { scanPct = Math.round(100 * f); idPct = 0; pct = 100 * f; }
    else { scanPct = job.kind === 'scan' ? 100 : null; idPct = Math.max(0, Math.min(100, Math.round((pct - 30) / 70 * 100))); pct = idPct; }
  }
  if (job.done && !job.error && (job.kind === 'scan' || job.kind === 'update')) { scanPct = job.kind === 'scan' ? 100 : null; idPct = 100; }
  if (job.kind === 'update' && !job.done) title = 'Full update of the plan · ' + title.replace('Step 2 · ', '');
  if (job.kind === 'fastupdate' && !job.done) { pct = 100 * f; title = 'Updating the plan with your new choices'; line = t ? `${fmt(n)} of ${fmt(t)} songs${p.cur ? ' · ' + p.cur : ''}` : 'getting ready…'; }
  if (job.kind === 'copy' && !job.done) {
    if (job.stage !== 'copy') { pct = 20 * f; title = 'Copy & tag · first: updating the plan with your Review choices'; }
    else if (label === 'Fetching covers + lyrics') { step = 3; pct = 20 + 20 * f; title = 'Step 3 · Finding covers + lyrics'; line = t ? `${fmt(n)} of ${fmt(t)}` : 'getting ready…'; }
    else { step = 3; pct = 40 + 60 * f; title = 'Step 3 · Copying + tagging'; line = t ? `${fmt(n)} of ${fmt(t)} songs${p.cur ? ' · ' + p.cur : ''}` : 'getting ready…'; }
  }
  if (job.kind === 'archive' && !job.done) {
    step = 4;
    if (label === 'Archiving originals') { pct = 50 + 50 * f; title = 'Step 4 · Moving originals into the archive'; }
    else { pct = 50 * f; title = 'Step 4 · Checking every copy against its original first'; }
    line = t ? `${fmt(n)} of ${fmt(t)}${p.cur ? ' · ' + p.cur : ''}` : 'getting ready…';
    if (S.B.confirm) title = 'Step 4 · Waiting for your answer';
  }
  if (['restore_one', 'reverse_log', 'undo_copy', 'restore_all'].includes(job.kind) && !job.done) { step = 4; pct = t ? 100 * f : 10; title = S.B.confirm ? 'Find & restore · waiting for your answer' : 'Find & restore · working…'; line = t ? `${fmt(n)} of ${fmt(t)}` : ''; }
  if (job.kind === 'loonybin' && !job.done) { step = 3; pct = 100 * f; title = S.B.confirm ? 'Duplicates · waiting for your answer' : 'Duplicates · working on the extra copies'; line = t ? `${fmt(n)} of ${fmt(t)}${p.cur ? ' · ' + p.cur : ''}` : 'getting ready…'; }
  if (job.done) { pct = 100; title = job.error ? ({ loonybin: 'Duplicates stopped',  update: 'Update cancelled', copy: 'Copy & tag stopped', scan: 'Scan cancelled', archive: 'Archive stopped' }[job.kind] || 'Stopped')
    : ({ fastupdate: 'Plan updated with your choices', restore_one: 'Restore finished', restore_all: 'Originals put back', reverse_log: 'Reverse finished', undo_copy: 'Undo finished', loonybin: 'Duplicates folder filled', update: 'Plan updated with your choices', copy: 'Copy & tag finished', scan: 'Scan & identify finished', archive: 'Archive finished' }[job.kind] || 'Finished');
    if (job.finished && job.started) title += ' in ' + dur(job.finished - job.started); }
  return { pct: Math.round(pct), title, line, step, left: job.done ? null : p && p.left, scanPct, idPct };
}
function dashAnimate() {                       // count up numbers and grow bars once Phase 2 has finished
  if (!S.dashAnim) return; S.dashAnim = false;
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) { render(); return; }
  requestAnimationFrame(() => {
    document.querySelectorAll('[data-w]').forEach(i => i.style.width = i.dataset.w + '%');
    const els = [...document.querySelectorAll('[data-count]')], t0 = performance.now();
    const step = now => { const k = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - k, 3);
      els.forEach(el => el.textContent = fmt(Math.round((+el.dataset.count || 0) * e)) + (el.dataset.suf || ''));
      if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
function progPanel(d, B, job, si, running) {
  const amber = 'var(--amber-text)', green = 'var(--green-text)';
  const done = job.done && !job.error;
  return `<section class="prog" aria-label="Scan progress" ${job.error ? 'style="border-color:var(--clay)"' : ''}>
      <div class="row" style="justify-content:space-between;align-items:baseline"><span class="t">${esc(si.title)}</span><span class="pct">${si.pct}%</span></div>
      ${si.scanPct != null ? (running && si.step === 1
        ? `<div class="sub" style="font-size:12px;display:flex;justify-content:space-between"><span>Step 1 · Scan · reading files</span><span>${si.scanPct}%</span></div><div class="bar"><i style="width:${si.scanPct}%"></i></div>`
        : running && si.step === 2
        ? `<div class="sub" style="font-size:12px;display:flex;justify-content:space-between"><span>Step 2 · Identify · matching songs</span><span>${si.idPct}%</span></div><div class="bar"><i style="width:${si.idPct}%"></i></div>`
        : `<div class="sub" style="font-size:12px;display:flex;justify-content:space-between"><span>Scan · reading files</span><span>${si.scanPct}%</span></div><div class="bar"><i style="width:${si.scanPct}%"></i></div>
      <div class="sub" style="font-size:12px;display:flex;justify-content:space-between;margin-top:6px"><span>Identify · matching songs</span><span>${si.idPct}%</span></div><div class="bar"><i style="width:${si.idPct}%"></i></div>`) : `<div class="bar big"><i style="width:${si.pct}%"></i></div>`}
      <div class="row sub" style="justify-content:space-between;font-size:13px"><span class="wrap">${job.done ? (job.error ? esc(job.error) : `${fmt(d.confirmed)} confirmed · ${fmt(d.waiting)} need you · ${fmt(d.unverified)} _Unverified`) : esc(si.line)}</span><span>${running ? (job.paused ? 'paused' : mins(si.left)) : ''}</span></div>
      ${running ? `<div class="row">${job.paused ? `<span style="font-weight:700;color:var(--amber-text)">Paused</span><button class="btn small amber" onclick="A.pause(false)">Resume</button>`
        : `<button class="btn small" onclick="A.pause(true)">Pause</button>`}<button class="btn small ghost" onclick="A.stop()" title="End the scan. Nothing is changed; the last finished results stay.">Cancel</button></div>` : ''}
      ${done ? `<div class="row"><span style="font-size:13px;color:var(--green-text);font-weight:600">${['restore_one', 'reverse_log', 'undo_copy', 'restore_all'].includes(job.kind) ? 'Done (if you said yes). Nothing was deleted; a restore log was written. See Details for exactly what happened.' : job.kind === 'loonybin' ? 'Duplicates done (see Details for exactly what happened). A report is in _LoonyBin and a restore log was written.' : job.kind === 'archive' ? 'Originals moved into the archive. Nothing was deleted; a restore log was written.' : job.kind === 'copy' ? 'Copies made. Your originals were not touched.' : ['update', 'fastupdate'].includes(job.kind) ? 'Plan updated with your choices.' : 'Done. Review the songs that need you when you are ready.'}</span>
        ${['restore_one', 'reverse_log', 'undo_copy', 'restore_all'].includes(job.kind) ? `<button class="btn amber small" onclick="S.fTab=${arg('logs')};A.go('search');A.fLogs()">See the restore logs</button>` : job.kind === 'loonybin' ? `<button class="btn amber small" onclick="A.go('dups')">Back to Duplicates</button>` : job.kind === 'archive' ? `<button class="btn amber small" onclick="A.go('archive')">See the archive</button><button class="btn outline small" onclick="A.go('search')">Restore logs</button>`
          : job.kind === 'copy' ? `<button class="btn amber small" onclick="A.seeCopied()">See what was copied</button><button class="btn outline small" onclick="A.openLib()">Open the library folder</button>`
          : ['update', 'fastupdate'].includes(job.kind) ? `<button class="btn amber small" onclick="A.go('review')">Back to Review</button><button class="btn outline small" onclick="A.go('plan')">Go to Plan preview →</button>` : `<button class="btn amber small" onclick="A.go('review')">Go to Review</button>`}
        </div>` : ''}
      ${job.error && job.done ? `<div class="row"><button class="btn small" onclick="A.go('sources')">Back to Sources</button><button class="btn amber small" onclick="A.scanAsk()">Scan again</button></div>` : ''}
      <details ${(S.logOpen ?? !!job.error) ? 'open' : ''} ontoggle="S.logOpen=this.open"><summary>Details</summary><div class="log" id="log">${esc((B.lines || []).join('\n'))}</div></details>
    </section>`;
}
const STEP_ICON = { 'Scan': 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4', 'Identify': 'M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z',
  'Copy & tag': 'M8 8h12v12H8zM4 16V4h12', 'Archive': 'M3 5h18v4H3zM5 9v11h14V9M10 13h4' };
function dashScreen() {
  const d = S.dash || {}, B = S.B, job = B.job, si = stageInfo(job, B.progress);
  const running = job && !job.done;
  const amber = 'var(--amber-text)', green = 'var(--green-text)';
  let prog = '';
  if (job && job.kind === 'copy') prog = `<section class="panel pad" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span><b>Copy &amp; tag</b> ${running ? 'is running' : job.error ? 'stopped' : 'finished'} · its progress is on the Copy &amp; tag page.</span><button class="btn small amber" onclick="A.go('apply')">Open Copy &amp; tag</button></section>`;
  else if (job) prog = progPanel(d, B, job, si, running);
  const inRead = running && si.step === 1, inId = running && si.step === 2;
  const st = (n, name, state, dot, ink) => `<div class="card"><div class="row" style="gap:8px"><span class="dot" style="background:${dot};color:${ink}">${n}</span><span style="font-weight:600">${name}</span><span style="margin-left:auto;color:var(--sub);display:inline-flex">${svg(STEP_ICON[name] || 'M5 12h14', 18)}</span></div><span class="sub" style="font-size:13px">${state}</span></div>`;
  const has = d.has_scan;
  const panel2 = 'var(--panel2)', subc = 'var(--sub)';
  const steps = [
    st(1, 'Scan', inRead ? 'reading files… ' + esc(si.line.split(' · ')[0]) : inId ? (job.files != null ? plural(job.files, 'file') + ' read' : S.B.readTotal ? plural(S.B.readTotal, 'file') + ' read' : 'files read') : has ? plural(d.scanned, 'file') + ' read' : 'not started', inRead ? '#E8A33D' : has || inId ? '#5CC0A7' : panel2, inRead ? '#1A1300' : has || inId ? '#0D2620' : subc),
    st(2, 'Identify', inRead ? 'waiting' : inId ? 'identifying… ' + si.pct + '%' : d.has_plan && !d.plan_stale ? plural(d.waiting, 'song') + ' wait for you' : 'not started', inId || (d.has_plan && d.waiting) ? '#E8A33D' : d.has_plan ? '#5CC0A7' : panel2, inId || (d.has_plan && d.waiting) ? '#1A1300' : d.has_plan ? '#0D2620' : subc),
    st(3, 'Copy & tag', d.copied ? plural(d.copied, 'song') + ' in the library' : 'after you approve', d.copied ? '#5CC0A7' : panel2, d.copied ? '#0D2620' : subc),
    st(4, 'Archive', d.archived ? plural(d.archived, 'original') + ' archived' : 'last step', d.archived ? '#5CC0A7' : panel2, d.archived ? '#0D2620' : subc)
  ].join('');
  const SI = ['M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z', 'M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z', 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z'];
  const stats = [[(d.sorted_pct || 0) + '%', 'Library sorted', green], [fmt(d.songs || d.scanned), 'Songs', 'var(--text)'], [fmt(d.confirmed), 'Confirmed online', 'var(--text)'], [fmt(d.waiting), 'Waiting for you', amber]]
    .map((s, i) => running ? `<div class="stat"><span class="si">${svg(SI[i], 18)}</span><div class="srow"><div class="k">${s[1]}</div><div class="v" style="color:var(--sub)">${i === 1 && S.B.progress && S.B.progress.total ? fmt(S.B.progress.total) : '–'}</div></div></div>`
      : `<div class="stat"><span class="si">${svg(SI[i], 18)}</span><div class="srow"><div class="k">${s[1]}</div><div class="v" data-count="${String(s[0]).replace(/\D/g, '')}" ${String(s[0]).endsWith('%') ? 'data-suf="%"' : ''} style="color:${s[2]}">${S.dashAnim ? '0' : s[0]}</div></div></div>`).join('');
  const bd = d.breakdown;
  const bdRow = !running && bd && bd.songs ? `<section class="panel bdrow" aria-label="What happened to your songs">${[
      [bd.placed, 'placed', 'var(--green-text)', 'Have a place in the library (found online, or decided by you)'],
      [bd.check, 'found · wait for your check', 'var(--amber-text)', 'Found by a song search: you check them (Review › Check)'],
      [bd.place, 'artist found · album not', '#8FA3C0', 'The artist is confirmed but no site lists the album (often box sets): Review › Place, or Trust my tags'],
      [bd.none, 'not found anywhere', 'var(--clay)', 'Review › No album: Dig deeper, Search again, Trust my tags or Keep'],
      [bd.later + bd.left_out, 'later / left out by you', 'var(--sub)', 'Your own choice'],
      [bd.extra_copies, 'extra copies (Duplicates)', 'var(--sub)', 'The same song more than once: the best copy is kept; these are not failures']]
    .map(r => `<span class="bdi" data-tip="${esc(r[3])}"><b style="color:${r[2]}">${fmt(r[0])}</b> ${r[1]}</span>`).join('')}
    <span class="sub" style="font-size:12px;flex-basis:100%">${bd.songs ? Math.round(bd.found / bd.songs * 100) : 0}% of ${fmt(bd.songs)} songs (without extra copies) were found online.</span></section>` : '';
  let tiers = bdRow;
  if (running && d.has_plan) tiers = `<section class="panel" style="padding:20px"><span class="sub" style="font-size:13px">Numbers and tiers appear when the scan has finished.</span></section>`;
  else if (d.tiers && d.tiers.some(t => t.count)) {
    const max = Math.max(1, ...d.tiers.map(t => t.count)), sm = d.summary || {};
    const noTiers = sm.tiers_known === false || d.tiers.every(t => t.short === 'Unknown Discography' || !t.count);
    tiers += `<div class="row" style="justify-content:space-between;align-items:center;padding:4px 2px"><h2 style="margin:0;font-size:20px">Analyze summary</h2>
        <button class="btn outline small" onclick="A.go('analyze')">${svg(ICON.chart, 16, 'currentColor', 2)} More analysis</button></div>
    <section class="panel" aria-label="Collection tiers" style="padding:20px;display:flex;flex-direction:column;gap:14px">
      <div class="row" style="justify-content:space-between"><div style="display:flex;flex-direction:column;gap:2px"><h2 style="margin:0;font-size:17px">Collection tiers</h2>
        <span class="sub" style="font-size:12px">artists · complete studio albums · click a tier to see its artists</span></div></div>
      ${noTiers ? `<span class="sub" style="font-size:13px">Tiers need the discography check of a <b>Complete</b> scan (a Fast scan skips it). ${fmt(sm.artists)} artists · ${fmt(sm.songs || 0)} different songs.</span>` : d.tiers.map(t => `<button class="tierrow" onclick="A.tier(${arg(t.short)})" aria-label="See ${esc(t.name)} artists"><span style="font-size:13px">${esc(t.name)}</span>
        <span class="tbar"><i data-w="${Math.round(t.count / max * 100)}" style="width:${S.dashAnim ? 0 : Math.round(t.count / max * 100)}%;background:${TIER_COLOR[t.short] || '#8C8880'}"></i></span><span class="mono" style="font-size:13px;text-align:right" data-count="${t.count}">${S.dashAnim ? '0' : fmt(t.count)}</span></button>`).join('')}
      <div class="facts"><div><div style="font-size:20px;font-weight:700;color:${green}">${fmt(sm.complete_releases)}</div><div class="sub" style="font-size:12px">complete albums (not counting compilations)</div></div>
        <div><div style="font-size:20px;font-weight:700">${fmt(sm.average_release_percent)}%</div><div class="sub" style="font-size:12px">avg. complete</div></div></div></section>`;
  }
  let more = '';
  if (!running && (d.top_artists || []).length) {
    const mx = Math.max(1, ...d.top_artists.map(a => a.songs));
    setTimeout(dashPics, 0);
    more = `<div class="grid2">
      <section class="panel" aria-label="Top artists" style="padding:20px;display:flex;flex-direction:column;gap:10px">
        <h2 style="margin:0;font-size:17px">Your top artists</h2><span class="sub" style="font-size:12px">different songs · albums · complete albums</span>
        ${d.top_artists.map((a, i) => { const pic = (S.anPics || {})[a.artist]; return `<div class="tierrow wide" style="cursor:default"><span style="font-size:13px;overflow-wrap:anywhere;display:flex;align-items:center;gap:8px"><span class="avatar" style="width:30px;height:30px;flex:none;font-size:11px">${pic ? `<img src="${esc(pic)}" alt="">` : esc(initials(a.artist))}</span><span>${i + 1}. ${esc(a.artist)}</span></span>
          <span class="tbar"><i data-w="${Math.round(a.songs / mx * 100)}" style="width:${S.dashAnim ? 0 : Math.round(a.songs / mx * 100)}%;background:${['#E8A33D', '#5CC0A7', '#7FA7E0', '#D9776A', '#B58FD8'][i % 5]}"></i></span>
          <span class="mono" style="font-size:12px;text-align:right;white-space:nowrap" title="${esc(fmt(a.songs) + ' songs, ' + a.releases + ' albums, ' + a.complete + ' complete' + (a.studio ? ', ' + a.studio + ' studio albums' : ''))}">${fmt(a.songs)} · ${a.releases} · ${a.complete}✓</span></div>`; }).join('')}
      </section>
      <section class="panel" aria-label="Top albums" style="padding:20px;display:flex;flex-direction:column;gap:10px">
        <h2 style="margin:0;font-size:17px">Top albums</h2><span class="sub" style="font-size:12px">complete albums first, then the biggest</span>
        ${(d.top_albums || []).map(a => `<div class="almost"><div><b>${esc(a.album)}</b><span class="sub"> · ${esc(a.artist)}${a.year ? ' · ' + esc(String(a.year).slice(0, 4)) : ''}</span></div>
          <div class="bar"><i style="width:${a.total ? Math.round(a.have / a.total * 100) : 100}%;background:${a.complete ? 'var(--green)' : 'var(--amber)'}"></i></div>
          <span class="sub" style="font-size:12px">${a.total ? a.have + ' of ' + a.total + (a.complete ? ' · complete' : '') : plural(a.have, 'song')}</span></div>`).join('') || '<span class="sub">None right now.</span>'}
      </section></div>`;
  }
  const sortLbl = d.sort_mode === 'collection' ? 'Collection sort' : 'Simple sort';
  return `<header class="head"><div><h1>Your library</h1><p>${d.library ? esc(sortLbl) + (d.last_run ? ' · last run ' + esc(d.last_run) : '') + (d.last_jobs && d.last_jobs.scan && !d.last_jobs.scan.error ? ' · last scan took ' + dur(d.last_jobs.scan.seconds) : '') + ' · <span class="mono">' + esc(d.library) + '</span>' : 'Choose your music and library on Sources first.'}</p></div>
    ${d.waiting && !running ? `<div class="row" style="gap:8px"><button class="btn amber" onclick="A.go('review')" data-tip="Opens Review from the start, with the first song that still needs you">${svg('M5 12l5 5L20 7', 15)} Review ${plural(d.waiting, 'song')}</button></div>` : ''}</header>
    ${prog}
    ${!has && !job ? `<div class="panel empty">No scan yet. <button class="btn amber small" onclick="A.go('sources')">Go to Sources</button></div>` : ''}
    <section class="grid4" aria-label="Steps">${steps}</section>
    ${(has && !d.plan_stale) || running ? `<section class="grid4" aria-label="Numbers">${stats}</section>` : ''}
    ${tiers}${more}`;
}

// ---------------------------------------------------------------- REVIEW

// 1.1.7: photos for the top artists on the Dashboard (the same pictures Analyze uses)
async function dashPics() {
  const names = ((S.dash || {}).top_artists || []).map(a => a.artist).filter(n => !(S.anPicAsked || {})[n]); if (!names.length || S.dashPicBusy) return;
  S.dashPicBusy = true; S.anPics = S.anPics || {}; S.anPicAsked = S.anPicAsked || {}; names.forEach(n => S.anPicAsked[n] = true);
  try { const r = await call('artist_pictures', names); if (r && !r.error && !r.busy) { Object.assign(S.anPics, r); if (S.screen === 'dash') render(); } } finally { S.dashPicBusy = false; }
}

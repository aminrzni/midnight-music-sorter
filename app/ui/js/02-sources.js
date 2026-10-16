/* Midnight 00:01 · Sources screen (+ whole-library panel) (part of the screens, loaded in order by index.html) */
'use strict';
function nestedBar() {
  const N = S.nested; if (!N || !N.nested || !N.nested.length) return '';
  const n = N.nested.reduce((t, x) => t + x.songs, 0);
  return N.skipping
    ? `<section class="note"><span>Skipping folders that start with "_" inside your music folders (${plural(N.nested.length, 'folder')}, ${plural(n, 'song')}). Change this in Settings.</span><button class="btn small ghost" onclick="A.openNestedSetting()">Open the setting</button></section>`
    : `<section class="warnbar"><b style="color:var(--amber-text)">Possible double counting</b><span class="grow">Inside your music folders there ${N.nested.length === 1 ? 'is a folder' : 'are folders'} starting with "_": ${N.nested.slice(0, 4).map(x => '<span class="mono">' + esc(x.folder) + '</span> (' + plural(x.songs, 'song') + ')').join(', ')}${N.nested.length > 4 ? ', …' : ''}. Songs in there are often copies of songs elsewhere in the same folder, so they would be counted and sorted twice.</span>
      <button class="btn amber" onclick="A.openNestedSetting()">Open the setting</button></section>`;
}
function sourcesScreen() {
  const B = S.B, info = S.info || {};
  const srcs = B.sources || info.sources || [];
  const nkey = srcs.map(s => s.path).join('|');
  if (S.nestedKey !== nkey) { S.nestedKey = nkey; if (srcs.length) call('nested_info').then(r => { S.nested = r; render(); }); else S.nested = null; }
  const ex = B.excludes || [];
  const lib = B.library || info.library;
  const pend = B.pending || [];
  // V2.0.5 experiment (flip GUIDED_SOURCES to false in 22-v205.js to go back): only ONE step is open at a time.
  // Songs added -> step 2 opens by itself; library chosen -> step 3 opens by itself. Click a step title to open it yourself.
  const G = typeof GUIDED_SOURCES !== 'undefined' && GUIDED_SOURCES, hasSrc = srcs.length > 0, hasLib = !!lib;
  const seen = S.srcSeen || (S.srcSeen = { src: hasSrc, lib: hasLib });
  if (S.srcStep == null) S.srcStep = !hasSrc ? 1 : !hasLib ? 2 : 3;
  if (hasSrc && !seen.src) S.srcStep = hasLib ? 3 : 2;
  if (hasLib && !seen.lib) S.srcStep = 3;
  seen.src = hasSrc; seen.lib = hasLib;
  const stepOpen = n => !G || S.srcStep === n;
  const stepHead = (n, title, summary, style) => `<h2 class="step" ${style ? `style="${style}"` : ''} ${G ? `onclick="A.srcStep(${n})" role="button" aria-expanded="${stepOpen(n)}" tabindex="0" onkeydown="if(event.key==='Enter')A.srcStep(${n})"` : ''}><span class="num">${n}</span>${title}${G && !stepOpen(n) && summary ? `<span class="sub" style="font-size:13px;font-weight:400;margin-left:8px">${summary}</span>` : ''}${G ? `<span class="sub" style="margin-left:auto;font-size:13px;font-weight:400;cursor:pointer">${stepOpen(n) ? '▴' : '▾'}</span>` : ''}</h2>`;
  const rows = srcs.map(s => {
    const c = (B.counts || {})[s.path];
    const files = s.file ? 'one song' : c ? (c.counting ? 'counting… ' + fmt(c.files) : plural(c.files, 'song')) : '';
    const inside = ex.filter(e => e.toLowerCase().startsWith(s.path.toLowerCase().replace(/[\\/]+$/, '') + (s.path.includes('\\') ? '\\' : '/')));
    return `<div class="srcrow">${s.file ? noteIcon : svg(ICON.folder)}<div class="grow"><div class="p">${esc(s.path)}</div>
      ${inside.length ? `<div class="ex">skipping ${plural(inside.length, 'folder')} inside: ${esc(inside.map(e => e.split(/[\\/]/).pop()).join(', '))}</div>` : ''}</div>
      <span class="sub" style="font-size:13px;white-space:nowrap">${files}</span>
      <button class="iconbtn" aria-label="Remove ${esc(s.path)}" onclick="A.removeSource(${arg(s.path)})">${svg(ICON.x, 16, 'currentColor', 2)}</button></div>`;
  }).join('');
  const total = srcs.reduce((t, s) => t + (((B.counts || {})[s.path] || {}).files || 0), 0);
  return `
  <header class="bighead"><div class="row" style="justify-content:space-between;align-items:flex-start;gap:12px"><h1>Sources</h1><span class="row" style="gap:8px;flex-wrap:wrap;justify-content:flex-end"><button class="btn outline small" onclick="A.newProject()" ${S.B.job && !S.B.job.done ? 'disabled' : ''} title="Empties the music folders list and lets you choose a new destination. Nothing on disk is touched.">Start a new project</button><button class="btn outline small" onclick="A.loadSession()" ${S.B.job && !S.B.job.done ? 'disabled' : ''} title="Open a project you saved before: choose its session file (Save session, bottom left).">Load session</button></span></div><p>Start here: tell the app where your music is now and where the organized library should go. Scanning only reads your files; nothing is changed.</p></header>
  ${stepHead(1, 'Where is your music?', hasSrc ? esc(plural(srcs.length, 'folder')) : 'not chosen yet', '')}
  <div class="stepbody" ${stepOpen(1) ? '' : 'hidden'}>
  <div class="drop ${S.dropOver ? 'over' : ''}" id="dropzone">
    ${svg(ICON.upload, 40, '#E8A33D', 1.5)}
    <span style="font-size:16px;font-weight:600">Drop music folders here</span>
    <span class="sub" style="font-size:13px">from Windows Explorer — or</span>
    <div class="row" style="justify-content:center">
      <button class="btn" onclick="A.browse()">Browse…</button>
      <button class="btn" onclick="A.browseSongs()" title="Scan only the songs you pick, not their whole folder">Add songs…</button>
      <button class="btn" onclick="A.wholeStart()" ${S.w && !S.w.st.done && !S.w.st.cancelled ? 'disabled' : ''}>Scan whole computer</button>
    </div>
  </div>
  <div class="row" style="gap:8px;margin:6px 0"><input class="text mono grow" placeholder="…or type / paste a folder path, e.g. D:\\Music" value="${esc(S.typedSrc || '')}" oninput="S.typedSrc=this.value" onkeydown="if(event.key==='Enter')A.typedSource()" aria-label="Music folder path"><button class="btn small" onclick="A.typedSource()">Add folder</button></div>
  ${S.w ? wholePanel() : ''}
  ${pend.length ? `<section class="note" style="border:1px solid var(--amber);flex-direction:column;align-items:stretch;gap:8px"><b>${plural(pend.length, 'folder')} waiting (added while a job was running)</b>
    <span class="mono wrap" style="font-size:12px">${esc(pend.join('  ·  '))}</span>
    <div class="row"><button class="btn small amber" onclick="A.pendingTake()">Add ${pend.length === 1 ? 'it' : 'them'} to the sources now</button><span class="sub" style="font-size:12px">The running job is not disturbed. Scan again afterwards: songs already read are skipped, only the new ones are read.</span></div></section>` : ''}
  <section class="panel" aria-label="Chosen sources">
    ${srcs.length > 1 ? `<div class="row" style="justify-content:flex-end;padding:8px 18px 0"><button class="btn small ghost" onclick="A.removeAll()" ${S.B.job && !S.B.job.done ? 'disabled' : ''}>Remove all</button></div>` : ''}
    ${rows || '<div class="srcrow"><span class="sub">No music folders yet.</span></div>'}
    <div class="pad sub" style="font-size:13px;padding:12px 18px">${srcs.length ? plural(total, 'song') + ' in ' + plural(srcs.length, 'folder') + ' · ' : ''}Skipped automatically: the output library, its logs and the archive${(info.protected || []).length ? ' · protected: ' + esc(info.protected.join(', ')) : ''}</div>
  </section>
  ${nestedBar()}
  </div>
  ${stepHead(2, 'Where should the organized library go?', hasLib ? esc(lib.split(/[\\/]/).filter(Boolean).pop()) : 'not chosen yet', 'margin-top:10px')}
  <div class="stepbody" ${stepOpen(2) ? '' : 'hidden'}>
  <section class="panel pad" aria-label="Output folder" style="display:flex;flex-direction:column;gap:12px">
    <div class="row">${svg(ICON.folder, 18, '#E8A33D', 1.6)}
      <span class="grow mono wrap" style="font-size:13px">${lib ? esc(lib) : '<span class="sub">Not chosen yet</span>'}</span>
      <button class="btn" onclick="A.pickOut()">${lib ? 'Change…' : 'Choose…'}</button></div>
    <div class="row" style="gap:8px"><input class="text mono grow" placeholder="…or type / paste the library folder path" value="${esc(S.typedLib || '')}" oninput="S.typedLib=this.value" onkeydown="if(event.key==='Enter')A.typedLibrary()" aria-label="Library folder path"><button class="btn small" onclick="A.typedLibrary()">Use this path</button></div>
    <div class="note"><span>Logs are kept automatically in <span class="mono wrap">${esc(lib ? lib + sep(lib) + '_logs' : '<library>\\_logs')}</span></span>
      <span class="sub">Every original name and location is recorded there, so anything can be undone or found later.</span></div>
  </section>
  </div>
  ${stepHead(3, 'How fast?', S.speed === 'fast' ? 'Fast' : S.speed === 'complete' ? 'Complete' : '', 'margin-top:10px')}
  <div class="stepbody" ${stepOpen(3) ? '' : 'hidden'}>
  <section class="modes" aria-label="Scan speed">${[['complete', 'Complete', 'Everything: identify by sound for songs not found by name, and the discography check for tiers. Slower.'],
    ['fast', 'Fast', 'Identifies by name only. No identify by sound, no discography check, no lyrics. Good for a first pass over big or messy folders. Tiers from your last Complete scan are kept.']]
    .map(m => `<button class="mode" aria-pressed="${S.speed === m[0]}" onclick="A.speed(${arg(m[0])})"><span class="t"><span class="radio"></span><span class="mico">${svg(m[0] === 'fast' ? 'M13 2L4 14h7l-1 8 9-12h-7z' : 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', 18)}</span>${m[1]}</span><span class="sub" style="font-size:13px">${m[2]}</span></button>`).join('')}</section>
  </div>
  <div class="row" style="gap:12px;flex-wrap:wrap;align-items:center">
    <button class="btn amber" style="min-height:48px;padding:0 22px;font-size:15px" onclick="A.scanAsk()" ${S.B.job && !S.B.job.done ? 'disabled' : ''}>Scan &amp; identify</button>
    ${S.B.job && !S.B.job.done ? '<span class="sub">A scan is running —</span><button class="btn outline" onclick="A.go(\'dash\')">See progress</button>' : ''}
    <span class="sub" style="font-size:12px">Forgot a folder? Just add it above, even during a scan.</span>
  </div>`;
}
const sep = p => p.includes('\\') ? '\\' : '/';

// whole computer tree
function wholePanel() {
  const W = S.w, st = W.st || {};
  const running = !st.done && !st.cancelled;
  const tot = {};
  const total = id => { if (tot[id] != null) return tot[id]; let t = W.nodes[id].own; (W.kids[id] || []).forEach(k => t += total(k)); return tot[id] = t; };
  const eff = (id, inh) => Object.prototype.hasOwnProperty.call(W.sel, id) ? W.sel[id] : inh;
  const mixed = (id, val) => (W.kids[id] || []).some(k => { const v = eff(k, val); return v !== val || mixed(k, v); });
  const used = (id, inh) => { const on = eff(id, inh); let t = on ? W.nodes[id].own : 0; (W.kids[id] || []).forEach(k => t += used(k, on)); return t; };
  let rows = '';
  const walk = (id, depth, inh) => {
    const n = W.nodes[id], open = !!W.open[id], on = eff(id, inh), custom = mixed(id, on), cnt = total(id), sub = (W.kids[id] || []).length;
    rows += `<div class="tnode ${n.top ? 'top' : ''}" role="treeitem" aria-expanded="${open}" style="padding-left:${6 + depth * 28}px">
      <button class="tog" aria-label="${open ? 'Close' : 'Open'} ${esc(n.name)}" onclick="A.wToggle(${arg(id)})">${svg(ICON.chev, 16, 'currentColor', 2.2)}</button>
      <button class="nm" onclick="A.wToggle(${arg(id)})" title="${open ? 'Close' : 'Open'} ${esc(n.name)}">${svg(open ? ICON.folderOpen : ICON.folder, 18, '#E8A33D', 1.6, 'style="flex:none"')}
        <span style="flex:1;min-width:0;display:flex;flex-direction:column;gap:1px"><b>${esc(n.name)}</b>${n.top ? `<span class="mono sub wrap" style="font-size:12px">${esc(n.id)}</span>` : ''}</span></button>
      <span class="chip">${plural(cnt, 'song')}${sub ? ' · ' + plural(sub, 'folder') : ''}</span>
      ${n.protected ? '<span class="chip prot">protected</span>' : ''}${n.junk ? `<span class="chip" title="Skipped automatically; click Use if it is music">auto-skipped: ${esc(n.junk)}</span>` : ''}${custom ? '<span class="chip custom">Custom</span>' : ''}
      <div class="useskip" role="group" aria-label="Use this folder?">
        <button class="use" aria-pressed="${on && !custom}" onclick="A.wChoose(${arg(id)},true)">Use</button>
        <button class="skip" aria-pressed="${!on && !custom}" onclick="A.wChoose(${arg(id)},false)">Skip</button></div></div>`;
    if (!open) return;
    skipLast(W.kids[id] || [], on).forEach(k => walk(k, depth + 1, on));
    const sg = W.songs[id];
    const pad = 48 + (depth + 1) * 28;
    if (!sg) { if (n.own) rows += `<div class="song off" style="padding-left:${pad}px">loading songs…</div>`; return; }
    sg.songs.slice(0, 8).forEach(s => rows += `<div class="song ${on ? '' : 'off'}" style="padding-left:${pad}px">${noteIcon}<span>${esc(s)}</span></div>`);
    if (sg.count > 8) rows += `<div class="song off" style="padding-left:${pad}px">${noteIcon}<span>… and ${fmt(sg.count - 8)} more</span></div>`;
  };
  // folders that end up with no songs used (skipped, or everything inside skipped) go to the bottom
  const skipLast = (ids, inh) => ids.map((k, i) => [k, i, used(k, inh) > 0]).sort((a, b) => (b[2] - a[2]) || a[1] - b[1]).map(x => x[0]);
  skipLast(W.tops, true).forEach(id => walk(id, 0, true));
  const chosen = W.tops.filter(id => used(id, true) > 0).length;
  const chosenSongs = W.tops.reduce((t, id) => t + used(id, true), 0);
  return `<section class="panel whole" aria-label="Music found on this computer">
    <div class="row" style="justify-content:space-between;align-items:baseline">
      <span style="font-weight:700;font-size:16px">${running ? 'Looking for music on this computer…' : st.cancelled ? 'Search stopped' : 'Music found on this computer'}</span>
      <span class="sub" style="font-size:13px">${plural(st.songs || 0, 'song')} in ${plural(W.tops.length, 'place')}${st.junk ? ' · ' + fmt(st.junk) + ' audio files auto-skipped (sounds, voice, apps)' : ''} · ${fmt(st.dirs)} folders looked at</span></div>
    ${running ? `<div style="display:flex;flex-direction:column;gap:6px"><div class="bar" role="progressbar" aria-label="Search progress" aria-valuenow="${st.pct || 0}"><i style="width:${Math.max(3, st.pct || 0)}%"></i></div>
      <span class="mono sub wrap" style="font-size:12px">looking in ${esc(st.folder || '')}</span></div>` : ''}
    <div class="tree" data-ks="tree" role="tree" aria-label="Found folders">${rows || '<span class="sub">Nothing found yet…</span>'}</div>
    <div class="row" style="justify-content:flex-end">
      <button class="btn ghost" onclick="A.wCancel()">${running ? 'Stop searching' : 'Close'}</button>
      ${!running && chosen ? `<button class="btn green" onclick="A.wAdd()">Add ${fmt(chosenSongs)} songs from ${plural(chosen, 'place')}</button>` : ''}
    </div></section>`;
}
function wholeSelection() {
  const W = S.w, sources = [], excludes = [];
  const eff = (id, inh) => Object.prototype.hasOwnProperty.call(W.sel, id) ? W.sel[id] : inh;
  const go = (id, inh, parentOn) => {
    const on = eff(id, inh);
    if (on && !parentOn) sources.push(id);
    if (!on && parentOn) excludes.push(id);
    (W.kids[id] || []).forEach(k => go(k, on, on));
  };
  W.tops.forEach(id => go(id, true, false));
  return { sources, excludes };
}

// ---------------------------------------------------------------- DASHBOARD

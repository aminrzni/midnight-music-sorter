/* Midnight 00:01 · Library review (1.1.5): Quick mode on the left, your library on the right.
   Right side: planned library or what is on disk; folder tree / album cards / song table; one search for both sides;
   a song picked on the left jumps to its album (and highlights possible matches); drag a song onto an album to place it. */
'use strict';
const LIBIDX = { arr: null, n: -1, map: null };
function rvById(id) {                                   // one lookup table per list, instead of scanning every song for every row
  const a = S.rv && S.rv.items; if (!a) return null;
  if (LIBIDX.arr !== a || LIBIDX.n !== a.length) { LIBIDX.arr = a; LIBIDX.n = a.length; LIBIDX.map = new Map(a.map(i => [i.id, i])); }
  return LIBIDX.map.get(id) || null;
}
function libState() {
  if (!S.lib) S.lib = { mode: 'plan', view: store.get('libView', 'tree'), open: {}, kids: {}, q: '', filt: {}, all: null, allLoading: false, hits: [], flash: '', focusId: null, cwd: '', sort: 'path' };
  if (S.libSplit == null) S.libSplit = +store.get('libSplit', 48) || 48;
  return S.lib;
}
const LIB_STATE = { copied: 'in library', ready: 'ready to copy', waiting: 'needs review', extra: 'extra copy' };
const libKey = (mode, path) => mode + '|' + path;
async function libLoad(path) {
  const L = libState(), k = libKey(L.mode, path);
  if (L.kids[k]) return L.kids[k];
  L.kids[k] = await call(L.mode === 'disk' ? 'lib_disk' : 'plan_tree', path);
  return L.kids[k];
}
function libDirOk(d) {          // right-side quick filters (planned library only)
  const f = libState().filt;
  if (f.low && !d.low) return false;
  if (f.inc && d.album && !(d.nt && d.songs < d.nt)) return false;
  if (f.tag && !d.waiting) return false;
  if (f.dup && !d.dups) return false;
  return true;
}
function libFileRow(f, depth, n) {
  const L = libState(), st = LIB_STATE[f.state] || f.state || '', low = f.pct != null && f.pct !== '' && +f.pct < 90;
  const rx = f.id ? rvById(f.id) : null, rdone = !!(rx && isDone(rx));      // v2.0: what you decide in Review shows here at once
  const inRv = !!rx, cur = f.id && S.rvSel === f.id, ck = !!(f.id && S.rvChecked[f.id]);
  const stem = x => String(x || '').replace(/\.[^.]+$/, '').toLowerCase(), renamed = f.from && stem(f.from) !== stem(f.name) && f.state !== 'waiting';
  // 1.1.7: a click opens the song (in Quick mode when it is in Review, otherwise it plays); a box selects it, and you can drag over rows to select many
  const act = f.id ? `A.libInfo(${arg(f.id)})` : '';
  return `<div class="librow file ${cur ? 'cur' : ''} ${inRv ? 'inrv' : ''} ${ck ? 'sel' : ''} ${rdone ? 'rdone' : ''}" data-id="${esc(f.id || '')}" style="padding-left:${10 + depth * 16}px;margin-bottom:2px" ${f.id ? `onmousedown="A.libDown(event,${arg(f.id)})" onmouseenter="A.libEnter(${arg(f.id)})" onclick="if(!S.libMoved&&!event.target.closest('button,input'))${act}" title="Click: preview this song on the right"` : ''}>
    ${f.id ? `<input type="checkbox" class="qck" aria-label="Select this song" ${ck ? 'checked' : ''} onclick="event.stopPropagation()" onchange="A.libTog(${arg(f.id)},this.checked)">` : ''}
    ${n != null && S.alLayout !== 'classic' ? `<span class="tno">${n}</span>` : ''}
    ${f.id ? `<button class="pv ${S.playing === f.id ? 'on' : ''}" aria-label="Play" onclick="event.stopPropagation();A.play(${arg(f.id)})">${S.playing === f.id ? '❚❚' : '▶'}</button>` : '<span style="width:26px"></span>'}
    <span class="lname" title="${esc((renamed ? f.from + ' → ' : '') + f.name)}">${renamed ? `<span class="sub" style="font-size:12px">${esc(f.from)}</span> <b style="color:var(--amber-text)">→</b> ` : ''}${esc(f.name)}</span>
    ${f.dup ? '<span class="lchip dup">extra copy</span>' : ''}
    ${rdone ? `<span class="lchip" style="color:var(--green-text)" title="You decided this in Review; the plan has it after Update plan">✓ ${esc(badgeOf(rx))}</span>` : f.state === 'waiting' ? '<span class="lchip warn">needs review</span>' : ''}
    ${low ? `<span class="lchip warn" title="How alike the new tags are to your file">${esc(f.pct)}%</span>` : ''}
    ${f.state === 'waiting' || rdone ? '' : `<span class="sub" style="font-size:11px">${esc(st)}</span>`}</div>`;
}
const libArtistName = n => String(n || '').replace(/^\[[^\]]*\]\s*/, '').replace(/^\d+\s+[A-Za-z ]+?\s+-\s+/, '').replace(/\s*\[[^\]]*\]$/, '').trim();
function libAvatar(name, sz) {
  const n = libArtistName(name), pic = (S.anPics || {})[n];
  return `<span class="libav" style="width:${sz}px;height:${sz}px">${pic ? `<img src="${esc(pic)}" alt="" loading="lazy">` : `<span>${esc(initials(n))}</span>`}</span>`;
}
function libWantPics(names) {                          // artist photos (only when you allowed Deezer): asked once per name
  if (!S.info || !S.info.services || !S.info.services.deezer) return;
  S.anPics = S.anPics || {}; S.anPicAsked = S.anPicAsked || {};
  const want = names.map(libArtistName).filter(n => n && !S.anPicAsked[n]).slice(0, 20);
  if (!want.length || S._libPicBusy) return;
  want.forEach(n => S.anPicAsked[n] = true); S._libPicBusy = true;
  call('artist_pictures', want).then(r => { S._libPicBusy = false; if (r && !r.error && Object.keys(r).length) { Object.assign(S.anPics, r); render(); } });
}
function libDoneRank(f) { const x = f.id ? rvById(f.id) : null; return (x && isDone(x)) || f.state === 'ready' || f.state === 'copied' ? 1 : 0; }      // songs already decided go to the end of their folder
function libMatched(d) { return !!(d && d.songs > 0 && !d.waiting && (d.album || d.name.charAt(0) !== '_')); }
function libDirsFor(path, K, srch) {             // folders to show: filtered, special folders first, folders with songs to review next, finished (Matched) ones last
  const L = libState();
  const a = (K.dirs || []).filter(d => (L.mode !== 'plan' || libDirOk(d)) && (!srch || L.qDirs.has(path ? path + '/' + d.name : d.name)));
  if (L.mode !== 'plan') return a;
  const rank = d => d.name.charAt(0) === '_' ? 0 : libMatched(d) ? 2 : 1;
  return a.map((d, i) => [d, i]).sort((x, y) => rank(x[0]) - rank(y[0]) || x[1] - y[1]).map(x => x[0]);
}
function libTree(path, depth) {
  const L = libState(), K = L.kids[libKey(L.mode, path)];
  if (!K) return `<div class="librow" style="padding-left:${10 + depth * 16}px"><span class="spin"></span></div>`;
  if (K.error) return `<div class="sub" style="padding:8px">${esc(K.error)}</div>`;
  const srch = L.mode === 'plan' && L.qDirs && L.qOn;
  let h = '', names = [];
  const vis = libDirsFor(path, K, srch), lim = (L.dlim && L.dlim[path]) || (path ? 150 : 100);
  for (const d of vis.slice(0, lim)) {
    const p = path ? path + '/' + d.name : d.name;
    const matched = libMatched(d);
    if (matched && L.open[libKey(L.mode, p)] && !(L.userOpen || {})[libKey(L.mode, p)]) L.open[libKey(L.mode, p)] = false;      // matched: the folder closes by itself (you can still open it)
    const open = srch && L.qDirs.size <= 400 ? true : !!L.open[libKey(L.mode, p)], fl = L.flash === p;
    if (open && !L.kids[libKey(L.mode, p)]) libLoad(p).then(render);
    const drop = d.album ? `ondragover="if(S.rvDrag){event.preventDefault();this.classList.add('over')}" ondragleave="this.classList.remove('over')" ondrop="A.libDrop(event,${arg(d.rid || '')},${arg(p)})"` : '';
    if (!depth) names.push(d.name);
    h += `<div class="libbox ${depth ? 'in' : ''}${d.album ? ' isalb' : ''}"><div class="librow dir ${fl ? 'flash' : ''} ${d.album ? 'album' : ''} ${matched ? 'matched' : ''}" data-lib="${esc(p)}" style="padding-left:${10 + depth * 4}px" ${drop} ondblclick="A.libSolo(${arg(p)})" title="Double-click: show only this folder">
      <button class="gtog" aria-expanded="${open}" onclick="A.libToggle(${arg(p)})">${open ? '▾' : '▸'}</button>
      ${!depth && !d.album ? libAvatar(d.name, 28) : ''}${d.album && S.alLayout !== 'classic' ? '<span class="alcov ph" aria-hidden="true"></span>' : ''}<span class="lname" onclick="A.libToggle(${arg(p)})"><b>${esc(d.name)}</b></span>
      ${d.songs ? (d.waiting ? `<span class="lchip warn">${d.waiting} out of ${plural(d.songs, 'song')} to review</span>` : `${matched ? '<span class="lchip" style="color:var(--green-text)">✓ Matched</span>' : ''}<span class="sub" style="font-size:12px">${plural(d.songs, 'song')}</span>`) : ''}
      ${d.album ? `<button class="btn small ghost" onclick="event.stopPropagation();A.libMatchFolder(${arg(p)})" data-tip="Find this album on the music sites and match its songs. The folder name is the default search; you can change it.">Match album</button>` : ''}
      ${d.album && S.rvDrag ? '<span class="lchip">drop here</span>' : ''}</div>`;
    if (open) h += libTree(p, depth + 1);
    h += '</div>';
  }
  if (vis.length > lim) h += `<div class="librow" style="padding-left:${10 + depth * 4}px"><button class="btn small outline" onclick="A.libMore(${arg(path)})">Show ${Math.min(200, vis.length - lim)} more (${fmt(vis.length - lim)} left)</button></div>`;
  const fl0 = (K.files || []).filter(f => !(srch && !L.qFiles.has(path ? path + '/' + f.name : f.name))).map((f, i) => [f, i]).sort((x, y) => libDoneRank(x[0]) - libDoneRank(y[0]) || x[1] - y[1]).map(x => x[0]);
  const fidx = new Map((K.files || []).map((f, i) => [f, i + 1]));
  if (L.byReal && fl0.some(f => f.id && rvById(f.id))) {   // 2.0.1: songs of this folder grouped by the real album they belong to
    const gr = new Map();
    for (const f of fl0) { const x = f.id ? rvById(f.id) : null, r = x ? realAlbumOf(x) : 'Not in Review'; if (!gr.has(r)) gr.set(r, []); gr.get(r).push(f); }
    for (const [r, arr] of gr) h += `<div class="libreal"><b>${esc(r)}</b><span class="sub" style="font-size:12px">${plural(arr.length, 'song')}</span></div>` + arr.map((f, i) => libFileRow(f, depth, fidx.get(f) || i + 1)).join('');
  } else fl0.forEach((f, i) => { h += libFileRow(f, depth, fidx.get(f) || i + 1); });
  if (K.more_files) h += `<div class="sub" style="padding:6px 10px">${fmt(K.more_files)} more songs not shown here. Use Table with “Load all”.</div>`;
  if (!depth) libWantPics(names);
  return h;
}
function libCards() {
  const L = libState(), cwd = L.cwd || L.solo || '', K = L.kids[libKey(L.mode, cwd)];
  const base = L.solo ? L.solo.split('/') : [];
  const crumbs = ['Library'].concat(cwd ? cwd.split('/') : []).map((n, i, a) => `<button class="btn small ghost" onclick="A.libCwd(${arg(a.slice(1, i + 1).join('/'))})">${esc(n)}</button>`).join(' › ');
  if (!K) { libLoad(cwd).then(render); return `<div class="row" style="gap:6px;flex-wrap:wrap">${crumbs}</div><div class="sub"><span class="spin"></span></div>`; }
  const srch = L.mode === 'plan' && L.qDirs && L.qOn;
  const all = libDirsFor(cwd, K, srch), cl = (L.dlim && L.dlim[cwd]) || 120, dirs = all.slice(0, cl);
  const top = !cwd;
  if (top) libWantPics(dirs.map(d => d.name));
  return `<div class="row" style="gap:6px;flex-wrap:wrap;margin-bottom:8px">${crumbs}</div><div class="libcards ${top ? 'artists' : ''}">${dirs.map(d => {
    const p = cwd ? cwd + '/' + d.name : d.name;
    const drop = d.album ? `ondragover="if(S.rvDrag){event.preventDefault();this.classList.add('over')}" ondragleave="this.classList.remove('over')" ondrop="A.libDrop(event,${arg(d.rid || '')},${arg(p)})"` : '';
    return `<button class="libcard ${top ? 'artist' : ''} ${L.flash === p ? 'flash' : ''}" ${drop} onclick="A.libCwd(${arg(p)})" ondblclick="A.libSolo(${arg(p)})" title="${top ? 'Click to open · double-click to show only this artist' : ''}">${top ? libAvatar(d.name, 64) : `<span class="art big">${d.album ? '♪' : '▤'}</span>`}<b>${esc(d.name)}</b>
      <span class="sub" style="font-size:12px">${d.songs ? (d.waiting ? d.waiting + ' out of ' + plural(d.songs, 'song') + ' need review' : plural(d.songs, 'song')) : ''}</span></button>`; }).join('')}</div>${all.length > cl ? `<div style="margin-top:8px"><button class="btn small outline" onclick="A.libMore(${arg(cwd)})">Show ${Math.min(200, all.length - cl)} more (${fmt(all.length - cl)} left)</button></div>` : ''}
    ${(K.files || []).filter(f => !srch || L.qFiles.has(cwd ? cwd + '/' + f.name : f.name)).length ? `<div style="margin-top:8px">${K.files.filter(f => !srch || L.qFiles.has(cwd ? cwd + '/' + f.name : f.name)).map(f => libFileRow(f, 0)).join('')}</div>` : ''}${!dirs.length && !(K.files || []).length ? '<div class="sub">Nothing here.</div>' : ''}`;
}
function libTable() {
  const L = libState();
  if (L.mode === 'disk') return '<div class="sub" style="padding:8px">The table lists the planned library. Switch to “Planned” (or use the tree for what is on disk).</div>';
  if (!L.all) { if (!L.allLoading) { L.allLoading = true; call('lib_all').then(r => { L.all = r || { rows: [] }; L.allLoading = false; render(); }); } return '<div class="sub" style="padding:8px"><span class="spin"></span> Loading every planned song…</div>'; }
  const q = (L.q || '').toLowerCase().trim(), f = L.filt;
  let rows = L.all.rows || [];
  if (q) rows = rows.filter(r => (r.path + ' ' + r.title + ' ' + r.artist).toLowerCase().includes(q));
  if (f.low) rows = rows.filter(r => r.pct != null && r.pct !== '' && +r.pct < 90);
  if (f.tag) rows = rows.filter(r => r.state === 'waiting');
  if (f.dup) rows = rows.filter(r => r.state === 'extra');
  const so = L.sort;
  rows = rows.slice().sort((a, b) => so === 'pct' ? (+a.pct || 101) - (+b.pct || 101) : so === 'artist' ? (a.artist || '').localeCompare(b.artist || '') : a.path.localeCompare(b.path));
  const lim = L.lim || 300, shown = rows.slice(0, lim);
  return `<div class="row" style="gap:6px;margin-bottom:6px"><span class="sub" style="font-size:12px">Sort</span><span class="seg small">${[['path', 'Folder'], ['artist', 'Artist'], ['pct', 'Match %']].map(o => `<button aria-pressed="${so === o[0]}" onclick="S.lib.sort=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span>
    <span class="sub" style="font-size:12px">${fmt(rows.length)} songs${L.all.capped ? ' (first 30,000)' : ''}</span></div>
    ${shown.map(r => libFileRow({ name: r.path, state: r.state, id: r.id, pct: r.pct, dup: r.state === 'extra' }, 0)).join('')}
    ${rows.length > lim ? `<button class="btn small outline" onclick="S.lib.lim=${lim + 300};render()">Show 300 more</button>` : ''}`;
}
function libQueryIndex() {                       // search keeps the layout you are in: the tree/cards just show only what leads to a match
  const L = libState(), qs = (L.q || '').toLowerCase().trim();
  L.qOn = false;
  if (!qs || L.mode !== 'plan') return;
  if (!L.all) { if (!L.allLoading) { L.allLoading = true; call('lib_all').then(r => { L.all = r || { rows: [] }; L.allLoading = false; render(); }); } return; }
  if (L.qKey !== qs) {
    const dirs = new Set(), files = new Set();
    for (const r of L.all.rows || []) {
      if (!(r.path + ' ' + r.title + ' ' + r.artist).toLowerCase().includes(qs)) continue;
      const parts = r.path.split('/'); files.add(r.path);
      for (let i = 1; i < parts.length; i++) dirs.add(parts.slice(0, i).join('/'));
    }
    L.qKey = qs; L.qDirs = dirs; L.qFiles = files;
  }
  L.qOn = true;
}
function libInfoPanel(id) {
  const L = libState(), I = L.infoData && L.infoData.id === id ? L.infoData : null;
  if (!I) return '<div class="panel empty"><span class="spin"></span> Loading the song…</div>';
  if (I.error) return `<div class="panel empty">${esc(I.error)}</div>`;
  const rows = [['Artist', 'artist'], ['Title', 'title'], ['Album', 'album'], ['Year', 'year'], ['Track', 'track']].map(([n, k]) => { const o = I.old[k] || '', w = I.new[k] || '', ch = w && o !== w;
    return `<tr><td class="sub">${n}</td><td>${esc(o) || '–'}</td><td ${ch ? 'style="color:var(--amber-text)"' : ''}>${esc(w) || '–'}</td></tr>`; }).join('');
  return `<section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:10px"><div class="row" style="gap:10px"><button class="pv ${S.playing === id ? 'on' : ''}" aria-label="Play" onclick="A.play(${arg(id)})">${S.playing === id ? '❚❚' : '▶'}</button>
    <span class="grow" style="min-width:0"><b style="font-size:17px;overflow-wrap:anywhere">${esc(I.new.title || I.old.title || I.file)}</b><br><span class="sub" style="font-size:12px">${esc([I.new.artist || I.old.artist, I.new.album || I.old.album].filter(Boolean).join(' · '))}</span></span>
    ${rvById(id) ? `<button class="btn small outline" onclick="A.libToReview(${arg(id)})" title="Open this song in Review (Song view)">Open in Review</button>` : ''}<button class="btn small ghost" onclick="A.libInfoClose()">Close</button></div>
    <div class="sub mono" style="font-size:11px;overflow-wrap:anywhere">${esc(I.path || I.file)}</div>
    <table class="infotbl" style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr><th></th><th align="left">Your file</th><th align="left">New tags</th></tr></thead><tbody>${rows}</tbody></table>
    <span class="sub" style="font-size:12px">${esc([I.verified ? 'confirmed by a music site' : 'not confirmed', I.kbps ? I.kbps + ' kbps' : '', I.duration ? Math.floor(I.duration / 60) + ':' + String(I.duration % 60).padStart(2, '0') : '', I.new_name ? 'new name: ' + I.new_name : ''].filter(Boolean).join(' · '))}</span></section>`;
}
let LIBSIG = null, LIBBUSY = false;
function libSyncDecisions() {          // what you decide in Review changes the folder counts ("25 to review"): re-read the folders that are already loaded, keeping the old ones on screen meanwhile
  if (!S.rv || !S.lib) return;
  let n = 0, h = 0; for (const x of S.rv.items) { const a = x.decision && x.decision.action; if (a) { n++; h = (h * 31 + a.length + (x.id ? String(x.id).length : 0)) | 0; } }
  const sig = n + ':' + h;
  if (LIBSIG === null) { LIBSIG = sig; return; }
  if (sig === LIBSIG || LIBBUSY) return;
  clearTimeout(LIBT); LIBT = setTimeout(() => libSyncNow(sig), 1500);        // wait until you stop deciding, so clicks never queue behind a re-read
}
let LIBT = null;
function libSyncNow(sig) {
  if (LIBBUSY) return;
  LIBSIG = sig; LIBBUSY = true;
  const L = S.lib, keys = Object.keys(L.kids);
  Promise.all(keys.map(async k => { const i = k.indexOf('|'), mode = k.slice(0, i), path = k.slice(i + 1); try { const r = await call(mode === 'disk' ? 'lib_disk' : 'plan_tree', path); if (r && !r.error) L.kids[k] = r; } catch (e) {} }))
    .then(() => { LIBBUSY = false; render(); });
}
function libSelFolder(path) { const L = libState(); L.sel = { type: 'folder', path }; L.info = null; S.rvGroupSel = null; }
function libFolderInfo(path) {                           // the folder's own line (counts, album?) lives in its parent's list
  const L = libState(), parts = path.split('/'), name = parts.pop(), P = L.kids[libKey(L.mode, parts.join('/'))];
  return ((P && P.dirs) || []).find(d => d.name === name) || null;
}
function libFolderPreview(path) {                         // right side: a preview of the folder you clicked on the left
  const L = libState(), K = L.kids[libKey(L.mode, path)], d = libFolderInfo(path) || {}, name = path.split('/').pop();
  if (!K) { libLoad(path).then(render); return '<section class="panel empty"><span class="spin"></span> Loading the folder…</section>'; }
  if (K.error) return `<section class="panel empty">${esc(K.error)}</section>`;
  const files = K.files || [], dirs = K.dirs || [];
  const cnt = st => files.filter(f => f.state === st).length;
  const rdone = f => { const x = f.id ? rvById(f.id) : null; return !!(x && isDone(x)); };
  const need = files.filter(f => f.state === 'waiting' && !rdone(f)).length;
  const first = files.find(f => f.id && S.rv && S.rv.cover_base);
  const cov = first ? `<img class="art big" src="${esc(S.rv.cover_base + encodeURIComponent(first.id))}" alt="" data-ph="art big" onerror="A.imgFail(this)">` : `<span class="art big" style="display:flex;align-items:center;justify-content:center;font-size:30px">♪</span>`;
  const chips = [d.album ? '<span class="lchip">album</span>' : '<span class="lchip">folder</span>',
    `<span class="lchip">${plural(d.songs || files.length, 'song')}</span>`,
    need ? `<span class="lchip warn">${need} to review</span>` : (files.length ? '<span class="lchip" style="color:var(--green-text)">nothing to review</span>' : ''),
    d.low ? `<span class="lchip warn">${d.low} low match</span>` : '', d.dups ? `<span class="lchip dup">${d.dups} extra copies</span>` : '',
    d.nt && d.album && files.length < d.nt ? `<span class="lchip warn">${files.length} of ${d.nt} tracks</span>` : ''].join('');
  const rowS = f => { const x = f.id ? rvById(f.id) : null, dn = x && isDone(x), st = dn ? '✓ ' + badgeOf(x) : f.state === 'waiting' ? 'needs review' : (LIB_STATE[f.state] || f.state || '');
    const act = f.id ? `A.libInfo(${arg(f.id)})` : '';
    return `<button class="lprow" ${act ? `onclick="${act}"` : ''}><span class="tno">${files.indexOf(f) + 1}</span><span class="lname" title="${esc(f.name)}">${esc(f.name.replace(/\.[^.]+$/, ''))}</span><span class="sub" style="font-size:12px;color:${dn ? 'var(--green-text)' : f.state === 'waiting' ? 'var(--amber-text)' : ''}">${esc(st)}</span></button>`; };
  const rowD = e => `<button class="lprow" onclick="A.libPick(${arg(path ? path + '/' + e.name : e.name)})"><span class="lname"><b>${esc(e.name)}</b></span><span class="sub" style="font-size:12px;color:${e.waiting ? 'var(--amber-text)' : ''}">${e.waiting ? e.waiting + ' out of ' : ''}${plural(e.songs || 0, 'song')}${e.waiting ? ' to review' : ''}</span></button>`;
  const list = (dirs.length ? dirs.slice(0, 200).map(rowD).join('') : '') + (files.length ? files.slice().sort((a, b) => libDoneRank(a) - libDoneRank(b)).slice(0, 200).map(rowS).join('') : '');
  return `<section class="panel libprev" style="padding:16px;display:flex;flex-direction:column;gap:12px" aria-label="Preview of the selected folder">
    <div class="row" style="gap:14px;align-items:flex-start">${cov}<span class="grow" style="min-width:0"><span class="cap">SELECTED</span><br><b style="font-size:18px;overflow-wrap:anywhere">${esc(name)}</b><br><span class="sub mono" style="font-size:11px;overflow-wrap:anywhere">${esc(path)}</span><div class="row" style="gap:6px;flex-wrap:wrap;margin-top:8px">${chips}</div></span>
      <button class="btn small ghost" onclick="A.libSelClose()">Close</button></div>
    <div class="row" style="gap:8px;flex-wrap:wrap">${d.album ? `<button class="btn small" onclick="A.libMatchFolder(${arg(path)})" data-tip="Find this album on the music sites and match its songs.">Match album</button>` : ''}<button class="btn small outline" onclick="A.libSolo(${arg(path)})">Show only this folder</button></div>
    <div class="lplist">${list || '<span class="sub">Nothing in this folder.</span>'}</div>
    ${files.length > 200 || dirs.length > 200 ? '<span class="sub" style="font-size:12px">Only the first 200 are listed here.</span>' : ''}</section>`;
}
function libEmptyPreview() {
  return `<section class="panel empty" style="padding:28px;text-align:center"><b style="font-size:16px">Nothing selected</b><br><span class="sub">Click a folder or a song on the left to see it here.</span></section>`;
}
function libraryView(q0) {
  const L = libState();
  Object.assign(S.rvGroups, S.libGroups || {});         // the review list rebuilds S.rvGroups on every draw; keep the folders you asked to match
  const qs = (L.q || '').toLowerCase().trim();
  const q = qs ? q0.filter(x => ((x.tags.title || '') + ' ' + (x.tags.artist || '') + ' ' + (x.tags.album || '') + ' ' + x.file).toLowerCase().includes(qs)) : q0;
  if (L.sel === undefined) L.sel = null;      // V2.0.6: the right side only previews what you click on the left (no review panel here)
  const fx = null;
  if (!L.kids[libKey(L.mode, '')]) libLoad('').then(render);
  if (L.solo && !L.kids[libKey(L.mode, L.solo)]) libLoad(L.solo).then(render);
  libSyncDecisions();
  libQueryIndex();
  const seg = (items, cur, fn) => `<span class="seg small">${items.map(o => `<button aria-pressed="${cur === o[0]}" onclick="${fn}(${arg(o[0])})">${o[1]}</button>`).join('')}</span>`;
  const chips = [['low', 'Low match'], ['inc', 'Incomplete albums'], ['tag', 'Needs review'], ['dup', 'Duplicates']].map(o => `<button class="fchip" aria-pressed="${!!L.filt[o[0]]}" onclick="A.libFilt(${arg(o[0])})">${o[1]}</button>`).join('');
  const root = L.solo || '';
  const body = L.view === 'cards' ? libCards() : L.view === 'table' ? libTable()
    : `<div class="libtree">${L.solo ? (L.kids[libKey(L.mode, L.solo)] ? libTree(L.solo, 0) : '<div class="sub"><span class="spin"></span></div>') : libTree('', 0)}</div>`;
  const hits = '';
  const solo = L.solo ? `<div class="row libsolo" style="gap:8px;margin-bottom:8px"><b>Only: ${esc(L.solo.split('/').join(' / '))}</b><button class="btn small outline" onclick="A.libSolo('')">Show everything</button></div>` : '';
  return `<div class="libwrap" style="--libL:${S.libSplit || 48}%">
    <section class="panel libR${S.alLayout === 'classic' ? '' : ' lcl'}" aria-label="Library">
      <div class="row" style="gap:8px;flex-wrap:wrap;margin-bottom:8px">
        <input class="libq" id="libq" type="search" placeholder="Search both sides…" value="${esc(L.q || '')}" oninput="A.libQ(this.value)" title="Searches the library and the songs to review at the same time. Your layout (tree / cards / table) stays as it is.">
        ${seg([['plan', 'Planned'], ['disk', 'On disk']], L.mode, 'A.libMode')}${seg([['tree', 'Tree'], ['cards', 'Cards'], ['table', 'Table']], L.view, 'A.libView')}
        <button class="btn small outline" title="Load every planned song into the table" onclick="A.libAll()">Load all</button>
        <button class="btn small ${L.byReal ? '' : 'outline'}" aria-pressed="${!!L.byReal}" title="In every folder, group the songs by the real album they belong to" onclick="S.lib.byReal=!S.lib.byReal;render()">Group by real albums</button></div>
      ${L.mode === 'plan' ? `<div class="fchips" style="margin-bottom:8px">${chips}</div>` : ''}
      ${solo}${hits}${body}</section>
    <div class="libdiv" role="separator" aria-label="Drag to resize" onmousedown="A.libResize(event)"></div>
    <div class="libL">${fx ? `<div class="libdrag" draggable="true" title="Drag this song onto an album in the library" ondragstart="S.rvDrag=${arg(fx.id)};try{event.dataTransfer.setData('text/plain',${arg(fx.id)});event.dataTransfer.effectAllowed='move'}catch(e){}" ondragend="S.rvDrag=null">⠿ drag this song onto an album ←</div>` : ''}${S.rvGroupSel && /^LB\|/.test(S.rvGroupSel.key) && S.rvGroups[S.rvGroupSel.key] ? `<section class="panel" style="padding:12px;margin-bottom:10px"><div class="row" style="justify-content:space-between"><b>Match album: ${esc(S.rvGroups[S.rvGroupSel.key].album)}</b><button class="btn small ghost" onclick="A.rvGroupClose()">Close ✕</button></div>${groupPanel(S.rvGroups[S.rvGroupSel.key], true)}</section>` : ''}${L.info ? libInfoPanel(L.info) : L.sel && L.sel.type === 'folder' ? libFolderPreview(L.sel.path) : libEmptyPreview()}</div></div>`;
}
async function libDropMany(ids, url, folder) {
  toast('Matching ' + ids.length + ' ticked songs to ' + folder.split('/').pop() + '…');
  const rel = await call('review_link', url);
  if (!rel || rel.error || !(rel.tracks || []).length) return toast((rel && rel.error) || 'That album has no track list.', true);
  const nk = t => String(t || '').toLowerCase().replace(/\(.*?\)|\[.*?\]/g, ' ').replace(/[^a-z0-9\u0400-\u04ff\u0600-\u06ff]+/g, ' ').trim();
  let ok = 0, left = 0;
  for (const id of ids) {
    const x = rvById(id); if (!x || isDone(x)) continue;
    const a = nk((x.tags && x.tags.title) || stem(x.file));
    const t = rel.tracks.find(t => nk(t.title) === a) || rel.tracks.find(t => a && nk(t.title) && (nk(t.title).includes(a) || a.includes(nk(t.title))) && Math.min(a.length, nk(t.title).length) >= 4);
    if (!t) { left++; continue; }
    await rvDecide(id, { action: 'pick', match: t.match, label: candLabel({ release: rel.title, year: rel.year, track: t.track, source: rel.source }) }, true); ok++;
  }
  S.rvChecked = {}; S.lib.flash = folder; setTimeout(() => { if (S.lib) { S.lib.flash = ''; render(); } }, 2500);
  toast(ok + ' of ' + ids.length + ' songs placed on ' + folder.split('/').pop() + (left ? '; ' + left + ' did not match a track by title and stay in Review.' : '.'), !ok);
  render();
}
Object.assign(A, {
  async libInfo(id) { const L = libState(); L.sel = { type: 'song', id }; L.info = id; L.infoData = null; render(); const r = await call('song_info', id); L.infoData = r && !r.error ? r : { id, error: (r && r.error) || 'No answer.' }; if (L.infoData.id == null) L.infoData.id = id; render(); },
  async libMatchFolder(p) {
    const L = libState(); let K = L.kids[libKey(L.mode, p)]; if (!K) { await libLoad(p); K = L.kids[libKey(L.mode, p)]; }
    const ids = ((K && K.files) || []).map(f => f.id).filter(id => { const x = id && rvById(id); return x && !isDone(x); });
    if (!ids.length) return toast('Nothing in this folder is waiting for review.', true);
    const parts = p.split('/'), key = 'LB|' + p;
    S.libGroups = S.libGroups || {}; S.libGroups[key] = S.rvGroups[key] = { key, ids, album: parts[parts.length - 1], artist: libArtistName(parts[0]) };
    S.rvGS[key] = S.rvGS[key] || { q: [libArtistName(parts[0]), parts[parts.length - 1]] };
    const L2 = libState(); L2.sel = { type: 'folder', path: p }; L2.info = null;
    S.rvGroupSel = { key }; render(); if (!(S.rvGS[key] && S.rvGS[key].releases)) A.rvGroupSearch(key);
  },
  libInfoClose() { const L = libState(); L.info = null; L.sel = null; render(); },
  async libPick(p) { await A.libGo(p); libSelFolder(p); render(); },
  libMore(p) { const L = libState(); L.dlim = L.dlim || {}; L.dlim[p] = ((L.dlim[p]) || (p ? 150 : 100)) + 200; render(); },
  libToReview(id) { S.rvSel = id; S.rvGroupSel = null; S.rvView = 'quick'; store.set('rvView2', 'quick'); saveSpot(); render(); const x = rvById(id); if (x) rvOpened(x); },
  libSelClose() { const L = libState(); L.sel = null; render(); },
  libSolo(p) { const L = libState(); L.solo = p; L.cwd = p; if (p) L.open[libKey(L.mode, p)] = true; render(); },
  libOpenSong(id) { const L = libState(); L.sel = { type: 'song', id }; L.info = null; L.focusId = id; S.rvSel = id; S.rvGroupSel = null; saveSpot(); render(); const x = rvById(id); if (x) rvOpened(x); },
  libMode(m) { const L = libState(); L.mode = m; L.hits = []; render(); },
  libView(v) { const L = libState(); L.view = v; store.set('libView', v); render(); },
  libFilt(k) { const L = libState(); L.filt[k] = !L.filt[k]; render(); },
  libQ(v) { const L = libState(); L.q = v; clearTimeout(L._qt); L._qt = setTimeout(() => { const el = document.activeElement; render(); const n = document.querySelector('.libq'); if (n && el && el.classList && el.classList.contains('libq')) { n.focus(); n.setSelectionRange(v.length, v.length); } }, 250); },
  async libAll() { const L = libState(); L.view = 'table'; L.all = null; L.allLoading = false; render(); },
  async libToggle(p) { const L = libState(), k = libKey(L.mode, p); libSelFolder(p); L.open[k] = !L.open[k]; L.userOpen = L.userOpen || {}; L.userOpen[k] = L.open[k]; render(); if (L.open[k] && !L.kids[k]) { await libLoad(p); render(); } },      // the folder opens at once (a spinner row), its songs arrive after
  async libCwd(p) { const L = libState(); L.cwd = p; await libLoad(p); render(); },
  async libGo(folder) { const L = libState(); const parts = folder.split('/'); for (let i = 1; i <= parts.length; i++) { const p = parts.slice(0, i).join('/'); L.open[libKey(L.mode, p)] = true; await libLoad(parts.slice(0, i - 1).join('/')); await libLoad(p); } L.mode = 'plan'; L.flash = folder; L.cwd = parts.slice(0, -1).join('/'); render(); setTimeout(() => { const el = document.querySelector(`[data-lib="${CSS.escape(folder)}"]`); if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 60); setTimeout(() => { if (L.flash === folder) { L.flash = ''; render(); } }, 2500); },
  async libJump(x) {
    const L = libState(), s = x.suggest || {}, album = s.release || x.tags.album || x.g_album || '', artist = s.artist || x.tags.artist || x.g_artist || '';
    const r = await call('lib_find', artist, album, s.release_id || '');
    L.hits = (r && r.hits) || [];
    if (L.hits.length && L.mode === 'plan') { await A.libGo(L.hits[0].folder); } else render();
  },
  libResize(ev) {
    const w = document.querySelector('.libwrap'); if (!w) return; ev.preventDefault();
    const move = e => { const b = w.getBoundingClientRect(); S.libSplit = Math.max(25, Math.min(75, Math.round((e.clientX - b.left) / b.width * 100))); w.style.setProperty('--libL', S.libSplit + '%'); };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); store.set('libSplit', S.libSplit); };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  },
  libDrop(ev, rid, folder) {
    ev.preventDefault(); ev.stopPropagation(); ev.currentTarget && ev.currentTarget.classList.remove('over');
    let id = S.rvDrag; try { id = id || ev.dataTransfer.getData('text/plain'); } catch (e) {} S.rvDrag = null; if (!id) return;
    if (!rid) return toast('This album has no known release (it was placed with your own tags), so a song cannot be put on a track of it.', true);
    const url = /^[0-9a-f-]{36}$/.test(rid) ? 'https://musicbrainz.org/release/' + rid : /^deezer:/.test(rid) ? 'https://www.deezer.com/album/' + rid.slice(7) : /^discogs:/.test(rid) ? 'https://www.discogs.com/release/' + rid.slice(8) : '';
    if (!url) return toast('Open this album on its site and paste the link in the song panel.', true);
    const many = Object.keys(S.rvChecked || {}).filter(k => S.rvChecked[k]);
    if (many.length > 1 && many.includes(id)) return libDropMany(many, url, folder);       // 1.1.5: all ticked songs at once
    S.rvSel = id; const u = rvU(id); u.find = true; u.link = url; A.rvLink(id); toast('Pick the track of ' + folder.split('/').pop() + ' for this song.'); render();
  },
  async libBack(id) {
    await call('review_decide', id, { action: 'reject', kind0: 'match', label: 'sent back from the library' });
    toast('Sent back to Review (Not this). Find another match there.'); await loadReview(); render();
  },
});

// ---- 1.1.7: select songs in the library list (box, or press and drag over rows)
function libPaint() {
  document.querySelectorAll('.librow.file[data-id]').forEach(el => { const on = !!S.rvChecked[el.dataset.id]; el.classList.toggle('sel', on); const c = el.querySelector('.qck'); if (c) c.checked = on; });
}
Object.assign(A, {
  libTog(id, on) { if (on) S.rvChecked[id] = true; else delete S.rvChecked[id]; libPaint(); },
  libDown(ev, id) {
    if (ev.button !== 0 || ev.target.closest('button,input,a')) return;
    S.libDragOn = !S.rvChecked[id]; S.libDrag = true; S.libMoved = false; S.libStart = id;
  },
  libEnter(id) {
    if (!S.libDrag) return;
    if (!S.libMoved && id !== S.libStart) { S.libMoved = true; A.libTog(S.libStart, S.libDragOn); }
    if (S.libMoved) A.libTog(id, S.libDragOn);
  }
});
document.addEventListener('mouseup', () => { if (S.libDrag) { S.libDrag = false; setTimeout(() => { S.libMoved = false; }, 0); } });

Object.assign(A, {
  // 1.1.7: View (Songs / Albums / Artists) and Mode (Quick / Library / Check tags) are two switches
  rvViewPick(k) {
    if (k === 'artists') { if (S.rvGroupBy === 'artist') A.rvGroupBy(''); S.alSort = 'artists'; store.set('alSort', 'artists'); return A.rvViewSet('albums'); }      // V2.0.6: the new artist list
    if (k === 'songs') { if (S.rvGroupBy === 'artist') A.rvGroupBy(''); return A.rvViewSet('songs'); }
    if (k === 'albums' && S.alSort === 'artists') { S.alSort = 'todo'; store.set('alSort', 'todo'); }
    return A.rvViewSet(k);
  }
});

// ---- 1.1.7: album page: press on a box and drag down to select many songs; "Accept if…" for this album only
function alPaint() { document.querySelectorAll('.alrow[data-id]').forEach(el => { const on = !!S.alSel[el.dataset.id]; el.classList.toggle('sel', on); const c = el.querySelector('.qck'); if (c) c.checked = on; }); }
Object.assign(A, {
  alSelDown(ev, id) { if (ev.button !== 0) return; ev.preventDefault(); S.alDragOn = !S.alSel[id]; S.alDrag = true; S.alSel[id] = S.alDragOn; if (!S.alDragOn) delete S.alSel[id]; alPaint(); },
  alSelEnter(id) { if (!S.alDrag) return; if (S.alDragOn) S.alSel[id] = true; else delete S.alSel[id]; alPaint(); },
  alAcceptIf(key) {
    const c = albumCards('all').find(k => k.key === key); if (!c) return;
    const mine = new Set(c.items.map(x => x.id)), off = {};
    sureOnes().forEach(x => { if (!mine.has(x.id)) off[x.id] = true; });
    S.dlg = { kind: 'sure', off }; renderLayer();
  }
});
document.addEventListener('mouseup', () => { if (S.alDrag) { S.alDrag = false; render(); } });

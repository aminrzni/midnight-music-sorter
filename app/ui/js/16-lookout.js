/* Midnight 00:01 · Look out: one artist full screen (every album, every missing track, a PC search for all of them) */
'use strict';
function loArtist() {
  const D = S.an; if (!D || !S.lo || !S.lo.artist) return null;
  return D.artists.find(a => a.artist === S.lo.artist) || null;
}
function lookoutScreen() {
  const D = S.an;
  if (!D) { if (!S.anLoading) { S.anLoading = true; call('analyze_data', S.anBasis || 'new', S.anScope || 'all').then(r => { S.an = r || {}; S.anLoading = false; render(); anPics(); }); }
    return `<header class="bighead"><h1>Analyze</h1><p><span class="spin"></span> Loading…</p></header>`; }
  if (D.error) return `<header class="bighead"><h1>Analyze</h1><div class="row" style="gap:8px;flex-wrap:wrap">${anTopRow()}</div><p>${esc(D.error)}</p></header>`;
  S.lo = S.lo || {};
  const q = (S.lo.q || '').toLowerCase();
  const a = loArtist();
  const head = anHeadBar('Look out: pick an artist or an album to see every album full screen, which songs are missing, and to search this PC for all of them at once. Nothing is moved.') + anToolBox();
  const view = S.lo.view === 'album' ? 'album' : 'artist', lim = S.lo.n || 60;
  let tiles = '', total = 0;
  if (!a) {
    if (view === 'artist') {
      const hid = store.get('loLeft', []) || [], L = D.artists.filter(x => (!q || x.artist.toLowerCase().includes(q)) && (S.lo.showLeft || !hid.includes(x.artist))); total = L.length;
      tiles = L.slice(0, lim).map(x => { const pic = (S.anPics || {})[x.artist], col = TIER_COLOR[x.tier] || '#8C8880';
        return `<button class="lotile" onclick="A.loPick(${arg(x.artist)})"><span class="avatar" style="width:84px;height:84px;font-size:26px;box-shadow:0 0 0 3px ${col}">${pic ? `<img src="${esc(pic)}" alt="">` : esc(initials(x.artist))}</span><b>${esc(x.artist)}</b><span class="sub">${plural(x.songs, 'song')}</span></button>`; }).join('');
    } else {
      const L = []; D.artists.forEach(x => (x.albums || []).forEach(al => { if (!q || (al.album + ' ' + x.artist).toLowerCase().includes(q)) L.push([x, al]); })); total = L.length;
      tiles = L.slice(0, lim).map(([x, al]) => `<button class="lotile" onclick="A.loPick(${arg(x.artist)})">${anCover(D, Object.assign({ artist: x.artist }, al), 84)}<b>${esc(al.album)}</b><span class="sub">${esc(x.artist)}</span></button>`).join('');
    }
  }
  const picker = `<section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:10px">
    <div class="row" style="gap:8px;flex-wrap:wrap">${a ? `<button class="btn ghost" onclick="A.loBack()">← Back</button>` : ''}<input class="text grow" id="loq" placeholder="Find an artist or album" value="${esc(S.lo.q || '')}" oninput="S.lo.q=this.value;S.lo.n=60;render()">
      ${(store.get('loLeft', []) || []).length ? `<button class="btn small ghost" onclick="S.lo.showLeft=!S.lo.showLeft;render()">${S.lo.showLeft ? 'Hide' : 'Show'} left-out artists (${(store.get('loLeft', []) || []).length})</button>` : ''}<span class="seg small" role="group" aria-label="Look out view">${[['artist', 'Artist view'], ['album', 'Album view']].map(o => `<button aria-pressed="${view === o[0]}" onclick="S.lo.view=${arg(o[0])};S.lo.n=60;S.lo.artist='';render()">${o[1]}</button>`).join('')}</span></div>
    ${a ? '' : `<div class="lotiles">${tiles || '<span class="sub">Nothing found.</span>'}</div>${total > lim ? `<div class="row" style="justify-content:center"><button class="btn outline" onclick="S.lo.n=${lim + 60};render()">Load more (${total - lim} left)</button></div>` : ''}`}</section>`;
  if (!a) return head + picker;
  const als = anSortAlbums(a.albums).slice().sort((x, y) => ((y.tracks_total ? y.tracks_total - y.tracks_owned : 0) - (x.tracks_total ? x.tracks_total - x.tracks_owned : 0)));
  const totalMissing = als.reduce((n, al) => n + (al.tracks_total ? Math.max(0, al.tracks_total - al.tracks_owned) : 0), 0);
  const pic = (S.anPics || {})[a.artist];
  const col = TIER_COLOR[a.tier] || '#8C8880';
  const hero = `<section class="panel" style="padding:18px;display:flex;gap:18px;align-items:center;flex-wrap:wrap">
    <span class="avatar" style="width:96px;height:96px;font-size:30px;box-shadow:0 0 0 4px ${col}">${pic ? `<img src="${esc(pic)}" alt="">` : esc(initials(a.artist))}</span>
    <div class="grow" style="min-width:220px"><div style="font-size:28px;font-weight:800">${esc(a.artist)}</div>
      <div class="sub">${esc([a.tier && a.tier !== 'Unknown Discography' ? a.tier : '', plural(a.songs, 'song'), plural(a.releases, 'album'), a.complete_releases ? a.complete_releases + ' complete' : '', totalMissing ? plural(totalMissing, 'missing song') : ''].filter(Boolean).join(' · '))}</div></div>
    <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn amber" onclick="A.loSearchAll()" ${S.lo.busy ? 'disabled' : ''}>${S.lo.busy ? '<span class="spin"></span> Searching…' : 'Search this PC for every missing song'}</button>
      <button class="btn green" onclick="A.loAddAll()">Add all found songs</button>
      <button class="btn outline" onclick="A.anFindArtist(${arg(a.artist)})">Find this artist's folders</button>
      <button class="btn ghost" onclick="A.loLeaveArtist(${arg(a.artist)})" data-tip="Hide this artist from Look out. Nothing is changed on your PC. Bring them back with 'Show left-out artists'.">${(store.get('loLeft', []) || []).includes(a.artist) ? 'Bring this artist back' : 'Leave this artist out'}</button>
      <button class="btn ghost" onclick="A.loMinAll(${arg(a.artist)},true)">Minimize all</button><button class="btn ghost" onclick="A.loMinAll(${arg(a.artist)},false)">Open all</button></div></section>${anArtistFound(a.artist)}`;
  const cards = als.map(al => {
    const ak = a.artist + '|' + (al.release_id || al.album), miss = al.tracks_total ? Math.max(0, al.tracks_total - al.tracks_owned) : 0;
    const mn = (S.lo.min || {})[ak];
    return `<div class="analbum open" style="cursor:pointer" onclick="if(!event.target.closest('button,a,input'))A.loMin(${arg(ak)})" title="Click to minimize or open this album">${anCover(D, Object.assign({ artist: a.artist }, al), 56)}
      <div class="grow" style="min-width:0;display:flex;flex-direction:column;gap:3px"><b style="overflow-wrap:anywhere">${esc(al.album)}</b>
        <span class="sub" style="font-size:12px">${esc([al.year, RTYPE[al.type] || al.type, al.tracks_total ? al.tracks_owned + ' of ' + al.tracks_total + ' songs' : al.tracks_owned + ' songs'].filter(Boolean).join(' · '))}</span>
        <span class="bar"><i style="width:${al.percent || 0}%;background:${al.complete ? 'var(--green)' : 'var(--amber)'}"></i></span></div>
      ${miss ? `<span class="chip" style="color:var(--amber-text)">${plural(miss, 'missing song')}</span>` : '<span class="chip" style="color:var(--green-text)">complete</span>'}</div>
      ${!mn && miss && al.release_id ? ((S.anTr || {})[ak] ? anTracks(a, al, ak) : '<div class="antracks"><span class="sub"><span class="spin"></span> Loading the track list…</span></div>') : ''}`;
  }).join('');
  return head + picker + hero + `<section class="panel lookout" style="padding:14px;display:flex;flex-direction:column;gap:10px"><h2 style="margin:0;font-size:17px">Albums · most missing first</h2>${cards || '<span class="sub">No albums known.</span>'}</section>${loBar()}`;
}
Object.assign(A, {
  loMin(k) { S.lo.min = S.lo.min || {}; S.lo.min[k] = !S.lo.min[k]; render(); },
  loMinAll(artist, on) { const a = loArtist(); S.lo.min = S.lo.min || {}; ((a && a.albums) || []).forEach(al => { S.lo.min[artist + '|' + (al.release_id || al.album)] = on; }); render(); },
  loLeaveArtist(artist) { const h = store.get('loLeft', []) || []; store.set('loLeft', h.includes(artist) ? h.filter(x => x !== artist) : h.concat(artist)); toast(h.includes(artist) ? 'Artist is back in Look out.' : 'Artist left out of Look out (nothing changed on your PC).'); render(); },
  loBack() { const f = S.lo && S.lo.from; if (f === 'suggest') { S.anView = 'suggest'; S.lo.artist = ''; S.lo.from = ''; render(); } else { S.lo.artist = ''; render(); } },
  async loPick(artist, from) {
    const keep = S.lo || {}; S.lo = { artist, q: '', view: keep.view, from: from || keep.from || '' }; render(); S.anTr = S.anTr || {};
    const a = loArtist(); if (!a) return;
    for (const al of a.albums) { const ak = a.artist + '|' + (al.release_id || al.album);
      if (al.release_id && al.tracks_total && al.tracks_owned < al.tracks_total && !S.anTr[ak]) { const r = await call('album_tracks', al.release_id); S.anTr[ak] = r && r.tracks ? r : { tracks: [], error: (r && r.error) || 'no answer' }; render(); } }
  },
  async loSearchAll() {
    const a = loArtist(); if (!a) return; S.lo.busy = true; S.anFind = S.anFind || {}; render();
    for (const al of a.albums) { const ak = a.artist + '|' + (al.release_id || al.album), T = (S.anTr || {})[ak]; if (!T) continue;
      for (const t of T.tracks.filter(t => !t.have)) { const k = pcKey({ release_id: al.release_id }, t); S.anFind[k] = { loading: true }; call('pc_find_start', k, a.artist, t.title || t.label); } }
    S.lo.busy = false; render(); pcPoll();
  },
  anViewSet(v) { S.anView = v === 'lookout' ? 'lookout' : v === 'suggest' ? 'suggest' : 'analyze'; if (v === 'lookout' && S.lo && S.lo.artist) A.loPick(S.lo.artist); else render(); },
  anScopeSet(v) { S.anScope = v === 'sources' ? 'sources' : 'all'; S.an = null; S.anTr = {}; S.anAlbums = {}; render(); },
  anFoundMin(n) { S.anFoundMin = S.anFoundMin || {}; S.anFoundMin[n] = !S.anFoundMin[n]; render(); },
  anFoundClose(n) { S.anFoundClosed = S.anFoundClosed || {}; S.anFoundClosed[n] = true; render(); },
  async anFindArtist(name) { S.anFoundClosed = S.anFoundClosed || {}; S.anFoundClosed[name] = false; S.anFind = S.anFind || {}; S.anFind['artist|' + name] = { loading: true }; render(); await call('pc_find_artist', 'artist|' + name, name); pcPoll(); },
  lookOut(artist, from) { const f = from || (S.anView === 'suggest' ? 'suggest' : ''); S.anView = 'lookout'; if (S.screen !== 'analyze') S.screen = 'analyze'; A.loPick(artist, f); },
  // single songs become sources (only those songs are scanned); scanning uses your default settings
  async anSongs(paths, scan) {
    const r = await call('add_source_files', paths); if (r && r.error) return toast(r.error, true);
    const n = (r && r.added || []).length, al = (r && r.already || []).length;
    if (r && r.problems && r.problems.length) toast(r.problems.join(' · '), true);
    else toast((n ? 'Added ' + plural(n, 'song') + ' to Sources.' : '') + (al ? (n ? ' ' : '') + plural(al, 'song') + (al === 1 ? ' was' : ' were') + ' already in your Sources (nothing to do).' : '') || 'Nothing to add.');
    S.loSel = {}; await poll(true); if (scan) A.scanAsk(); else render(); },
  // 1.1.7: add ONLY the artist's songs (never the whole folder); afterwards the list refreshes and a "Scan now" button shows
  async anArtistAdd(name, idx, scan) {
    const f = (S.anFind || {})['artist|' + name]; if (!f || !f.folders) return;
    const paths = idx == null ? f.folders.reduce((a, x) => a.concat(x.files || []), []) : (f.folders[idx] && f.folders[idx].files) || [];
    if (!paths.length) return toast('Nothing to add.', true);
    const r = await call('add_source_files', paths); if (r && r.error) return toast(r.error, true);
    const n = (r && r.added || []).length;
    S.anAddedSongs = S.anAddedSongs || {}; S.anAddedSongs[name] = (S.anAddedSongs[name] || 0) + n;
    if (r && r.problems && r.problems.length) toast(r.problems.join(' · '), true); else toast(n ? 'Added ' + plural(n, 'song') + ' to Sources.' : 'Those songs are already in your Sources.');
    await poll(true); if (scan) return A.scanAsk();
    S.anFind['artist|' + name] = { loading: true }; render(); await call('pc_find_artist', 'artist|' + name, name); pcPoll(); },
  async anAddScan(path) { return A.anSongs([path], false); },
  async anScanNow(path) { return A.anSongs([path], true); },
  async anSourcesAll(ak, scan) {
    const T = (S.anTr || {})[ak]; if (!T) return; const [artist] = ak.split('|'), rid = ak.split('|').slice(1).join('|');
    const al = (S.an.artists.find(a => a.artist === artist) || { albums: [] }).albums.find(x => (x.release_id || x.album) === rid) || {};
    const paths = []; T.tracks.filter(t => !t.have).forEach(t => { const f = (S.anFind || {})[pcKey({ release_id: al.release_id || rid }, t)]; (f && f.hits || []).forEach(h => { if (!paths.includes(h.path)) paths.push(h.path); }); });
    if (!paths.length) return toast('Nothing found yet: search the PC first.', true);
    return A.anSongs(paths, scan); },
  // drag to select found songs
  loToggle(p, on) { S.loSel = S.loSel || {}; if (on) S.loSel[p] = true; else delete S.loSel[p]; loPaint(); },
  loDown(ev, p) { if (ev.target.closest('button,input,a')) return; S.loSel = S.loSel || {}; S.loDragOn = !S.loSel[p]; S.loDrag = true; A.loToggle(p, S.loDragOn); ev.preventDefault(); },
  loEnter(ev, p) { if (S.loDrag && (ev.buttons & 1)) A.loToggle(p, S.loDragOn); },
  loClear() { S.loSel = {}; loPaint(); },
  async loAddAll() { const a = loArtist(); if (!a) return; for (const al of a.albums) { const ak = a.artist + '|' + (al.release_id || al.album); if ((S.anTr || {})[ak]) await A.anAddAllFound(ak); } },
});
SCREENS.lookout = () => { S.anView = 'lookout'; return analyzeScreen(); };
PAGE_SHORT.lookout = 'Look out';

function loBar() {
  const n = Object.keys(S.loSel || {}).length;
  return `<div class="nbar ${n ? 'on' : ''}" id="lobar">${n ? `<b>${plural(n, 'song')} selected</b><button class="btn small outline" onclick="A.anSongs(Object.keys(S.loSel),false)">Add to sources</button>
    <button class="btn small amber" onclick="A.anSongs(Object.keys(S.loSel),true)">Add &amp; scan</button><button class="btn small ghost" onclick="A.loClear()">Clear</button>` : ''}</div>`;
}
function loPaint() {                  // selection changes without redrawing the whole page
  document.querySelectorAll('.lohit[data-lp]').forEach(e => { const on = !!(S.loSel || {})[e.dataset.lp]; e.classList.toggle('sel', on); const c = e.querySelector('input.qck'); if (c) c.checked = on; });
  const b = document.getElementById('lobar'); if (b) b.outerHTML = loBar();
}
document.addEventListener('mouseup', () => { S.loDrag = false; });

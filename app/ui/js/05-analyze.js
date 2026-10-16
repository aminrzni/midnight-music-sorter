/* Midnight 00:01 · Analyze screen (part of the screens, loaded in order by index.html) */
'use strict';
const initials = n => String(n || '?').replace(/^the\s+/i, '').split(/[\s\-&,]+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
function anCover(D, al, size) {
  const sz = size || 44;
  const grad = `linear-gradient(135deg, hsl(${(al.album || '').length * 37 % 360} 40% 35%), hsl(${(al.artist || '').length * 53 % 360} 45% 22%))`;
  return `<span class="ancover" style="width:${sz}px;height:${sz}px;background:${grad}">${al.release_id && al.confirmed !== false && /^[0-9a-f-]{36}$/.test(al.release_id) && S.info && S.info.services && (S.info.services.covers || S.info.services.mb) ? `<img src="https://coverartarchive.org/release/${esc(al.release_id)}/front-250" alt="" loading="lazy" onerror="${al.fid && D.covers ? `this.onerror=function(){this.remove()};this.src='${esc(D.covers + encodeURIComponent(al.fid))}'` : 'this.remove()'}">` : al.fid && D.covers ? `<img src="${esc(D.covers + encodeURIComponent(al.fid))}" alt="" loading="lazy" onerror="this.remove()">` : `<span>${esc(initials(al.album))}</span>`}${al.complete ? '<b class="okdot" title="complete">✓</b>' : ''}</span>`;
}
function anTopRow() {                 // kept for the error screens: the old one-line layout
  return anSearchReport();
}
function anSearchReport() {
  return `<input class="text" id="antopq" type="search" style="min-width:200px;max-width:260px" placeholder="Find an artist or album…" title="Search your artists and albums from any Analyze view" value="${esc(S.anQ || '')}" oninput="S.anQ=this.value;S.anMore=60;if(S.anView!=='analyze'){S.anView='analyze';S.screen='analyze'}A.anSongQ();render()">
    <button class="btn outline small" onclick="A.anReport('')">Report…</button>`;
}
// 1.1.7: header = title + info on the left, Search + Report on the right
function anHeadBar(long) {
  return `<header class="pagehead"><h1>Analyze</h1><span class="infoi" tabindex="0" role="button" aria-label="About this page"><b>!</b><span class="itip" role="tooltip">${esc(long)}</span></span><span class="pdesc">${esc(PAGE_SHORT.analyze)}</span><span class="pextra">${anSearchReport()}</span></header>`;
}
// 1.1.7: one box: Analyze / Look out / Suggestions (with icons) on the left, the two scope switches on the right
function anToolBox() {
  const ic = d => `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="${d}"/></svg>`;
  const views = [['analyze', 'Analyze', 'M4 20V10M10 20V4M16 20v-7M22 20H2', ''], ['lookout', 'Look out', 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4', 'One artist full screen: find the missing songs on this PC'],
    ['suggest', 'Suggestions', 'M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z', 'What to look for next: almost complete albums, missing songs, better versions, similar artists, hidden gems']];
  const cur = S.anView === 'lookout' ? 'lookout' : S.anView === 'suggest' ? 'suggest' : 'analyze';
  const sw = (aria, items, c, fn) => `<span class="seg small" role="group" aria-label="${aria}">${items.map(o => `<button aria-pressed="${c === o[0]}" onclick="${fn}(${arg(o[0])})" ${o[2] ? `title="${esc(o[2])}"` : ''}>${o[1]}</button>`).join('')}</span>`;
  return `<section class="panel" style="padding:10px 14px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between">
    <span class="seg small" role="group" aria-label="View">${views.map(o => `<button aria-pressed="${cur === o[0]}" onclick="A.anViewSet(${arg(o[0])})" ${o[3] ? `title="${esc(o[3])}"` : ''} style="display:inline-flex;align-items:center;gap:6px">${ic(o[2])}${o[1]}</button>`).join('')}</span>
    <span class="row" style="gap:8px;flex-wrap:wrap">${sw('Analyze based on', [['new', 'New tags (matched)'], ['old', 'Old tags (your files now)']], S.anBasis === 'old' ? 'old' : 'new', 'A.anBasis')}
    ${sw('Which songs', [['all', 'Whole library'], ['sources', 'Only songs in my sources', 'Only the songs and folders you added in Sources']], S.anScope === 'sources' ? 'sources' : 'all', 'A.anScopeSet')}</span></section>`;
}
function analyzeScreen() {
  const D = S.an;
  if (!D) { if (!S.anLoading) { S.anLoading = true; call('analyze_data', S.anBasis || 'new', S.anScope || 'all').then(r => { S.an = r || {}; S.anLoading = false; render(); anPics(); }); }
    return `<header class="bighead"><h1>Analyze</h1><p><span class="spin"></span> Loading…</p></header>`; }
  if (D.error) return `<header class="bighead"><h1>Analyze</h1><p>${esc(D.error)}</p></header>`;

  if (S.anView === 'lookout') return lookoutScreen();
  if (S.anView === 'suggest') return suggestScreen();
  const sm = D.summary || {}, tierKnown = sm.tiers_known !== false && D.tiers.some(t => t.short !== 'Unknown Discography' && t.count);
  const q = (S.anQ || '').toLowerCase(), tier = S.anTier || '', sort = S.anSort || 'complete';
  let arts = D.artists.filter(a => (!tier || a.tier === tier) && (!q || a.artist.toLowerCase().includes(q) || a.albums.some(x => x.album.toLowerCase().includes(q)) || ((S.anSongHits || {})[a.artist] && S.anSongHitQ === q.trim())));
  arts.sort((a, b) => sort === 'songs' ? b.songs - a.songs : sort === 'az' ? a.artist.localeCompare(b.artist)
    : ((b.percent || 0) - (a.percent || 0)) || (b.complete_releases - a.complete_releases) || (b.songs - a.songs));
  const shown = arts.slice(0, S.anMore || 60);
  const tiles = [['users', fmt(sm.artists), 'artists'], ['note', fmt(sm.songs || 0), 'different songs'], ['disc', fmt(sm.releases), 'albums'],
    ['check', fmt(sm.complete_releases), 'complete albums'], ['half', fmt(sm.almost_complete), 'almost complete'], ['pct', (sm.average_release_percent || 0) + '%', 'avg. complete']];
  const tierBar = tierKnown ? `<section class="panel" style="padding:16px 20px;display:flex;flex-direction:column;gap:8px"><div class="row" style="justify-content:space-between"><h2 style="margin:0;font-size:17px">Collection tiers</h2><span class="sub" style="font-size:12px">complete studio albums per artist · click to filter</span></div>
      ${D.tiers.map(t => `<button class="tierrow ${tier === t.short ? 'on' : ''}" onclick="A.anTierSet(${arg(t.short)})"><span style="font-size:13px">${esc(t.name)}</span><span class="tbar"><i style="width:${Math.round(t.count / Math.max(1, ...D.tiers.map(x => x.count)) * 100)}%;background:${TIER_COLOR[t.short] || '#8C8880'}"></i></span><span class="mono" style="font-size:13px;text-align:right">${fmt(t.count)}</span></button>`).join('')}</section>`
    : `<div class="note"><span>Collection tiers need the discography check of a <b>Complete</b> scan. Everything else below works with any scan.</span></div>`;
  const rows = shown.map(a => {
    const open = S.anOpen === a.artist, col = TIER_COLOR[a.tier] || '#8C8880', pic = (S.anPics || {})[a.artist];
    const stack = a.albums.slice().sort((x, y) => (y.complete ? 1 : 0) - (x.complete ? 1 : 0) || (y.tracks_owned - x.tracks_owned)).slice(0, 4);
    return `<div class="anrow ${open ? 'open' : ''}"><button class="anhead" onclick="A.anOpen(${arg(a.artist)})" aria-expanded="${open}">
        <span class="avatar" style="box-shadow:0 0 0 3px ${col}">${pic ? `<img src="${esc(pic)}" alt="">` : esc(initials(a.artist))}</span>
        <span class="anname"><b>${esc(a.artist)}</b><span>${esc([a.tier && a.tier !== 'Unknown Discography' ? a.tier : '', a.studio_total ? a.studio_complete + ' of ' + a.studio_total + ' studio albums complete (' + a.percent + '%)' : '', plural(a.songs, 'song'), plural(a.releases, 'album'), a.complete_releases ? a.complete_releases + ' complete' : '', (S.anSongHits || {})[a.artist] && S.anSongHitQ === q.trim() ? 'has: ' + S.anSongHits[a.artist].join(' / ') : ''].filter(Boolean).join(' · '))}</span></span>
        <span class="stack">${stack.map(al => anCover(D, Object.assign({ artist: a.artist }, al), 38)).join('')}${a.albums.length > 4 ? `<span class="more">+${a.albums.length - 4}</span>` : ''}</span></button>
      ${open ? `<div class="analbums"><div class="row" style="gap:6px;flex-wrap:wrap"><span class="sub" style="font-size:12px">Sort albums</span><span class="seg small">${AN_AL_SORTS.map(o => `<button aria-pressed="${(S.anAlSort || 'year') === o[0]}" onclick="S.anAlSort=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span>
          <button class="btn small outline" onclick="A.anFindArtist(${arg(a.artist)})" data-tip="Looks for folders and songs of this artist anywhere on this PC (names only; nothing is moved).">Find this artist's music on this PC</button>
          <button class="btn small amber" onclick="A.lookOut(${arg(a.artist)})" data-tip="Opens this artist full screen: every album, every missing track, and a search of the PC for all of them.">Look out</button></div>
        <div class="row" style="gap:6px"><button class="btn small outline" onclick="A.anSongsToggle(${arg(a.artist)})" aria-expanded="${!!(S.anSongsOpen || {})[a.artist]}" data-tip="Every song you have by this artist, album by album. Click ▶ to listen.">${(S.anSongsOpen || {})[a.artist] ? '▾ Hide songs' : '▸ Songs (' + a.songs + ')'}</button></div>
        ${(S.anSongsOpen || {})[a.artist] ? anArtistSongs(a.artist) : ''}
        ${anArtistFound(a.artist)}
        <span class="sub" style="font-size:12px" data-tip="The same album can exist as several releases (original, remaster, deluxe, another country). Your songs are filed under the release their tags point to. If one release is complete and others show only 1–2 songs, those few songs carry the tags of the other edition: nothing is missing, and the complete one is the album you own. Review can move them if you want them together.">Several albums with the same name? ⓘ</span>
        ${anTwinBar(a)}
        ${anSortAlbums(anVisibleAlbums(a)).map(al => { const ak = a.artist + '|' + (al.release_id || al.album), ao = !!(S.anAlbums || {})[ak];
          const nk = x => String(x.album).toLowerCase().replace(/\(.*?\)|\[.*?\]|deluxe|remaster(ed)?|edition|\d{4}|[^a-z0-9]+/g, ''), twin = a.albums.some(o => o !== al && nk(o) === nk(al) && (o.complete || o.tracks_owned > al.tracks_owned)) && !al.complete && al.tracks_owned <= 2;
          return `<div class="analbum ${ao ? 'open' : ''}">${anCover(D, Object.assign({ artist: a.artist }, al), 48)}
        <button class="grow anal" style="min-width:0;display:flex;flex-direction:column;gap:3px" onclick="A.anAlbumOpen(${arg(ak)},${arg(al.release_id || '')},event)" aria-expanded="${ao}"><b style="overflow-wrap:anywhere">${ao ? '▾' : '▸'} ${esc(al.album)}</b><span class="sub" style="font-size:12px">${esc([al.year, RTYPE[al.type] || al.type].filter(Boolean).join(' · '))}${twin ? ' · <b style="color:var(--amber-text)" title="Another edition of this album is the one you own; these few songs carry this edition\'s tags">partial edition: you own the full album as another release</b>' : ''}</span>
          <span class="bar"><i style="width:${al.percent || 0}%;background:${al.complete ? 'var(--green)' : 'var(--amber)'}"></i></span>
          <span class="sub" style="font-size:12px">${al.tracks_total ? al.tracks_owned + ' of ' + al.tracks_total + ' songs' : al.tracks_owned + ' songs'}${al.missing && !ao ? ' · missing: ' + esc(al.missing) : ''}</span></button></div>
          ${ao ? anTracks(a, al, ak) : ''}`; }).join('') || '<span class="sub">No albums known.</span>'}</div>` : ''}</div>`;
  }).join('');
  const almost = (D.almost || []).map((x, i) => {
    const tracks = x.tracks && x.tracks.length ? x.tracks : /^\d+ songs?$/.test(x.missing || '') ? [] : String(x.missing || '').split(', ').filter(Boolean).map(l => ({ label: l, title: l.replace(/^[\d-]+\s+/, '') }));
    return `<div class="almostcard"><div class="row" style="gap:12px">${anCover(D, Object.assign({}, x, (D.artists.find(a => a.artist === x.artist) || { albums: [] }).albums.find(al => al.album === x.album) || {}), 52)}
      <div class="grow" style="min-width:0"><b style="overflow-wrap:anywhere">${esc(x.album)}</b><div class="sub" style="font-size:12px">${esc(x.artist)} · ${x.have} of ${x.total}</div><div class="bar" style="margin-top:4px"><i style="width:${Math.round(x.have / x.total * 100)}%;background:var(--amber)"></i></div></div></div>
      ${!tracks.length ? `<span class="sub" style="font-size:12px">${x.total - x.have} missing · the names come from MusicBrainz in a Complete scan</span>` : ''}
      <div class="row" style="gap:6px"><button class="btn small outline" onclick="A.anAlmostPlay(${i})">${S.anAlmostOpen === i ? 'Hide the songs you have' : '▶ Songs you have'}</button></div>
      ${S.anAlmostOpen === i ? anAlmostSongs(x) : ''}
      <div class="row" style="gap:6px;flex-wrap:wrap">${tracks.map((t, ti) => `<button class="fchip ${S.anHelp === i + ':' + ti ? 'on' : ''}" aria-pressed="${S.anHelp === i + ':' + ti}" onclick="A.anHelp(${i},${ti})">${esc(t.label || t.title)}${t.src ? ' <span style="color:var(--green-text)">●</span>' : ''}</button>`).join('')}</div>
      ${S.anHelp && S.anHelp.split(':')[0] == i ? anHelper(x, tracks[+S.anHelp.split(':')[1]]) : ''}</div>`;
  }).join('');
  return `${anHeadBar(`How much of each artist and album you own: complete albums, tiers, and the songs missing from almost complete albums (with help to find them). Made ${esc(D.made || '')}. Read only.`)}
    <section class="tiles">${tiles.map(t => `<div class="tile"><span class="ticon">${{ users: svg('M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 3.6-7 8-7s8 3 8 7', 22), note: svg('M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z', 22), disc: svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 22), check: svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', 22), half: svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 3v18', 22), pct: svg('M19 5L5 19M7 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', 22) }[t[0]]}</span><div><div class="v">${t[1]}</div><div class="k">${t[2]}</div></div></div>`).join('')}</section>
    ${tierBar}
    ${anToolBox()}
    <div class="grid2" style="align-items:start">
    <section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:10px">
      <div class="row" style="gap:8px;justify-content:space-between"><h2 style="margin:0;font-size:17px">Artists${tier ? ' · ' + esc(tier) + ' <button class="btn small ghost" onclick="A.anTierSet(\'\')">show all</button>' : ''}</h2>
        <span class="seg small">${[['complete', 'Most complete'], ['songs', 'Most songs'], ['az', 'A–Z']].map(o => `<button aria-pressed="${sort === o[0]}" onclick="S.anSort=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span></div>
      <input class="text" id="anq" placeholder="Find an artist or album" value="${esc(S.anQ || '')}" oninput="S.anQ=this.value;S.anMore=60;A.anSongQ();render()">
      <div class="anlist">${rows || '<span class="sub">Nothing found.</span>'}</div>
      ${arts.length > shown.length ? `<button class="btn outline" onclick="S.anMore=(S.anMore||60)+100;render();anPics()">Show more (${fmt(arts.length - shown.length)} left)</button>` : ''}
    </section>
    <section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:10px"><h2 style="margin:0;font-size:17px">Almost complete</h2>
      <span class="sub" style="font-size:12px">Albums missing 1 or 2 songs. Click a missing song for help. <span style="color:var(--green-text)">●</span> = you already have it on another album.</span>
      ${almost || '<span class="sub">None right now.</span>'}</section></div>${loBar()}`;
}
// 1.1.7: an album with 1-2 songs whose twin (same name, another edition) is the complete one you own is hidden by default
const anNk = x => String(x.album).toLowerCase().replace(/\(.*?\)|\[.*?\]|deluxe|remaster(ed)?|edition|\d{4}|[^a-z0-9]+/g, '');
const anIsTwin = (a, al) => !al.complete && al.tracks_owned <= 2 && a.albums.some(o => o !== al && anNk(o) === anNk(al) && (o.complete || o.tracks_owned > al.tracks_owned));
function anVisibleAlbums(a) { return (S.anShowTwins || {})[a.artist] ? a.albums : a.albums.filter(al => !anIsTwin(a, al)); }
function anTwinBar(a) {
  const n = a.albums.filter(al => anIsTwin(a, al)).length; if (!n) return '';
  const on = (S.anShowTwins || {})[a.artist];
  return `<div class="row" style="gap:8px"><span class="sub" style="font-size:12px">${on ? 'Showing' : 'Hiding'} ${plural(n, 'duplicate album')} (the same album as another edition, with only 1-2 songs: the full one is listed).</span><button class="btn small ghost" onclick="S.anShowTwins=S.anShowTwins||{};S.anShowTwins[${arg(a.artist)}]=${!on};render()">${on ? 'Hide them' : 'Show them'}</button></div>`;
}
const AN_AL_SORTS = [['year', 'Year ↑'], ['year_desc', 'Year ↓'], ['pct', '% complete'], ['missing', 'Missing songs'], ['name', 'Name'], ['owned', 'Songs owned']];
function anSortAlbums(list) {
  const so = S.anAlSort || 'year', y = x => String(x.year || '9999'), miss = x => x.tracks_total ? x.tracks_total - x.tracks_owned : 999;
  return list.slice().sort((a, b) => so === 'year' ? y(a).localeCompare(y(b)) : so === 'year_desc' ? y(b).localeCompare(y(a))
    : so === 'pct' ? (+b.percent || 0) - (+a.percent || 0) : so === 'missing' ? (miss(a) || 999) - (miss(b) || 999) || miss(a) - miss(b)
    : so === 'owned' ? b.tracks_owned - a.tracks_owned : a.album.localeCompare(b.album));
}
function anTracks(a, al, ak) {
  const T = (S.anTr || {})[ak];
  if (!T) return '<div class="antracks"><span class="sub"><span class="spin"></span> Loading the track list…</span></div>';
  if (!T.tracks.length) return `<div class="antracks"><span class="sub">${esc(T.error || 'No track list known for this album.')}</span></div>`;
  const x = { artist: a.artist, album: al.album, release_id: al.release_id };
  const missing = T.tracks.map((t, ti) => [t, ti]).filter(x => !x[0].have), many = missing.length > 1;
  const pcAll = missing.length ? `<div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small amber" onclick="A.anFindAlbum(${arg(ak)})">Find all ${missing.length} missing tracks on this PC</button><span class="sub" style="font-size:12px">Looks for each missing song by name; nothing is moved.</span></div>
      ${missing.some(([t]) => ((S.anFind || {})[pcKey(x, t)] || {}).hits && ((S.anFind || {})[pcKey(x, t)] || {}).hits.length) ? `<div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small green" onclick="A.anAddAllFound(${arg(ak)})">Add all found songs to this album</button><button class="btn small outline" onclick="A.anSourcesAll(${arg(ak)},false)">Add all to sources</button><button class="btn small outline" onclick="A.anSourcesAll(${arg(ak)},true)">Add all &amp; scan</button><span class="sub" style="font-size:12px">Uses the best match for each missing track (same length first). Extra copies are made in the next Copy &amp; tag.</span></div>` : ''}` : '';
  return `<div class="antracks"><span class="sub" style="font-size:12px">${T.tracks.filter(t => t.have).length} of ${T.tracks.length} tracks${T.source ? ' · track list from ' + esc(T.source) : ''} · Ctrl+click another album to keep this one open</span>${pcAll}
    ${T.tracks.map((t, ti) => `<div class="antrk ${t.have ? 'have' : 'miss'}"><span class="mark">${t.have ? '✓' : '○'}</span><span class="grow" style="min-width:0"><b>${esc(t.label || t.title)}</b>${t.length ? ' <span class="sub">' + mmss(t.length) + '</span>' : ''}${t.have ? '<span class="sub mono" style="font-size:11px;display:block;overflow-wrap:anywhere">' + esc(t.file) + '</span>' : ''}</span>
      ${t.have ? (t.fid ? `<button class="btn small ghost" onclick="A.play(${arg(t.fid)})">${S.playing === t.fid ? '❚❚' : '▶'}</button>` : '') : `<button class="btn small outline" onclick="A.anTrHelp(${arg(ak + '#' + ti)})">${S.anTrHelp === ak + '#' + ti ? 'Close' : 'Find it'}</button>`}</div>
      ${!t.have && S.anTrHelp === ak + '#' + ti ? anHelper(x, t) : ''}
      ${!t.have && S.anTrHelp !== ak + '#' + ti ? pcHits(x, t, (S.anFind || {})[pcKey(x, t)]) : ''}`).join('')}</div>`;
}
const pcKey = (x, t) => x.release_id + '|' + t.disc + '|' + t.track;
function pcHits(x, t, f) {            // one place for found songs: each file once, under its own missing song
  if (!f || f.loading || !f.hits || !f.hits.length) return '';
  const meta = JSON.stringify({ release_id: x.release_id, disc: t.disc, track: t.track, title: t.title || t.label, artist: x.artist, album: x.album });
  const sel = S.loSel || {};
  const multi = f.hits.length > 1 ? `<div class="row" style="gap:8px;flex-wrap:wrap;padding:2px 0 4px 6px"><span class="sub" style="font-size:12px">${plural(f.hits.length, 'version')} found.</span>
      <button class="btn small outline" onclick="A.anSongs(${arg(JSON.stringify(f.hits.map(h => h.path)))},true)" title="Adds every version as a song source and scans them: the Duplicates page then shows which one is the best quality (FLAC and MP3 are both kept).">Add all ${f.hits.length} to sources &amp; scan: best version wins</button></div>` : '';
  return multi + f.hits.map(h => `<div class="copyrow lohit ${sel[h.path] ? 'sel' : ''}" data-lp="${esc(h.path)}" style="cursor:default;flex-wrap:wrap" onmousedown="A.loDown(event,${arg(h.path)})" onmouseenter="A.loEnter(event,${arg(h.path)})">
      <input type="checkbox" class="qck" aria-label="Select this song" ${sel[h.path] ? 'checked' : ''} onclick="event.stopPropagation()" onchange="A.loToggle(${arg(h.path)},this.checked)">
      <span class="grow mono wrap" style="font-size:12px">${h.suggest ? '<span class="srcchip" style="color:var(--green-text)" title="Best quality of the versions found (a lossless and a lossy one are both suggested)">★ suggested</span> ' : ''}${esc(h.path)}</span>
      <span class="sub">${esc((h.ext || '').toUpperCase())}${h.bitrate ? ' ' + Math.round(h.bitrate / (h.bitrate > 5000 ? 1000 : 1)) + ' kbps' : ''}${h.size ? ' · ' + (h.size / 1e6).toFixed(1) + ' MB' : ''} · ${mmss(h.duration)}${t.length ? (Math.abs(h.duration - t.length) <= 5 ? ' · same length' : ' · ' + mmss(t.length) + ' on the album') : ''}${h.copies > 1 ? ' · ' + h.copies + ' copies on this PC' : ''}</span>
      <button class="btn small amber" onclick="A.anAddHere(${arg(JSON.stringify({ path: h.path, meta: JSON.parse(meta) }))})" title="Makes an extra copy tagged for this album in the next Copy & tag. The file itself is not touched.">Add to this album</button>
      <button class="btn small outline" onclick="A.anSongs([${arg(h.path)}],false)" title="Adds only this song to Sources (not its folder); it is read in the next scan.">Add song to sources</button>
      <button class="btn small outline" onclick="A.anSongs([${arg(h.path)}],true)" title="Adds only this song to Sources and scans it now with your default settings.">Add &amp; scan</button></div>`).join('');
}
function anArtistFound(name) {
  const f = (S.anFind || {})['artist|' + name]; if (!f) return '';
  if (S.anFoundClosed && S.anFoundClosed[name]) return '';
  if (f.loading) return '<div class="sub" style="font-size:13px"><span class="spin"></span> Looking for this artist on every drive…</div>';
  const added = (S.anAddedSongs || {})[name] || 0;
  const scanBar = added ? `<div class="row" style="gap:8px;flex-wrap:wrap;padding:6px 0"><b>${plural(added, 'song')} added to Sources.</b><button class="btn small amber" onclick="A.scanAsk()">Scan now</button><span class="sub" style="font-size:12px">Only these songs are read, not their folders.</span></div>` : '';
  if (!f.folders || !f.folders.length) return scanBar + '<div class="sub" style="font-size:13px">' + (added ? 'No more songs of this artist to add.' : 'Nothing found on this PC for this artist.') + '</div>';
  const mn = (S.anFoundMin || {})[name], all = f.folders.reduce((a, x) => a.concat(x.files || []), []);
  return `<div class="antracks">${scanBar}<div class="row" style="gap:6px;flex-wrap:wrap"><span class="sub grow" style="font-size:12px">Found ${plural(all.length, 'song')} in ${plural(f.folders.length, 'folder')} on this PC (only this artist's songs, not the whole folders)</span>
    <button class="btn small outline" onclick="A.anArtistAdd(${arg(name)},null,false)" title="Adds only the ${all.length} songs listed below to Sources (never the whole folder).">Add all ${fmt(all.length)} songs to Sources</button>
    <button class="btn small ghost" onclick="A.anFoundMin(${arg(name)})" title="${mn ? 'Show the folders' : 'Fold the folders away'}">${mn ? '▸ Show' : '▾ Minimize'}</button><button class="btn small ghost" onclick="A.anFoundClose(${arg(name)})" title="Close this list">✕ Close</button></div>${mn ? '' : f.folders.map((x, xi) => `<div class="copyrow" style="cursor:default"><span class="grow mono wrap" style="font-size:12px">${esc(x.folder)}</span><span class="sub">${plural(x.songs, 'song')}</span>
    <button class="btn small ghost" onclick="call('open_folder',${arg(x.folder)})">Explorer</button><button class="btn small outline" onclick="A.anArtistAdd(${arg(name)},${xi},false)" title="Adds only these ${x.songs} songs, not the rest of the folder.">Add ${x.songs === 1 ? 'song' : 'these ' + x.songs + ' songs'}</button></div>`).join('')}</div>`;
}
function anHelper(x, t) {
  if (!t) return '';
  const k = pcKey(x, t), req = (S.extraReq || {})[k], f = (S.anFind || {})[k];
  const qs = encodeURIComponent(x.artist + ' ' + (t.title || t.label));
  const sites = [['Apple Music', 'https://music.apple.com/search?term=' + qs], ['Deezer', 'https://www.deezer.com/search/' + qs], ['YouTube Music', 'https://music.youtube.com/search?q=' + qs],
    ['Bandcamp', 'https://bandcamp.com/search?q=' + qs], ['Discogs', 'https://www.discogs.com/search/?q=' + qs + '&type=all']];
  return `<div class="helper">
    <div><span class="cap">IN YOUR LIBRARY</span>${t.src ? `<div style="font-size:13px">You have it on <b>${esc(t.where)}</b> · ${t.same ? 'same recording (MusicBrainz)' : 'a different version'}</div>
      <div class="row" style="gap:8px"><button class="btn small ${req ? 'green' : 'amber'}" onclick="A.anExtra(${arg(JSON.stringify({ src: t.src, release_id: x.release_id, disc: t.disc, track: t.track, title: t.title, artist: x.artist, album: x.album }))},${!req})">${req ? 'Will be copied ✓ (click to undo)' : 'Copy it into this album'}</button>
      <span class="sub" style="font-size:12px">An extra copy tagged for this album, made in the next Copy &amp; tag after your approval. The other file is not touched.</span></div>` : '<div class="sub" style="font-size:13px">Not in your library.</div>'}</div>
    <div><span class="cap">ON THIS PC</span><div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small" onclick="A.anFind(${arg(k)},${arg(x.artist)},${arg(t.title || t.label)})" ${f && f.loading ? 'disabled' : ''}>${f && f.loading ? '<span class="spin"></span> Searching every drive…' : 'Find on this PC'}</button>
      <button class="btn small" onclick="A.anBrowse(${arg(JSON.stringify({ release_id: x.release_id, disc: t.disc, track: t.track, title: t.title, artist: x.artist, album: x.album }))})" data-tip="You know where this version is: pick the file. It is COPIED into this album (tagged as this track) in the next Copy & tag; the file itself is not touched.">Browse…</button>
      ${req && req.browse ? `<span style="font-size:12px;color:var(--green-text)">Will be copied ✓</span>` : ''}<span class="sub" style="font-size:12px">File names and tags only; nothing is moved.</span></div>
      ${f && f.hits ? (f.hits.length ? pcHits(x, t, f) : `<span class="sub" style="font-size:13px">Not found on this PC (${fmt(f.folders || 0)} folders looked at).</span>`) : ''}</div>
    <div><span class="cap">ONLINE</span><div class="row" style="gap:6px;flex-wrap:wrap">${sites.map(s => `<button class="btn small ghost" onclick="call('open_url',${arg(s[1])})">${s[0]} ↗</button>`).join('')}</div></div></div>`;
}
async function anPics() {
  const D = S.an; if (!D || !D.pics) return;
  S.anPics = S.anPics || {}; S.anPicAsked = S.anPicAsked || {};
  if (S.anPicBusy) return; S.anPicBusy = true;                         // v1.1: every artist gets a photo, 40 at a time
  try { for (let i = 0; i < 400; i++) {
    const want = D.artists.map(a => a.artist).filter(n => !S.anPicAsked[n]).slice(0, 20);
    if (!want.length) break;
    want.forEach(n => S.anPicAsked[n] = true);
    const r = await call('artist_pictures', want); if (r && !r.error) { Object.assign(S.anPics, r); render(); }
  } } finally { S.anPicBusy = false; }
}

// ---- Plan preview: the folder tree of the new library + Customize folders

function anArtistSongs(name) {
  const L = (S.anSongs || {})[name];
  if (!L) return '<div class="antracks"><span class="sub"><span class="spin"></span> Loading the songs…</span></div>';
  if (!L.length) return '<div class="antracks"><span class="sub">No songs found for this artist in the current plan.</span></div>';
  let last = null;
  return `<div class="antracks">${L.map(t => { const head = t.album !== last ? (last = t.album, `<div class="qsec"><b>${esc(t.album || 'No album')}${t.year ? ' · ' + esc(t.year) : ''}</b></div>`) : '';
    return head + `<div class="antrk have"><span class="mark">${t.track ? String(t.track).padStart(2, '0') : '•'}</span><span class="grow" style="min-width:0"><b>${esc(t.title)}</b></span>${t.id ? `<button class="btn small ghost" aria-label="Play" onclick="A.play(${arg(t.id)})">${S.playing === t.id ? '❚❚' : '▶'}</button>` : ''}</div>`; }).join('')}</div>`;
}
function anAlmostSongs(x) {
  const T = (S.anTr || {})[x.artist + '|' + x.release_id];
  if (!T) return '<span class="sub"><span class="spin"></span> Loading the songs…</span>';
  const have = (T.tracks || []).filter(t => t.have);
  if (!have.length) return '<span class="sub">No playable songs found for this album.</span>';
  return `<div class="antracks">${have.map(t => `<div class="antrk have"><span class="mark">✓</span><span class="grow" style="min-width:0"><b>${esc(t.label || t.title)}</b>${t.length ? ' <span class="sub">' + mmss(t.length) + '</span>' : ''}</span>${t.fid ? `<button class="btn small ghost" aria-label="Play" onclick="A.play(${arg(t.fid)})">${S.playing === t.fid ? '❚❚' : '▶'}</button>` : ''}</div>`).join('')}</div>`;
}

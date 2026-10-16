/* Midnight 00:01 · Review screen: lists, album cards, compare tables, action row (part of the screens, loaded in order by index.html) */
'use strict';
const KC = { place: '#7FA7E0', match: '#E8A33D', none: '#D9776A' };
const KCT = () => S.theme === 'light' ? { place: '#2F5FA8', match: '#8A5200', none: '#A8432F' } : KC;
const KNAME = { place: 'Find Match', match: 'Check', none: 'No album' };
const RTYPE = { Album: 'Album', EP: 'EP', Single: 'Single', Live: 'Live', OST: 'Soundtrack', Comp: 'Compilation', Box: 'Box set', Remix: 'Remix', Bootleg: 'Bootleg', Mix: 'DJ mix' };
function dur(sec) { sec = Math.max(0, Math.round(sec || 0)); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  return h ? `${h} h ${m} min` : m ? `${m} min ${s ? s + ' s' : ''}`.trim() : `${s} s`; }
const mmss = s => { s = Math.round(s || 0); return s ? Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0') : '–'; };
const stem = f => String(f || '').replace(/\.[^.]+$/, '');
const rvU = id => (S.rvUI[id] = S.rvUI[id] || {});
const effKind = x => (x.decision && x.decision.action === 'reject') ? 'none' : x.kind;
const isDone = x => !!(x.decision && x.decision.action && x.decision.action !== 'reject' && x.decision.action !== 'later');
function badgeOf(x) {
  const d = x.decision;
  if (!isDone(x)) return KNAME[effKind(x)];
  return { accept: 'Accepted', pick: x.kind === 'place' ? 'Placed' : 'Matched', unverified: 'Kept', leave: 'Left out', trust: 'Your tags', edit: 'Edited' }[d.action] || 'Done';
}
const isAside = x => !!(x.decision && x.decision.action === 'reject');
const isLater = x => !!(x.decision && x.decision.action === 'later');
const LATER_C = '#8FA3C0';
function groupKey(x, mode) {
  if (mode === 'album') return (x.g_album || '(no album tag)') + '\u0000' + (x.g_artist || '');
  if (mode === 'artist') return x.g_artist || x.tags.artist || '(no artist)';
  if (mode === 'folder') return x.folder;
  return '';
}
// V2.0.6: 'What changes' filter: only the songs where the match would change the title / album / artist / year / track (several can be on: any of them)
const CHG_FIELDS = [['title', 'Title'], ['album', 'Album'], ['artist', 'Artist'], ['year', 'Year'], ['track', 'Track']];
const CHGC = new WeakMap();
function chgOf(x) {
  const k = x.suggest, h = CHGC.get(x); if (h && h.k === k && h.t === x.tags && h.d === ((x.decision && x.decision.action) || '') && h.c === x.kind) return h.v;
  const v = chgOf0(x); CHGC.set(x, { k, t: x.tags, d: (x.decision && x.decision.action) || '', c: x.kind, v }); return v;
}
function chgOf0(x) {
  const s = x.suggest, t = x.tags || {}; if (effKind(x) !== 'match' || !s) return {};
  const nk = v => String(v || '').toLowerCase().replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/ß/g, 'ss').normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^\p{L}\p{N}]/gu, '');
  const trk = v => String(v || '').trim().split(' ')[0].split('-').pop().split('/')[0].replace(/^0+/, '');
  const diff = (a, b) => !!a && !!b && nk(a) !== nk(b);
  return { title: diff(t.title || stem(x.file), withVer(s.title, t.title)), album: diff(t.album, s.release), artist: diff(t.artist, s.artist),
    year: !!(t.year && s.year) && String(t.year).slice(0, 4) !== String(s.year).slice(0, 4), track: !!(t.track && s.track) && trk(t.track) !== trk(s.track) };
}
function chgOn() { return CHG_FIELDS.map(f => f[0]).filter(k => (S.rvChg || {})[k]); }
function chgPass(x) { if (S.rvView !== 'songs') return true; const on = chgOn(); if (!on.length) return true; const c = chgOf(x); return on.some(k => c[k]); }
function chgRow() {
  const items = (S.rv.items || []).filter(x => !isDone(x) && !isAside(x) && !isLater(x)), cnt = {};
  items.forEach(x => { const c = chgOf(x); CHG_FIELDS.forEach(f => { if (c[f[0]]) cnt[f[0]] = (cnt[f[0]] || 0) + 1; }); });
  const on = chgOn(), lab = on.length ? ': ' + CHG_FIELDS.filter(f => on.includes(f[0])).map(f => f[1]).join(', ') : '';
  return `<div class="row chgwrap" style="gap:6px;margin-top:4px;flex-wrap:wrap"><details class="moremenu chgmenu" ${S.chgOpen ? 'open' : ''}><summary class="btn small ${on.length ? '' : 'outline'}" onclick="event.preventDefault();A.chgMenu()" title="Show only the songs where the match would change this. You can tick several.">Only where this changes${esc(lab)} ▾</summary><div class="moredrop chgdrop">${CHG_FIELDS.map(f =>
    `<label class="chgit"><input type="checkbox" ${(S.rvChg || {})[f[0]] ? 'checked' : ''} onchange="A.rvChg(${arg(f[0])})"><span>${f[1]}</span><span class="sub">${fmt(cnt[f[0]] || 0)}</span></label>`).join('')}${on.length ? '<button class="btn small ghost" onclick="A.rvChgClear()">Clear</button>' : ''}</div></details></div>`;
}
function rvQueue() {
  const R = S.rv; if (!R) return [];
  if (S._rc && S._rc.q) return S._rc.q;          // V2.0.6: the list is worked out once per redraw, not 3-4 times
  const res = rvQueue0(R); if (S._rc) S._rc.q = res; return res;
}
function rvQueue0(R) {
  const f = S.rvFilter || 'all', g = S.rvGroupBy || '';
  const all = R.items.filter(x => !S.rvSoloAr || (x.g_artist || '(no artist tag)') === S.rvSoloAr).filter(x => f === 'sure' ? sureIds().has(x.id) : f === 'classical' ? (x.classical && !isDone(x) && !isAside(x) && !isLater(x)) : f === 'all' ? !isLater(x) : f === 'aside' ? isAside(x) : f === 'later' ? isLater(x) : f === 'done' ? isDone(x) : effKind(x) === f && !isDone(x) && !isAside(x) && !isLater(x)).filter(chgPass);
  const nm = x => (x.tags.title || stem(x.file)).toLowerCase();
  const so = S.rvSort || 'pct_desc', pv = x => effKind(x) === 'match' ? (x.match_pct == null ? 50 : x.match_pct) : effKind(x) === 'place' ? -1 : -2;
  const inner = (a, b) => so === 'pct_desc' ? pv(b) - pv(a) || nm(a).localeCompare(nm(b)) : so === 'pct_asc' ? pv(a) - pv(b) || nm(a).localeCompare(nm(b))
    : so === 'artist' ? (a.g_artist || a.tags.artist || '~').localeCompare(b.g_artist || b.tags.artist || '~') || nm(a).localeCompare(nm(b))
    : so === 'artist_desc' ? (b.g_artist || b.tags.artist || '~').localeCompare(a.g_artist || a.tags.artist || '~') || nm(b).localeCompare(nm(a))
    : so === 'name_desc' ? nm(b).localeCompare(nm(a)) : nm(a).localeCompare(nm(b));
  const byName = (a, b) => g ? (groupKey(a, g).localeCompare(groupKey(b, g)) || (g === 'artist' ? (a.g_album || '~').localeCompare(b.g_album || '~') : 0)
    || (parseInt(a.tags.disc) || 1) - (parseInt(b.tags.disc) || 1) || (parseInt(a.tags.track) || 999) - (parseInt(b.tags.track) || 999) || nm(a).localeCompare(nm(b))) : inner(a, b);
  const pc = x => x.match_pct == null ? -1 : x.match_pct;
  const cl = (u, v) => String(u).localeCompare(String(v), undefined, { sensitivity: 'base', numeric: true });
  const libOrd = (a, b) => cl(a.g_artist || a.tags.artist || '~', b.g_artist || b.tags.artist || '~') || cl(a.g_album || a.tags.album || '~', b.g_album || b.tags.album || '~')
    || (parseInt(a.tags.disc) || 1) - (parseInt(b.tags.disc) || 1) || (parseInt(a.tags.track) || 999) - (parseInt(b.tags.track) || 999) || nm(a).localeCompare(nm(b));
  // 2.0.1 Library mode: the right side only follows the library tree on the left (folder by folder, song by song, same order as the tree), so the next song is the next one in the tree
  const treeOrd = (a, b) => {
    const pa = String(a.dest || '').replace(/\\/g, '/').split('/'), pb = String(b.dest || '').replace(/\\/g, '/').split('/');
    if (!a.dest || !b.dest) return a.dest ? -1 : b.dest ? 1 : libOrd(a, b);
    for (let i = 0; i < Math.min(pa.length, pb.length); i++) {
      const fa = i === pa.length - 1, fb = i === pb.length - 1;
      if (fa !== fb) return fa ? 1 : -1;                                              // folders come before songs, like in the tree
      const x = pa[i].toLowerCase(), y = pb[i].toLowerCase();
      if (x === y) continue;
      if (!fa) { const ux = pa[i].startsWith('_'), uy = pb[i].startsWith('_'); if (ux !== uy) return ux ? -1 : 1; }
      return x < y ? -1 : 1;
    }
    return pa.length - pb.length;
  };
  const open = all.filter(x => !isDone(x) && !isAside(x) && !isLater(x)).sort(S.rvSoloAr ? libOrd : S.rvView === 'library' && (so === 'artist' || so === 'artist_desc') ? treeOrd : byName);      // V2.0.6: Solo artist walks album by album, track by track
  const later = all.filter(x => !isDone(x) && !isAside(x) && isLater(x)).sort((a, b) => g ? byName(a, b) : pv(b) - pv(a));
  const aside = all.filter(isAside).sort(byName);
  const done = all.filter(isDone).sort(S.rvFilter === 'done' ? byName : (a, b) => a.decision.t - b.decision.t);      // V2.0.5 (#8): the Done list follows Sort / Group by
  return open.concat(later, aside, done);
}
function rvFocus() {
  const R = S.rv; if (!R) return null;
  const q = rvQueue();
  let x = R.items.find(i => i.id === S.rvSel);
  if (!x) x = q.find(i => !isDone(i)) || null;
  if (!x && q.length && (S.rvFilter === 'done' || !R.items.some(i => !isDone(i)))) x = q[0];      // v2.0: the Done list (or an all-done Review) opens too
  return x;
}
function coverHtml(c, big) {
  const url = c && (c.cover_url || (c.mbid ? 'https://coverartarchive.org/release/' + c.mbid + '/front-250' : ''));
  if (url && S.rv && S.rv.covers) return `<img class="art ${big ? 'big' : ''}" src="${esc(url)}" alt="" referrerpolicy="no-referrer" data-ph="art ${big ? 'big' : ''}" onerror="A.imgFail(this)">`;
  return `<span class="art ${big ? 'big' : ''}" aria-hidden="true">${big ? 'COVER' : ''}</span>`;
}
function albCover(items) {                       // the album's cover: the found release's, else the one inside the files, else a soft placeholder
  items = items || [];
  const hit = items.find(i => i.suggest && (i.suggest.cover_url || i.suggest.mbid));
  const own = S.rv && S.rv.cover_base && items[0] ? S.rv.cover_base + encodeURIComponent(items[0].id) : '';
  const url = hit && S.rv && S.rv.covers ? (hit.suggest.cover_url || 'https://coverartarchive.org/release/' + hit.suggest.mbid + '/front-250') : own;
  return url ? `<img class="alcov" loading="lazy" src="${esc(url)}" alt="" referrerpolicy="no-referrer" data-ph="alcov ph" onerror="A.imgFail(this)">` : '<span class="alcov ph" aria-hidden="true"></span>';
}
function resultRows(x, list, mode, mineKey) {
  if (!list || !list.length) return '';
  return `<ul class="res">${list.map((c, i) => {
    const mine = mineKey && mineKey === c.match.release_id + '|' + c.match.disc + '|' + c.match.track;
    const det = [c.artist, c.release, c.year, RTYPE[c.rtype] || c.rtype, c.track ? 'track ' + (c.disctotal > 1 ? c.disc + '-' : '') + c.track : ''].filter(Boolean).join(' · ');
    return `<li class="${mine ? 'mine' : ''} rescl" title="Click to show or hide the tag comparison" onclick="if(!event.target.closest('button,summary,details,a,input')){const d=this.querySelector('.rescmp');if(d)d.open=!d.open}">${c.preview ? `<button class="pv ${S.playing === 'u:' + c.preview ? 'on' : ''}" title="Play a 30-second preview from ${esc(c.source)} (streamed from their site)" aria-label="Preview" onclick="A.playUrl(${arg(c.preview)},${arg(c.deezer_track || '')})">${S.playing === 'u:' + c.preview ? '❚❚' : '▶'}</button>` : ''}<span style="flex:1 1 220px;min-width:0;display:flex;flex-direction:column;gap:2px">
      <span style="font-size:13px;font-weight:600;overflow-wrap:anywhere">${diffHtml(c.title, x.tags.title || x.q[1])}</span><span class="sub" style="font-size:12px">${diffHtml(c.artist, x.tags.artist)} · ${diffHtml(c.release, x.tags.album)}${esc([c.year, RTYPE[c.rtype] || c.rtype, c.track ? 'track ' + (c.disctotal > 1 ? c.disc + '-' : '') + c.track : ''].filter(Boolean).map(s => ' · ' + s).join(''))}</span>
      <span class="sub" style="font-size:11px">${esc(c.how || '')}</span></span>
      <span class="srcchip">${esc(c.source)}</span>${c.other_version ? '<span class="srcchip" style="color:var(--amber-text)" title="This track is labelled as another version (mono, mix, live, take…) than your file">other version</span>' : ''}
      <span style="font-size:12px;color:${c.len_ok ? 'var(--green-text)' : 'var(--amber-text)'}">${esc((c.length ? mmss(c.length) + ' · ' : '') + c.len_text)}</span>
      ${c.match_pct != null ? `<span style="font-size:12px;color:${pctColor(c.match_pct)}" title="How close this is to the tags your file has now">${c.match_pct}% alike</span>` : ''}
      <button class="btn small ghost" onclick="A.rvAlbum(${arg(x.id)},${i})" title="Show every track of this album, then click the right one">Album tracks</button>
      <button class="btn small ${mine ? 'green' : 'amber'}" onclick="A.rvUse(${arg(x.id)},${arg(mode)},${i})">${mine ? 'Using this' : 'Use this'}</button>
      <details class="rescmp" style="flex-basis:100%" ${(S.rvCmpOpen || {})[x.id + '|' + i] ?? (i === 0) ? 'open' : ''} ontoggle="(S.rvCmpOpen=S.rvCmpOpen||{})[${arg(x.id + '|' + i)}]=this.open"><summary class="sub" style="font-size:12px;cursor:pointer">Compare your tags with these new tags</summary><div class="cmpgrid">${cmpTable(x, c, c)}</div></details></li>`;
  }).join('')}</ul>`;
}
function regRel(rel) {
  if (rel._rid == null) { rel._rid = S.relReg.length; S.relReg.push(rel); }
  return rel._rid;
}
function releaseCard(x, rel, ri, clickable) {
  const owned = rel.owned || {}, rid = regRel(rel), xid = x ? x.id : '';
  const multi = new Set(rel.tracks.map(t => t.disc)).size > 1;
  const nz = v => String(v || '').toLowerCase().replace(/\(.*?\)|\[.*?\]/g, '').replace(/[^a-z0-9\u00c0-\uffff]+/g, '');
  let bestTi = -1;                                   // the track that fits this song best: same title, same track number, same length
  if (x) { let bs = 0; const xt = nz(x.tags.title || stem(x.file)), xn = parseInt(String(x.tags.track || '').split('/')[0], 10);
    rel.tracks.forEach((t, i) => { const tt = nz(t.title); let sc = 0;
      if (xt && tt) sc += xt === tt ? 100 : (tt.includes(xt) || xt.includes(tt)) ? 60 : 0;
      if (xt && sc < 60) return;            // V2.0.6: a track whose title is not your song's title is never the 'best match' (the track number alone is not enough)
      if (xn > 0 && +t.track === xn && (!multi || (t.disc || 1) === (parseInt(x.tags.disc, 10) || 1))) sc += 20;
      if (x.duration && t.length) { const dd = Math.abs(t.length - x.duration); sc += dd <= 3 ? 15 : dd <= 10 ? 8 : 0; }
      if (sc > bs) { bs = sc; bestTi = i; } });
    if (bs < 20) bestTi = -1; }
  if (x && rel) rel._hasTitle = bestTi >= 0;
  const slot = (t, ti) => {
    const key = (t.disc || 1) + '-' + t.track, have = owned[key], best = ti === bestTi;
    const fits = x && x.duration && t.length && Math.abs(t.length - x.duration) <= 10;
    const n = (multi ? t.disc + '-' : '') + String(t.track).padStart(2, '0');
    const ev = clickable ? `onclick="A.rvSlotR(${arg(xid)},${rid},${ti})" ondragover="event.preventDefault();this.classList.add('over')" ondragleave="this.classList.remove('over')" ondrop="A.rvDropR(event,${rid},${ti})"` : '';
    const state = have ? `<span class="s sub" title="${esc(have)}">in library · click to put this copy here too</span>`
      : `<span class="s" style="color:${fits ? 'var(--green-text)' : 'var(--amber-text)'}">${!x ? 'drop a song here' : best ? 'best match · click to place' : fits ? 'fits · click to place' : 'empty · click to place'}</span>`;
    return `<li class="slotrow">${t.preview ? `<button class="pv ${S.playing === 'u:' + t.preview ? 'on' : ''}" title="Play a 30-second preview from ${esc(rel.source)} (streamed from their site)" aria-label="Preview" onclick="A.playUrl(${arg(t.preview)},${arg(t.deezer_track || '')})">${S.playing === 'u:' + t.preview ? '❚❚' : '▶'}</button>` : ''}<button class="slot ${have ? 'owned' : 'empty'} ${t.focus ? 'focus' : ''} ${best ? 'bestfit' : ''}" ${ev}>
      <span class="n">${esc(n)}</span><span class="t">${esc(t.title)}${t.focus ? ' <span class="srcchip" style="margin-left:6px">the song in your link</span>' : ''}</span><span class="sub" style="font-size:12px;white-space:nowrap">${mmss(t.length)}</span>
      ${state}</button></li>`;
  };
  const slots = rel.tracks.map(slot).join('');
  const fi = rel.tracks.findIndex(t => t.focus);
  const top = fi >= 0 ? `<div class="linktop"><span class="cap">THE SONG FROM YOUR LINK</span><ol class="slots">${slot(rel.tracks[fi], fi)}</ol></div>` : '';
  return `<article class="relcard"><div class="row" style="gap:14px">${coverHtml(rel, true)}
    <div style="flex:1;min-width:0"><div style="font-weight:700;font-size:15px;overflow-wrap:anywhere">${esc(rel.title)}</div>
      <div class="sub" style="font-size:13px">${esc([rel.artist, rel.year, RTYPE[rel.rtype] || rel.rtype].filter(Boolean).join(' · '))}</div></div>
    <span class="srcchip">${esc(rel.source)}</span></div>
    ${top}<span class="sub" style="font-size:12px">${clickable ? (x ? 'Click the track this song is, or drag any of your songs onto a track.' : 'Drag your songs onto their tracks.') : ''}</span><ol class="slots">${slots}</ol></article>`;
}
function searchTool(x, mode, title) {
  const u = rvU(x.id), q = u.q || x.q;
  const sites = (S.rv.sites || []).join(', then ') || 'no site (switched off)';
  const t = x.tags;
  const st = u.stats || {};
  return `<div class="tool"><span style="font-size:13px;font-weight:700">${esc(title)}</span>
    <div class="mytags"><span class="cap">YOUR FILE</span><b>${esc(t.title || stem(x.file))}</b><span>${esc([t.artist || 'no artist', t.album || 'no album', t.year, t.track ? 'track ' + t.track : '', mmss(x.duration)].filter(Boolean).join(' · '))}</span></div>
    <div class="flds">${[['Artist', 'e.g. Gary Jules'], ['Title', 'song title'], ['Album (optional)', 'if you know it']].map((f, i) =>
      `<label>${f[0]}<input id="q_${x.id}_${i}" value="${esc(q[i] || '')}" placeholder="${f[1]}" oninput="A.rvQ(${arg(x.id)},${i},this.value)" onkeydown="if(event.key==='Enter')A.rvSearch(${arg(x.id)})"></label>`).join('')}
      <button class="rcirc" aria-label="Copy artist, title and album" data-tip="Copy artist, title and album, to search for them on the web" onclick="A.rvCopyQ(${arg(x.id)})">${svg('M9 9h10v11H9zM5 4h10v3M5 4v12h2', 16)}</button>
      <button class="btn amber" style="min-height:40px" onclick="A.rvSearch(${arg(x.id)})" ${u.loading ? 'disabled' : ''}>${u.loading === 'search' ? '<span class="spin"></span> Searching…' : 'Search again'}</button></div>
    <label class="lbl">…or type or paste a MusicBrainz, Discogs, Deezer, Apple Music or Spotify link
      <span class="row" style="gap:8px"><input class="mono grow" id="l_${x.id}" value="${esc(u.link || '')}" placeholder="https://musicbrainz.org/release/…" oninput="A.rvLinkSet(${arg(x.id)},this.value)" onkeydown="if(event.key==='Enter')A.rvLink(${arg(x.id)})">
      <button class="rcirc" aria-label="Paste a link" data-tip="Paste the link from your clipboard (then press Load release)" onclick="A.rvPasteLink(${arg(x.id)})">${svg('M9 4h6v3H9zM7 5.5H5V21h14V5.5h-2M8 12h8M8 16h8', 16)}</button>
      <button class="btn small" onclick="A.rvLink(${arg(x.id)})" ${u.loading ? 'disabled' : ''}>${u.loading === 'link' ? '<span class="spin"></span>' : 'Load release'}</button></span></label>
    ${u.link && !/(musicbrainz\.org\/(release|release-group|recording|track)\/|discogs\.com\/(.+\/)?(release|master)\/|deezer\.com\/(.+\/)?(album|track)\/|apple\.com\/|spotify\.com\/(.+\/)?(album|track)\/|spotify:(album|track):)/i.test(u.link.trim()) ? '<span style="font-size:12px;color:var(--amber-text)">This does not look like a MusicBrainz, Discogs, Deezer, Apple Music or Spotify album or song link.</span>' : u.link ? '<span class="sub" style="font-size:12px">Loads the album from that site (only the id in the link is sent); then click the track. A song link marks its track.</span>' : ''}
    ${u.err ? `<span style="font-size:13px;color:var(--clay)">${esc(u.err)}</span>` : ''}
    ${u.rel ? `<div id="relTop_${x.id}"><div class="row" style="gap:8px"><button class="btn small outline" onclick="A.rvLinkGroup(${arg(x.id)})" title="Match every song of your album '${esc(x.g_album || '')}' to this album">Use this album for all songs of my album</button></div>` + releaseCard(x, u.rel, -1, true) + '</div>' : ''}
    ${resultRows(x, u.results, mode, u.pendingKey)}
    ${u.searched && u.results && !u.results.length ? '<span style="font-size:13px">Nothing found. Try fewer words, or the title in its original language.</span>' : ''}
    ${st.more ? `<div class="row" style="gap:8px;font-size:12px"><span class="sub">A ${st.edition ? 'special edition / remaster, so Apple Music and Deezer were asked first;' : ''} a same-version result was found, so the other sites were skipped (faster).</span><button class="btn small ghost" onclick="A.rvSearch(${arg(x.id)},true)">Search the other sites too</button></div>` : ''}
    ${st.no_album_hit ? '<span class="sub" style="font-size:12px">Nothing on the album you typed, so results from other albums are shown.</span>' : ''}
    <span class="sub" style="font-size:12px">Only a real release you pick is used. ${/remaster|\bmono\b|stereo|deluxe|edition|anniversary|expanded|\d{4} mix/i.test([q[1], q[2], x.tags.title, x.tags.album, x.file].join(' ')) ? 'Remaster / special edition: Apple Music and Deezer are asked first, then ' + esc(sites) : 'Asks ' + esc(sites)}. Sent: only the words above and the song length.</span></div>`;
}
function reviewScreen() {
  const R = S.rv;
  if (!R && !S.rvErr && !S.rvLoading) setTimeout(loadReview, 0);      // V2.0.5 (#1): opened from the saved session or a restart: load the list now, never wait forever
  if (!R) return `<header class="head"><div><h1>Review</h1><p>${S.rvErr ? 'The list could not be loaded.' : '<span class="spin"></span> Loading…'}</p></div></header>
    ${S.rvErr ? `<div class="panel pad" style="display:flex;flex-direction:column;gap:10px"><span class="mono wrap" style="font-size:12px;color:var(--clay)">${esc(S.rvErr)}</span>
      <span class="sub" style="font-size:13px">The details were saved in the logs folder (app_errors.txt).</span><div><button class="btn amber small" onclick="loadReview()">Try again</button></div></div>` : ''}`;
  if (S.B.job && !S.B.job.done && S.B.job.kind === 'scan') return `<header class="head"><div><h1>Review</h1><p>A scan is running. The Review list is made when it finishes; your earlier choices are kept for the same files.</p></div></header>
    <div class="panel pad"><button class="btn outline" onclick="A.go('dash')">See progress</button></div>`;
  const items = R.items, done = items.filter(isDone).length, total = items.length;
  const job = S.B.job, updating = job && ['update', 'fastupdate'].includes(job.kind) && !job.done;
  const counts = { all: items.filter(x => !isDone(x) && !isAside(x) && !isLater(x)).length };
  ['place', 'match', 'none'].forEach(k => counts[k] = items.filter(x => effKind(x) === k && !isDone(x)).length);
  const allDone = total > 0 && done === total;
  const vw = S.rvView || 'albums';
  const ic = d => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none"><path d="${d}"/></svg>`;
  const byArtist = S.rvGroupBy === 'artist';
  const VIEWS = [['songs', 'Songs', 'M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z', 'Every song, one by one'],
    ['albums', 'Albums', 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', 'Songs grouped by album'],
    ['artists', 'Artists', 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0', 'Songs grouped by artist']];
  const MODES = [['quick', 'Quick', 'M13 2L4 14h7l-1 8 9-12h-7z', 'One song (or one album) at a time'],
    ['library', 'Library', 'M4 5h4v14H4zM10 5h4v14h-4zM16 7l4-1 3 12-4 1z', 'Quick mode on the left, your library on the right'],
    ['tags', 'Check tags', 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11', 'Tags now next to the tags they will get']];
  const arList = vw === 'albums' && S.alSort === 'artists';      // V2.0.6: the Artists tab is the new artist list (the Albums view sorted by artist)
  const vOn = k => k === 'songs' ? vw === 'songs' && !byArtist : k === 'albums' ? vw === 'albums' && !arList : k === 'artists' ? arList || (vw === 'songs' && byArtist) : false;
  const mOn = k => k === 'quick' ? (vw === 'quick' || vw === 'album') : vw === k;
  const btn = (o, on, fn) => `<button aria-pressed="${on}" title="${esc(o[3])}" onclick="${fn}" style="display:inline-flex;align-items:center;gap:6px">${ic(o[2])}${o[1]}</button>`;
  const views = (vw === 'album' ? `<button class="btn small outline" onclick="A.rvViewSet('albums')" title="Back to the list of albums">← Back to albums</button>` : '')
    + `<span class="modelbl" title="How the songs are grouped, and how you work through them">View mode</span><span class="seg" role="group" aria-label="View">${VIEWS.map(o => btn(o, vOn(o[0]), `A.rvViewPick(${arg(o[0])})`)).join('')}</span>`
    + `<span class="seg" role="group" aria-label="Mode">${MODES.map(o => btn(o, mOn(o[0]), `A.rvViewPick(${arg(o[0])})`)).join('')}</span>`
    + (vw === 'quick' || vw === 'album' ? `<span class="modelbl" title="Quick mode works on one song or one whole album at a time">Quick</span><span class="seg small" role="group" aria-label="Quick mode">
      <button aria-pressed="${vw === 'quick'}" title="One song at a time" onclick="A.rvViewSet('quick')">Song</button>
      <button aria-pressed="${vw === 'album'}" title="One whole album at a time (also opens when you solo an album)" onclick="A.quickAlbum()">Album</button></span>` : '');
  const head = `<header class="head"><div><h1>Review</h1><p>${vw === 'album' ? 'One album at a time: every song next to its new tags, each one editable on its own.' : vw === 'albums' ? 'Your albums, each song next to its new tags. Differences are highlighted.' : vw === 'tags' ? 'Every confirmed song: the tags it has now next to the tags it will get. Accept the new tags, keep yours, or find another match.' : vw === 'quick' ? 'One song at a time. A accept · K keep · F find another album · E edit · L later · N not this.' : vw === 'library' ? 'Quick mode on the left, your library on the right. Pick a song and its album opens; drag a song onto an album to place it.' : 'Pick a song on the left; decide on the right. After each decision the next song opens.'}</p></div>
    <div class="row" style="gap:12px;align-items:stretch;flex-wrap:wrap"><div class="panel" style="padding:8px 10px;display:flex;flex-direction:row;gap:8px;align-items:center" aria-label="Plan">
        <button class="btn small outline" style="display:inline-flex;align-items:center;gap:6px" onclick="A.updatePlan()" ${R.stale && !updating ? '' : 'disabled'} title="Only the songs you changed - takes seconds">${ic('M21 12a9 9 0 1 1-3-6.7M21 4v5h-5')}Update plan</button>
        <button class="btn small ghost" style="display:inline-flex;align-items:center;gap:6px" onclick="A.updatePlan('full')" ${updating ? 'disabled' : ''} title="Works out the whole plan again (best at the end, or after adding music / changing settings). Takes longer.">${ic('M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5')}Full update</button></div>
      <div style="display:flex;flex-direction:column;gap:6px;min-width:220px"><span style="font-size:13px;font-weight:600">${fmt(done)} of ${fmt(total)} reviewed <span class="sub" style="font-weight:600">${total ? Math.round(done / total * 100) : 0}%</span></span>
      ${allDone ? `<button class="btn amber small" onclick="A.toPlan()">Go to Plan preview →</button>` : ''}
      <div class="bar"><i style="width:${total ? Math.round(done / total * 100) : 0}%;background:var(--green)"></i></div></div></div></header>`;
  const toolbar = (full) => `<div class="rvtop"><div class="rvtopL">${full ? `<span class="rvprep" style="display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap">${actionRow('__prep')}</span>` : ''}${views}</div>${full ? `<div class="rvtopR">${actionRow(vw, true)}</div>` : ''}</div>`;
  const look = S.B.lookups === 'loading' ? `<div class="banner" style="border-color:var(--line);background:var(--panel)"><span class="spin"></span> Getting the lookup memory ready (first time after start, can take a minute). You can keep working — searches wait for it.</div>` : '';
  const soloBn = S.rvSoloAr && (vw === 'quick' || vw === 'songs' || vw === 'library') ? `<div class="banner" style="border-color:var(--amber);display:flex;gap:12px;align-items:center;flex-wrap:wrap"><b>Solo artist: ${esc(S.rvSoloAr)}</b><span class="sub">${plural(rvQueue().filter(x => !isDone(x) && !isAside(x) && !isLater(x)).length, 'song')} left, album by album</span><button class="btn small outline" onclick="A.soloClear()">Show everyone</button></div>` : '';
  const banner = look + soloBn + (updating ? `<div class="banner"><span class="spin"></span> Updating the plan with your choices… <span id="jobline">${esc(stageInfo(job, S.B.progress).line)}</span></div>`
    : R.stale ? `<div class="banner">Your choices are saved. They go into the plan when it is updated with Update plan above (nothing is copied).</div>` : '');
  if (vw === 'tags') { const nb = neatScreen().replace(/<header class="bighead">[\s\S]*?<\/header>/, '').replace(/<div class="banner">[\s\S]*?<\/div>/, ''); return head + toolbar(false) + banner + (nb.trim() || '<div class="panel empty"><span class="spin"></span> Loading…</div>'); }
  if (!total) return head + toolbar(false) + banner + `<div class="panel empty">Nothing needs review. ${S.dash && S.dash.has_plan ? '' : 'Scan first on Sources.'}</div>`;
  const q = rvQueue(), fx = S.rvGroupSel ? null : rvFocus();
  const pctChip = x => effKind(x) === 'match' && x.match_pct != null ? ` · <span style="color:${pctColor(x.match_pct)}">${x.match_pct}% alike</span>` : '';
  const row = x => {
    const k = effKind(x), dn = isDone(x), sel = fx && fx.id === x.id, lt = isLater(x);
    const ck = S.rvChecked[x.id];
    const col = dn ? '#5CC0A7' : KC[k];
    return `<div class="qrow"><input type="checkbox" class="qck" aria-label="Select ${esc(x.tags.title || stem(x.file))}" ${ck ? 'checked' : ''} onclick="A.rvCheck(event,${arg(x.id)})">
      <button class="qitem ${dn ? 'done' : ''} ${ck ? 'checked' : ''}" aria-pressed="${sel}" onclick="A.rvPick(${arg(x.id)})" draggable="true" ondragstart="S.rvDrag=${arg(x.id)};try{event.dataTransfer.setData('text/plain',${arg(x.id)});event.dataTransfer.effectAllowed='move'}catch(e){}" ondragend="S.rvDrag=null">
      <span class="stripe" style="background:${col}"></span>
      ${S.rv && S.rv.cover_base && S.rvThumbs !== false ? `<img class="qthumb" loading="lazy" src="${esc(S.rv.cover_base + encodeURIComponent(x.id))}" alt="" onerror="this.style.visibility='hidden'">` : ''}
      <span class="tx" title="${esc((x.tags.title || stem(x.file)) + ' — ' + x.file)}"><b>${esc(x.tags.title || stem(x.file))}</b><span>${esc((S.rvGroupBy === 'artist' ? (x.g_album || 'no album') : (x.tags.artist || x.artist_found || 'no artist')) + ' · ' + mmss(x.duration))}${pctChip(x)}${x.prep ? ` · <span style="color:var(--green-text)">${x.dig ? 'found by dig deeper' : 'results ready'}</span>` : x.dig ? ' · dug, nothing found' : ''}</span></span>
      <span class="kbadge" style="color:${dn ? 'var(--green-text)' : KCT()[k]}">${esc(isAside(x) ? 'Not this' : badgeOf(x))}</span>${lt ? '<span class="ltag">Later</span>' : ''}</button>${dn ? `<button class="btn small ghost" onclick="A.rvUndo(${arg(x.id)})" title="Move back to Review">Redo</button>` : ''}</div>`;
  };
  const g = S.rvGroupBy || '';
  S.rvGroups = {};
  let list = '', lastSec = '', lastKey = null, lastAlb = null;
  if (vw === 'songs') {
    // long lists are drawn in pages (the app stays fast with thousands of songs)
    const lim = S.rvLimit || 250, gids = {}, aids = {};
    const onlyDone = S.rvFilter === 'done';                                  // V2.0.5 (#8): Artists / Album / Folder grouping also works inside the Done filter
    if (g) q.forEach(y => { if (onlyDone ? isDone(y) : (!isDone(y) && !isAside(y))) { (gids[groupKey(y, g)] = gids[groupKey(y, g)] || []).push(y.id);
      if (g === 'artist') { const k2 = 'AA|' + groupKey(y, g) + '\u0000' + (y.g_album || y.tags.album || '(no album)'); (aids[k2] = aids[k2] || []).push(y.id); } } });
    const nAside = q.filter(isAside).length, nDone = q.filter(isDone).length;
    let shown = 0, more = 0;
    for (const x of q) {
      const sec = isDone(x) ? 'done' : isAside(x) ? 'aside' : 'open';
      if (sec !== lastSec) {
        lastSec = sec; lastKey = null;
        if (sec === 'aside') list += `<div class="qsec"><b>SET ASIDE · ${nAside}</b><span class="sub">you said "Not this"</span><button class="btn small outline" onclick="A.rvAsideSearch()">Search again for these<span class="key">S</span></button></div>`;
        if (sec === 'done') list += `<div class="qsec"><b>DONE · ${nDone}</b></div>`;
      }
      if (g && (sec === 'open' || (onlyDone && sec === 'done'))) {
        const key = groupKey(x, g);
        if (key !== lastKey) {
          lastKey = key; lastAlb = null;
          const ids = gids[key] || [];
          const [al, ar] = g === 'album' ? key.split('\u0000') : [key, ''];
          S.rvGroups[key] = { key, ids, album: g === 'album' && x.g_album ? al : '', artist: g === 'album' ? ar : (g === 'artist' ? key : '') };
          if (shown < lim) {
            const closed = S.rvClosed[key], allck = ids.every(i => S.rvChecked[i]);
            list += `<div class="ghead ${S.rvGroupSel && S.rvGroupSel.key === key ? 'on' : ''}">
          <button class="gtog" aria-label="${closed ? 'Open' : 'Close'} group" onclick="A.rvGroupToggle(${arg(key)})">${closed ? '▸' : '▾'}</button>
          <input type="checkbox" class="qck" aria-label="Select the group" ${allck ? 'checked' : ''} onclick="A.rvGroupCheck(${arg(key)},this.checked)">
          ${g === 'album' ? albCover(q.filter(y => ids.includes(y.id))) : ''}<span class="gname" title="${esc(g === 'folder' ? key : al)}"><b>${esc(g === 'folder' ? key.split(/[\\/]/).pop() : al)}</b><span>${esc((ar ? ar + ' · ' : '') + plural(ids.length, 'song'))}</span></span>
          ${onlyDone ? '' : g !== 'artist' && (g !== 'album' || x.g_album) ? `<button class="btn small outline" onclick="A.rvGroupOpen(${arg(key)})" title="Find this album and match all its songs at once">Match album</button>` : ''}${onlyDone ? '' : g === 'artist' ? leaveArtistBtn(key) : ''}</div>`;
          }
        }
        if (S.rvClosed[key]) continue;
        if (g === 'artist') { const ab = x.g_album || x.tags.album || '(no album)'; if (ab !== lastAlb) { lastAlb = ab; const k2 = 'AA|' + groupKey(x, g) + '\u0000' + ab, ids2 = aids[k2] || [], real = !!(x.g_album || x.tags.album);
          if (real) S.rvGroups[k2] = { key: k2, ids: ids2, album: ab, artist: groupKey(x, g) };
          list += `<div class="qsec" style="margin-left:18px">${albCover(q.filter(y => ids2.includes(y.id)))}<b>${esc(ab)}</b><span class="sub">${plural(ids2.length, 'song')}</span>${real && ids2.length && !onlyDone ? `<button class="btn small outline" style="margin-left:auto" onclick="A.rvGroupOpen(${arg(k2)})" title="Find this album and match all its songs at once">Match album</button>` : ''}</div>`; } }
      }
      if (shown < lim || (fx && fx.id === x.id)) { list += row(x); shown++; } else more++;
    }
    if (more) list += `<div class="row" style="padding:8px 4px"><button class="btn small outline" onclick="S.rvLimit=${lim + 500};render()">Show ${fmt(Math.min(500, more))} more</button><span class="sub" style="font-size:12px">${fmt(more)} not shown yet</span></div>`;
  }
  list = list || '<p class="sub" style="margin:8px 4px;font-size:13px">Nothing here.</p>';
  counts.aside = items.filter(isAside).length; counts.later = items.filter(isLater).length; counts.done = done;
  counts.all = items.filter(x => !isDone(x)).length;      // V2.0.5 (#2): 'left' = every song that still needs you (open + Later + Not this): same number as the Dashboard and the menu badge
  ['place', 'match', 'none'].forEach(k => counts[k] = items.filter(x => effKind(x) === k && !isDone(x) && !isAside(x) && !isLater(x)).length);
  counts.classical = items.filter(x => x.classical && !isDone(x) && !isAside(x) && !isLater(x)).length;      // V2.0.5: Classical is a filter inside the Review
  counts.sure = sureOnes().length;
  const TABHINT = { all: 'everything open', match: 'a match to check', place: 'pick the album', none: 'nothing found', classical: 'classical music (the performer is the artist, the composer goes in the composer tag)', aside: 'matches you refused', later: 'come back to these', done: 'decided' };
  const FT = [['all', 'All'], ['match', 'Check'], ['place', 'Find Match'], ['none', 'No album'], ['classical', 'Classical'], ['aside', 'Not this'], ['later', 'Later'], ['done', 'Done']].concat(S.rvFilter === 'sure' ? [['sure', 'Sure ones']] : []);
  const chip = f => `<button class="fchip fc-${f[0]}" aria-pressed="${(S.rvFilter || 'all') === f[0]}" title="${esc(TABHINT[f[0]] || '')}" onclick="A.rvFilter(${arg(f[0])})">${f[0] === 'done' ? '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="vertical-align:-2px;margin-right:3px"><path d="M4 12l5 5L20 6"/></svg>' : ''}${f[1]} ${counts[f[0]]}</button>`;
  const isShown = f => f[0] === 'all' || counts[f[0]] > 0 || (S.rvFilter || 'all') === f[0];      // 1.1.5: categories with 0 go into "More"
  const curF = FT.find(f => f[0] === (S.rvFilter || 'all')) || FT[0];      // V2.0.6: the filter is one drop-down menu (every view uses it)
  const tabs = `<details class="moremenu chgmenu fltmenu" ${S.fltOpen ? 'open' : ''}><summary class="btn small fltc fltc-${curF[0]}" onclick="event.preventDefault();A.fltMenu()" title="Choose which songs to show">Show: ${curF[1]} ${counts[curF[0]]} ▾</summary><div class="moredrop chgdrop">${FT.map(f =>
    `<button class="chgit fltit ${(S.rvFilter || 'all') === f[0] ? 'on' : ''}" title="${esc(TABHINT[f[0]] || '')}" onclick="A.fltPick(${arg(f[0])})"><span>${f[1]}</span><span class="sub">${counts[f[0]]}</span></button>`).join('')}</div></details>`;
  const soNow = S.rvSort || 'pct_desc', soKey = soNow.startsWith('pct') ? 'pct' : soNow.startsWith('artist') ? 'artist' : 'name', soDir = soNow === 'pct_desc' || soNow.endsWith('_desc') ? 'desc' : 'asc';
  const soMake = (k, d) => k === 'pct' ? (d === 'desc' ? 'pct_desc' : 'pct_asc') : d === 'desc' ? k + '_desc' : k;
  const sortRow = `<div class="row" style="gap:6px;width:100%;margin-top:4px"><span class="sub" style="font-size:12px">Sort</span><span class="seg small">${[['pct', 'Match'], ['artist', 'Artist'], ['name', 'Title']].map(o =>
      `<button aria-pressed="${soKey === o[0]}" onclick="A.rvSortBy(${arg(soMake(o[0], soDir))})">${o[1]}</button>`).join('')}</span><span class="seg small" aria-label="Direction"><button aria-pressed="${soDir === 'asc'}" title="${soKey === 'pct' ? 'Hardest first: songs not found, then songs to place, then low matches' : 'A to Z'}" onclick="A.rvSortBy(${arg(soMake(soKey, 'asc'))})">↑</button><button aria-pressed="${soDir === 'desc'}" title="${soKey === 'pct' ? 'Surest first: the easy ones go fast' : 'Z to A'}" onclick="A.rvSortBy(${arg(soMake(soKey, 'desc'))})">↓</button></span></div>`;
  const groupRow = `<div class="row" style="gap:6px;width:100%;margin-top:4px"><span class="sub" style="font-size:12px">Group by</span><span class="seg small">${[['', 'None'], ['album', 'Album'], ['artist', 'Artist'], ['folder', 'Folder']].map(o =>
      `<button aria-pressed="${(S.rvGroupBy || '') === o[0]}" onclick="A.rvGroupBy(${arg(o[0])})">${o[1]}</button>`).join('')}</span></div>`;
  const bars = toolbar(true) + prepBar();
  if (vw === 'album') { const cs = albumCards('all'), ci = cs.findIndex(c => c.key === S.alKey), nxt = cs.slice(ci + 1).filter(c => c.open).slice(0, 5);
    return head + banner + bars + `<div class="rvwrap"><div style="flex:1;min-width:0">${albumPage()}</div><aside class="panel" style="flex:0 1 240px;padding:14px;display:flex;flex-direction:column;gap:8px"><span class="cap">NEXT ALBUMS</span><div class="qnext">${nxt.map(c =>
      `<button onclick="A.alPage(${arg(c.key)})"><b>${esc(c.album || c.folder.split(/[\\/]/).pop())}</b><br><span class="sub" style="font-size:12px">${esc((c.artist || 'no artist') + ' · ' + plural(c.open, 'song') + ' to decide')}</span></button>`).join('') || '<span class="sub">No more albums with songs to do.</span>'}</div></aside></div>`; }
  if (vw === 'albums') return head + banner + bars + `<section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:10px"><div class="fchips" role="group" aria-label="Filter">${tabs}</div></section>` + albumsView();
  if (vw === 'library') return head + banner + bars + `<section class="panel" style="padding:12px 14px"><div class="fchips" role="group" aria-label="Filter">${tabs}${sortRow}</div></section>` + libraryView(q);
  if (vw === 'quick') return head + banner + bars + `<section class="panel" style="padding:12px 14px"><div class="fchips" role="group" aria-label="Filter">${tabs}${sortRow}</div></section>` + quickView(q);
  return head + banner + bars + `<section class="panel rvfilters" aria-label="Filter, sort and group"><div class="rvfopts">${sortRow}${byArtist ? '' : groupRow}${chgRow()}<div class="fchips fltslot" role="group" aria-label="Filter">${tabs}</div></div></section><div class="rvwrap rvsplit" style="--rvL:${S.rvSplit || +store.get('rvSplit', 340) || 340}px">
    <section class="panel rvlist" data-ks="rvlist" aria-label="Needs review"><div class="row" style="justify-content:space-between;padding:2px 4px"><h2 style="margin:0;font-size:15px">Needs review</h2><span class="sub" style="font-size:12px">${fmt(counts.all)} left</span></div>
      ${bulkBar(q)}${list}</section>
    <div class="rvdiv" role="separator" aria-label="Drag to resize the two sides" title="Drag to make the list wider or narrower" onmousedown="A.rvResize(event)"></div>
    <section class="panel rvfocus" aria-label="Selected song">${S.rvGroupSel ? groupPanel(S.rvGroups[S.rvGroupSel.key] || S.rvGroupSel) : fx ? (S.rvCollapsed ? `<div class="row" style="gap:10px"><b style="font-size:16px">${esc(fx.tags.title || stem(fx.file))}</b><span class="sub">preview minimized · click the song again, or here, to open it</span><button class="btn small outline" onclick="S.rvCollapsed=false;render()">Open ▾</button></div>` : focusPanel(fx, q)) : `<div style="padding:40px 10px;text-align:center;display:flex;flex-direction:column;gap:8px;align-items:center">
      <span style="font-size:20px;font-weight:700;color:var(--green-text)">All reviewed</span><span class="sub">Every song has a decision. Next, check where everything will go.</span>
      <button class="btn amber" style="margin-top:8px;min-height:48px;font-size:15px" onclick="A.toPlan()">Go to Plan preview →</button></div>`}</section></div>`;
}
function pctColor(p) { return p >= 90 ? 'var(--green-text)' : p >= 60 ? 'var(--amber-text)' : 'var(--clay)'; }
function minPct(items) { const v = (items || []).map(x => x.match_pct).filter(v => v != null); return v.length ? Math.min(...v) : ''; }
// a song the album match left out (mostly: a different length) - match it anyway, by hand
function unmatchedPick(x, rel, ri) {
  const rid = regRel(rel), tr = rel.tracks || [], me = nkw(x.tags.title || stem(x.file));
  let best = -1;
  tr.forEach((t, i) => { const k = nkw(t.title); if (best < 0 && k && me && (k === me || k.startsWith(me) || me.startsWith(k))) best = i; });
  const bt = best >= 0 ? tr[best] : null;
  return `<span class="gtrk"><span class="sub">not matched${bt ? ' (length differs)' : ''}</span>
    ${bt ? `<button class="btn small outline" onclick="A.rvSlotR(${arg(x.id)},${rid},${best},1)" title="Same title, different length: use it anyway">Use ${esc(String(bt.track).padStart(2, '0') + ' ' + bt.title)}${bt.length ? ' · ' + mmss(bt.length) : ''}</button>` : ''}
    <select class="text" style="width:auto;max-width:240px;padding:3px 6px" onchange="if(this.value!=='')A.rvSlotR(${arg(x.id)},${rid},+this.value,1)"><option value="">Match to track…</option>${tr.map((t, i) => `<option value="${i}">${esc((t.disc > 1 ? t.disc + '-' : '') + String(t.track).padStart(2, '0') + ' ' + t.title + (t.length ? ' · ' + mmss(t.length) : ''))}</option>`).join('')}</select></span>`;
}
function groupPanel(g, inCard) {
  const st = S.rvGS[g.key] || (S.rvGS[g.key] = { q: [g.artist || '', g.album || ''] });
  const items = g.ids.map(i => S.rv.items.find(x => x.id === i)).filter(Boolean);
  const res = (st.releases || []).map((rel, ri) => {
    const rows = items.map(x => {
      const m = rel.map && rel.map[x.id], t = m && rel.tracks[m.i];
      return `<li class="gmap"><span class="gsong">${esc(x.tags.title || stem(x.file))} <span class="sub">${mmss(x.duration)}</span></span>
        <span class="garrow">→</span>${t ? `<span class="gtrk">${esc((t.disc > 1 ? t.disc + '-' : '') + String(t.track).padStart(2, '0') + ' ')}${diffHtml(t.title, x.tags.title)} <span style="color:${m.len_ok ? 'var(--green-text)' : 'var(--amber-text)'}">· ${esc(m.len_text)}</span></span>`
        : unmatchedPick(x, rel, ri)}</li>`;
    }).join('');
    return `<article class="relcard"><div class="row" style="gap:14px">${coverHtml(rel, true)}
      <div style="flex:1;min-width:0"><div style="font-weight:700;font-size:15px">${esc(rel.title)}</div>
        <div class="sub" style="font-size:13px">${esc([rel.artist, rel.year, RTYPE[rel.rtype] || rel.rtype, rel.disambiguation].filter(Boolean).join(' · '))}</div></div>
      <span class="srcchip">${esc(rel.source)}</span></div>
      <div class="row"><b style="color:${rel.matched === items.length ? 'var(--green-text)' : rel.matched ? 'var(--amber-text)' : 'var(--clay)'}">${rel.matched === items.length ? 'Album checks out ✓ · ' : ''}${rel.matched} of ${items.length} songs match</b><span class="sub" style="font-size:12px">${(rel.tracks || []).length} tracks on this release</span></div>
      <ul class="gmaps">${rows}</ul>
      <div class="acts">${rel.matched ? `<button class="btn amber small" onclick="A.rvGroupUse(${arg(g.key)},${ri})">Use this album for ${plural(rel.matched, 'song')}</button>` : ''}
        <button class="btn small ghost" onclick="S.rvGS[${arg(g.key)}].tracks=S.rvGS[${arg(g.key)}].tracks===${ri}?null:${ri};render()">${st.tracks === ri ? 'Hide the tracks' : 'Show all tracks (drag songs onto them)'}</button></div>
      ${st.tracks === ri ? releaseCard(null, rel, ri, true) : ''}</article>`;
  }).join('');
  return `<div class="row" style="gap:14px"><div style="flex:1;min-width:0"><span class="sub" style="font-size:12px;font-weight:700;letter-spacing:.5px">ALBUM GROUP</span>
      <div style="font-size:20px;font-weight:700">${esc(g.album || g.key)}</div><span class="sub">${esc((g.artist ? g.artist + ' · ' : '') + plural(items.length, 'song') + ' still to decide')}</span></div>
      <button class="btn small ghost" onclick="${inCard ? 'S.alMatchOpen=null;S.rvGroupSel=null;render()' : 'A.rvGroupClose()'}">${inCard ? 'Close' : 'Back to songs'}</button></div>
    <span class="sub" style="font-size:13px">Finds this album and matches every song of the group to its track (same version, length within 7 s). Only an album you pick is used.</span>
    <div class="tool"><div class="flds">${[['Artist', 'artist'], ['Album', 'album name']].map((f, i) =>
      `<label>${f[0]}<input id="gq_${i}" value="${esc(st.q[i] || '')}" placeholder="${f[1]}" oninput="S.rvGS[${arg(g.key)}].q[${i}]=this.value" onkeydown="if(event.key==='Enter')A.rvGroupSearch(${arg(g.key)})"></label>`).join('')}
      <button class="rcirc" aria-label="Copy artist and album" data-tip="Copy artist and album, to search for them on the web" onclick="A.rvGroupCopy(${arg(g.key)})">${svg('M9 9h10v11H9zM5 4h10v3M5 4v12h2', 16)}</button>
      <button class="btn amber" style="min-height:40px" onclick="A.rvGroupSearch(${arg(g.key)})" ${st.loading ? 'disabled' : ''}>${st.loading ? '<span class="spin"></span> Searching…' : 'Find this album'}</button></div>
      <label class="lbl">…or paste an album link (MusicBrainz, Discogs, Deezer, Apple Music, Spotify)
        <span class="row" style="gap:8px"><input class="mono grow" id="gl" value="${esc(st.link || '')}" placeholder="https://musicbrainz.org/release/…" oninput="S.rvGS[${arg(g.key)}].link=this.value" onkeydown="if(event.key==='Enter')A.rvGroupSearch(${arg(g.key)},true)">
        <button class="rcirc" aria-label="Paste a link" data-tip="Paste the link from your clipboard (then press Load album)" onclick="A.rvGroupPaste(${arg(g.key)})">${svg('M9 4h6v3H9zM7 5.5H5V21h14V5.5h-2M8 12h8M8 16h8', 16)}</button>
        <button class="btn small" onclick="A.rvGroupSearch(${arg(g.key)},true)" ${st.loading ? 'disabled' : ''}>Load album</button></span></label>
      ${st.err ? `<span style="font-size:13px;color:var(--clay)">${esc(st.err)}</span>` : ''}
      ${st.releases && !st.releases.length ? '<span style="font-size:13px">No album found. Try fewer words, or paste a link.</span>' : ''}</div>
    ${res}`;
}
// ---- differences between your tags and the new tags (word by word)
const nkw = w => String(w || '').toLowerCase().replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/ß/g, 'ss').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^\p{L}\p{N}]/gu, '');
function diffHtml(text, other) {
  text = String(text || '');
  if (!other || nkw(text) === nkw(other)) return esc(text);
  const set = new Set(String(other).split(/\s+/).map(nkw).filter(Boolean));
  return text.split(/(\s+)/).map(w => { const k = nkw(w); return k && !set.has(k) ? `<mark class="df">${esc(w)}</mark>` : esc(w); }).join('');
}
function placeTags(x) {             // Place: your file's own tags in a box of their own, with the cover; it stays in view while you scroll the tracks
  const t = x.tags, sites = (S.rv.sites || []).join(', ') || 'the music sites';
  const cv = S.rv && S.rv.cover_base ? `<img class="art big" src="${esc(S.rv.cover_base + encodeURIComponent(x.id))}" alt="" data-ph="art big" onerror="A.imgFail(this)">` : '<span class="art big">no cover</span>';
  const f = (l, v, note, wide) => (v || note) ? `<div class="pt${wide ? ' wide' : ''}"><span class="sub">${l}</span><b>${esc(v || '–')}</b>${note || ''}</div>` : '';
  const artNote = `<span class="pnote"><span class="okc">✓ Confirmed</span>${x.artist_found && nkw(x.artist_found) !== nkw(t.artist || '') ? ' <span class="sub">as ' + esc(x.artist_found) + '</span>' : ''}</span>`;
  return `<div class="placetags pstick"><div class="pcov"><span class="cap">YOUR FILE</span>${cv}</div><div class="pbody"><span class="cap" title="${esc(x.file)}">${esc(x.file)}</span>
    <div class="pgrid">${f('Title', t.title || stem(x.file), '', true)}${f('Artist', t.artist || x.artist_found || '', artNote)}${f('Release', t.album || '', t.album ? `<span class="pnote" title="not found on ${esc(sites)}"><span class="nfc">not found</span> <span class="sub">on ${esc(sites)}</span></span>` : '<span class="pnote sub">no album tag</span>')}
    ${f('Year', (t.year || '').slice(0, 4))}${f('Track', t.track ? String(t.track).split('/')[0] : '')}${f('Length', mmss(x.duration))}${t.albumartist && nkw(t.albumartist) !== nkw(t.artist || '') ? f('Album artist', t.albumartist) : ''}</div></div></div>`;
}
function myTags(x) {
  const t = x.tags;
  return `<div class="mytags"><span class="cap">YOUR FILE</span><b>${esc(t.title || stem(x.file))}</b><span>${esc([t.artist || 'no artist', t.album || 'no album', t.year, t.track ? 'track ' + t.track : '', mmss(x.duration), x.file].filter(Boolean).join(' · '))}</span></div>`;
}
// V2.0.6: a version label at the end of YOUR title ('(Rescored Alt)', '[Live 1979]') stays in the new title (same rule as the engine), so the preview shows it too
const VER_LAB = /\b(?:alt(?:ernate|ernative)?|re-?scor\w*|re-?record\w*|re-?edit\w*|unused|outtake|take\s*\d*|session|demo|rough|early|live|acoustic|instrumental|extended|radio|single|original|mono|stereo|mix|remix|edit|version|cut|film|score|theme|reprise|orchestral|karaoke|unplugged|rehearsal|bootleg)\b/i;
function withVer(newT, fileT) {
  newT = String(newT || ''); const t = String(fileT || '').trim();
  const m = t.match(/[\(\[]([^\(\)\[\]]{2,40})[\)\]]\s*$/) || t.match(/\s+-\s+([^-]{2,40})$/);
  if (!m) return newT; const lab = m[1].trim(); if (!VER_LAB.test(lab) || /re-?mast/i.test(lab)) return newT;
  const k = v => String(v).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''); if (k(lab) && k(newT).includes(k(lab))) return newT;
  return newT + ' (' + lab + ')';
}
function cmpTable(x, s, p) {
  const t = x.tags, tn = v => String(v || '').split('/')[0].replace(/^0+/, '');
  const rows = [
    ['Artist', t.artist, s.artist], ['Title', t.title || stem(x.file), withVer(s.title, t.title)], ['Album', t.album, s.release],
    ['Track', t.track ? tn(t.track) : '', s.track ? (s.disctotal > 1 ? s.disc + '-' : '') + tn(s.track) + (s.tracktotal ? ' of ' + s.tracktotal : '') : ''],
    ['Year', (t.year || '').slice(0, 4), s.year], ['Type', '', RTYPE[s.rtype] || s.rtype || ''],
    ['Length', mmss(x.duration), p && p.length ? mmss(p.length) + (p.len_text ? ' · ' + p.len_text : '') : '']];
  const trk = v => String(v || '').trim().split(' ')[0].split('-').pop().split('/')[0].replace(/^0+/, '');      // V2.0.6: "4", "4/11", "1-4 of 11" and "04" are all track 4
  const same = (a, b, f) => !a || !b || nkw(a) === nkw(b) || (/^\d/.test(a) && (f === 'Track' ? trk(a) === trk(b) : tn(a) === tn(String(b).split(' ')[0])));
  const full = S.diffMode === 'full', shown = rows.filter(r => (r[1] || r[2]) && (full || !same(r[1], r[2], r[0]) || r[0] === 'Length' || r[0] === 'Title'));
  const hidden = rows.filter(r => (r[1] || r[2])).length - shown.length;
  const oldCv = S.rv && S.rv.cover_base ? `<img class="art big" src="${esc(S.rv.cover_base + encodeURIComponent(x.id))}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'art big',textContent:'no cover'}))">` : '<span class="art big">no cover</span>';
  const coverRow = `<div class="row" style="gap:14px;align-items:center;flex-wrap:wrap"><span style="display:flex;flex-direction:column;align-items:center;gap:4px">${oldCv}<span class="sub" style="font-size:11px">YOUR FILE'S COVER</span></span><span style="font-size:20px;color:var(--amber-text)">→</span>
    <span style="display:flex;flex-direction:column;align-items:center;gap:4px">${coverHtml(s, true)}<span class="sub" style="font-size:11px">NEW COVER${s.source ? ' · ' + esc(s.source) : ''}</span></span>
    <span class="sub" style="font-size:12px;max-width:340px">The new cover is only used when this match is accepted. It is fetched at Copy &amp; tag (Settings: Covers).</span></div>`;
  return coverRow + `<div class="row" style="gap:8px;justify-content:space-between"><span class="seg small">${[['changes', 'Only what changes'], ['full', 'Full table']].map(o =>
      `<button aria-pressed="${(S.diffMode || 'changes') === o[0]}" onclick="A.diffSet(${arg(o[0])})">${o[1]}</button>`).join('')}</span>
      ${!full && hidden ? `<span class="sub" style="font-size:12px">${plural(hidden, 'field')} the same — hidden</span>` : ''}</div>
    <div class="cmpt" role="table" aria-label="Your file and the new tags"><div class="h" role="row"><span></span><span>YOUR FILE</span><span>NEW TAGS</span></div>
    ${shown.map(r => { const d = !same(r[1], r[2], r[0]), tk = r[0] === 'Track' && !d && r[1] && r[2];
      return `<div class="r ${d ? 'dif' : ''}" role="row"><span class="f">${r[0]}</span><span>${tk ? esc(r[1]) : r[1] ? diffHtml(r[1], r[2]) : `<i class="sub">${r[0] === 'Type' ? '–' : 'empty'}</i>`}</span><span>${tk ? esc(r[2]) : r[2] ? diffHtml(r[2], r[1]) : `<i class="sub">${r[0] === 'Length' ? '–' : 'kept'}</i>`}</span></div>`; }).join('')}</div>`;
}

// ---- Accept the sure ones
// 2.0.2: "Accept if… 95%" shows ONLY the songs from 95 up to (not including) the next step, so 100 = exactly 100, 95 = 95-99, 90 = 90-94, 80 = 80-89.
// The switch "only this band" can be turned off to get the old "at least" behaviour.
const SURE_STEPS = [100, 95, 90, 80];
function sureHi(min) { const i = SURE_STEPS.indexOf(min); return i > 0 && S.sureBand !== false ? SURE_STEPS[i - 1] : Infinity; }
function sureTxt(min) { min = min || S.sureMin || 90; const hi = sureHi(min); return hi === Infinity ? min + '%+' : (min === 100 ? '100%' : min + '–' + (hi - 1) + '%'); }
// 2.0.3: a song confirmed by a second site ("verified") counts as 100 here, whatever its own %, and carries a "verified" tag
function effPct(x) { return x.safe ? 100 : x.match_pct; }
function sureOnes(minArg) {
  if (!minArg && S._rc && S._rc.s) return S._rc.s;
  const out = sureOnes0(minArg); if (!minArg && S._rc) S._rc.s = out; return out;
}
function sureOnes0(minArg) {
  const min = minArg || S.sureMin || 90, hi = sureHi(min), inb = p => (p || 0) >= min && (p || 0) < hi;
  return S.rv ? S.rv.items.filter(x => !isDone(x) && (effKind(x) === 'match' && !isAside(x) && (x.sure || x.safe) && inb(effPct(x))
    || x.prep_sure && inb(x.prep_sure.match_pct))) : [];
}
function verifiedTip(x) {
  const v = x.verify || {}, src = (v.sources || []).join(' + ');
  return 'Verified: the match was confirmed by a second, independent source' + (src ? ' (' + src + ')' : '') + ': same artist, title, album and length, and no edition mismatch (remaster, live, deluxe…).';
}
function sureIds() { if (S._rc && S._rc.si) return S._rc.si; const r = new Set(sureOnes().map(x => x.id)); if (S._rc) S._rc.si = r; return r; }
function sureChange(x) {           // what accepting would use: the suggestion, or the Prepare Previews result
  if (effKind(x) === 'match' && x.sure && !isAside(x)) return { s: x.suggest, pct: x.match_pct, how: 'suggestion' };
  const c = x.prep_sure; return c ? { s: { title: c.title, artist: c.artist, release: c.release, year: c.year, track: c.track, disc: c.disc, disctotal: c.disctotal, rtype: c.rtype, source: c.source }, pct: c.match_pct, how: 'found by Prepare Previews', c } : null;
}
function moreMenu(inner, label, left) {            // 1.1.5: fewer buttons - the rarely used ones live behind one "More" button
  return `<details class="moremenu${left ? ' ml' : ''}"><summary class="btn small ghost">${left ? '<span class="mar"></span>' + (label || 'More') : (label || 'More') + ' ▾'}</summary><div class="moredrop">${inner}</div></details>`;
}
function prepBar() {                 // only the running part (progress); the buttons live in the action row
  // V2.0.5 (#10): two lanes can run together: Prepare Previews / Dig deeper (main) and Verify with other sites (verify)
  const one = (P, which) => {
    if (P && P.running && P.cancelled) return `<div class="surebar"><span class="spin"></span><b>Stopping…</b><span class="sub" style="font-size:13px">finishing the current search (${fmt(P.done)} of ${fmt(P.total)} done; their results are kept)</span></div>`;
    if (P && P.running) return `<div class="surebar"><span class="spin"></span><b>${P.mode === 'dig' ? 'Digging deeper' : P.mode === 'verify' ? 'Checking the other sites' : 'Preparing Previews'}</b><span class="sub" style="font-size:13px">${fmt(P.done)} of ${fmt(P.total)} searched · ${fmt(P.found)} with results · ${fmt(P.sure)} sure${P.cur ? ' · ' + esc(P.cur) : ''}</span>
    <div class="bar" style="flex:1 1 160px"><i style="width:${Math.round(P.done / Math.max(1, P.total) * 100)}%"></i></div>
    ${P.paused ? `<button class="btn small amber" onclick="A.prepPause(false,${arg(which)})">Resume</button>` : `<button class="btn small" onclick="A.prepPause(true,${arg(which)})">Pause</button>`}<button class="btn small ghost" onclick="A.prepCancel(${arg(which)})">Cancel</button>
    <span class="sub" style="font-size:12px;flex-basis:100%">You can keep working; results appear on the songs as they arrive ("results ready"). Everything found is saved, also for next time.</span></div>`;
    return '';
  };
  const h = one(S.B.prep, 'main') + one(S.B.vprep, 'verify');
  return h ? `<div id="prepbar" style="display:flex;flex-direction:column;gap:8px">${h}</div>` : '';
}
function autoSureMin() {          // 1.1.5: Accept if… starts at the highest % that has songs; after the 100% ones are accepted it moves to the next one
  if (S.sureMinUser || !S.rv) return;
  const hit = SURE_STEPS.find(v => sureOnes(v).length > 0);
  if (hit) S.sureMin = hit;
}
function actionRow(vw, noPrep) {
  autoSureMin();
  const showS = !vw || vw === 'songs' || vw === 'quick' || vw === 'library', showA = !vw || vw === 'albums' || vw === 'album' || vw === 'quick' || vw === 'library';
  const R = S.rv, P = S.B.prep, busy = P && P.running;
  const todo = R ? R.items.filter(x => (effKind(x) !== 'match' || isAside(x)) && !isDone(x) && !x.prep).length : 0;
  const dig = R ? R.items.filter(x => effKind(x) === 'none' && !isDone(x) && !x.dig).length : 0;
  const n = sureOnes().length, na = sureAlbums().length, last = S.lastSure;
  // the Accept-if row hides only when EVERY step (100/95/90/80) has nothing, not when the chosen step happens to be empty
  const anyS = SURE_STEPS.some(v => sureOnes(v).length > 0), anyA = SURE_STEPS.some(v => { const keep = S.sureMin; S.sureMin = v; const k = sureAlbums().length > 0; S.sureMin = keep; return k; });
  const sureRow = (showS && anyS) || (showA && anyA);
  const tip = t => `data-tip="${esc(t)}"`;
  const prepBtns = `<button class="btn amber" ${tip('Searches every song to place, not found or set aside in the background, so the results are ready when you open them. Sends only names and lengths. Results are saved and stay there next time.')} onclick="A.prepStart()" ${todo && !busy ? '' : 'disabled'}>${svg('M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18', 15)} Prepare Previews${todo ? ' (' + fmt(todo) + ')' : ''}</button>
    <button class="btn outline c-dig" ${tip('For songs nobody recognized: MusicBrainz IDs in the tags → classical search → title-only and file-name search → identify by sound (if set up). Runs in the background.')} onclick="A.digStart()" ${dig && !busy ? '' : 'disabled'}>${svg('M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-5-5M11 8v6M8 11h6', 15)} Dig deeper${dig ? ' (' + fmt(dig) + ')' : ''}</button><button class="btn small ghost" ${tip('Search ONLY the songs that are still not identified, once more (songs already identified are left alone).')} onclick="A.digStart(true)" ${busy ? 'disabled' : ''}>Search the unidentified again</button>`;
  const verBtns = '';          // V2.0.3: "Verify with other sites" and "Placed automatically" live on the Check tags page now
  if (vw === '__prep') return prepBtns + verBtns;
  if (noPrep && !sureRow && !last) return '';
  return `<div class="actrow">
    ${noPrep ? '' : prepBtns + '<span class="actsep"></span>' + verBtns + '<span class="actsep"></span>'}
    ${showS && anyS ? `<button class="btn green" ${tip('Same song title, same version, same artist (or a Prepare Previews result with the same length) and at least this % alike. You see every change first.')} onclick="A.rvSureAsk()" ${n ? '' : 'disabled'}>Accept if… (${fmt(n)})</button>` : ''}
    ${showA && anyA ? `<button class="btn green outline" ${tip('Whole albums where every open song points to the same found album and is at least this % alike. You see every album and every change first.')} onclick="A.alSureAsk()" ${na ? '' : 'disabled'}>Accept album if… (${fmt(na)})</button>` : ''}
    ${!sureRow ? '' : `<label class="sub" style="font-size:12px;display:flex;gap:6px;align-items:center" ${tip('A higher number = fewer mistakes. 100% shows only the 100% ones, 95% only 95-99%, 90% only 90-94%, 80% only 80-89%.')}>${S.sureBand === false ? 'at least' : 'only'} <select onchange="A.rvSureMin(this.value)">${[100, 95, 90, 80].map(v => `<option value="${v}" ${(S.sureMin || 90) === v ? 'selected' : ''}>${v}%</option>`).join('')}</select> alike <label class="sub" style="font-size:12px;display:inline-flex;gap:4px;align-items:center;cursor:pointer" ${tip('On: only this band (95 = 95-99%). Off: this % and everything above it.')}><input type="checkbox" ${S.sureBand === false ? '' : 'checked'} onchange="A.rvSureBand(this.checked)">only this band</label></label>`}
    ${last ? `<span style="font-size:12px">Accepted ${plural(last.length, 'song')}.</span><button class="btn small ghost" onclick="A.rvSureUndo()">Undo</button>` : ''}</div>`;
}
function sureBar() { return actionRow(); }
// 'Accept album if…': albums where every open song is a match to ONE found album, each sure and alike enough
function sureAlbums() {
  if (!S.rv) return [];
  const min = S.sureMin || 90, hi = sureHi(min), base = [S.rvVer || 0, JSON.stringify(S.alMove || {}).length, S.rv.items.length].join('|'), key = min + '|' + hi;
  // V2.0.6: one answer per "at least N%" step (the toolbar asks for every step on each redraw: with a single slot it worked everything out again 5 times, which made every click lag)
  if (!S._sa || S._sa.rv !== S.rv || S._sa.base !== base) S._sa = { rv: S.rv, base, map: new Map() };
  if (S._sa.map.has(key)) return S._sa.map.get(key);
  if (S._rc && !S._saForce && S._saLast && S._saLast.rv === S.rv) {         // redrawing (stepping through songs): show the last answer now, work out the new one when you pause
    clearTimeout(S._saT); S._saT = setTimeout(() => { S._saForce = true; try { sureAlbums(); } finally { S._saForce = false; } if (S.screen === 'review') render(); }, 700);
    S._sa.wait = true; return S._saLast.res;
  }
  const res = albumCards('all').filter(c => {
    const open = c.items.filter(x => !isDone(x) && !isAside(x));
    if (!open.length) return false;
    const rels = new Set(open.map(x => effKind(x) === 'match' ? x.suggest.release + '|' + (x.suggest.year || '') : '?'));
    return rels.size === 1 && !rels.has('?') && open.every(x => (x.sure || x.safe) && (effPct(x) || 0) >= min && (effPct(x) || 0) < hi);
  });
  S._sa.map.set(key, res); S._saLast = { rv: S.rv, res };
  return res;
}

// ---- Albums view: your albums as cards, songs side by side with the new tags
function albumKeyOf(x) {
  const mv = (S.alMove || {})[x.id]; if (mv) return mv;          // you moved it (drag, or 'Not from this album')
  return x.g_album ? 'a|' + x.g_album.toLowerCase() + '|' + (x.g_artist || '').toLowerCase() : 'f|' + x.folder;
}
function albumCards(fArg) {
  if (!S._rc) return albumCards0(fArg);
  const ck = 'ac|' + (fArg || ''); if (S._rc[ck]) return S._rc[ck];           // V2.0.6: once per redraw
  return (S._rc[ck] = albumCards0(fArg));
}
function albumCards0(fArg) {
  const f = fArg || S.rvFilter || 'all', m = new Map();
  S.rv.items.forEach(x => {
    if (f === 'sure' ? !sureIds().has(x.id) : f === 'aside' ? !isAside(x) : f === 'later' ? !isLater(x) : f === 'done' ? !isDone(x) : f !== 'all' && (effKind(x) !== f || isDone(x))) return;
    const k = albumKeyOf(x);
    if (!m.has(k)) m.set(k, k.startsWith('x|') ? { key: k, album: (x.tags.title || stem(x.file)) + ' — taken out of ' + (x.g_album || 'its folder'), artist: x.g_artist, folder: x.folder, items: [], single: true }
      : { key: k, album: x.g_album, artist: x.g_artist, folder: x.folder, items: [] });
    m.get(k).items.push(x);
  });
  const cards = [...m.values()];
  cards.forEach(c => {
    c.items.sort((a, b) => (isLater(a) - isLater(b)) || (parseInt(a.tags.disc) || 1) - (parseInt(b.tags.disc) || 1) || (parseInt(a.tags.track) || 999) - (parseInt(b.tags.track) || 999) || (a.tags.title || a.file).localeCompare(b.tags.title || b.file));
    c.open = c.items.filter(x => !isDone(x)).length;
    const ms = c.items.filter(x => effKind(x) === 'match');
    c.rels = [...new Set(ms.map(x => x.suggest.release + ' (' + (x.suggest.year || '?') + ') · ' + x.suggest.source))];
    c.checks = ms.length === c.items.length && c.rels.length === 1 && ms.every(x => x.sure && (x.match_pct || 0) >= 90);
    c.found = ms.length > 0 || c.items.some(x => isDone(x));          // an album was found (or you decided) - not one to search for
  });
  const by = S.alSort || 'todo';
  const art = (a, b) => (a.artist || '~').localeCompare(b.artist || '~'), alb = (a, b) => (a.album || '~').localeCompare(b.album || '~');
  // open albums first; found albums before ones you still have to search for; then most to do, artist, album
  const splitEnd = c => (c.single && c.items.every(x => x.mixed)) ? 1 : 0;          // V2.0.6: songs taken out with Split up sit at the very end
  cards.sort((a, b) => (splitEnd(a) - splitEnd(b)) || (!a.open - !b.open) || (!a.found - !b.found) || (by === 'todo' ? b.open - a.open || art(a, b) || alb(a, b)
    : by === 'album' ? alb(a, b) : art(a, b) || alb(a, b)));
  return cards;
}
function songCell(x) {
  const k = effKind(x), dn = isDone(x);
  const badge = `<span class="bd"><span class="kbadge" style="color:${dn ? 'var(--green-text)' : KCT()[k]}">${esc(isAside(x) ? 'Not this' : badgeOf(x))}</span>${isLater(x) ? '<span class="ltag">Later</span>' : ''}</span>`;
  let right;
  if (k === 'match' && !dn) {
    const s = x.suggest;
    right = `<span class="nt"><b>${diffHtml(withVer(s.title, x.tags.title), x.tags.title)}</b><span>${diffHtml(s.artist, x.tags.artist)} · ${diffHtml(s.release, x.tags.album)}${s.year ? ' · ' + esc(s.year) : ''}${s.track ? ' · track ' + esc(s.track) : ''}</span></span>
      ${x.match_pct != null ? `<span class="pct" style="color:${pctColor(x.match_pct)}">${x.match_pct}%</span>` : ''}`;
  } else if (dn) right = `<span class="nt sub"><span>${esc(x.decision.label || badgeOf(x))}</span></span>`;
  else right = `<span class="nt sub"><span>${k === 'place' ? 'artist confirmed · drag onto a track or open' : esc(x.why || 'not found')}</span></span>`;
  return { badge, right: `<span class="rt">${right}</span>` };
}
const RI = { ok: 'M5 12l5 5L20 7', match: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4', split: 'M12 3v6M12 9l-6 6M12 9l6 6M6 15v6M18 15v6', trust: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z', group: 'M3 6h18M3 12h12M3 18h8',
  later: 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', leave: 'M6 6l12 12M18 6L6 18', dig: 'M3 12h4l3-8 4 16 3-8h4', sound: 'M3 12h2M7 8v8M11 4v16M15 8v8M19 11v2', undo: 'M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3',
  min: 'M5 12h14', open: 'M12 5v14M5 12h14', found: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6' };
const rb = (cls, ic, label, on, tip, pct) => `<button class="btn small ${cls || ''}" onclick="${on}" ${tip ? `data-tip="${esc(tip)}"` : ''} ${pct != null && pct !== '' ? `data-pct="${pct}"` : ''}>${ic ? svg(RI[ic], 14) : ''}<span>${label}</span></button>`;
const trackNo = (x, n) => { const t = parseInt(String(x.tags.track || '').split('/')[0], 10); return t > 0 ? t : n; };
function alTrack(x, n, mode) {                   // one numbered track row, shared by the album boxes and the album page
  const { badge, right } = songCell(x), ex = S.alRow === x.id, dn = isDone(x), k = effKind(x), id = arg(x.id);
  const chk = mode === 'page'
    ? `<input type="checkbox" class="qck" aria-label="Select (press and drag down to select many)" ${S.alSel[x.id] ? 'checked' : ''} onmousedown="A.alSelDown(event,${id})" onclick="event.preventDefault()">`
    : `<input type="checkbox" class="qck" aria-label="Select" ${S.rvChecked[x.id] ? 'checked' : ''} onclick="A.rvCheck(event,${id})">`;
  const acts = dn ? rb('ghost', 'undo', 'Undo', `A.alDecide(${id},'undo')`, 'Move this song back to Review so you can decide again')
    : ((k === 'match' ? rb('green', 'ok', 'Accept', `A.alDecide(${id},'accept')`, 'Accept (A)', x.match_pct) : '') + rb('c-dig', 'dig', 'Dig in', `A.alTool(${id},'digin')`, 'Search by hand, Dig deeper and Identify by sound') + '<span class="vsep"></span>' + rb('c-edit', 'edit', 'Edit manually', `A.alTagEdit(${id})`, 'Change the tags yourself: artist, title, album, year, track, genre'));
  const more = (!dn ? `<button class="btn small ghost" onclick="A.alDecide(${id},'leave')" data-tip="Not copied anywhere; the original stays. Undo any time.">Leave out</button><button class="btn small ghost" onclick="A.alDecide(${id},'trust')" data-tip="Place this one song using your tags">Trust tags</button><button class="btn small ghost" onclick="A.alDecide(${id},'unverified')" data-tip="Only this song; goes to _Unverified">Keep in _Unverified</button>` : '')
    + `<button class="btn small ghost" onclick="A.alNot(${id})" data-tip="This song is not from this album: it is taken out and matched on its own">Not from this album</button>`;
  return `<div class="alrow ${ex ? 'ex' : ''} ${dn ? 'dn' : ''} ${isLater(x) && !dn ? 'lat' : ''} ${S.alSel[x.id] ? 'sel' : ''}" data-id="${esc(x.id)}" ${mode === 'page' ? `onmouseenter="A.alSelEnter(${id})"` : ''} draggable="true" ondragstart="S.rvDrag=${id};try{event.dataTransfer.setData('text/plain',${id});event.dataTransfer.effectAllowed='move'}catch(e){}" ondragend="S.rvDrag=null">
      <span class="grip" title="Drag this song onto a track of another album (or onto another album)">⠿</span>${chk}<span class="tno">${trackNo(x, n)}</span>
      <button class="pv ${S.playing === x.id ? 'on' : ''}" aria-label="Play" onclick="A.play(${id})">${S.playing === x.id ? '❚❚' : '▶'}</button>
      <button class="mine" onclick="A.alRowOpen(${id})" title="${esc(x.file)}"><b>${k === 'match' && !dn ? diffHtml(x.tags.title || stem(x.file), withVer(x.suggest.title, x.tags.title)) : esc(x.tags.title || stem(x.file))}</b><span>${k === 'match' && !dn && x.tags.artist ? diffHtml(x.tags.artist, x.suggest.artist) + esc(' · ' + mmss(x.duration)) : esc((x.tags.artist || 'no artist') + ' · ' + mmss(x.duration))}</span></button>
      <span class="arr" aria-hidden="true">→</span>${right}${badge}
      <span class="racts">${acts}${moreMenu(more)}</span></div>`;
}
function alRowsHtml(c, mode, cap) {              // numbered rows; undecided first, decided behind a thin line; optional grouping by real album
  const sections = new Map(), undone = c.items.filter(x => !isDone(x)), done = c.items.filter(isDone);
  undone.concat(done).forEach(x => { const r = S.alByReal ? realAlbumOf(x) : ''; if (!sections.has(r)) sections.set(r, []); sections.get(r).push(x); });
  let seenDone = false, n = 0, shown = 0;
  const html = [...sections.entries()].map(([r, xs]) => (r ? `<div class="qsec"><b>${esc(r)}</b><span class="sub">${plural(xs.length, 'song')}</span></div>` : '') + xs.map(x => {
    if (shown >= cap) return ''; shown++; n++;
    const dn = isDone(x), divider = dn && !seenDone && done.length < c.items.length ? (seenDone = true, `<div class="qsec"><b>DECIDED · ${done.length}</b></div>`) : (seenDone = seenDone || dn, '');
    return divider + alTrack(x, n, mode);
  }).join('')).join('');
  return { html, hidden: Math.max(0, c.items.length - shown) };
}
function alBar(c, nm, opts) {                    // the album buttons, always outside (no More): Accept · Match | Split up | Trust tags · Group | Later · Leave out
  const k = arg(c.key), o = opts || {}, sep = '<span class="vsep"></span>', mixed = c.items.every(x => x.mixed), g = S.rvGroups['AL|' + c.key] || S.rvGroups['AP|' + c.key];
  const gs = S.rvGS[(g && g.key) || ''];
  return `<div class="acts albar">${nm ? rb('green', 'ok', `Accept album (${nm})`, `A.alAll(${k},'accept')`, 'Accept every song that has a match', minPct(c.items.filter(x => effKind(x) === 'match' && !isDone(x)))) : ''}${o.acceptIf || ''}
    ${c.open ? rb('amber', 'match', gs ? 'Find another album' : 'Match album', o.matchOn || `A.alMatch(${k})`, 'Find this album on the music sites and match every song to its track') : ''}${o.selMatch || ''}${sep}
    ${rb(mixed ? 'outline' : '', 'split', mixed ? 'One album after all' : 'Split up', `A.alSplit(${k})`, 'Songs from different albums tagged as one: match each song on its own')}${sep}
    ${c.open ? rb('', 'trust', 'Trust tags', `A.alTrustAsk(${k})`, 'Place this whole album using YOUR tags exactly (box sets and bootlegs no site knows). You see the result first.') : ''}${o.matchOn ? rb(S.alByReal ? 'outline' : '', 'group', S.alByReal ? 'Show in track order' : 'Group by real albums', 'S.alByReal=!S.alByReal;render()', 'Songs that belong to different real albums are shown in groups') : ''}${sep}
    ${c.open ? rb('', 'later', 'Later', `A.alAll(${k},'later')`) + rb('', 'leave', 'Leave out', `A.alAll(${k},'leave')`, 'Leave this whole album out: not copied anywhere, the original stays. Undo any time.') : ''}
    ${c.items.some(isDone) ? rb('ghost', 'undo', 'Undo all', `A.alRedoAll(${k})`, 'Move every decided song of this album back to Review') : ''}${o.right || ''}</div>`;
}
let SIDE_MATCH = false;      // V2.0.6: in the Box layout, Match album opens on the RIGHT (next to the songs), not under the album
function albumCard(c, idx) {
  const g = { key: 'AL|' + c.key, ids: c.items.filter(x => !isDone(x)).map(x => x.id), album: c.album || '', artist: c.artist || '' };
  S.rvGroups[g.key] = g;
  const opened = S.alOpen[c.key] != null ? S.alOpen[c.key] : (!!c.open || S.rvFilter === 'done') && (idx == null || idx < 6);
  const nm = c.items.filter(x => effKind(x) === 'match' && !isDone(x)).length;
  const st = c.checks ? `<span class="chk ok">Checks out ✓</span>` : !c.open ? `<span class="chk ok">All decided</span>`
    : c.rels.length > 1 ? `<span class="chk warn" title="${esc(c.rels.join('\n'))}">Songs suggested on ${c.rels.length} different albums</span>` : `<span class="chk warn">${plural(c.open, 'song')} to decide</span>`;
  const found = c.found ? `<span class="chk found" title="An album was found for these songs">${svg(RI.found, 13)} Album found</span>` : '';
  const akOn = g.ids.length > 0 && g.ids.every(i => S.rvChecked[i]);
  const akBox = g.ids.length ? `<input type="checkbox" class="qck akck" aria-label="Select this album (press and drag down to select many albums)" title="Select this album: press and drag down to select many" ${akOn ? 'checked' : ''} onmousedown="A.akDown(event,${arg(c.key)})" onclick="event.preventDefault();event.stopPropagation()">` : '';
  const head = `<div class="alhead" onclick="if(!event.target.closest('button,input'))A.alToggle(${arg(c.key)})">${akBox}<button class="gtog" aria-expanded="${opened}" aria-label="${opened ? 'Minimize' : 'Open'} this album" onclick="A.alToggle(${arg(c.key)})">${opened ? '▾' : '▸'}</button>${albCover(c.items)}
    <div class="alname" title="Click to open or close"><b>${esc(c.album || c.folder.split(/[\\/]/).pop())}</b><span>${esc([c.artist || (c.album ? '' : 'folder · no album tag'), plural(c.items.length, 'song'), c.rels.length === 1 ? 'suggested: ' + c.rels[0] : ''].filter(Boolean).join(' · '))}</span></div>
    <button class="btn small ghost" onclick="A.alPage(${arg(c.key)})" title="Solo this album: open it on its own page">Solo album</button>${nm ? `<button class="btn small green" onclick="A.alAll(${arg(c.key)},'accept')" title="Accept every song of this album that has a match">${svg('M5 12l5 5L20 7', 13)} Accept album (${nm})</button>` : ''}<span class="alchips2">${found}${st}</span></div>`;
  const dropAttr = `${g.ids.length ? `onmouseenter="A.akEnter(${arg(c.key)})"` : ''} ondragover="if(S.rvDrag){event.preventDefault();this.classList.add('over')}" ondragleave="this.classList.remove('over')" ondrop="A.alDropCard(event,${arg(c.key)})"`;
  if (!opened) return `<article class="alcard ${c.open ? '' : 'alldone'} ${akOn ? 'akon' : ''}" data-alkey="${esc(c.key)}" ${dropAttr}>${head}</article>`;
  const cap = (S.alAll || {})[c.key] ? 1e9 : 30, R = alRowsHtml(c, 'card', cap), gs = S.rvGS[g.key];
  const place = c.items.some(x => !isDone(x) && !isAside(x) && effKind(x) !== 'match') ? rb('amber', 'match', 'Place all', `A.alPlaceAll(${arg(c.key)})`, 'Finds the album and places every song on its track when they all fit') : '';
  return `<article class="alcard ${akOn ? 'akon' : ''}" data-alkey="${esc(c.key)}" ${dropAttr}>${head}<div class="alline"></div>
    <div class="alrows">${R.html}${R.hidden ? `<button class="btn small outline" onclick="S.alAll=S.alAll||{};S.alAll[${arg(c.key)}]=true;render()">Show all ${fmt(c.items.length)} songs (${fmt(R.hidden)} more)</button>` : ''}</div>
    ${gs && S.alMatchOpen === c.key && !SIDE_MATCH ? `<div class="alx">${groupPanel(g, true)}</div>` : ''}</article>`;
}
function selAlbums(cards) {                      // albums whose every open song is ticked
  return (cards || albumCards()).filter(c => { const ids = c.items.filter(x => !isDone(x)).map(x => x.id); return ids.length && ids.every(i => S.rvChecked[i]); });
}
function albSelBar(cards) {                      // one page-wide panel under the albums: what you can do with the selected album(s)
  const sel = selAlbums(cards);
  if (!sel.length) {                                // 2.0.2: ticked loose songs use this same panel (their buttons used to sit in a second bar at the top)
    const ticked = S.rv.items.filter(x => S.rvChecked[x.id]); if (!ticked.length) return '';
    return `<section class="albsel" aria-label="Selected songs">${bulkBar(ticked, false, true)}</section>`;
  }
  const one = sel.length === 1, c0 = sel[0];
  const nm = sel.reduce((n, c) => n + c.items.filter(x => effKind(x) === 'match' && !isDone(x)).length, 0);
  const songs = sel.reduce((n, c) => n + c.items.filter(x => !isDone(x)).length, 0);
  const anyOpenFind = sel.some(c => c.open);
  const b = (cls, ic, label, on, tipTxt, pct) => rb(cls, ic, label, on, tipTxt, pct);
  return `<section class="albsel" aria-label="Selected albums"><div class="albsel-t"><b>${one ? '1 album selected' : plural(sel.length, 'album') + ' selected'}</b><span class="sub">${one ? esc((c0.album || c0.folder.split(/[\\/]/).pop()) + ' · ' + plural(songs, 'song')) : plural(songs, 'song') + ' to decide'}</span></div>
    <div class="acts">${nm ? b('green', 'ok', one ? `Accept album (${nm})` : `Accept albums (${nm})`, 'A.alSelDo(\'accept\')', 'Accept every song that has a match', minPct(sel.flatMap(c => c.items.filter(x => effKind(x) === 'match' && !isDone(x))))) : ''}${anyOpenFind ? b('amber', 'match', one ? 'Match album' : 'Match albums', 'A.alSelDo(\'match\')', one ? 'Find this album on the music sites and match every song to its track' : 'Find each album and place all its songs when every one fits. The rest stay for you.') : ''}<span class="vsep"></span>
      ${b('', 'split', 'Split up', 'A.akSplit()', 'Songs from different albums tagged as one: match each song on its own')}${anyOpenFind ? b('', 'trust', 'Trust tags', 'A.alSelDo(\'trust\')', 'Place the whole album using YOUR tags exactly. You see the result first.') : ''}<span class="vsep"></span>
      ${anyOpenFind ? b('', 'later', 'Later', 'A.alSelDo(\'later\')') + b('', 'leave', 'Leave out', 'A.alSelDo(\'leave\')', 'Not copied anywhere, the originals stay. Undo any time.') : ''}
      <span class="bulkr">${b('ghost', 'undo', 'Undo all', 'A.alSelDo(\'undo\')', 'Move every decided song of the selected albums back to Review')}${b('ghost', '', 'Clear', 'A.rvCheckAll(false)', 'Unselect')}</span></div></section>`;
}
function albumsView() {
  S.rvGroups = {};
  const cards = albumCards();
  const open = cards.filter(c => c.open).length;
  const allOpen = cards.length > 0 && cards.every((c, i) => S.alOpen[c.key] != null ? S.alOpen[c.key] : (!!c.open || S.rvFilter === 'done') && i < 6);
  const sel = selAlbums(cards), cov = new Set(sel.flatMap(c => c.items.filter(x => !isDone(x)).map(x => x.id)));
  const extra = Object.keys(S.rvChecked).filter(i => S.rvChecked[i] && !cov.has(i)).length;
  return `<div class="alview">${bulkBar(cards.flatMap(c => c.items), true)}
    <div class="row" style="gap:8px"><button class="btn small amber" onclick="A.placeAllAlbums()" ${S.placeBusy ? 'disabled' : ''} title="For every album with songs to place: finds the album and places all its songs when every one fits. The rest is left for you. Redo moves any back.">${S.placeBusy ? '<span class="spin"></span> Placing…' : 'Place all albums'}</button><span class="sub" style="font-size:12px">Sort</span><span class="seg small">${[['todo', 'Most to do'], ['artist', 'Artist'], ['album', 'Album'], ['artists', 'Artists']].map(o =>
      `<button aria-pressed="${(S.alSort || 'todo') === o[0]}" onclick="A.alSortBy(${arg(o[0])})">${o[1]}</button>`).join('')}</span>
      <span class="vsep"></span>${allOpen ? rb('', 'min', 'Minimize all', 'A.alOpenAll(false)', 'Close every album box') : rb('', 'open', 'Open all', 'A.alOpenAll(true)', 'Open every album box')}${rb(S.alByReal ? 'outline' : '', 'group', 'Group by real albums', 'S.alByReal=!S.alByReal;render()', 'Songs that belong to different real albums are shown in groups')}${rb('', 'ok', 'Select all', 'A.alCheckAll()', 'Tick every song shown (then Accept / Match / Later above)')}${rb('', 'group', S.alLayout === 'classic' ? 'Box layout' : 'Classic layout', 'A.alLayoutToggle()', 'Switch how the album boxes look: Box layout (header, line, numbered rows, details on the right) or the Classic one')}<span class="sub" style="font-size:12px" title="Found albums first, albums to search for at the end. Drag a song onto a track of any album shown.">${plural(open, 'album')} to do ⓘ</span></div>
    <div class="alsplit${S.alLayout === 'classic' ? '' : ' lc'}"><div class="alleft">${(SIDE_MATCH = S.alLayout !== 'classic', (S.alSort || 'todo') === 'artists' ? artistBlocks(cards) : pagedCards(cards))}${albSelBar(cards)}</div>${(() => { try { return detailPane(); } finally { SIDE_MATCH = false; } })()}</div></div>`;
}
function detailPane() {                         // layout C: the details of the clicked song sit on the right
  const x = S.alRow && S.rv.items.find(i => i.id === S.alRow);
  const mg = SIDE_MATCH && S.alMatchOpen && S.rvGroups['AL|' + S.alMatchOpen], mgs = mg && S.rvGS[mg.key];
  const side = mgs ? `<section class="panel alx" style="padding:12px;margin-bottom:10px">${groupPanel(mg, true)}</section>` : '';
  return `<aside class="aldetail">${side}${x ? `<div class="alx">${focusPanel(x, rvQueue())}</div>` : side ? '' : '<div class="panel empty" style="font-size:13px">Click a song to see its details here: compare tags, Dig deeper, Identify by sound.</div>'}</aside>`;
}
function pagedCards(cards) {
  const lim = S.alLimit || 40, shown = cards.slice(0, lim);
  return (shown.map((c, i) => albumCard(c, i)).join('') || '<div class="panel empty">Nothing here.</div>')
    + (cards.length > lim ? `<div class="row"><button class="btn outline" onclick="S.alLimit=${lim + 40};render()">Show 40 more albums (${fmt(cards.length - lim)} left)</button></div>` : '');
}
// 2.0.2 (item 76): leave a whole artist out of the library. Two clicks (the second confirms); Undo works per song as always.
function leaveArtistBtn(gkey) {
  const g = S.rvGroups[gkey], n = g ? g.ids.length : 0; if (!n) return '';
  const ask = S.arLeaveAsk === gkey;
  return `<button class="btn small ${ask ? 'amber' : 'ghost'} leaveart" onclick="event.stopPropagation();A.leaveArtist(${arg(gkey)})" data-tip="Leave this whole artist out: nothing of theirs is copied, the originals stay where they are. You can undo it song by song.">${svg('M18 6L6 18M6 6l12 12', 13)} ${ask ? 'Sure? Leave out ' + plural(n, 'song') : 'Leave out artist'}</button>`;
}
function artistBlocksClassic(cards) {
  const by = new Map();
  cards.forEach(c => { const a = c.artist || '(no artist tag)'; if (!by.has(a)) by.set(a, []); by.get(a).push(c); });
  const arts = [...by.entries()].sort((a, b) => (!b[1].some(c => c.open) - !a[1].some(c => c.open)) || a[0].localeCompare(b[0]));
  const lim = S.arLimit || 40;
  return arts.slice(0, lim).map(([a, cs]) => {
    const open = S.arOpen[a] != null ? S.arOpen[a] : cs.some(c => c.open), todo = cs.reduce((n, c) => n + c.open, 0);
    cs.sort((x, y) => (!x.open - !y.open) || y.open - x.open || (x.album || '~').localeCompare(y.album || '~'));   // unfinished albums first
    const chips = cs.map(c => `<button class="alchip ${c.open ? 'todo' : 'ok'}" onclick="A.arChip(${arg(a)},${arg(c.key)})" title="${esc(c.album || c.folder)}">${esc(c.album || c.folder.split(/[\\/]/).pop())} <span>${c.open ? c.open + ' to do' : '✓'}</span></button>`).join('');
    const arg_ = { key: 'AR|' + a, artist: a, ids: cs.flatMap(c => c.items.filter(x => !isDone(x)).map(x => x.id)) };
    S.rvGroups[arg_.key] = arg_;
    const arOn = arg_.ids.length > 0 && arg_.ids.every(i => S.rvChecked[i]);
    const arBox = arg_.ids.length ? `<input type="checkbox" class="qck akck" aria-label="Select all albums of this artist (press and drag down to select many)" title="Select all albums of this artist: press and drag down to select many" ${arOn ? 'checked' : ''} onmousedown="A.akDown(event,${arg(arg_.key)})" onclick="event.preventDefault();event.stopPropagation()">` : '';
    return `<section class="artblock ${arOn ? 'akon' : ''}" data-arkey="${esc(a)}" ${arg_.ids.length ? `onmouseenter="A.akEnter(${arg(arg_.key)})"` : ''}><div class="arthead">${arBox}<button class="gtog" aria-expanded="${open}" onclick="A.arToggle(${arg(a)})">${open ? '▾' : '▸'}</button>
      <b>${esc(a)}</b><span class="sub" style="font-size:12px">${plural(cs.length, 'album')} · ${plural(cs.reduce((n, c) => n + c.items.length, 0), 'song')}</span>
      ${todo ? `<span class="chk warn">${plural(todo, 'song')} to decide</span>` : '<span class="chk ok">All decided</span>'}${todo ? leaveArtistBtn(arg_.key) : ''}</div>
      <div class="alchips">${chips}</div>
      ${open ? `<div class="artalbums"><span class="sub" style="font-size:12px">Drag a song (⠿) onto another album of this artist to move it there.</span>${cs.map(albumCard).join('')}</div>` : ''}</section>`;
  }).join('') + (arts.length > lim ? `<div class="row"><button class="btn outline" onclick="S.arLimit=${lim + 40};render()">Show 40 more artists (${fmt(arts.length - lim)} left)</button></div>` : '') || '<div class="panel empty">Nothing here.</div>';
}

// V2.0.6: Artists as a list (layout B): one line per artist with a progress strip, albums as plain rows, an album opens in place
function artistBlocks(cards) {
  const lay = (S.arLayout = S.arLayout || store.get('arLayout', 'list'));
  const sw = `<div class="arbar"><input id="arq" class="arsearch" placeholder="Search artist…" value="${esc(S.arQ || '')}" oninput="A.arSearch(this.value)"><label class="sub"><input type="checkbox" ${S.arHide ? 'checked' : ''} onchange="A.arHideSet(this.checked)"> Hide finished artists</label><span class="grow"></span><button class="btn small ghost" onclick="A.arLayout('${lay === 'list' ? 'classic' : 'list'}')" title="Switch between the new list and the old layout">${lay === 'list' ? 'Old artist layout' : 'New artist list'}</button></div>`;
  if (lay === 'classic') return sw + artistBlocksClassic(cards);
  const by = new Map();
  cards.forEach(c => { const a = c.artist || '(no artist tag)'; if (!by.has(a)) by.set(a, []); by.get(a).push(c); });
  const q = (S.arQ || '').trim().toLowerCase();
  let arts = [...by.entries()].filter(([a, cs]) => (!q || a.toLowerCase().includes(q)) && (!S.arHide || cs.some(c => c.open)));
  arts.sort((a, b) => (!b[1].some(c => c.open) - !a[1].some(c => c.open)) || a[0].localeCompare(b[0]));    // artists with work first, finished ones last
  const lim = S.arLimit || 40;
  const rows = arts.slice(0, lim).map(([a, cs]) => {
    const open = !!S.arOpen[a], todo = cs.reduce((n, c) => n + c.open, 0), songs = cs.reduce((n, c) => n + c.items.length, 0);
    cs.sort((x, y) => (!x.open - !y.open) || y.open - x.open || (x.album || '~').localeCompare(y.album || '~'));
    const arg_ = { key: 'AR|' + a, artist: a, ids: cs.flatMap(c => c.items.filter(x => !isDone(x)).map(x => x.id)) };
    S.rvGroups[arg_.key] = arg_;
    const arOn = arg_.ids.length > 0 && arg_.ids.every(i => S.rvChecked[i]);
    const arBox = arg_.ids.length ? `<input type="checkbox" class="qck akck" aria-label="Select all albums of this artist" title="Select all albums of this artist: press and drag down to select many" ${arOn ? 'checked' : ''} onmousedown="A.akDown(event,${arg(arg_.key)})" onclick="event.preventDefault();event.stopPropagation()">` : '<span style="width:18px"></span>';
    const strip = `<div class="arstrip">${cs.map(c => `<i class="${c.open ? 't' : ''}" title="${esc((c.album || c.folder.split(/[\\/]/).pop()) + ' · ' + plural(c.items.length, 'song') + ' · ' + (c.open ? c.open + ' to decide' : 'done'))}"></i>`).join('')}</div>`;
    let body = '';
    if (open) body = `<div class="artalbums">${cs.map(c => S.alOpen[c.key] ? albumCard(c) : `<div class="alrowc ${c.open ? '' : 'fin'}"><span class="grow"><b>${esc(c.album || c.folder.split(/[\\/]/).pop())}</b> <span class="sub">· ${plural(c.items.length, 'song')}</span></span>${c.open ? `<span class="chk warn">${c.open} to decide</span>` : '<span class="chk ok">✓ All decided</span>'}<button class="btn small ${c.open ? 'amber' : 'ghost'}" onclick="A.arAl(${arg(c.key)})">${c.open ? 'Open' : 'View'}</button></div>`).join('')}${todo ? `<div class="row" style="gap:8px">${leaveArtistBtn(arg_.key)}</div>` : ''}</div>`;
    return `<section class="artblock arl ${arOn ? 'akon' : ''} ${todo ? '' : 'fin'}" data-arkey="${esc(a)}" ${arg_.ids.length ? `onmouseenter="A.akEnter(${arg(arg_.key)})"` : ''}><div class="arthead">${arBox}<button class="gtog" aria-expanded="${open}" onclick="A.arTog2(${arg(a)})">${open ? '▾' : '▸'}</button>${libAvatar(a, 34)}<b class="arname" onclick="A.arTog2(${arg(a)})">${esc(a)}</b>
      <div class="arstripw" onclick="A.arTog2(${arg(a)})">${strip}<span class="sub" style="font-size:12px">${plural(cs.length, 'album')} · ${plural(songs, 'song')}</span></div>
      ${todo ? `<span class="chk warn">${plural(todo, 'song')} to decide</span><button class="btn small outline" onclick="event.stopPropagation();A.soloArtist(${arg(a)})" title="Quick mode on this artist only: song after song, album by album">Solo artist</button>` : '<span class="chk ok">✓ All decided</span>'}</div>${body}</section>`;
  }).join('') + (arts.length > lim ? `<div class="row"><button class="btn outline" onclick="S.arLimit=${lim + 40};render()">Show 40 more artists (${fmt(arts.length - lim)} left)</button></div>` : '');
  setTimeout(() => libWantPics(arts.slice(0, lim).map(x => x[0]).filter(n => n !== '(no artist tag)')), 0);      // artist photos (Deezer), asked once per name
  return sw + `<div class="sub" style="font-size:12px;margin:2px 0 6px">${fmt(arts.length)} of ${fmt(by.size)} artists</div>` + (rows || '<div class="panel empty">Nothing here.</div>');
}

// ---- Album page: one album at a time, each song editable on its own
function realAlbumOf(x) {
  const d = x.decision;
  if (d && d.label && (d.action === 'pick' || d.action === 'accept')) return d.label.split(' · ')[0].replace(/, track \d+$/, '');
  if (d && d.action === 'unverified') return 'Kept with your tags (_Unverified)';
  if (effKind(x) === 'match' && !isAside(x)) return (x.suggest.release || '?') + (x.suggest.year ? ' (' + x.suggest.year + ')' : '') + ' · suggested';
  return 'Not matched yet';
}
function albumPage() {
  const cards = albumCards('all');
  if (!cards.length) return '<div class="panel empty">Nothing here.</div>';
  let i = cards.findIndex(c => c.key === S.alKey); if (i < 0) { i = Math.max(0, cards.findIndex(c => c.open)); S.alKey = cards[i].key; }
  const c = cards[i], ids = c.items.map(x => x.id), mixed = c.items.every(x => x.mixed);
  const g = { key: 'AP|' + c.key, ids: c.items.filter(x => !isDone(x)).map(x => x.id), album: c.album || '', artist: c.artist || '' };
  S.rvGroups[g.key] = g;
  const selIds = ids.filter(k => S.alSel[k]);
  if (selIds.length) S.rvGroups['APS|' + c.key] = { key: 'APS|' + c.key, ids: selIds, album: c.album || '', artist: c.artist || '' };
  const nm = c.items.filter(x => effKind(x) === 'match' && !isDone(x)).length;
  const R = alRowsHtml(c, 'page', 1e9), rows = R.html;
  return `<section class="panel albumpage"><div class="alsticky"><div class="row" style="gap:10px">
      <button class="arrow" aria-label="Previous album" onclick="A.alPageMove(-1)" ${i ? '' : 'disabled'}>←</button>
      <div style="flex:1;min-width:0"><span class="cap">ALBUM ${i + 1} OF ${cards.length}</span><div style="font-size:22px;font-weight:700;overflow-wrap:anywhere">${esc(c.album || c.folder.split(/[\\/]/).pop())}</div>
        <span class="sub">${esc([c.artist, plural(c.items.length, 'song'), c.open ? plural(c.open, 'song') + ' to decide' : 'all decided', c.album ? '' : 'folder: ' + c.folder].filter(Boolean).join(' · '))}</span></div>
      <button class="arrow" aria-label="Next album" onclick="A.alPageMove(1)" ${i < cards.length - 1 ? '' : 'disabled'}>→</button></div>
    ${mixed ? '<div class="banner" style="border-color:var(--line);background:var(--panel2)">Marked <b>Not one album</b>: each song is matched on its own when the plan is updated.</div>' : ''}
    ${alBar(c, nm, { matchOn: `A.alPageMatch(${arg(g.key)})`,
      acceptIf: (() => { const set = new Set(ids), ns = sureOnes().filter(x => set.has(x.id)).length; return ns ? rb('green outline', 'ok', `Accept if… (${ns})`, `A.alAcceptIf(${arg(c.key)})`, `Only the songs of this album that are at least ${S.sureMin || 90}% alike. You see every change first.`) : ''; })(),
      selMatch: selIds.length ? rb('amber', 'match', `Same album for ${plural(selIds.length, 'selected song')}`, `A.alPageMatch(${arg('APS|' + c.key)})`) : '',
      right: `<label class="sub selall"><input type="checkbox" class="qck" ${selIds.length === ids.length ? 'checked' : ''} onclick="${ids.map(k => `S.alSel['${k}']=this.checked;`).join('')}render()"> Select all</label>` })}</div>
    ${S.rvGroupSel && /^APS?\|/.test(S.rvGroupSel.key) && S.rvGroups[S.rvGroupSel.key] ? `<div class="alx">${groupPanel(S.rvGroups[S.rvGroupSel.key], true)}</div>` : ''}
    <div class="alsplit"><div class="alrows">${rows}</div>${detailPane()}</div></section>`;
}

// ---- Quick mode: one song at a time, big, keys only
function quickView(q, inLib) {
  const fx = rvFocus(), left = q.filter(x => !isDone(x) && !isAside(x)).length;
  if (!fx) return `<section class="panel pad" style="text-align:center"><b style="color:var(--green-text);font-size:20px">All reviewed</b></section>`;
  const open = q.filter(x => !isDone(x) && !isAside(x)), i = open.findIndex(x => x.id === fx.id);
  const nbtn = x => `<button onclick="A.rvPick(${arg(x.id)})"><b>${esc(x.tags.title || stem(x.file))}</b><br><span class="sub" style="font-size:12px">${esc(x.tags.artist || 'no artist')}${effKind(x) === 'match' && x.match_pct != null ? ' · ' + x.match_pct + '%' : ' · ' + KNAME[effKind(x)]}${x.prep ? ' · results ready' : ''}</span></button>`;
  const head = `<div class="row" style="justify-content:space-between"><span class="sub" style="font-size:13px">${plural(left, 'song')} to go · ← → move · the next song opens after each decision</span></div>`;
  if (inLib) {                                       // 1.1.7 Library mode: no list of next songs, just the one that comes next, at the bottom
    const nx = open[i + 1];
    return `<section class="panel rvfocus quick" aria-label="Quick review">${head}${focusPanel(fx, q)}
      <div class="row" style="gap:10px;padding-top:10px;margin-top:10px;border-top:1px solid var(--line);align-items:center"><span class="cap">NEXT</span>${nx ? `<div class="qnext" style="flex:1;min-width:0">${nbtn(nx)}</div>` : '<span class="sub">Nothing after this one.</span>'}</div></section>`;
  }
  const next = open.slice(i + 1, i + 6), sure = sureOnes().slice(0, 200), ns = sureOnes().length;
  return `<div class="rvwrap"><section class="panel rvfocus quick" aria-label="Quick review">${head}
    ${focusPanel(fx, q)}</section>
    <aside class="panel" style="flex:0 1 260px;padding:14px;display:flex;flex-direction:column;gap:8px"><span class="cap">NEXT</span><div class="qnext">${next.map(nbtn).join('') || '<span class="sub">Nothing after this one.</span>'}</div>
      ${ns ? `<hr style="border:0;border-top:1px solid var(--line);margin:6px 0"><span class="cap">ACCEPT IF… · ${fmt(ns)}</span><span class="sub" style="font-size:12px">${S.sureBand === false ? 'At least ' + (S.sureMin || 90) + '%' : 'Only ' + sureTxt()} alike. Click one to open it.</span>
        <div class="qnext" style="max-height:340px;overflow:auto">${sure.map(nbtn).join('')}</div><button class="btn green small" onclick="A.rvSureAsk()">Accept them…</button>` : ''}</aside></div>`;
}

// ---- Analyze: tiers, artists and their albums, almost complete albums with helpers to find missing songs

// V2.0.3: the verify / automatic-accept buttons, shown at the top of the Check tags page
function verifyBar() {
  const R = S.rv, P = S.B.vprep, busy = P && P.running;        // V2.0.5 (#10): Verify has its own lane, Prepare Previews running does not block it
  const nver = R ? R.items.filter(x => effKind(x) === 'match' && !isDone(x) && !isAside(x) && !x.verify).length : 0;
  return `<div class="actrow" style="margin:0 0 10px"><button class="btn outline" data-tip="${esc('Asks the other sites you turned on (Deezer, Spotify, Apple Music, Discogs...) whether they agree with each waiting match: same artist, title, album and length. 4 songs at a time. Sends names and lengths only. Read-only. Songs two sites agree on show up in Accept if… as 100% with a verified tag.')}" onclick="A.verifyStart()" ${busy ? 'disabled' : ''}>${svg('M5 12l5 5L20 7', 15)} Verify with other sites${nver ? ' (' + fmt(nver) + ')' : ''}</button>
    <button class="btn ghost" data-tip="${esc('The songs that were placed on their own because their tags were already exactly right. Undo any of them.')}" onclick="A.autoLogOpen()">Placed automatically</button></div>${typeof prepBar === 'function' ? prepBar() : ''}`;
}

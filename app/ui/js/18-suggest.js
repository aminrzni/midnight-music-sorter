/* Midnight 00:01 · Analyze › Suggestions (1.1.5): what to look for next. Five modes, like Review's modes. */
'use strict';
const SUG_MODES = [
  ['albums', 'Album suggestion', 'Nine well-known albums from artists like the ones you own (needs a Last.fm key)', 'M12 3a9 9 0 1 0 0 18 9 9 0 0 1 0-18zM12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4z'],
  ['similar', 'Similar artists', 'Artists like the ones you own most (needs a Last.fm key)', 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 8a2.5 2.5 0 1 1 0 5M21 19c0-2.4-1.5-4.4-3.6-5'],
  ['gems', 'Hidden gems', 'Artists you own only 1–2 songs of, but who are well known (needs a Last.fm key)', 'M6 4h12l3 5-9 11L3 9z'],
  null,
  ['almost', 'Almost complete', 'Albums where only a few songs are missing', 'M4 12l5 5L20 6'],
  ['missing', 'Missing from my artists', 'Albums and songs you lack from artists you already own', 'M12 5v14M5 12h14'],
  ['upgrade', 'Better version', 'Low-quality files (under 192 kbps) worth replacing', 'M12 19V6M6 12l6-6 6 6'],
  ['mixups', 'Sound-effect mix-ups', 'Sound effects matched to real songs, and short real tracks that look like effects (checked on this PC only)', 'M4 12h3l3-7 4 14 3-7h3'],
  ['renames', 'Artist renames', 'Artist names the scan wants to change into a clearly different name (checked on this PC only)', 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4'],
];
const SUG_PAGE = 9;
function sugState() { if (!S.sug) S.sug = { mode: store.get('sugMode', 'albums'), data: {}, loading: {}, shown: {} }; if (!SUG_MODES.some(m => m && m[0] === S.sug.mode)) S.sug.mode = 'albums'; return S.sug; }
// one title card: picture on top, name, a line, a button
function sugCard(c) {
  const pic = c.img ? `<img src="${esc(c.img)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'sugph',textContent:'♪'}))">` : '<div class="sugph">♪</div>';
  return `<div class="sugcard"><div class="sugpic">${pic}</div><div class="sugtxt"><b>${esc(c.title)}</b>${c.sub ? `<span class="sub">${esc(c.sub)}</span>` : ''}</div><div class="sugact">${c.act || ''}</div></div>`;
}

// 2.0.1 Aurora Glass: suggestions as a 3D stack of cards (wheel / arrows / click to move through); the front card opens its details at the side
const s3dHue = t => { let h = 0; for (const ch of String(t)) h = (h * 31 + ch.charCodeAt(0)) % 360; return h; };
function s3dStyle(o) {              // isometric: square cards stand on edge in two stacks; the chosen one is pulled out in the gap between them
  const a = Math.abs(o), hide = a > 14, y = o === 0 ? 0 : o * 15 + (o < 0 ? -150 : 150), z = o === 0 ? 26 : 0;
  return `transform:translate3d(0,${y}px,${z}px) rotateX(-90deg) ${o === 0 ? 'scale(1.12)' : ''};opacity:${hide ? 0 : o === 0 ? 1 : Math.max(0, 1 - Math.max(0, a - 1) * .09).toFixed(2)};pointer-events:${hide ? 'none' : 'auto'};filter:brightness(${o === 0 ? 1 : Math.max(.45, 1 - a * .04).toFixed(2)}) blur(${a > 3 ? ((a - 3) * .45).toFixed(1) : 0}px)`;
}
function s3dInfo(c) {
  const pic = c.img ? `<img src="${esc(c.img)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'sugph',textContent:'♪'}))">` : '<div class="sugph">♪</div>';
  return `<div class="s3dpic" style="--h:${s3dHue(c.title)}">${pic}</div><b class="s3dtitle">${esc(c.title)}</b>${c.sub ? `<span class="sub">${esc(c.sub)}</span>` : ''}<div class="sugact">${c.act || ''}</div>`;
}
function sug3d(cards) {
  const G = sugState(), key = G.mode, f = Math.min(Math.max(0, (G.focus || {})[key] || 0), cards.length - 1);
  S.sugCur = cards;
  return `<div class="s3d"> <div class="s3dstage" tabindex="0" onwheel="event.preventDefault();A.s3dMove(event.deltaY>0?1:-1)" onkeydown="if(event.key==='ArrowDown'||event.key==='ArrowRight'){event.preventDefault();A.s3dMove(1)}else if(event.key==='ArrowUp'||event.key==='ArrowLeft'){event.preventDefault();A.s3dMove(-1)}" aria-label="Suggestions, scroll or use the arrow keys">
    <div class="s3dscene">${cards.map((c, i) => `<button class="s3dcard" data-i="${i}" style="--h:${s3dHue(c.title)};${s3dStyle(i - f)}" onclick="A.s3dGo(${i})" aria-label="${esc(c.title)}">${c.img ? `<img src="${esc(c.img)}" alt="" loading="lazy" onerror="this.remove()">` : ''}<span class="s3dstrip"><b>${esc(c.title)}</b><i>${esc((c.sub || '').split(' · ')[0])}</i></span></button>`).join('')}</div>
    <span class="s3dhint">scroll · ↑ ↓</span></div>
    <aside class="s3dinfo" id="s3dinfo">${s3dInfo(cards[f])}</aside></div>`;
}
function suggestScreen() {
  const D = S.an, G = sugState();
  if (!D) { if (!S.anLoading) { S.anLoading = true; call('analyze_data', S.anBasis || 'new', S.anScope || 'all').then(r => { S.an = r || {}; S.anLoading = false; render(); }); }
    return `<header class="bighead"><h1>Analyze</h1><p><span class="spin"></span> Loading…</p></header>`; }
  if (D.error) return `<header class="bighead"><h1>Analyze</h1><div class="row" style="gap:8px;flex-wrap:wrap">${anTopRow()}</div><p>${esc(D.error)}</p></header>`;
  const BIG = ['albums', 'similar', 'gems'];
  const left = SUG_MODES.map(m => m ? `<button class="sugmode ${BIG.includes(m[0]) ? 'big' : ''}" data-c="${m[0]}" title="${esc(m[2])}" aria-pressed="${G.mode === m[0]}" onclick="A.sugMode(${arg(m[0])})">${svg(m[3], BIG.includes(m[0]) ? 22 : 18)}<span>${m[1]}</span></button>` : '<div class="navsep" role="separator" style="margin:6px 0"></div>').join('');
  const lo = a => `<button class="btn small outline" onclick="A.lookOut(${arg(a)},'suggest')">Look out</button>`;
  const lfm = a => `<button class="btn small outline" onclick="call('open_url', ${arg('https://www.last.fm/music/' + encodeURIComponent(a))})">Last.fm</button>`;
  let cards = [], note = '', empty = '';
  if (G.mode === 'almost') {
    cards = (D.almost || []).slice().sort((a, b) => (a.total - a.have) - (b.total - b.have) || a.artist.localeCompare(b.artist)).slice(0, 200)
      .map(r => ({ title: r.album, sub: `${r.artist} · ${r.have} of ${r.total} songs · missing: ${r.missing || (r.total - r.have)}`, act: lo(r.artist) }));
    empty = 'No almost-complete albums.';
  } else if (G.mode === 'missing') {
    cards = (D.artists || []).filter(a => (a.songs || 0) >= 3).sort((a, b) => (b.songs || 0) - (a.songs || 0)).slice(0, 60).map(a => {
      const miss = (a.albums || []).filter(al => !al.complete && al.tracks_total); if (!miss.length) return null;
      return { title: a.artist, sub: `${plural(a.songs, 'song')} · ${miss.length} album${miss.length === 1 ? '' : 's'} not complete: ${miss.slice(0, 3).map(al => al.album + ' (' + al.tracks_owned + '/' + al.tracks_total + ')').join(', ')}`, act: lo(a.artist) }; }).filter(Boolean);
    empty = 'Nothing missing.';
  } else {
    const d = G.data[G.mode];
    if (!d && ['albums', 'similar', 'gems'].includes(G.mode) && !G.approved) {        // asks before anything goes online
      note = `<div class="note" style="flex-direction:column;align-items:flex-start;gap:8px"><span><b>Ask the internet?</b> To suggest music, the names of your top artists (up to 10, plus the ones you have only 1–2 songs of) are sent to <b>Last.fm</b>, and artist / album names to <b>Deezer</b> for the pictures. No songs, files or paths are sent.</span>
        <span class="row" style="gap:8px"><button class="btn small amber" onclick="sugState().approved=true;render()">Yes, look it up</button></span></div>`; }
    else if (!d) { if (!G.loading[G.mode]) { G.loading[G.mode] = true; call('suggest_music', G.mode).then(r => { G.data[G.mode] = r || { error: 'no answer' }; G.loading[G.mode] = false; render(); }); }
      note = '<div class="sub"><span class="spin"></span> Looking…</div>'; }
    else if (d.error) note = `<div class="note"><span>${esc(d.error)}</span></div><button class="btn small outline" onclick="A.sugReload()">Try again</button>`;
    else if (G.mode === 'upgrade') { note = `<div class="sub">${fmt(d.total || 0)} songs under 192 kbps (lowest first). Use “Find my…” or Look out to search for a better file.</div>`;
      cards = (d.items || []).map(r => ({ title: r.title, sub: `${r.artist || 'no artist'} · ${r.kbps} kbps ${(r.ext || '').replace('.', '').toUpperCase()}${r.album ? ' · ' + r.album : ''}`, act: r.id ? `<button class="pv" aria-label="Play" onclick="A.play(${arg(r.id)})">▶</button>` : '' })); }
    else if (G.mode === 'mixups') { note = `<div class="sub">${fmt(d.total || 0)} songs to look at. Play them; fix the wrong ones in Review (Later / Not this / No album).</div>`;
      cards = (d.items || []).map(r => ({ title: r.title, sub: `${r.artist || 'no artist'} · ${r.why}${r.album ? ' · ' + r.album : ''}`, act: r.id ? `<button class="pv" aria-label="Play" onclick="A.play(${arg(r.id)})">▶</button>` : '' })); empty = 'Nothing suspicious.'; }
    else if (G.mode === 'renames') { note = `<div class="sub">${fmt(d.total || 0)} different renames. If one looks wrong, find it in Review and choose Not this.</div>`;
      cards = (d.items || []).map(r => ({ title: `${r.artist}  →  ${r.to}`, sub: `${plural(r.n, 'song')}: ${(r.songs || []).join(', ')}`, act: lo(r.to) })); empty = 'No surprising renames.'; }
    else if (G.mode === 'albums') { cards = (d.items || []).map(r => ({ title: r.album, sub: `${r.artist} · because you have ${(r.because || []).slice(0, 2).join(', ')}`, img: r.img, act: lo(r.artist) })); empty = 'No album suggestions.'; }
    else if (G.mode === 'similar') { cards = (d.items || []).map(r => ({ title: r.artist, sub: 'because you have ' + (r.because || []).slice(0, 3).join(', '), img: r.img, act: lfm(r.artist) })); empty = 'No suggestions.'; }
    else { cards = (d.items || []).map(r => ({ title: r.artist, sub: `${fmt(r.listeners)} listeners${r.albums && r.albums.length ? ' · try: ' + r.albums.join(', ') : ''}`, img: r.img, act: lfm(r.artist) })); empty = 'No hidden gems found.'; }
  }
  const shown = G.shown[G.mode] || SUG_PAGE, more = cards.length > shown;
  const v3 = store.get('sugView', '3d') === '3d';
  const vsw = cards.length ? `<span class="seg small" style="align-self:flex-end">${[['3d', '3D stack'], ['grid', 'Grid']].map(o => `<button aria-pressed="${(v3 ? '3d' : 'grid') === o[0]}" onclick="store.set('sugView',${arg(o[0])});render()">${o[1]}</button>`).join('')}</span>` : '';
  const body = cards.length && v3 ? sug3d(cards.slice(0, 200)) : cards.length ? `<div class="sugcards">${cards.slice(0, shown).map(sugCard).join('')}</div>${more ? `<div class="row" style="justify-content:center"><button class="btn outline" onclick="A.sugMore()">Load more (${cards.length - shown} left)</button></div>` : ''}` : (note ? '' : `<div class="sub">${empty}</div>`);
  const info = SUG_MODES.find(m => m && m[0] === G.mode);
  return `${anHeadBar('What to look for next in your collection.')}${anToolBox()}
    <div class="sugwrap"><nav class="sugleft panel" aria-label="Suggestion kind">${left}</nav>
    <section class="panel sugright">${vsw}<div class="sub" style="font-size:12px">${esc(info ? info[2] : '')}${['albums', 'similar', 'gems'].includes(G.mode) ? ' · only artist names are sent (Last.fm for the suggestions, Deezer for the pictures)' : ''}</div>${note}${body}</section></div>`;
}
Object.assign(A, {
  sugMode(m) { const G = sugState(); G.mode = m; store.set('sugMode', m); render(); },
  sugMore() { const G = sugState(); G.shown[G.mode] = (G.shown[G.mode] || SUG_PAGE) + SUG_PAGE; render(); },
  s3dGo(i) { const G = sugState(); G.focus = G.focus || {}; const n = (S.sugCur || []).length; G.focus[G.mode] = Math.max(0, Math.min(n - 1, i));
    document.querySelectorAll('.s3dcard').forEach(el => { el.setAttribute('style', `--h:${el.style.getPropertyValue('--h')};` + s3dStyle(+el.dataset.i - G.focus[G.mode])); });
    const inf = document.getElementById('s3dinfo'); if (inf && S.sugCur[G.focus[G.mode]]) inf.innerHTML = s3dInfo(S.sugCur[G.focus[G.mode]]); },
  s3dMove(d) { const G = sugState(); A.s3dGo(((G.focus || {})[G.mode] || 0) + d); },
  sugReload() { const G = sugState(); delete G.data[G.mode]; render(); },
});

Object.assign(A, {
  // v2.0: "See what was copied" opens the list of copied songs (it also works when you are already on this page)
  seeCopied() { S.copyOpen = true; if (S.screen !== 'apply') A.go('apply'); else render(); setTimeout(() => { const el = document.getElementById('copiedbox'); if (el) { el.open = true; el.scrollIntoView({ behavior: 'smooth', block: 'start' }); } }, 120); },
});

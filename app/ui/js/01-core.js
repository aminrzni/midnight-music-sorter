/* Midnight 00:01 · Music Sorter — the app's screens.
   Talks to midnight_app.py: in the app window through pywebview, in the browser test mode through /api/<name>. */
'use strict';

// ---------------------------------------------------------------- connection to Python
let DESKTOP = false;
async function rawCall(name, args) {
  if (DESKTOP) {
    const fn = window.pywebview.api[name];
    if (!fn) throw new Error('The app has no "' + name + '" yet — please close the app and start it again.');
    return await fn(...args);
  }
  const r = await fetch('/api/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(args) });
  return await r.json();
}
async function call(name, ...args) {
  try {
    // music-site lookups wait in line behind each other (each site has a speed limit), so they get much longer
    const slow = /^review_(search|sound|link|suggest|group)$|^preview_url$/.test(name), lim = slow ? 600 : 90;
    const r = await Promise.race([rawCall(name, args),
      new Promise((_, rej) => setTimeout(() => rej(new Error('No answer from the app after ' + (slow ? '10 minutes' : '90 seconds'))), lim * 1000))]);
    return r;
  } catch (e) {
    const msg = (e && (e.name ? e.name + ': ' : '') + e.message) || String(e);
    if (/^No answer from the app/.test(msg)) { if (name !== 'poll') toast('The app is busy with a long task — this will finish by itself. Try again in a moment.'); return { error: msg, busy: true }; }
    if (name !== 'report_error' && name !== 'poll') { reportError('call ' + name, msg + '\n' + ((e && e.stack) || '')); toast('Error in ' + name + ': ' + msg, true); }
    return { error: msg };
  }
}
let reported = 0;
function reportError(where, message) {
  if (reported++ > 30) return;
  try { rawCall('report_error', [where, String(message).slice(0, 4000)]).catch(() => {}); } catch (e) {}
}
window.addEventListener('error', e => { reportError('page', (e.message || '') + ' @ ' + (e.filename || '') + ':' + (e.lineno || '') + '\n' + ((e.error && e.error.stack) || '')); });
window.addEventListener('unhandledrejection', e => { const r = e.reason || {}; reportError('promise', (r.message || String(r)) + '\n' + (r.stack || '')); });
function whenReady() {
  return new Promise(res => {
    if (window.pywebview && window.pywebview.api) { DESKTOP = true; return res(); }
    let done = false;
    window.addEventListener('pywebviewready', () => { if (!done) { done = true; DESKTOP = true; res(); } });
    setTimeout(() => { if (!done) { done = true; DESKTOP = !!(window.pywebview && window.pywebview.api); res(); } },
      location.protocol === 'file:' ? 4000 : 400);
  });
}

// ---------------------------------------------------------------- helpers
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const arg = v => esc(JSON.stringify(v));               // a value inside onclick="A.x(...)"
const fmt = n => (n || 0).toLocaleString('en-US');
const plural = (n, a, b) => fmt(n) + ' ' + (n === 1 ? a : (b || a + 's'));
const mins = s => { if (s == null) return ''; s = Math.round(s); if (s < 60) return 'less than a minute left in this step';
  const m = Math.round(s / 60); return m < 60 ? '~' + m + ' min left in this step' : '~' + Math.floor(m / 60) + 'h ' + (m % 60) + 'm left in this step'; };
const store = { get(k, d) { try { const v = localStorage.getItem('mn_' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('mn_' + k, JSON.stringify(v)); } catch (e) {} } };

const ICON = {
  logo: '<svg width="34" height="34" viewBox="0 0 120 120" fill="none" aria-hidden="true"><circle cx="60" cy="60" r="56" fill="#15120d" stroke="#E8A33D" stroke-width="5"/><circle cx="60" cy="60" r="44" stroke="#4a3b20" stroke-width="2.5"/><circle cx="60" cy="60" r="34" stroke="#4a3b20" stroke-width="2.5"/><circle cx="60" cy="60" r="22" fill="#E8A33D"/><path d="M64 49a12 12 0 1 0 0 22 9.5 9.5 0 0 1 0-22z" fill="#15120d"/></svg>',
  folder: 'M3 7h6l2 2h10v10H3z', folderOpen: 'M3 19V6h6l2 2h8v3M3 19l3-8h16l-3 8z',
  x: 'M6 6l12 12M18 6L6 18', chev: 'M9 6l6 6-6 6', moon: 'M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z',
  upload: 'M3 7h6l2 2h10v10H3zM12 12v5M9.5 14.5L12 12l2.5 2.5', chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  note: 'M9 18V5l11-2v13', shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z'
};
const svg = (d, size = 18, color = 'currentColor', sw = 1.7, extra = '') =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}><path d="${d}"/></svg>`;
const noteIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true" style="flex:none"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>';

const NAV = [
  ['sources', 'Sources', 'M3 7h6l2 2h10v10H3z'],
  ['dash', 'Dashboard', 'M3 13h8V3H3zM13 21h8V11h-8zM3 21h8v-6H3zM13 3v6h8V3z'],
  ['review', 'Review', 'M4 12l5 5L20 6'],
  ['dups', 'Duplicates', 'M8 8h11v11H8zM5 16V5h11'],
  ['neat', 'Neat Picky', 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11'],
  ['analyze', 'Analyze', 'M4 20V10M10 20V4M16 20v-7M22 20H2'],
  ['playlists', 'Playlist manager', 'M4 6h12M4 11h12M4 16h7M17 14v7M17 14l4-1v3l-4 1'],
  ['plan', 'Plan preview', 'M5 4v16M5 8h7M5 16h7M12 6h7v4h-7zM12 14h7v4h-7z'],
  ['apply', 'Copy & tag', 'M8 8h12v12H8zM4 16V4h12'],
  ['archive', 'Archive', 'M3 5h18v4H3zM5 9v11h14V9M10 13h4'],
  ['search', 'Find & restore', 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4'],
  ['activity', 'Activity', 'M12 8v5l3 2M21 12a9 9 0 1 1-3-6.7M21 4v5h-5'],
  ['settings', 'Settings', 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 4v4M8 10v4M16 16v4']
];
const TIER_COLOR = { 'Golden Full Collection': '#E8C55A', 'Get To Collection': '#5CC0A7', 'Starter Collection': '#7FA7E0',
  'Scattered Collection': '#B49BD8', 'Unknown Discography': '#8C8880' };

// ---------------------------------------------------------------- state
const S = {
  screen: 'sources', theme: store.get('theme', 'dark'), info: null, B: { rev: -1 }, dash: null,
  mode: 'simple', speed: store.get('speed', 'complete'), dropOver: false, lastDrop: 0,
  planOpen: {}, planKids: {},
  rv: null, rvUI: {}, rvSel: null, rvFilter: store.get('rvFilter', 'match'), playing: null, alKey: store.get('alKey', ''), arOpen: {}, alSel: {}, rvChecked: {}, rvLastCheck: null,
  rvGroupBy: store.get('rvGroupBy', ''), rvGroups: {}, rvClosed: {}, rvGroupSel: null, rvGS: {},
  rvView: store.get('rvView2', 'songs'), alLayout: store.get('alLayout', 'c'), songMore: store.get('songMore', false), rvSort: store.get('rvSort', 'pct_desc'), diffMode: store.get('diffMode', 'changes'), relReg: [], alOpen: {}, alRow: null, alMatchOpen: null, alSort: store.get('alSort', 'artist'),
  sureMin: +store.get('sureMin', 90), sureBand: store.get('sureBand', true), lastSure: null, dups: null,
  w: null,                      // whole-computer search: { nodes:{}, kids:{}, tops:[], since, sel:{}, open:{}, songs:{}, st }
  dlg: null, toast: null
};

// ---------------------------------------------------------------- render
// v1.1: every page starts the same way: Title  (!)  small description  ──────  (the long text is in the ! tip)
const PAGE_SHORT = { sources: 'Choose your music and the destination', dash: 'Progress and numbers', review: 'Check the songs that need you', dups: 'Songs found more than once',
  neat: 'Compare tags before and after', analyze: 'How complete your collection is', playlists: 'Box sets and playlists', plan: 'Where every song will go',
  apply: 'Make the tagged copies', activity: 'What happened, and when', archive: 'Move the originals into the archive', search: 'Find a song or undo a change', settings: 'Services, keys and options' };
const PAGE_LONG = {
  dash: 'Your library at a glance: progress of the running job (Scan and Identify have their own bars), the numbers, and what to do next.',
  review: 'The songs the app could not confirm by itself. Pick the right match, search again, dig deeper, keep your own tags or leave a song out. Nothing is copied or changed here.' };
function normalizeHead(main) {
  const h = main.querySelector('header.bighead, header.head'); if (!h) return;
  const h1 = h.querySelector('h1'); if (!h1) return;
  const p = h.querySelector('p'), plain = p ? p.textContent.trim() : '';
  const fixed = plain.length >= 100 || PAGE_LONG[S.screen];
  const short = PAGE_SHORT[S.screen]; if (!short || !fixed) return;
  const long = PAGE_LONG[S.screen] ? PAGE_LONG[S.screen] + (['review', 'dash'].includes(S.screen) && plain ? ' ' + plain : '') : plain;
  const others = [...h.children].filter(c => c !== h1 && c !== p && !(c.tagName === 'DIV' && c.contains(h1)));
  const wrap = h.querySelector('div') && h.querySelector('div').contains(h1) ? h.querySelector('div') : null;
  const inner = wrap ? [...wrap.children].filter(c => c !== h1 && c !== p) : [];
  const head = document.createElement('header'); head.className = 'pagehead';
  head.innerHTML = `<h1>${h1.innerHTML}</h1><span class="infoi" tabindex="0" role="button" aria-label="About this page"><b>!</b><span class="itip" role="tooltip">${esc(long)}</span></span><span class="pdesc">${esc(short)}</span><span class="pextra"></span>`;
  const ex = head.querySelector('.pextra'); [...others, ...inner].forEach(c => ex.appendChild(c));
  if (p && p.querySelector && p.querySelector('.spin')) { const s2 = document.createElement('span'); s2.className = 'sub'; s2.append(...p.childNodes); ex.appendChild(s2); }
  h.replaceWith(head);
}
// 1.1.5: every scrolling box (lists, trees, panels) keeps its place when the screen is redrawn - nothing jumps back to the top
const SCROLLED = new Set();                      // 2.0.2: remember which boxes were scrolled, so a redraw does not have to measure every element on the page (that made big lists and the library laggy)
addEventListener('scroll', e => { const t = e.target; if (t && t.nodeType === 1 && t !== document.documentElement && t !== document.body) SCROLLED.add(t); }, true);
function scrollKeep(root) {
  const out = [];
  SCROLLED.forEach(e => {
    if (!e.isConnected) { SCROLLED.delete(e); return; }
    if (e !== root && root.contains(e) && e.scrollTop > 0 && e.scrollHeight > e.clientHeight + 1) {
      const path = []; let n = e;
      while (n && n !== root) { const p = n.parentElement; path.push(p ? Array.prototype.indexOf.call(p.children, n) : 0); n = p; }
      out.push([path.join('.'), e.scrollTop, e.id || '']);
    }
  });
  return out;
}
function scrollRestore(root, keep) {
  keep.forEach(([path, top, id]) => {
    let e = id ? document.getElementById(id) : null;
    if (!e) { e = root; const idx = path.split('.').map(Number).reverse(); for (const i of idx) { e = e && e.children[i]; if (!e) break; } }
    if (e && e.scrollHeight > e.clientHeight && Math.abs(e.scrollTop - top) > 1) e.scrollTop = top;
  });
}
// V2.0.5: "the page jumped back to the top". When a screen is redrawn while its data reloads, the page is briefly short, the browser
// clamps the scroll position to the top, and it was never put back. WANT_Y remembers where you were until the page is tall enough again,
// and is forgotten as soon as YOU scroll (wheel, touch, keys, mouse press).
let WANT_Y = 0, WANT_SCREEN = '';
['wheel', 'touchmove', 'keydown', 'mousedown'].forEach(ev => addEventListener(ev, e => { if (ev === 'keydown' && !/^(PageUp|PageDown|Home|End|ArrowUp|ArrowDown| )$/.test(e.key)) return; WANT_Y = 0; }, { passive: true, capture: true }));
function render() {
  document.documentElement.dataset.theme = S.theme;
  renderNav();
  const main = document.getElementById('main');
  const f = document.activeElement, fid = f && f.id, sel = f && f.selectionStart;
  let scr;
  S._rc = {};                                   // per-redraw cache (review list, sure list): valid only while this redraw runs
  try { scr = (SCREENS[S.screen] || placeholder)(); }
  catch (e) {
    reportError('render ' + S.screen, (e && e.message) + '\n' + ((e && e.stack) || ''));
    scr = `<header class="head"><div><h1>Something went wrong</h1><p>This screen could not be shown. The details were saved in the logs folder (app_errors.txt).</p></div></header>
      <div class="panel pad mono wrap" style="font-size:12px;color:var(--clay)">${esc((e && e.message) || e)}</div>`;
  }
  S._rc = null;
  const ks = {}; document.querySelectorAll('[data-ks]').forEach(e => ks[e.dataset.ks] = e.scrollTop);
  const keep = scrollKeep(main);
  const same = S.lastScreen === S.screen; S.lastScreen = S.screen;
  const wy = same && WANT_Y && WANT_SCREEN === S.screen ? Math.max(window.scrollY, WANT_Y) : window.scrollY;
  main.innerHTML = scr;
  try { normalizeHead(main); } catch (e) { reportError('head', e.message); }
  try { decorate(main); } catch (e) { reportError('decorate', e.message); }
  try { v203Decorate(main); } catch (e) { reportError('v203', e.message); }
  document.querySelectorAll('[data-ks]').forEach(e => { if (ks[e.dataset.ks] != null) e.scrollTop = ks[e.dataset.ks]; });
  if (same) scrollRestore(main, keep);
  if (same && Math.abs(window.scrollY - wy) > 2) window.scrollTo(0, wy);
  if (same && wy > 0 && window.scrollY < wy - 2) { WANT_Y = wy; WANT_SCREEN = S.screen; } else { WANT_Y = 0; }      // page still too short: keep the place for the next redraw
  if (S.screen === 'dash') dashAnimate(); else S.dashAnim = false;
  try { playerBar(); } catch (e) {}
  if (fid) { const el = document.getElementById(fid); if (el) { el.focus(); try { el.setSelectionRange(sel, sel); } catch (e) {} } }
}
function decorate(main) {                       // 2.0.1: a hover tip on every button, an icon beside every screen title
  main.dataset.screen = S.screen;
  document.querySelectorAll('#main button, nav.side button').forEach(b => {
    if (b.title || b.dataset.tip || b.classList.contains('arrow')) return;
    const t = (b.getAttribute('aria-label') || b.textContent || '').replace(/\s+/g, ' ').replace(/\b[A-Z]$/, '').trim();
    if (t && t.length < 90) b.title = t;
  });
  const h = main.querySelector('.pagehead h1, .head h1, .bighead h1'), n = (NAV || []).find(n => n[0] === S.screen);
  if (h && n && !h.querySelector('svg')) h.insertAdjacentHTML('afterbegin', `<span class="h1ic">${svg(n[2], 22)}</span>`);
}
function renderNav() {
  const d = S.dash || {};
  if (S.navCol === undefined) S.navCol = !!store.get('navCol', false);
  document.getElementById('nav').classList.toggle('collapsed', !!S.navCol);
  const btn = n => {
    const badge = n[0] === 'review' && d.waiting ? `<span class="badge">${fmt(d.waiting)}</span>` : n[0] === 'activity' && S.actUnseen ? `<span class="badge">${fmt(S.actUnseen)}</span>` : '';
    return `<button class="navbtn" onclick="A.go(${arg(n[0])})" ${S.screen === n[0] ? 'aria-current="page"' : ''}>${svg(n[2])}<span class="l">${n[1]}</span>${badge}</button>`;
  };
  const by = k => NAV.find(n => n[0] === k);
  // v2.0 order: Sources, Dashboard, Review, Plan review, Copy & tag, Archive | Analyze, Duplicates, Playlist manager
  const top1 = ['sources', 'dash', 'review', 'plan', 'apply', 'archive'].map(by).filter(Boolean).map(btn).join('');
  const top2 = ['analyze', 'dups', 'playlists'].map(by).filter(Boolean).map(btn).join('');
  const low = ['search'].map(by).filter(Boolean).map(btn).join('');
  document.getElementById('nav').innerHTML = `
    <div class="brand">${ICON.logo}<div style="display:flex;flex-direction:column"><b>Midnight <span class="t">00:01</span></b><span class="sub" style="font-size:12px">Music Sorter</span></div></div>
    ${top1}<div class="navsep" role="separator"></div>${top2}<div style="flex:1"></div>
    ${low}
    <div class="navcircles"><button class="circbtn" onclick="A.navToggle()" title="${S.navCol ? 'Open the left column' : 'Minimize the left column'}" aria-label="${S.navCol ? 'Open the left column' : 'Minimize the left column'}">${svg(S.navCol ? 'M3 4h18v16H3zM9 4v16M13 10l3 2-3 2' : 'M3 4h18v16H3zM9 4v16M16 10l-3 2 3 2', 18)}</button>
      <button class="circbtn" onclick="A.go('activity')" title="Activity" aria-label="Activity" style="position:relative" ${S.screen === 'activity' ? 'aria-current="page"' : ''}>${svg(by('activity')[2], 18)}${S.actUnseen ? `<span class="badge" style="position:absolute;top:-4px;right:-4px;min-width:16px;height:16px;font-size:10px;padding:0 4px">${fmt(S.actUnseen)}</span>` : ''}</button>
      <button class="circbtn" onclick="A.go('settings')" title="Settings" aria-label="Settings" ${S.screen === 'settings' ? 'aria-current="page"' : ''}>${svg(by('settings')[2], 18)}</button></div>
    <div class="sesrow"><button class="btn small ghost" onclick="A.saveSession(false,true)" title="Keeps your settings and the page you are on, and saves them to a file you choose (your keys are not written to the file)">${svg('M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6', 18)}<span class="stx">Save session</span></button><button class="circbtn" onclick="A.loadSession()" title="Load a saved session file" aria-label="Load a session file">${svg('M12 16V4M7 9l5-5 5 5M4 20h16', 16)}</button></div>
    <span class="navfoot" title="${esc(S.info && S.info.app_dir || '')}">${esc(S.info ? 'v' + S.info.version : '')}${DESKTOP ? '' : ' · browser test mode'}</span>`;
}
function renderLayer() {
  const L = document.getElementById('layer');
  let h = '';
  if (S.dlg) h += `<div class="veil" onclick="if(event.target===this)A.closeDlg()"><div class="dialog" role="dialog" aria-modal="true">${DIALOGS[S.dlg.kind]()}</div></div>`;
  const cf = S.B && S.B.confirm;
  if (cf && !S.dlg) {
    const big = /^\s*move these/i.test(cf.question), qtext = cf.question.replace(/\s*\[Y\]es\s*\/\s*\[N\]o\s*$/i, '');
    h += `<div class="veil"><div class="dialog" role="alertdialog" aria-modal="true"><h2>Are you sure?</h2>
      <div class="log" id="cflog" style="max-height:40vh">${esc((cf.details || []).join('\n'))}</div>
      <p style="margin:0;font-weight:600">${esc(qtext)}</p>
      ${big ? `<p class="sub" style="margin:0">Type <b>YES</b> to move the originals. Nothing is deleted; a restore log lets you put everything back.</p>
        <input class="text" id="cfyes" value="${esc(S.confirmTyped || '')}" oninput="S.confirmTyped=this.value;renderLayer()" onkeydown="if(event.key==='Enter'&&this.value.trim()==='YES')A.answer(true)">` : ''}
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.answer(false)">No, leave everything as it is</button>
        <button class="btn green" onclick="A.answer(true)" ${big && (S.confirmTyped || '').trim() !== 'YES' ? 'disabled' : ''}>Yes</button></div></div></div>`;
  }
  if (S.toast) h += `<div class="toast ${S.toast.warn ? 'warn' : ''}" role="status">${esc(S.toast.text)}</div>`;
  const f = document.activeElement, fid = f && f.id, sel = f && f.selectionStart;
  const dOld = L.querySelector('.dialog'), dTop = dOld ? dOld.scrollTop : 0;
  // V2.0.5: every scrolling box inside a dialog keeps its place too (the "Accept if…" song list jumped to the top when you pressed Select all / a sort / a tick box)
  const boxes = []; L.querySelectorAll('*').forEach(e => { if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight) { const sib = e.parentElement ? Array.prototype.indexOf.call(e.parentElement.children, e) : 0; boxes.push([e.id, e.className, sib, e.scrollTop]); } });
  L.innerHTML = h;
  const dNew = L.querySelector('.dialog'); if (dNew && dOld) dNew.scrollTop = dTop;      // choosing something keeps your place
  boxes.forEach(([id, cls, sib, top]) => { let e = id ? document.getElementById(id) : null; if (!e && cls) { e = [...L.getElementsByClassName(String(cls).split(' ')[0])].find(x => x.className === cls) || null; } if (e && e.scrollHeight > e.clientHeight) e.scrollTop = top; });
  if (fid) { const el = document.getElementById(fid); if (el) { el.focus(); try { el.setSelectionRange(sel, sel); } catch (e) {} } }
}
function toast(text, warn) {
  S.toast = { text, warn }; renderLayer();
  clearTimeout(toast.t); toast.t = setTimeout(() => { S.toast = null; renderLayer(); }, 6000);
}

// ---------------------------------------------------------------- SOURCES

// v1.1.5: one sticky player at the bottom; it is only there while something plays or is paused
function playerBar() {
  let el = document.getElementById('playerbar');
  if (!el) { el = document.createElement('div'); el.id = 'playerbar'; el.className = 'playerbar'; el.hidden = true; document.body.appendChild(el);
    const a0 = S.audio; if (a0 && !a0._pb) { a0._pb = true; a0.addEventListener('timeupdate', () => { const i = document.getElementById('pbseek'); if (i && a0.duration) { i.max = a0.duration; i.value = a0.currentTime; const t = document.getElementById('pbtime'); if (t) t.textContent = mmss(a0.currentTime) + ' / ' + mmss(a0.duration); } }); } }
  const a = S.audio;
  if (a && !a._pb) { a._pb = true; a.addEventListener('timeupdate', () => { const i = document.getElementById('pbseek'); if (i && a.duration) { i.max = a.duration; i.value = a.currentTime; const t = document.getElementById('pbtime'); if (t) t.textContent = mmss(a.currentTime) + ' / ' + mmss(a.duration); } }); }
  if (!S.playing || !a) { el.hidden = true; document.body.classList.remove('hasplayer'); return; }
  const x = S.rv && S.rv.items && S.rv.items.find(i => i.id === S.playing);
  const name = String(S.playing).startsWith('u:') ? 'Preview' : x ? ((x.tags.artist || '') + ' — ' + (x.tags.title || x.file)) : 'Playing';
  const seek = document.getElementById('pbseek'), keepVal = seek ? seek.value : 0;
  el.innerHTML = `<button class="btn small" aria-label="${a.paused ? 'Play' : 'Pause'}" onclick="A.pbToggle()">${a.paused ? '▶' : '❚❚'}</button><span class="pbname">${esc(name)}</span>
    <input id="pbseek" type="range" min="0" max="${a.duration || 100}" step="0.5" value="${keepVal}" aria-label="Position" oninput="S.audio.currentTime=this.value"><span id="pbtime" class="sub mono" style="font-size:12px">${mmss(a.currentTime)} / ${mmss(a.duration)}</span>
    <button class="btn small ghost" aria-label="Stop" onclick="A.play(null)">✕</button>`;
  el.hidden = false; document.body.classList.add('hasplayer');
}

// narrow layout: window is under 70% of the screen width
(function(){const f=()=>document.documentElement.classList.toggle('narrow',window.innerWidth/Math.max(screen.width,1)<=.7005);f();addEventListener('resize',f)})();

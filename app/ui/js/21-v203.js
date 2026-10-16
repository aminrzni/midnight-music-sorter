/* Midnight 00:01 · V2.0.3 additions: Accept colour + match %, weak-match question, tag editor, Dig in, verify, automatic-accept log.
   Loaded last; it only adds to / wraps what the other files define. */
'use strict';

// ---- Accept button: green 80-100, yellow 60-79, orange 55-59, then red towards 20, with the match % written on it
function pctHue(p) {
  p = Math.max(0, Math.min(100, p));
  if (p >= 80) return 158;                  // 80-100 green
  if (p >= 60) return 52;                   // 60-79 yellow
  if (p >= 55) return 30;                   // 55-59 orange
  if (p > 20) return 30 * ((p - 20) / 35);  // below 55: orange fading to red
  return 0;                                 // 20 and below: red
}
function v203Decorate(root) {
  (root || document).querySelectorAll('button[data-pct]').forEach(b => {
    if (b.dataset.pd) return; b.dataset.pd = '1';
    const raw = b.dataset.pct; if (raw === '' || raw == null || isNaN(+raw)) return;
    const p = Math.round(+raw), h = Math.round(pctHue(p));
    b.style.setProperty('--ah', h); b.classList.add('aur');       // Aurora Glass colour comes from the CSS (.btn.aur), hue = match %
    const tag = document.createElement('span'); tag.className = 'pcttag'; tag.textContent = p + '%';
    tag.title = p + '% alike: how close the new tags are to your file\'s tags';
    const key = b.querySelector('.key'); if (key) b.insertBefore(tag, key); else b.appendChild(tag);
    b.title = (b.title ? b.title + ' · ' : '') + p + '% alike' + (p < 40 ? ' (weak: you will be asked)' : '');
  });
}

// ---- below 40% every Accept asks "weak match, sure?" first
const WEAK_BELOW = 40;
function weakAsk(pct, go) { S.dlg = { kind: 'weak', pct, go }; renderLayer(); }
document.addEventListener('click', e => {
  const b = e.target && e.target.closest && e.target.closest('button[data-pct]');
  if (!b || S._weakOK) return;
  const raw = b.dataset.pct; if (raw === '' || isNaN(+raw) || +raw >= WEAK_BELOW) return;
  e.preventDefault(); e.stopPropagation();
  weakAsk(Math.round(+raw), () => b.click());
}, true);
DIALOGS.weak = () => `<h2>Weak match: are you sure?</h2>
  <p style="margin:0">The new tags are only <b style="color:hsl(${Math.round(pctHue(S.dlg.pct))} 60% 55%)">${S.dlg.pct}%</b> alike to what your file says. Accepting it may put the wrong artist, title or album on the song.</p>
  <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn green" onclick="A.weakNo()">No, go back</button><button class="btn" onclick="A.weakYes()">Yes, accept anyway</button></div>`;

Object.assign(A, {
  weakNo() { S.dlg = null; renderLayer(); },
  weakYes() { const go = S.dlg && S.dlg.go; S.dlg = null; renderLayer(); S._weakOK = true; try { if (go) go(); } finally { setTimeout(() => { S._weakOK = false; }, 0); } },

  // ---- Edit = a real tag editor
  rvTagEdit(id) { const u = rvU(id); u.tagEd = !u.tagEd; u.tf = null; render(); if (u.tagEd) focus('tf_' + id + '_artist'); },
  rvTf(id, k, v) { const u = rvU(id); u.tf = u.tf || {}; u.tf[k] = v; },
  rvTagFile(id) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id), t = (x && x.tags) || {};
    u.tf = { artist: t.artist || '', title: t.title || stem(x.file), album: t.album || '', albumartist: t.albumartist || '', year: String(t.year || '').slice(0, 4), track: String(t.track || '').split('/')[0], genre: t.genre || '' };
    render();
  },
  rvTagSave(id) {
    const u = rvU(id), f = u.tf; if (!f) return;
    if (!(f.artist || '').trim() || !(f.title || '').trim()) return toast('Artist and title cannot be empty.', true);
    const fields = {}; Object.keys(f).forEach(k => { fields[k] = String(f[k] == null ? '' : f[k]).trim(); });
    u.tagEd = false; u.tf = null;
    rvDecide(id, { action: 'edit', fields, label: 'edited by you: ' + fields.artist + ' - ' + fields.title });
  },
  alTagEdit(id) { S.alRow = id; S.rvSel = id; const x = S.rv.items.find(i => i.id === id); const u = rvU(id); u.tagEd = true; u.tf = null; render(); if (x) rvOpened(x); },

  // ---- Dig in: Search / Dig deeper / Identify in one place (remembers the tab you used last)
  rvDigIn(id, t) {
    const x = S.rv.items.find(i => i.id === id); if (!x) return;
    const k = effKind(x), u = rvU(id), findOpen = u.find != null ? u.find : !!(u.sugg && !u.sugg.length);
    if (digOpenOf(x, u, k, findOpen) && !t) { u.tool = ''; u.edit = false; if (k === 'place') u.find = false; render(); return; }
    A.rvDigTab(id, t || store.get('digTab', 'search'));
  },
  rvDigTab(id, t) {
    const x = S.rv.items.find(i => i.id === id); if (!x) return;
    const k = effKind(x), u = rvU(id); store.set('digTab', t);
    u.tool = ''; u.tagEd = false;
    if (t === 'dig' || t === 'sound') { u.tool = t; u.edit = false; if (k === 'place') u.find = false; }
    else if (k === 'match') u.edit = true;
    else if (k === 'place') u.find = true;
    else u.tool = 'search';
    render(); rvOpened(x);
    if (t === 'search') focus('q_' + id + '_1');
  },
  alTool_orig: A.alTool,

  // ---- verify with the other sites + accept what two sources agree on
  async verifyStart() {
    const r = await call('verify_start'); if (r && r.error) return toast(r.error, true);
    toast('Checking ' + plural(r.total, 'song') + ' with the other sites (4 at a time). You can keep working.'); refreshDash();
  },
  verifiedAsk() { if (!safeOnes().length) return; S.dlg = { kind: 'verified', off: {} }; renderLayer(); },
  async verifiedGo() {
    const off = S.dlg.off, ids = safeOnes().filter(x => !off[x.id]).map(x => x.id); S.dlg = null; renderLayer(); if (!ids.length) return;
    const d = { action: 'accept', label: 'verified by two sources' };
    const r = await call('review_decide_many', ids, d);
    if (r && !r.error) { rvSetLocal(r.ids || ids, d); S.lastSure = r.ids || ids; toast('Accepted ' + plural(S.lastSure.length, 'verified song') + '. You can undo it.'); }
    render(); refreshDash();
  },

  // ---- the automatic accepts (identical tags) with Undo
  async autoLogOpen() { const r = await call('auto_list'); S.dlg = { kind: 'autolog', items: (r && r.items) || [], sel: {} }; renderLayer(); },
  async autoUndoGo(ids) {
    const r = await call('auto_undo', ids); if (r && r.error) return;
    S.dlg.items.forEach(i => { if (ids.includes(i.file_id)) i.undone = true; }); renderLayer(); toast(plural(ids.length, 'song') + ' moved back to Review (Later).'); loadReview();
  },

  // ---- Check tags: select everything that is shown (not only the first 100)
  nSelAll(on) { const sel = S.nSel || (S.nSel = {}); (S.nOrder || []).forEach(id => { if (on) sel[id] = true; else delete sel[id]; }); render(); }
});
function safeOnes() { return S.rv ? S.rv.items.filter(x => x.safe && !isDone(x) && !isAside(x) && effKind(x) === 'match') : []; }
{ // wrap the keyboard / bulk paths so they ask too
  const asks = (pct, f) => { if (!S._weakOK && pct !== '' && pct != null && pct < WEAK_BELOW) { weakAsk(pct, f); return true; } return false; };
  const _acc = A.rvAccept; A.rvAccept = function (id) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id), pc = u.pending ? u.pending.match_pct : x && x.match_pct;
    if (x && effKind(x) === 'match' && asks(pc, () => _acc.call(A, id))) return; return _acc.call(A, id); };
  const _all = A.alAll; A.alAll = function (k, action) {
    if (action === 'accept') { const c = albumCards('all').find(c => c.key === k); const p = c ? minPct(c.items.filter(x => effKind(x) === 'match' && !isDone(x))) : ''; if (asks(p, () => _all.call(A, k, action))) return; }
    return _all.call(A, k, action); };
  const _bulk = A.rvBulk; A.rvBulk = function (act) {
    if (act === 'accept') { const p = minPct(S.rv.items.filter(x => S.rvChecked[x.id] && effKind(x) === 'match')); if (asks(p, () => _bulk.call(A, act))) return; }
    return _bulk.call(A, act); };
  const _tool = A.alTool; A.alTool = function (id, tool) { if (tool === 'digin') { S.alRow = id; S.rvSel = id; A.rvDigIn(id); return; } return _tool.call(A, id, tool); };
}

DIALOGS.verified = () => {
  const d = S.dlg, list = safeOnes(), n = list.filter(x => !d.off[x.id]).length;
  return `<h2>Accept the verified songs</h2><p class="sub" style="margin:0">Each of these was found by MusicBrainz (or the site that matched it) <b>and</b> confirmed by another site: same artist, title, album and length. Untick any you want to check yourself. Nothing is copied now.</p>
    <div class="row" style="gap:8px"><button class="btn small outline" onclick="S.dlg.off={};renderLayer()">Select all</button><button class="btn small outline" onclick="safeOnes().forEach(x=>S.dlg.off[x.id]=true);renderLayer()">Select none</button><span class="sub" style="font-size:12px">${plural(n, 'song')} selected</span></div>
    <div class="surelist">${list.slice(0, 600).map(x => `<label class="surerow"><input type="checkbox" ${d.off[x.id] ? '' : 'checked'} onchange="S.dlg.off[${arg(x.id)}]=!this.checked;renderLayer()"><span class="sr"><b>${esc(x.suggest.title)}</b> <span class="sub">· ${esc(x.suggest.artist)} · ${esc(x.suggest.release)}${x.suggest.year ? ' (' + esc(x.suggest.year) + ')' : ''} · ${x.match_pct}% · ${esc((x.verify && x.verify.sources || []).join(' + '))}</span>
      <span class="chg sub">was: ${esc(x.tags.artist || '–')} · ${esc(x.tags.title || stem(x.file))} · ${esc(x.tags.album || '–')}</span></span></label>`).join('')}${list.length > 600 ? `<div class="sub" style="padding:8px">…and ${fmt(list.length - 600)} more (they are accepted too unless unticked above).</div>` : ''}</div>
    <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn green" onclick="A.verifiedGo()" ${n ? '' : 'disabled'}>Accept ${plural(n, 'song')}</button></div>`;
};
DIALOGS.autolog = () => {
  const d = S.dlg, items = d.items || [];
  return `<h2>Placed automatically</h2><p class="sub" style="margin:0">These songs already had exactly the right tags, so there was nothing to decide. ${plural(items.length, 'song')}. Undo sends a song back to Review (Later).</p>
    <div class="surelist">${items.slice(0, 500).map(i => `<div class="surerow"><span class="sr"><b>${esc(i.title)}</b> <span class="sub">· ${esc(i.artist)} · ${esc(i.album)}</span></span>${i.undone ? '<span class="sub">undone</span>' : `<button class="btn small ghost" onclick="A.autoUndoGo([${arg(i.file_id)}])">Undo</button>`}</div>`).join('') || '<div class="sub" style="padding:8px">None.</div>'}${items.length > 500 ? `<div class="sub" style="padding:8px">…and ${fmt(items.length - 500)} more.</div>` : ''}</div>
    <div class="row" style="justify-content:flex-end"><button class="btn" onclick="A.closeDlg()">Close</button></div>`;
};

// Ctrl+A on Check tags selects everything in the list (all pages)
document.addEventListener('keydown', e => {
  if (S.screen !== 'neat' || !(e.ctrlKey || e.metaKey) || (e.key !== 'a' && e.key !== 'A')) return;
  if (/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '')) return;
  e.preventDefault(); e.stopPropagation(); A.nSelAll(true);
}, true);

Object.assign(A, {
  openNestedSetting() { A.go('settings'); setTimeout(() => { const e = document.getElementById('set_nested'); if (e) { e.scrollIntoView({ block: 'center' }); e.style.outline = '2px solid var(--amber)'; setTimeout(() => { e.style.outline = ''; }, 2500); } }, 350); }
});


// ---- V2.0.3: cover pictures from the song files no longer flicker. Every redraw of the list rebuilt the <img> tags, so each picture
// was asked for again (and a cancelled/slow answer left a blank). Now each cover is fetched ONCE (3 at a time), kept in memory and handed back instantly.
(() => {
  const cache = new Map();            // url -> blob url, or '' when the file has no cover
  const waiting = new Map();          // url -> Set of <img>
  let running = 0; const queue = [];
  const isRemote = u => /^https?:\/\/(?:[^/]*\.)?(coverartarchive\.org|archive\.org|dzcdn\.net|mzstatic\.com|discogs\.com|scdn\.co|lastfm\.freetls\.fastly\.net)\//.test(u || '');      // V2.0.6: pictures from the sites are kept too, so they stop flickering on every redraw
  const isCov = u => /\/cover\/F\d+/.test(u || '') || isRemote(u);
  function pump() {
    while (running < 3 && queue.length) {
      const u = queue.shift(); running++;
      fetch(u, isRemote(u) ? { referrerPolicy: 'no-referrer' } : undefined).then(r => r.ok ? r.blob() : (r.status === 404 && !isRemote(u) ? null : Promise.reject(r.status))).then(b => { cache.set(u, b ? URL.createObjectURL(b) : ''); }, () => { cache.set(u, u); })
        .finally(() => { running--; const set = waiting.get(u); waiting.delete(u); if (set) set.forEach(img => apply(img, u)); pump(); });
    }
  }
  function apply(img, u) {
    const b = cache.get(u);
    if (b === undefined) return;
    if (b) { img.src = b; img.dataset.cv = 'ok'; } else { img.style.visibility = 'hidden'; img.dataset.cv = 'none'; }
  }
  function handle(img) {
    const u = img.getAttribute('data-cvsrc') || img.getAttribute('src');
    if (!isCov(u) || img.dataset.cv) return;
    img.setAttribute('data-cvsrc', u);
    if (cache.has(u)) return apply(img, u);
    img.removeAttribute('src');
    img.dataset.cv = 'wait';
    if (!waiting.has(u)) { waiting.set(u, new Set()); queue.push(u); }
    waiting.get(u).add(img);
    pump();
  }
  new MutationObserver(ms => {
    for (const m of ms) for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      if (n.tagName === 'IMG') handle(n); else n.querySelectorAll && n.querySelectorAll('img[src*="/cover/F"], img[src^="http"]').forEach(handle);
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();

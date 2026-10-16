/* Midnight 00:01 · V2.0.5 additions (loaded last): folder picker for every mode, pasted paths, and the small fixes listed in the V2.0.5 report */
'use strict';

// ---- #4 folder picker: the Windows dialog in the app window; the same kind of picker inside the page in browser mode
function pickDir(title) {
  if (DESKTOP) return call('pick_folder', title);
  return new Promise(async res => {
    const r0 = await call('list_dirs', '');
    const r = (r0 && r0.start) ? await call('list_dirs', r0.start) : r0;
    S.dlg = { kind: 'folder', title: title || 'Choose a folder', F: r || {}, value: (r && r.path) || (r0 && r0.start) || '', resolve: res };
    renderLayer(); focus('dlgpath');
  });
}
DIALOGS.folder = function () {
  const d = S.dlg, F = d.F || {};
  const drives = (F.drives || []).map(x => `<button class="btn small outline" onclick="A.fdGo(${arg(x)})">${esc(x)}</button>`).join('');
  const rows = (F.dirs || []).map(x => `<button class="navbtn" style="width:100%;justify-content:flex-start;height:34px" onclick="A.fdGo(${arg(x.path)})">${svg(ICON.folder, 16, '#E8A33D', 1.6)}<span class="l">${esc(x.name)}</span></button>`).join('')
    || '<span class="sub" style="padding:8px">No sub-folders here.</span>';
  return `<h2>${esc(d.title)}</h2>
    <p class="sub" style="margin:0">Type or paste a folder path, or click through the folders.</p>
    <div class="row" style="gap:6px"><button class="btn small" ${F.parent ? '' : 'disabled'} onclick="A.fdGo(${arg(F.parent || '')})">↑ Up</button>
      <input class="text mono grow" id="dlgpath" value="${esc(d.value || '')}" placeholder="C:\\…" oninput="S.dlg.value=this.value" onkeydown="if(event.key==='Enter')A.fdGo(S.dlg.value)">
      <button class="btn small" onclick="A.fdGo(S.dlg.value)">Go</button></div>
    ${drives ? `<div class="row" style="gap:6px;flex-wrap:wrap">${drives}</div>` : ''}
    ${F.error ? `<span style="font-size:13px;color:var(--clay)">${esc(F.error)}</span>` : ''}
    <div style="max-height:42vh;overflow:auto;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:10px;padding:4px">${rows}</div>
    <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button>
      <button class="btn amber" onclick="A.fdChoose()">Use this folder</button></div>`;
};
Object.assign(A, {
  async fdGo(p) {
    if (!S.dlg || S.dlg.kind !== 'folder') return;
    const r = await call('list_dirs', p || '');
    if (!S.dlg || S.dlg.kind !== 'folder') return;
    S.dlg.F = r || {}; S.dlg.value = (r && r.path) || p || ''; renderLayer(); focus('dlgpath');
  },
  async fdChoose() {
    const d = S.dlg; if (!d || d.kind !== 'folder') return;
    const p = String(d.value || '').trim(); if (!p) return;
    const c = await call('check_path', p);
    if (c && !c.exists) { d.F = Object.assign({}, d.F, { error: 'That folder does not exist. Check the path, or pick a folder from the list.' }); return renderLayer(); }
    call('note_pick', p); S.dlg = null; renderLayer(); d.resolve && d.resolve(p);
  },
  async typedSource() { const p = String(S.typedSrc || '').trim(); if (!p) return; const c = await call('check_path', p);
    if (c && !c.exists) return toast('That folder does not exist.', true); S.typedSrc = ''; call('note_pick', p); await addSources([p]); },
  async typedLibrary() { const p = String(S.typedLib || '').trim(); if (!p) return; S.typedLib = ''; call('note_pick', p); await setLibrary(p); },
});
(function () {                       // a cancelled picker must never leave the page waiting
  const close0 = A.closeDlg;
  A.closeDlg = function () { const d = S.dlg; if (d && d.kind === 'folder' && d.resolve) d.resolve(null); return close0.call(A); };
})();


// V2.0.5 (#13): the final Excel report
A.finalReport = async function () {
  toast('Making the Excel report…');
  const r = await call('final_report');
  if (r && r.ok) toast('Report saved: ' + r.path); else toast((r && r.error) || 'The report could not be made.', 'warn');
};


// V2.0.5 experiment: Sources shows ONE step at a time (songs added -> step 2, library chosen -> step 3).
// To go back to the old all-open layout, change true to false.
const GUIDED_SOURCES = false;
A.srcStep = function (n) { S.srcStep = n; render(); };


// V2.0.5: catch-all for "I clicked and the page jumped back to the top". After every click, the scroll positions (the page and every
// scrolling box that was scrolled) are remembered. If shortly afterwards one of them was thrown back to the top while you did NOT scroll
// and the screen is the same, it is put back, and the action that did it is written to app_errors.txt so the real cause can be fixed.
(function () {
  let userT = 0, jumps = 0;
  ['wheel', 'touchmove'].forEach(ev => addEventListener(ev, () => { userT = Date.now(); }, { passive: true, capture: true }));
  addEventListener('keydown', e => { if (/^(PageUp|PageDown|Home|End|ArrowUp|ArrowDown| )$/.test(e.key)) userT = Date.now(); }, true);
  addEventListener('click', ev => {
    const t0 = Date.now(), scr = S.screen, y = window.scrollY, dlg = !!S.dlg;
    const tgt = ev.target && ev.target.closest ? ev.target.closest('[onclick],button,label,summary,[role=button]') : null;
    const what = tgt ? ((tgt.getAttribute('onclick') || '') + ' | ' + (tgt.textContent || '').trim().slice(0, 40)) : '(no button)';
    const boxes = [];
    SCROLLED.forEach(e => { if (e.isConnected && e.scrollTop > 100) boxes.push([e, e.scrollTop]); });
    [150, 500].forEach(ms => setTimeout(() => {
      if (S.screen !== scr || userT > t0) return;
      let fixed = [];
      if (y > 100 && window.scrollY < y - 80) { window.scrollTo(0, y); fixed.push('page ' + y + '->0'); }
      boxes.forEach(([e, top]) => { if (e.isConnected && e.scrollTop < top - 80) { e.scrollTop = top; fixed.push((e.className || e.tagName) + ' ' + top + '->0'); } });
      if (fixed.length && jumps++ < 12) reportError('scroll-jump', 'screen=' + scr + (dlg ? ' (dialog open)' : '') + ' click=' + what + ' jumped: ' + fixed.join(', ') + ' (put back)');
    }, ms));
  }, true);
})();


// V2.0.5: a "More" menu that would run off the bottom of the window opens upwards instead.
document.addEventListener('toggle', e => {
  const d = e.target; if (!d || !d.classList || !d.classList.contains('moremenu')) return;
  d.classList.remove('up'); if (!d.open) return;
  const drop = d.querySelector('.moredrop'); if (!drop) return;
  const r = drop.getBoundingClientRect(), s = d.getBoundingClientRect();
  if (r.bottom > window.innerHeight - 8 && s.top - r.height - 8 > 0) d.classList.add('up');
}, true);

/* V2.0.6: keyboard shortcuts work with any keyboard language (Persian, Arabic, Russian…). When the typed character is not a Latin letter,
   the shortcut uses the PHYSICAL key (the key in the "A" place is A, whatever the layout). Typing in text boxes is never changed. */
(function () {
  addEventListener('keydown', e => {
    try {
      if (!e.code || e.code.indexOf('Key') !== 0 || e.code.length !== 4) return;
      if (typeof e.key !== 'string' || e.key.length !== 1 || /^[a-zA-Z]$/.test(e.key)) return;
      const t = e.target, tag = (t && t.tagName || '').toLowerCase();
      if (tag === 'textarea' || tag === 'select' || (t && t.isContentEditable)) return;
      if (tag === 'input' && !(e.ctrlKey || e.metaKey) && !['checkbox', 'radio', 'button'].includes((t.type || '').toLowerCase())) return;
      Object.defineProperty(e, 'key', { value: e.code.slice(3).toLowerCase(), configurable: true });
    } catch (x) { /* never block a key press */ }
  }, true);
})();


/* V2.0.6: a cover that does not load is tried again (other size / a second try) before the grey placeholder appears.
   Pictures are asked for without a referrer, because some picture servers refuse pictures requested from another site. */
Object.assign(A, {
  imgFail(img) {
    try {
      const step = +(img.dataset.try || 0), src = img.getAttribute('src') || '';
      img.dataset.try = step + 1;
      if (step === 0 && /coverartarchive\.org\/.*\/front-250$/.test(src)) { img.src = src.replace(/front-250$/, 'front-500'); return; }
      if (step <= 1 && /^https?:/.test(src) && !/^https?:\/\/(127\.0\.0\.1|localhost)/.test(src)) { setTimeout(() => { img.src = src + (src.includes('?') ? '&' : '?') + 'r=' + Date.now(); }, 1200); return; }
      img.replaceWith(Object.assign(document.createElement('span'), { className: img.dataset.ph || 'art' }));
    } catch (e) { /* the placeholder is only a nicety */ }
  }
});


Object.assign(A, {
  rvChg(k) { S.rvChg = S.rvChg || {}; S.rvChg[k] = !S.rvChg[k]; S.rvSel = null; S.alRow = null; render(); const fx = rvFocus && rvFocus(); if (fx && S.rvView !== 'albums') rvOpened(fx); },
  rvChgClear() { S.rvChg = {}; render(); },
  chgMenu() { S.chgOpen = !S.chgOpen; S.fltOpen = false; render(); },
  fltMenu() { S.fltOpen = !S.fltOpen; S.chgOpen = false; render(); },
  fltPick(k) { S.fltOpen = false; A.rvFilter(k); }
});


Object.assign(A, {
  // V2.0.6: none of the albums has your song: search with your song's TITLE (artist + title, no album), all the sites you allowed
  rvFindTitle(id) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id); if (!x) return;
    u.find = true; u.q = [x.tags.artist || (x.q && x.q[0]) || '', x.tags.title || stem(x.file), ''];
    render(); A.rvSearch(id);
  }
});

document.addEventListener('mousedown', e => { if ((S.chgOpen || S.fltOpen) && !e.target.closest('.chgmenu')) { S.chgOpen = false; S.fltOpen = false; document.querySelectorAll('details.chgmenu[open]').forEach(d => d.removeAttribute('open')); } });      // V2.0.6: no redraw here, a redraw between press and release swallowed the click (Open / Close did nothing the first time)

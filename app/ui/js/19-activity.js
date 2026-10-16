/* Midnight 00:01 · Activity screen (1.1.7): what happened in the app, newest first */
'use strict';
async function actRefresh() {
  try { const n = await call('activity_unseen'); if (typeof n === 'number' && n !== S.actUnseen) { S.actUnseen = n; renderNav(); } } catch (e) {}
}
setInterval(() => { if (S.info && !document.hidden) actRefresh(); }, 20000);
function activityScreen() {
  const A_ = S.act;
  if (!A_) { if (!S.actLoading) { S.actLoading = true; call('activity_list').then(r => { S.act = r || { items: [] }; S.actLoading = false; S.actUnseen = 0; call('activity_seen'); render(); }); }
    return `<header class="head"><div><h1>Activity</h1><p><span class="spin"></span> Loading…</p></div></header>`; }
  const f = S.actFilter || 'all';
  const kinds = [['all', 'All'], ['job', 'Jobs'], ['sources', 'Sources'], ['attention', 'Needs attention']];
  const rows = (A_.items || []).filter(e => f === 'all' || (f === 'attention' ? e.result !== 'ok' : e.kind === f));
  const chip = r => `<span class="srcchip" style="${r === 'ok' ? 'color:var(--green-text)' : 'color:var(--amber-text)'}">${esc(r === 'ok' ? 'done' : r)}</span>`;
  const when = t => { const d = new Date(t * 1000); return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }); };
  return `<header class="head"><div><h1>Activity</h1><p>What happened in the app, newest first. Interrupted or failed jobs show up here too.</p></div></header>
    <div class="row" style="gap:6px;flex-wrap:wrap;margin-bottom:8px">${kinds.map(k => `<button class="btn small ${f === k[0] ? 'amber' : 'outline'}" onclick="S.actFilter=${arg(k[0])};render()">${k[1]}</button>`).join('')}</div>
    ${rows.length ? `<section class="panel" style="padding:6px 14px"><div class="copylist">${rows.map(e => `<div class="copyrow" style="cursor:default;gap:12px"><span class="sub mono" style="min-width:110px;font-size:12px">${esc(when(e.t))}</span><span class="grow">${esc(e.text)}</span>${chip(e.result)}
        ${e.kind === 'job' && e.where === 'copy' ? `<button class="btn small ghost" onclick="A.go('apply')">Open</button>` : e.kind === 'sources' ? `<button class="btn small ghost" onclick="A.go('sources')">Open</button>` : ''}</div>`).join('')}</div></section>`
      : '<p class="sub">Nothing here yet.</p>'}`;
}

Object.assign(A, { async testSpotify() { S.spTesting = true; S.spMsg = ''; render(); const r = await call('test_spotify'); S.spTesting = false; S.spMsg = (r && (r.message || r.error)) || 'No answer.'; render(); toast(S.spMsg, !(r && r.ok)); } });

Object.assign(A, { async titlebarToggle() { const on = !(S.info && S.info.titlebar); const r = await call('titlebar_set', on); if (r && r.error) return toast(r.error, true);
  if (S.info) S.info.titlebar = on; toast(on ? 'Turned on. Close the app and start it again to see the round buttons.' : 'Turned off. Close the app and start it again for the normal title bar.'); render(); } });
// the round buttons (only when the option is on and the window has no Windows title bar)
setInterval(() => {
  if (!DESKTOP || !S.info || !S.info.titlebar || document.getElementById('tbar')) return;
  const b = document.createElement('div'); b.id = 'tbar'; b.className = 'pywebview-drag-region';
  b.innerHTML = '<span class="tbtitle">Midnight 00:01</span><button class="tb min" aria-label="Minimize" title="Minimize" onclick="call(\'win_minimize\')">–</button><button class="tb cls" aria-label="Close" title="Close" onclick="call(\'win_close\')">×</button>';
  document.body.prepend(b); document.body.classList.add('hastbar');
}, 1000);

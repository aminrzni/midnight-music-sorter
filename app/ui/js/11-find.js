/* Midnight 00:01 · Find & restore screen (part of the screens, loaded in order by index.html) */
'use strict';
function findScreen() {
  const tab = S.fTab || 'find', job = S.B.job, running = job && !job.done;
  const tabs = [['find', 'Find a song'], ['logs', 'Restore logs'], ['back', 'Put the archive back'], ['undo', 'Undo copy & tag']].map(t =>
    `<button aria-pressed="${tab === t[0]}" onclick="S.fTab=${arg(t[0])};${t[0] === 'logs' ? 'A.fLogs()' : 'render()'}">${t[1]}</button>`).join('');
  let body = '';
  if (tab === 'find') {
    const F = S.fRes;
    const ex = (p, ok) => p ? `<span class="mono wrap" style="font-size:12px">${esc(p)}</span>${ok ? '' : ' <span class="chip" style="color:var(--amber-text)">not there now</span>'}` : '<span class="sub">–</span>';
    const SC = { verified: 'var(--green-text)', copied: 'var(--green-text)', original_archived: 'var(--amber-text)', planned: 'var(--sub)', 'not copied': 'var(--sub)', skipped: 'var(--sub)' };
    const SN = { verified: 'copied + checked', copied: 'copied', original_archived: 'original archived', planned: 'in the plan, not copied yet', 'not copied': 'not in the library', skipped: 'copy undone' };
    body = `<section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:12px">
      <div class="row"><input class="text grow" id="fq" placeholder="Part of a file name, folder, artist, title or album…" value="${esc(S.fQ || '')}" oninput="S.fQ=this.value" onkeydown="if(event.key==='Enter')A.fFind()">
        <button class="btn amber" onclick="A.fFind()">Search</button></div>
      ${F ? (F.rows.length ? F.rows.map(r => `<article class="frow"><div class="row" style="justify-content:space-between;gap:10px">
          <span style="display:flex;flex-direction:column;min-width:0"><b style="overflow-wrap:anywhere">${esc(r.artist || '?')} — ${esc(r.title)}</b><span class="sub" style="font-size:12px">${esc(r.album || 'no album')} · ${esc(r.id)}</span></span>
          <span class="chip" style="color:${SC[r.status] || 'var(--sub)'}">${esc(SN[r.status] || r.status)}</span></div>
        <div class="fgrid"><span class="k">Original</span><span>${ex(r.original, r.original_there)}</span>
          <span class="k">Library copy</span><span>${r.copy ? ex(r.copy, r.copy_there) : r.planned ? '<span class="sub">will be: </span>' + ex(r.planned, true) : '<span class="sub">–</span>'}</span>
          <span class="k">Archived original</span><span>${ex(r.archived, r.archived_there)}</span>
          ${r.changes ? `<span class="k">Changes</span><span style="font-size:12px">${esc(r.changes)}</span>` : ''}</div>
        <div class="row" style="gap:6px"><button class="btn small ghost" onclick="A.reveal(${arg(r.id)})">Show in Explorer</button>
          ${r.status === 'original_archived' ? `<button class="btn small amber" ${running || r.original_there || !r.archived_there ? 'disabled' : ''} onclick="A.fRestore(${arg(r.id)})" title="Moves the archived original back to where it was. You confirm first. Nothing is overwritten.">Put the original back</button>` : ''}</div></article>`).join('')
          + (F.more ? '<span class="sub">Showing the first 200 — type more to narrow it.</span>' : '') : '<div class="empty">No song matches.</div>') : '<span class="sub" style="font-size:13px">Every song you scanned: where it came from, where its copy is, and where the original was archived.</span>'}
    </section>`;
  } else if (tab === 'logs') {
    const L = S.fLogs;
    const card = g => g.error ? `<article class="panel" style="padding:14px"><b>${esc(g.name || g.path)}</b><span style="color:var(--clay)"> ${esc(g.error)}</span></article>` : `<article class="panel logcard">
      <button class="duphead" onclick="S.fOpen=S.fOpen===${arg(g.path)}?null:${arg(g.path)};render()"><span class="grow" style="display:flex;flex-direction:column;min-width:0"><b>${esc(g.action)}</b>
        <span class="sub" style="font-size:12px">${esc(g.made)} · ${Object.entries(g.kinds).map(([k, v]) => fmt(v) + ' ' + esc(k)).join(' · ')}</span></span>
        <span class="chip" style="color:${g.can ? 'var(--green-text)' : 'var(--sub)'}">${g.can ? fmt(g.can) + ' can be reversed' : 'nothing to reverse'}</span>${g.n_skipped ? `<span class="chip">${fmt(g.n_skipped)} skipped</span>` : ''}</button>
      ${S.fOpen === g.path ? `<div style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
        <span class="mono wrap sub" style="font-size:11px">${esc(g.path)}</span>
        <div class="loglist">${g.sample.map(e => `<span><b>${esc(e.kind)}</b> <span class="mono">${esc(e.from)}</span> → <span class="mono">${esc(e.to)}</span></span>`).join('')}${g.total > g.sample.length ? `<span class="sub">… ${fmt(g.total - g.sample.length)} more</span>` : ''}</div>
        ${g.n_skipped ? `<details><summary>${fmt(g.n_skipped)} will be skipped</summary><div class="loglist">${g.skipped.map(x => `<span>${esc(x.why)}: <span class="mono">${esc(x.path)}</span></span>`).join('')}</div></details>` : ''}
        <span class="sub" style="font-size:12px">Reversing: moved files go back to where they were${g.copies ? `; the ${plural(g.copies, 'copy', 'copies')} go to a new <span class="mono">_undone</span> folder in the library` : ''}. Nothing is deleted or overwritten. A new restore log is written.</span>
        <div class="row"><button class="btn green" ${!g.can || running ? 'disabled' : ''} onclick="A.fReverse(${arg(g.path)})">Reverse ${plural(g.can, 'change')}</button></div></div>` : ''}</article>`;
    body = `<section class="row" style="gap:8px"><button class="btn outline" onclick="A.fLoadLog()">Load a restore log from anywhere…</button>${L && L.folder ? `<button class="btn ghost small" onclick="call('open_folder',${arg(L.folder)})">Open the logs folder</button>` : ''}</section>
      ${S.fExtra ? card(S.fExtra) : ''}
      ${!L ? '<p><span class="spin"></span> Loading…</p>' : L.logs.length ? L.logs.map(card).join('') : '<div class="panel empty">No restore logs yet. Every copy, archive and reverse writes one.</div>'}`;
  } else if (tab === 'back') {
    body = `<section class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px">
      <b>Put everything back from the archive</b><span style="font-size:14px">Every archived original is moved back to exactly where it came from. If something already sits at an old place, that original stays in the archive (you see a list). Nothing is overwritten or deleted, and a restore log is written. Your library copies are not touched.</span>
      <div class="row"><button class="btn amber" ${running ? 'disabled' : ''} onclick="A.fRestoreAll()">Put everything back…</button><span class="sub" style="font-size:12px">You see the count and confirm first. Single songs: use Find a song.</span></div></section>`;
  } else {
    body = `<section class="panel" style="padding:18px;display:flex;flex-direction:column;gap:10px">
      <b>Undo copy & tag</b><span style="font-size:14px">Every copy in the library (and the cover.jpg files made) is <b>moved</b> into a new folder <span class="mono">_undone_…</span> inside the library. Nothing is deleted. Originals are not touched (already archived originals stay archived — put them back from Find a song or a restore log).</span>
      <div class="row"><button class="btn amber" ${running ? 'disabled' : ''} onclick="A.fUndoCopy()">Undo copy & tag…</button><span class="sub" style="font-size:12px">You see the count and confirm first.</span></div></section>`;
  }
  return `<header class="bighead"><h1>Find & restore</h1><p>Search any song, put an archived original back, or reverse any change from its restore log. Nothing is ever deleted or overwritten.</p></header>
    <div class="seg" style="align-self:flex-start">${tabs}</div>${body}`;
}

// ---- Settings: online services (asked before use, data sent shown), keys, site order, cover order, look

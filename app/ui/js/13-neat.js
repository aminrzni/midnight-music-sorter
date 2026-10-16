/* Midnight 00:01 · Neat Picky screen (part of the screens, loaded in order by index.html) */
'use strict';
const NF = [['artist', 'Artist'], ['title', 'Title'], ['album', 'Album'], ['albumartist', 'Album artist'], ['year', 'Year'], ['track', 'Track'], ['disc', 'Disc'], ['genre', 'Genre']];
const NSTATE = { accept: ['✓ Approved · new tags', 'var(--green-text)'], keep: ['✓ Approved · my tags kept', 'var(--blue, #8FA3C0)'], later: ['Later', LATER_C], find: ['Find another (in Review)', 'var(--amber-text)'] };
function ring(p) {
  const c = 2 * Math.PI * 16, col = pctColor(p);
  return `<span class="ring" title="${p}% alike"><svg width="42" height="42" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="var(--line)" stroke-width="4"/><circle cx="20" cy="20" r="16" fill="none" stroke="${col}" stroke-width="4" stroke-dasharray="${c * p / 100} ${c}" transform="rotate(-90 20 20)" stroke-linecap="round"/></svg><b style="color:${col}">${p}</b></span>`;
}
function neatScreen() {
  const N = S.neat;
  if (!N) { if (!S.neatLoading) { S.neatLoading = true; call('neat_list').then(r => { S.neat = r || { rows: [] }; S.neatLoading = false; render(); }); }
    return `<header class="bighead"><h1>Neat Picky</h1><p><span class="spin"></span> Loading…</p></header>`; }
  const dens = S.nDens || store.get('nDens', 'full'), opened = S.nOpen || (S.nOpen = {});
  const f = S.nF || 'recent', so = S.nSort || (f === 'recent' ? 'recent' : 'pct_asc'), gb = S.nGroup || '', min = S.nMin || 90, all = S.nAll;
  const changed = r => NF.some(([k]) => r.new[k] && (r.old[k] || '') !== r.new[k]);
  const pass = (r, k) => k === 'all' || (k === 'recent' && r.t > 0) || (k === 'changes' && changed(r)) || (k === 'low' && r.pct < 80) || (k === 'open' && !r.state) || r.state === k;
  const rows = N.rows.filter(r => pass(r, f));
  const nm = r => (r.new.title || r.file).toLowerCase();
  const by = (a, b) => so === 'recent' ? (b.t || 0) - (a.t || 0) || nm(a).localeCompare(nm(b)) : so === 'pct_asc' ? a.pct - b.pct || nm(a).localeCompare(nm(b)) : so === 'pct_desc' ? b.pct - a.pct || nm(a).localeCompare(nm(b))
    : so === 'artist' ? (a.new.artist || '').localeCompare(b.new.artist || '') || nm(a).localeCompare(nm(b))
    : so === 'track' ? (parseInt(a.new.disc) || 1) - (parseInt(b.new.disc) || 1) || (parseInt(a.new.track) || 0) - (parseInt(b.new.track) || 0) || nm(a).localeCompare(nm(b))
    : nm(a).localeCompare(nm(b));
  const gk = r => gb === 'album' ? (r.new.album || '?') + ' — ' + (r.new.albumartist || r.new.artist) : gb === 'artist' ? r.new.artist || '?' : gb === 'folder' ? r.folder : '';
  // decided songs go to the end; groups keep the sort you chose inside them
  const rec = id => (S.nRecent || []).indexOf(id), recA = r => rec(r.id) >= 0 && r.state;
  const logMode = f === 'recent' && so === 'recent';          // 2.0.1: Check tags opens as a log: what you changed last is on top, so a mistake is easy to undo
  if (logMode) rows.sort((a, b) => (b.t || 0) - (a.t || 0)); else rows.sort((a, b) => (!recA(b) - !recA(a)) || (recA(a) && recA(b) ? rec(a.id) - rec(b.id) : 0) || (!!a.state - !!b.state) || (gb ? gk(a).localeCompare(gk(b)) : 0) || by(a, b));
  S.nOrder = rows.map(r => r.id);
  const page = S.nPage || 100, shown = rows.slice(0, page);
  const sel = S.nSel || (S.nSel = {}), nsel = Object.keys(sel).filter(k => sel[k]).length;
  const easy = rows.filter(r => !r.state && r.pct >= min);
  const groups = {}; if (gb) rows.forEach(r => { if (!r.state) (groups[gk(r)] = groups[gk(r)] || []).push(r.id); });
  let lastG = null, decidedShown = logMode;
  const body = shown.map(r => {
    let head = '';
    if (r.state && !decidedShown) { decidedShown = true; lastG = null; head += `<div class="qsec"><b>DECIDED · ${fmt(rows.filter(x => x.state).length)}</b><span class="sub">accepted, kept or later — at the end</span></div>`; }
    const g = gb && !r.state ? gk(r) : null;
    if (g !== null && g !== lastG) { const ids = groups[g] || [], allSel = ids.length && ids.every(i => sel[i]);
      head += `<div class="qsec ngrp"><label class="row" style="gap:8px;cursor:pointer"><input type="checkbox" ${allSel ? 'checked' : ''} onchange="A.nGroupSel(${arg(g)},this.checked)"><b>${esc(gb === 'folder' ? g.split(/[\\/]/).pop() : g)}</b></label><span class="sub">${plural(ids.length, 'song')}${gb === 'folder' ? ' · ' + esc(g) : ''}</span></div>`; }
    lastG = g;
    const fields = NF.filter(([k]) => all || (r.old[k] || '') !== (r.new[k] || ''));
    const st = NSTATE[r.state] || (r.t > 0 ? ['Decided in Review', 'var(--green-text)'] : ['Needs approval', 'var(--amber-text)']);
    const when = r.t > 0 ? new Date(r.t * 1000).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
    const showTab = dens === 'full' || opened[r.id];
    const summary = dens !== 'full' && !opened[r.id] ? `<button class="nsum" onclick="event.stopPropagation();S.nOpen[${arg(r.id)}]=true;render()" title="Show the details">${fields.length ? fields.map(([k, l]) => { const p = r.per[k]; return `<span class="nchg">${l}: ${esc(String(r.old[k] || '–'))} → ${esc(String(r.new[k] || ''))}</span>`; }).join('') : '<span class="sub">nothing changes</span>'}</button>` : (dens !== 'full' ? `<button class="btn small ghost" onclick="event.stopPropagation();delete S.nOpen[${arg(r.id)}];render()">Hide details</button>` : '');
    return head + `<article class="nrow ${dens} ${r.state ? 'decided' : ''} ${sel[r.id] ? 'sel' : ''}" data-nid="${esc(r.id)}" onmousedown="A.nDown(event,${arg(r.id)})" onmouseenter="A.nEnter(event,${arg(r.id)})">
      <label class="nck"><input type="checkbox" class="qck" ${sel[r.id] ? 'checked' : ''} onclick="event.stopPropagation()" onchange="A.nToggle(${arg(r.id)},this.checked)"></label>${ring(r.pct)}
      <div class="nmain"><div class="row" style="gap:8px;justify-content:space-between"><span style="min-width:0;display:flex;flex-direction:column"><b style="overflow-wrap:anywhere">${esc(r.new.artist)} — ${esc(r.new.title)}</b>
        <span class="sub mono" style="font-size:11px;overflow-wrap:anywhere">${esc(r.file)} · ${esc(r.source || '')}${r.rtype ? ' · ' + esc(RTYPE[r.rtype] || r.rtype) : ''}</span></span>
        ${st ? `<span class="chip" style="color:${st[1]}">${st[0]}${when ? ' · ' + when : ''}</span>` : ''}</div>
        ${summary}${showTab ? (fields.length ? `<table class="ntab"><tr><th></th><th>Now</th><th>After</th></tr>${fields.map(([k, l]) => { const p = r.per[k];
          return `<tr><td class="sub">${l}${p != null && p < 100 ? ` <span style="color:${pctColor(p)};font-size:11px">${p}%</span>` : p === null && r.new[k] ? ' <span class="sub" style="font-size:11px">added</span>' : ''}</td><td>${r.old[k] ? diffHtml(r.old[k], r.new[k]) : '<span class="sub">–</span>'}</td><td>${r.new[k] ? diffHtml(r.new[k], r.old[k]) : '<span class="sub">(unchanged)</span>'}</td></tr>`; }).join('')}</table>`
          : '<span class="sub" style="font-size:12px">Tags already match — nothing changes.</span>') : ''}
        <div class="row" style="gap:6px;flex-wrap:wrap">${r.state || r.t > 0 ? '' : `<button class="btn small green" data-pct="${r.pct}" onclick="A.neat([${arg(r.id)}],'accept')">Accept new tags</button>`}${!(r.state || r.t > 0) && r.per && r.per.genre != null && r.per.genre < 100 ? `<button class="btn small outline" data-pct="${r.pct}" onclick="A.neat([${arg(r.id)}],'accept_nogenre')" title="Take the new tags but keep the genre your file has">Accept, keep my genre</button>` : ''}<button class="btn small" onclick="A.neat([${arg(r.id)}],'keep')" title="The song is still placed in the library, but its tags are not changed">Keep my tags</button>
          <button class="btn small outline" onclick="A.neat([${arg(r.id)}],'find')" title="Not this match: the song goes to Review (Not this) to search for the right one">Find another</button><button class="btn small ghost" onclick="A.neat([${arg(r.id)}],'later')">Later</button>
          <button class="btn small ghost" onclick="A.play(${arg(r.id)})">${S.playing === r.id ? '❚❚' : '▶'} Play</button><button class="btn small ghost" onclick="A.reveal(${arg(r.id)})">Explorer</button>
          ${r.state ? `<button class="btn small" onclick="A.neat([${arg(r.id)}],'undo')" title="Take the decision back so you can decide again">Undo</button>` : r.t > 0 ? `<button class="btn small" onclick="A.rvUndo(${arg(r.id)});S.neat=null" title="Take your decision from Review back">Undo</button>` : ''}</div></div></article>`;
  }).join('');
  return `<header class="bighead"><h1>Neat Picky</h1><p>Every confirmed song: the tags it has now and the tags it will get. Accept the new tags, keep yours (the song is still sorted), find another match, or leave it for later. Nothing is written until Copy & tag — and only to the copies.</p></header>
    ${N.stale ? `<div class="banner">Your choices go into the plan when it is updated (nothing is copied).<button class="btn small outline" onclick="A.updatePlan()">Update the plan now</button></div>` : ''}
    ${verifyBar()}
    <section class="grid4"><div class="stat"><div class="v">${fmt(N.rows.length)}</div><div class="k">confirmed songs</div></div><div class="stat"><div class="v">${fmt(N.rows.filter(r => r.pct === 100).length)}</div><div class="k">already 100% alike</div></div>
      <div class="stat"><div class="v" style="color:var(--amber-text)">${fmt(N.rows.filter(r => r.pct < 80).length)}</div><div class="k">under 80% alike</div></div><div class="stat"><div class="v">${fmt(N.rows.filter(r => r.state).length)}</div><div class="k">approved / decided by you</div></div></section>
    <section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:10px">
      <div class="row" style="gap:6px;flex-wrap:wrap">${[['recent', 'Recently changed'], ['changes', 'With changes'], ['low', 'Under 80%'], ['open', 'Needs approval'], ['all', 'All'], ['accept', 'New tags'], ['keep', 'My tags kept'], ['find', 'Find another'], ['later', 'Later']].map(x =>
        `<button class="fchip" aria-pressed="${f === x[0]}" onclick="S.nF=${arg(x[0])};S.nPage=100;render()">${x[1]} ${fmt(N.rows.filter(r => pass(r, x[0])).length)}</button>`).join('')}</div>
      <div class="row" style="gap:10px;flex-wrap:wrap"><span class="sub">Sort</span><div class="seg small">${[['recent', 'Recent'], ['pct_asc', 'Match % ↑'], ['pct_desc', 'Match % ↓'], ['artist', 'Artist'], ['title', 'Title'], ['track', 'Track']].map(x => `<button aria-pressed="${so === x[0]}" onclick="S.nSort=${arg(x[0])};render()">${x[1]}</button>`).join('')}</div>
        <span class="sub">Group by</span><div class="seg small">${[['', 'None'], ['album', 'Album'], ['artist', 'Artist'], ['folder', 'Folder']].map(x => `<button aria-pressed="${gb === x[0]}" onclick="S.nGroup=${arg(x[0])};render()">${x[1]}</button>`).join('')}</div>
        <label class="row" style="gap:6px;font-size:13px;cursor:pointer"><input type="checkbox" class="qck" ${all ? 'checked' : ''} onchange="S.nAll=this.checked;render()"> show every field</label>
        <span class="sub">Size</span><div class="seg small" title="Smaller cards show more songs at once; the details open with a click">${[['full', 'Detailed'], ['compact', 'Compact'], ['tiles', 'Tiles']].map(x => `<button aria-pressed="${dens === x[0]}" onclick="S.nDens=${arg(x[0])};store.set('nDens',${arg(x[0])});render()">${x[1]}</button>`).join('')}</div></div>
      <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small outline selbtn" onclick="A.nSelAll(true)" title="Select every song in this list, not only the ones on screen (Ctrl+A)">${svg('M5 12l5 5L20 7', 14)} Select all ${fmt(rows.length)} shown</button><button class="btn small outline selbtn" onclick="A.nSelAll(false)">Select none</button><button class="btn small green" ${easy.length ? '' : 'disabled'} onclick="A.neatEasy()">Accept all safe changes: ${plural(easy.length, 'song')} at least</button>
        <select class="text" style="width:auto;padding:4px 8px" onchange="S.nMin=+this.value;render()">${[100, 95, 90, 80, 70].map(v => `<option ${v === min ? 'selected' : ''} value="${v}">${v}%</option>`).join('')}</select><span class="sub" style="font-size:12px">alike (shown, not decided)</span>
        <span class="sub" style="font-size:12px;flex-basis:100%">Select: click a card · Shift+click selects everything between · hold the mouse and move down to select many · tick a group to select it all.</span></div></section>
    <div class="nlist ${dens}">${body || '<div class="panel empty">Nothing here.</div>'}</div>
    ${rows.length > page ? `<div class="row"><button class="btn outline" onclick="S.nPage=${page + 100};render()">Show 100 more (${fmt(rows.length - page)} left)</button></div>` : ''}
    ${neatBar()}`;
}
function neatSelMin() { const sel = S.nSel || {}; const v = ((S.neat && S.neat.rows) || []).filter(r => sel[r.id] && !r.state).map(r => r.pct); return v.length ? Math.min(...v) : ''; }
function neatBar() {
  const sel = S.nSel || {}, n = Object.keys(sel).filter(k => sel[k]).length;
  return `<div class="nbar ${n ? 'on' : ''}" id="nbar">${n ? `<b>${plural(n, 'song')} selected</b><button class="btn small green" data-pct="${neatSelMin()}" onclick="A.neatSel('accept')">Accept new tags</button><button class="btn small" onclick="A.neatSel('keep')">Keep my tags</button><button class="btn small outline" onclick="A.neatSel('find')">Find another</button><button class="btn small ghost" onclick="A.neatSel('later')">Later</button><span class="grow"></span><button class="btn small ghost" onclick="S.nSel={};render()">Clear</button>` : ''}</div>`;
}

// ---- Playlist manager: box sets / compilations (keep together, or sort + playlist) and your playlist files

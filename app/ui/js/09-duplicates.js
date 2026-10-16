/* Midnight 00:01 · Duplicates screen + the duplicates folder (part of the screens, loaded in order by index.html) */
'use strict';
function qText(c) {
  const lossless = c.lossless === 'yes';
  const sr = c.sample_rate ? (c.sample_rate / 1000).toFixed(c.sample_rate % 1000 ? 1 : 0) + ' kHz' : '';
  return lossless ? `Lossless${c.bits ? ' ' + c.bits + '-bit' : ''}${sr ? ' / ' + sr : ''}` : `${c.format} ${c.bitrate_kbps || '?'} kbps${c.format === 'M4A' || c.format === 'AAC' ? ' (AAC)' : ''}${sr ? ' · ' + sr : ''}`;
}
function qScore(c) {
  if (c.lossless === 'yes') return Math.min(100, 85 + ((c.bits || 16) > 16 ? 10 : 0) + ((c.sample_rate || 44100) > 48000 ? 5 : 0));
  const w = { OPUS: 1.6, M4A: 1.3, AAC: 1.3, OGG: 1.2, MP3: 1, WMA: 0.9 }[c.format] || 1;
  return Math.max(5, Math.min(80, Math.round((c.bitrate_kbps || 0) * w / 320 * 80)));
}
function dupState(g, c) {
  const ch = g.choice;
  if (ch && (ch.leave || []).includes(c.file_id)) return 'out';
  if (c.flat) return 'flat';                                  // an extra copy: goes to the flat _Duplicates folder
  if (ch && ch.mode === 'all') return 'in';
  if (ch && (ch.include || []).includes(c.file_id)) return 'in';
  if (!ch && g.live) return c.extra ? 'in' : 'kept';
  return c.extra ? 'out' : 'kept';
}
const LOONY_MODES = [
  ['copy', 'Copy', 'Copies the extras into one flat folder. Originals stay. Safest.', 'Copy them'],
  ['C01', 'Move · music folder', 'Moves the extras into a folder inside their music folder.', 'Move them'],
  ['C02', 'Move · library', 'Moves the extras into a folder inside your new library.', 'Move them'],
  ['C03', 'Both', 'Moves them out of the music folder and copies them into the library.', 'Move + copy them'],
  ['C04', 'Delete identical', 'Only copies with exactly the same audio as the copy you keep. They go to the Windows Recycle Bin (restore from there if needed).', 'Delete identical ones…']];
function dupsScreen() {
  const D = S.dups;
  if (!D) { if (!S.dupsLoading) { S.dupsLoading = true; call('dup_list').then(r => { S.dups = r || { groups: [] }; S.dupsLoading = false; render(); }); }
    return `<header class="bighead"><h1>Duplicates</h1><p><span class="spin"></span> Loading…</p></header>`; }
  const gs = D.groups || [];
  gs.forEach(g => { const o = (S.dupOrder || {})[g.group]; if (o) { const i = g.copies.findIndex(c => c.file_id === o); if (i > 0) g.copies.unshift(g.copies.splice(i, 1)[0]); } });
  const f = S.dupF || 'all', job = S.B.job, running = job && !job.done;
  const extra = gs.reduce((n, g) => n + g.copies.filter(c => dupState(g, c) === 'flat').length, 0);
  const saved = gs.reduce((n, g) => n + g.copies.filter(c => dupState(g, c) === 'flat').reduce((t, c) => t + (c.size_mb || 0), 0), 0);
  const pairs = gs.filter(g => g.pair).length;
  const list = gs.filter(g => g.group === S.dupOpen || f === 'all' || (f === 'reviewed' && g.choice) || (f === 'identical' && g.identical) || (f === 'lower' && g.lower) || (f === 'pair' && g.pair) || (f === 'unsure' && g.sure < 90));
  if ((S.dupSort || 'unsure') === 'artist') list.sort((a, b) => (a.copies[0].artist || '~').localeCompare(b.copies[0].artist || '~') || (a.copies[0].title || '').localeCompare(b.copies[0].title || ''));
  else list.sort((a, b) => a.sure - b.sure);
  const open = list.filter(g => !g.choice), done = list.filter(g => g.choice).sort((a, b) => a.choice.t - b.choice.t);
  if (!S.dupOpen || !list.some(g => g.group === S.dupOpen)) S.dupOpen = (open[0] || {}).group;
  const card = g => {
    const top = g.copies[0], isOpen = S.dupOpen === g.group, ch = g.choice, cmp = (S.dupCmp || {})[g.group];
    const badge = ch ? `<span class="chk ok">Done · ${ch.mode === 'best' ? 'best of each kind' : ch.mode === 'all' ? 'all copies' : 'custom ' + g.copies.filter(c => dupState(g, c) !== 'out').length + ' of ' + g.copies.length}</span>` : '';
    const custom = S.dupCustom && S.dupCustom.group === g.group;
    const rows = g.copies.map((c, i) => {
      const stt = custom ? (S.dupCustom.keep[c.file_id] ? (c.extra || c.flat ? 'in' : 'kept') : (c.extra || c.flat ? 'flat' : 'out')) : dupState(g, c), q = c.quality || {};
      const best = g.copies.find(x => !x.extra && x.kind === c.kind) || top;
      const safe = c.extra && c.identical_audio === 'yes' && qScore(c) <= qScore(best);
      const sameAs = cmp ? cmp.pairs.filter(p => (p.a === c.file_id || p.b === c.file_id) && p.pct != null).map(p => `#${g.copies.findIndex(x => x.file_id === (p.a === c.file_id ? p.b : p.a)) + 1} ${p.pct}%`).join(' · ') : '';
      return `<div class="duprow ${stt === 'out' ? 'out' : ''} ${i ? '' : 'best'}" draggable="true" title="Drag a copy to the top to make it the one you keep" ondragstart="S.dupDrag=${arg(c.file_id)};event.dataTransfer.effectAllowed='move'" ondragover="event.preventDefault();this.classList.add('dropto')" ondragleave="this.classList.remove('dropto')" ondrop="event.preventDefault();A.dupDropFirst(${arg(g.group)},${i})">
        <span class="rank">#${i + 1}</span><button class="pv ${S.playing === c.file_id ? 'on' : ''}" aria-label="Play" onclick="A.play(${arg(c.file_id)})">${S.playing === c.file_id ? '❚❚' : '▶'}</button>
        <span class="dq"><span class="row" style="gap:6px"><span class="fmt ${c.lossless === 'yes' ? 'll' : ''}">${esc(c.format)}</span><b>${esc(qText(c))}</b>${c.identical_audio === 'yes' ? '<span class="chip">identical audio</span>' : ''}${c.tag ? '<span class="chip" title="The copy in _Duplicates gets the Comment tag DUPLICATE. Clear the Comment tag to remove it.">tagged DUPLICATE</span>' : ''}${c.flat && c.dup_name ? '<span class="chip" title="Name in _Duplicates">' + esc(c.dup_name) + '</span>' : ''}${safe ? '<span class="chip safe" title="Same audio as the kept copy and not better: safe to delete after archiving">safe to delete</span>' : ''}</span>
          <span class="qbar"><i style="width:${qScore(c)}%"></i></span>
          <span>${mmss(c.length)} · ${c.size_mb} MB · tags ${c.tags_filled}/7${c.cover_px ? ' · cover ' + c.cover_px + ' px' : ' · no cover'}${sameAs ? ' · alike: ' + sameAs : ''}</span>
          ${q && Object.keys(q).length ? `<span>${q.fake_lossless ? '<b style="color:var(--clay)">not real lossless (made from a lossy file)</b> · ' : ''}${q.bandwidth ? 'sound ' + esc(q.bandwidth) + ' · ' : ''}${q.peak_db != null ? 'peak ' + q.peak_db + ' dB · mean ' + q.mean_db + ' dB' : ''}${q.clipped ? ' · <b style="color:var(--amber-text)">clipping</b>' : ''}</span>` : ''}
          <span class="sub" style="font-size:12px">${esc(c.why || (c.extra ? '' : 'best ' + c.kind)).replace(/\bF\d{6}\b/g, m => '#' + (g.copies.findIndex(x => x.file_id === m) + 1))}</span></span>
        <span class="dp mono" title="${esc(c.source)}">${esc(c.source)}</span>
        <span class="dd"><button class="tog ${stt}" onclick="A.dupToggle(${arg(g.group)},${arg(c.file_id)})">${stt === 'kept' ? 'Kept ✓' : stt === 'in' ? 'Kept in album ✓' : stt === 'flat' ? 'In _Duplicates · keep in album' : 'Left out · include'}</button>
          <button class="btn small ghost" onclick="A.reveal(${arg(c.file_id)})" title="Show in Explorer">Explorer</button></span></div>`;
    }).join('');
    return `<article class="panel dupcard ${ch ? 'done' : ''}" data-g="${esc(g.group)}"><button class="duphead" onclick="S.dupOpen=${isOpen ? 'null' : arg(g.group)};S.dupCustom=null;render()">
        ${D.covers ? `<span class="ancover" style="width:44px;height:44px;background:var(--panel2)"><img src="${esc(D.covers + encodeURIComponent(top.file_id))}" alt="" loading="lazy" onerror="this.remove()"></span>` : ''}
        <span class="grow" style="min-width:0;display:flex;flex-direction:column"><b style="overflow-wrap:anywhere">${esc(top.artist || '?')} — ${esc(top.title || top.new_name || '')}</b><span class="sub" style="font-size:12px">${plural(g.copies.length, 'copy', 'copies')} · ${esc(top.album || '')}</span></span>
        <span class="chip" style="color:${pctColor(g.sure)}" title="How sure the app is that these are the same song: ${esc(g.sure_how)}">${g.sure}% same song</span>${g.identical ? '<span class="chip">identical</span>' : ''}${g.pair ? '<span class="chip">FLAC + MP3</span>' : ''}${badge}</button>
      ${isOpen ? `<div class="duprows">${rows}</div>
        <div class="acts" style="justify-content:space-between"><span class="row" style="gap:8px;flex-wrap:wrap">${custom ? `<button class="btn green small" onclick="A.dupCustomDone(${arg(g.group)})">Done with this choice</button><button class="btn small ghost" onclick="S.dupCustom=null;render()">Cancel</button>`
          : g.sure < 90 ? `<span class="sub" style="font-size:12px;flex-basis:100%;color:var(--amber-text)">Not sure these are the same song (${g.sure}%): they may be different versions or lengths. Nothing is left out unless you choose it.</span><button class="btn green small" onclick="A.dupDecide(${arg(g.group)},'all')">Keep all copies</button><button class="btn small" onclick="A.dupDecide(${arg(g.group)},'best')">Best of each kind only</button>`
          : `<button class="btn green small" onclick="A.dupDecide(${arg(g.group)},'best')">Best of each kind only</button><button class="btn small" onclick="A.dupDecide(${arg(g.group)},'all')">Include all copies</button>
          ${ch ? `<button class="btn small ghost" onclick="A.dupDecide(${arg(g.group)},'undo')">Undo</button>` : ''}`}</span>
          <span class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small outline" onclick="A.dupQuality(${arg(g.group)})" ${(S.dupBusy || {})[g.group] ? 'disabled' : ''}>${(S.dupBusy || {})[g.group] === 'q' ? '<span class="spin"></span> Measuring…' : 'Measure quality'}</button>
          <button class="btn small outline" onclick="A.dupCompare(${arg(g.group)})" ${(S.dupBusy || {})[g.group] ? 'disabled' : ''}>${(S.dupBusy || {})[g.group] === 'c' ? '<span class="spin"></span> Comparing…' : 'Compare copies'}</button></span></div>` : ''}</article>`;
  };
  return `<header class="bighead"><h1>Duplicates</h1><p>Songs found more than once in the same album folder. The best copy of each kind is kept (a FLAC and an MP3 both stay); every other copy is copied into one flat <b>_Duplicates</b> folder, named "Song (2)", "Song (3)"…; copies with exactly the same audio also get the removable Comment tag DUPLICATE. Originals are never changed or deleted.</p></header>
    <section class="grid4"><div class="stat"><span class="si">${svg('M8 8h12v12H8zM4 16V4h12', 18)}</span><div class="srow"><div class="k">duplicate songs</div><div class="v">${fmt(gs.length)}</div></div></div><div class="stat"><span class="si">${svg('M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', 18)}</span><div class="srow"><div class="k">extra copies in _Duplicates</div><div class="v" style="color:var(--amber-text)">${fmt(extra)}</div></div></div>
      <div class="stat"><span class="si">${svg('M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7', 18)}</span><div class="srow"><div class="k">size of _Duplicates</div><div class="v">${saved >= 1000 ? (saved / 1000).toFixed(1) + ' GB' : Math.round(saved) + ' MB'}</div></div></div><div class="stat"><span class="si">${svg('M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7', 18)}</span><div class="srow"><div class="k">FLAC + MP3 pairs (both kept)</div><div class="v">${fmt(pairs)}</div></div></div></section>
    ${D.possible ? `<div class="banner" style="border-color:var(--amber)"><b>${plural(D.possible, 'song')}</b>&nbsp;still waiting in Review ${D.possible === 1 ? 'looks' : 'look'} like a copy of another planned song (same name, same folder, same length). They become duplicates here once you accept them and update the plan.<button class="btn small outline" onclick="A.go('review')">Go to Review</button></div>` : ''}
    ${D.stale ? `<div class="banner">Your choices go into the plan when it is updated (nothing is copied).<button class="btn small outline" onclick="A.updatePlan()">Update the plan now</button></div>` : ''}
    <section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:10px">
      <div class="row" style="gap:6px;flex-wrap:wrap;align-items:center">${(() => { const CIC = { all: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', unsure: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h0', identical: 'M8 8h12v12H8zM4 16V4h12', lower: 'M12 4v14M6 13l6 6 6-6', pair: 'M7 4L3 8l4 4M3 8h14M17 20l4-4-4-4M21 16H7', reviewed: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6' };
        const chip = x => `<button class="fchip fc-${x[0]} ${x[0] === 'reviewed' ? 'fc-done' : ''}" aria-pressed="${f === x[0]}" onclick="S.dupF=${arg(x[0])};render()" ${x[0] === 'unsure' ? 'title="Not sure: under 90%"' : ''}><span class="mico">${svg(CIC[x[0]], 15)}</span>${x[1]} ${x[2]}</button>`, sep = '<span style="width:1px;align-self:stretch;min-height:22px;background:var(--line);margin:0 6px"></span>';
        return chip(['all', 'All', gs.length]) + sep + [['unsure', 'Not sure', gs.filter(g => g.sure < 90).length], ['identical', 'Identical', gs.filter(g => g.identical).length], ['lower', 'Lower', gs.filter(g => g.lower).length], ['pair', 'FLAC + MP3', pairs]].map(chip).join('') + sep + chip(['reviewed', 'Reviewed', gs.filter(g => g.choice).length]); })()}
        <span class="dupsep"></span>
        <button class="btn small green" onclick="A.dupBestAll()">${svg('M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z', 15)} Best only, everywhere</button>
        <button class="btn small outline" onclick="A.dupCheckAll()" ${S.dupAll ? 'disabled' : ''} data-tip="Compares the sound of every song you are not sure about (fingerprints made on this PC, nothing is sent). Takes a while.">${S.dupAll ? '<span class="spin"></span> Checking ' + S.dupAll : svg('M3 12h2M7 8v8M11 4v16M15 8v8M19 10v4', 15) + ' Check the unsure ones by sound'}</button>
        <button class="btn small outline" onclick="A.dupClear()" data-tip="Removes your choice from every song in the category shown above, so they are open again (nothing is deleted).">${svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9 9l6 6M15 9l-6 6', 15)} Deselect all shown</button></div>
      <div class="sub" style="font-size:12px">Keys: ↑ ↓ move between songs · Enter = best of each kind · A = include all · U = undo · Space = play the top copy.</div>
    </section>
    <section class="panel" style="padding:14px;display:flex;flex-direction:column;gap:10px">
      <div class="loony"><div class="row" style="gap:8px;align-items:center"><b>Duplicate copies</b>
          <span class="infoi" tabindex="0" role="button" aria-label="About duplicate copies" style="position:relative;display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;border:1.5px solid var(--amber-text);color:var(--amber-text);font-size:12px;cursor:help" data-tip="What happens to the ${plural(extra, 'extra copy', 'extra copies')}. They are copied into one flat folder, _Duplicates, inside the library, named Song (2), Song (3)… Exactly identical copies get the Comment tag DUPLICATE (remove it by clearing the Comment tag). Copy &amp; tag keeps the best copy of each kind in the album. Moves ask 'Are you sure?' first and write a restore log. Nothing is ever deleted."><b>i</b></span></div>
        <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center;margin-top:6px">
          <select class="text" aria-label="What to do with the extra copies" style="min-width:210px" onchange="S.loonyMode=this.value;render()">${LOONY_MODES.map(m => `<option value="${m[0]}" ${(S.loonyMode || 'copy') === m[0] ? 'selected' : ''}>${esc(m[1])}</option>`).join('')}</select>
          <button class="btn small ${(S.loonyMode || 'copy') === 'C04' ? 'clay' : 'amber'}" onclick="A.loonyGo()" ${!extra || running ? 'disabled' : ''}>${(LOONY_MODES.find(m => m[0] === (S.loonyMode || 'copy')) || LOONY_MODES[0])[3]}</button>
          ${D.loony_count ? `<button class="btn small outline" onclick="call('open_folder',${arg(D.loony)})">Open the duplicates folder (${D.loony_count})</button>` : ''}</div>
        <span class="sub" style="font-size:12px;display:block;margin-top:4px">${esc((LOONY_MODES.find(m => m[0] === (S.loonyMode || 'copy')) || LOONY_MODES[0])[2])}</span></div>
      <div class="row" style="gap:8px;flex-wrap:wrap;justify-content:flex-end"><span class="sub" style="font-size:12px">Sort the songs below</span><span class="seg small">${[['unsure', 'Least sure first'], ['artist', 'Artist']].map(o => `<button aria-pressed="${(S.dupSort || 'unsure') === o[0]}" onclick="S.dupSort=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span></div></section>
    ${open.map(card).join('') || (gs.length ? '' : '<div class="panel empty">No duplicates found.</div>')}
    ${done.length ? `<div class="qsec"><b>DONE · ${done.length}</b></div>${done.map(card).join('')}` : ''}`;
}


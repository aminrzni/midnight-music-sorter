/* Midnight 00:01 · Plan preview screen (layout, name blocks) (part of the screens, loaded in order by index.html) */
'use strict';
const LEVELS = { tier: 'Collection tier', artist: 'Artist', genre: 'Genre', decade: 'Decade', letter: 'First letter', type: 'Release type' };
const PRESETS = [['Standard', ['tier', 'artist']], ['Artist only', ['artist']], ['By genre', ['genre', 'artist']], ['By decade', ['decade', 'artist']], ['A–Z letter', ['letter', 'artist']], ['Artist, then type', ['artist', 'type']]];
const PRESET_IC = { 'Standard': 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', 'Artist only': 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0', 'By genre': 'M3 12V4h8l9 9-8 8z', 'By decade': 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4', 'A–Z letter': 'M5 19l5-14 5 14M7 14h6M18 5v14', 'Artist, then type': 'M4 6h12M4 11h12M4 16h7' };
function planExample(L, s) {
  s = s || { artist_folder: 'The Beatles', credit_text: 'The Beatles', album: 'Abbey Road', year: '1969', track: '7', title: 'Here Comes the Sun', genre: 'Rock', rtype: 'Album', tier: '79 Get To Collection', ext: '.flac' };
  const af = s.artist_folder || 'Artist', y = String(s.year || '').slice(0, 4);
  const tierS = s.tier || '79 Get To Collection', tp = tierS.split(' ');
  const afT = (L.tier_style === 'name' && !s.tier_plain) ? (L.tier_name === 'dash' ? `${tp[0]} ${tp[1] || ''} - ${af}` : L.tier_name === 'suffix' ? `${af} [${tp[1] || ''} ${tp[0]}]` : `[${tp[0]}] ${af}`) : af;
  const lv = L.levels.filter(l => !(l === 'tier' && L.tier_style === 'name')).map(l => l === 'tier' ? tierS : l === 'artist' ? afT : l === 'genre' ? ((s.genre || 'Other').split(/[;/]/)[0].trim() || 'Other')
    : l === 'decade' ? (y ? y.slice(0, 3) + '0s' : 'Unknown Year') : l === 'letter' ? (af.replace(/^(the|a|an)\s+/i, '')[0] || '#').toUpperCase() : l === 'type' ? 'Albums' : '');
  const alb = (L.levels.includes('artist') ? '' : af + ' - ') + (L.release === 'album_year' ? `${s.album} (${y})` : L.release === 'album' ? s.album : `${y} - ${s.album}`);
  const n = String(s.track || '1').padStart(2, '0');
  const vals = { artist: s.credit_text || af, albumartist: af, year: y, album: s.album, track: n, disc: s.disc || '1', title: s.title, genre: (s.genre || '').split(/[;/]/)[0].trim(), type: '' };
  const fill = p => (p || []).map(b => b.startsWith('{') ? (vals[b.slice(1, -1)] || '') : b).join('').replace(/\(\s*\)|\[\s*\]/g, '').replace(/(\s*-\s*){2,}/g, ' - ').replace(/\s{2,}/g, ' ').replace(/^[\s\-._]+|[\s\-._]+$/g, '');
  const alb2 = L.release === 'custom' && (L.release_pattern || []).length ? (L.levels.includes('artist') ? '' : af + ' - ') + fill(L.release_pattern) : alb;
  const fn = L.file === 'custom' && (L.file_pattern || []).length ? fill(L.file_pattern) : L.file === 'track_title' ? `${n} ${s.title}` : L.file === 'artist_track_title' ? `${s.credit_text || af} - ${n} ${s.title}` : `${s.credit_text || af} - ${y} ${s.album} - ${n} ${s.title}`;
  return ['Library'].concat(lv, [alb2, fn + (s.ext || '.mp3')]);
}
const PAT_BLOCKS = [['{artist}', 'Artist'], ['{albumartist}', 'Album artist'], ['{year}', 'Year'], ['{album}', 'Album'], ['{track}', 'Track no.'], ['{disc}', 'Disc'],
  ['{title}', 'Title'], ['{genre}', 'Genre'], ['{type}', 'Type'], [' - ', ' - '], [' ', 'space'], ['(', '('], [')', ')'], ['[', '['], [']', ']'], ['.', '.'], ['_', '_']];
const PAT_NAME = Object.fromEntries(PAT_BLOCKS);
function patBuilder(which) {
  const key = which + '_pattern', pat = S.lay[key] || [];
  return `<div class="patb"><span class="sub" style="font-size:12px">Drag blocks into the row (or click them), drag inside the row to change the order, × removes.</span>
    <div class="patrow" ondragover="event.preventDefault();this.classList.add('over')" ondragleave="this.classList.remove('over')" ondrop="A.patDrop(event,${arg(which)},-1)">${pat.map((b, i) =>
      `<span class="pblk ${b.startsWith('{') ? 'tok' : 'lit'}" draggable="true" ondragstart="S.patDrag={which:${arg(which)},from:${i}};event.dataTransfer.setData('text/plain','x')" ondragover="event.preventDefault()" ondrop="event.stopPropagation();A.patDrop(event,${arg(which)},${i})">${esc(PAT_NAME[b] || b)}<button aria-label="Remove" onclick="A.patDel(${arg(which)},${i})">×</button></span>`).join('') || '<span class="sub" style="font-size:12px">drop blocks here</span>'}</div>
    <div class="patpal">${PAT_BLOCKS.map(b => `<span class="pblk ${b[0].startsWith('{') ? 'tok' : 'lit'}" draggable="true" ondragstart="S.patDrag={which:${arg(which)},add:${arg(b[0])}};event.dataTransfer.setData('text/plain','x')" onclick="A.patAdd(${arg(which)},${arg(b[0])})">${esc(b[1])}</span>`).join('')}</div></div>`;
}
function planScreen() {
  const P = S.plan, job = S.B.job, running = job && !job.done;
  if (!P) { if (!S.planLoading) { S.planLoading = true; call('plan_tree', '').then(r => { S.plan = r || {}; S.planLoading = false; S.planKids = {}; S.planKids[''] = r; if (!S.lay && r && r.layout) S.lay = JSON.parse(JSON.stringify(r.layout)); render(); }); }
    return `<header class="bighead"><h1>Plan preview</h1><p><span class="spin"></span> Loading…</p></header>`; }
  if (P.error) return `<header class="bighead"><h1>Plan preview</h1><p>${esc(P.error)}</p></header>`;
  const L = S.lay || P.layout, st = P.stats || {}, changed = JSON.stringify(L) !== JSON.stringify(P.layout) || (S.laySort && S.laySort !== P.sort_mode);
  const tree = folder => {
    const d = S.planKids[folder]; if (!d) return '<div class="song off">loading…</div>';
    return d.dirs.map(x => { const id = folder ? folder + '/' + x.name : x.name, open = S.planOpen[id];
      return `<div class="pnode"><button class="pn" onclick="A.planToggle(${arg(id)})">${open ? '▾' : '▸'} ${svg(open ? ICON.folderOpen : ICON.folder, 16, '#E8A33D', 1.6)} <b>${esc(x.name)}</b>
        <span class="sub" style="font-size:12px">${plural(x.songs, 'song')}${x.waiting ? ' · <span style="color:var(--amber-text)">' + x.waiting + ' wait for review</span>' : ''}</span></button>
        ${open ? `<div class="pkids">${tree(id)}</div>` : ''}</div>`; }).join('')
      + d.files.map(f => `<div class="pfile ${f.state}"><span class="mono" style="font-size:12px;overflow-wrap:anywhere">${esc(f.name)}</span><span class="pstate">${{ copied: 'in the library', ready: 'ready to copy', waiting: 'waits for review', extra: 'extra copy · not copied' }[f.state]}</span></div>`).join('')
      + (d.more_files ? `<div class="sub" style="font-size:12px">… and ${fmt(d.more_files)} more</div>` : '');
  };
  const simpleSort = (S.laySort || P.sort_mode) !== 'collection';      // V2.0.5 (#7): Simple sort makes NO tier folders, so the example must not show them either
  const ex = planExample(simpleSort ? Object.assign({}, L, { levels: L.levels.filter(l => l !== 'tier') }) : L, P.sample);
  const chips = L.levels.map((l, i) => l === 'tier' && simpleSort ? `<span class="lchip" style="opacity:.5;text-decoration:line-through" title="Simple sort makes no tier folders. Switch to Collection sort to use this level.">${LEVELS[l]}</span>` : `<span class="lchip"><button aria-label="Move left" onclick="A.layMove(${i},-1)" ${i ? '' : 'disabled'}>◀</button>${LEVELS[l]}<button aria-label="Move right" onclick="A.layMove(${i},1)" ${i < L.levels.length - 1 ? '' : 'disabled'}>▶</button><button aria-label="Remove" onclick="A.layDel(${i})">×</button></span>`).join('<span class="sub">/</span>');
  const add = Object.keys(LEVELS).filter(k => !L.levels.includes(k));
  return `<header class="bighead"><h1>Plan preview</h1><p>Where every song will go in your new library. Nothing is copied here. Change the folder layout with Customize folders.</p></header>
    <section class="grid4"><div class="stat"><span class="si">${svg('M8 8h12v12H8zM4 16V4h12', 18)}</span><div class="srow"><div class="k">ready to copy</div><div class="v" style="color:var(--green-text)">${fmt(st.ready || 0)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12l3 3 5-6', 18)}</span><div class="srow"><div class="k">already in the library</div><div class="v">${fmt(st.copied || 0)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', 18)}</span><div class="srow"><div class="k">wait for review</div><div class="v" style="color:var(--amber-text)">${fmt(st.waiting || 0)}</div></div></div>
      <div class="stat"><span class="si">${svg('M12 3l9 5-9 5-9-5zM3 13l9 5 9-5', 18)}</span><div class="srow"><div class="k">extra copies (not copied)</div><div class="v">${fmt(st.extra || 0)}</div></div></div></section>
    <div class="grid2" style="align-items:start">
    <section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:6px"><div class="row" style="justify-content:space-between"><h2 style="margin:0;font-size:17px">Your new library</h2><span class="mono sub" style="font-size:12px">${esc(P.library)}</span></div>
      <div class="ptree" data-ks="ptree">${tree('')}</div></section>
    <section class="panel" style="padding:16px;display:flex;flex-direction:column;gap:12px"><h2 style="margin:0;font-size:17px">Customize folders</h2>
      <div class="row" style="gap:6px;flex-wrap:wrap">${PRESETS.map(p => `<button class="fchip" aria-pressed="${JSON.stringify(p[1]) === JSON.stringify(L.levels)}" onclick="A.layPreset(${arg(JSON.stringify(p[1]))})"><span class="mico">${svg(PRESET_IC[p[0]] || 'M4 6h12M4 11h12M4 16h7', 15)}</span>${p[0]}</button>`).join('')}</div>
      <div><span class="cap">FOLDER LEVELS</span><div class="row" style="gap:6px;flex-wrap:wrap;margin-top:6px"><span class="lchip fixed">Library</span><span class="sub">/</span>${chips}<span class="sub">/</span><span class="lchip fixed">release folder</span>
        ${add.length ? `<select onchange="A.layAdd(this.value);this.value=''"><option value="">+ add</option>${add.map(k => `<option value="${k}">${LEVELS[k]}</option>`).join('')}</select>` : ''}</div></div>
      ${L.levels.includes('tier') ? `<div class="row" style="gap:8px;flex-wrap:wrap"><span class="sub" style="font-size:12px">Tier</span><span class="seg small">${[['folder', 'as its own folder'], ['name', 'in the artist folder name']].map(o => `<button aria-pressed="${(L.tier_style || 'folder') === o[0]}" onclick="S.lay.tier_style=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span>
        ${L.tier_style === 'name' ? `<span class="seg small">${[['bracket', '[100] Dean Martin'], ['dash', '100 Golden - Dean Martin'], ['suffix', 'Dean Martin [Golden 100]']].map(o => `<button aria-pressed="${(L.tier_name || 'bracket') === o[0]}" onclick="S.lay.tier_name=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span><span class="sub" style="font-size:12px">Artists with under 2% of their studio albums complete get no number (just “Ben Folds”).</span>` : ''}</div>` : ''}
      <div class="row" style="gap:8px;flex-wrap:wrap"><span class="sub" style="font-size:12px"><b>Library sort</b> (you decide here)</span><span class="seg small">${[['collection', 'Collection sort'], ['simple', 'Simple sort']].map(o => `<button aria-pressed="${(S.laySort || P.sort_mode) === o[0]}" onclick="S.laySort=${arg(o[0])};render()">${o[1]}</button>`).join('')}</span><span class="sub" style="font-size:12px">Simple = A–Z, no tier folders. Collection = groups artists into tiers by how complete their studio albums are.</span></div>
      <div><span class="cap">RELEASE FOLDER</span><div class="seg small" style="margin-top:6px">${[['year_album', 'Year - Album'], ['album_year', 'Album (Year)'], ['album', 'Album only'], ['custom', 'Custom…']].map(o => `<button aria-pressed="${L.release === o[0]}" onclick="A.laySet('release',${arg(o[0])})">${o[1]}</button>`).join('')}</div>
        ${L.release === 'custom' ? patBuilder('release') : ''}</div>
      <div><span class="cap">FILE NAME</span><div class="seg small" style="margin-top:6px">${[['full', 'Artist - Year Album - 01 Title'], ['track_title', '01 Title'], ['artist_track_title', 'Artist - 01 Title'], ['custom', 'Custom…']].map(o => `<button aria-pressed="${L.file === o[0]}" onclick="A.laySet('file',${arg(o[0])})">${o[1]}</button>`).join('')}</div>
        ${L.file === 'custom' ? patBuilder('file') : ''}</div>
      <div><span class="cap">EXAMPLE</span><div class="mono example">${ex.map((p, i) => `<div style="padding-left:${i * 14}px">${i < ex.length - 1 ? '📁' : '♪'} ${esc(p)}</div>`).join('')}</div></div>
      <span class="sub" style="font-size:12px">_Unverified, _Short Files, _Long Files and _Playlists always stay at the top. Without an Artist level the artist goes into the album folder name.</span>
      <div class="row" style="gap:8px"><button class="btn amber" onclick="A.layApply()" ${!changed || running ? 'disabled' : ''}>Use this layout (updates the plan)</button>
        <button class="btn ghost" onclick="A.layPreset(${arg(JSON.stringify(['tier', 'artist']))});S.lay.release='year_album';S.lay.file='full';render()">Back to standard</button></div>
    </section></div>`;
}

// ---- Archive (Phase 4): moves your originals into an archive folder - never deletes anything

/* Midnight 00:01 · Review: focus panel, bulk bar, decisions, keyboard keys (part of the screens, loaded in order by index.html) */
'use strict';
function artistAlbums(x) {
  const u = rvU(x.id), A_ = u.arAlbums;
  if (!A_) return `<div><button class="btn small outline" onclick="A.rvArtistAlbums(${arg(x.id)})" ${u.arLoading ? 'disabled' : ''}>${u.arLoading ? '<span class="spin"></span> Loading…' : 'Show ' + esc(x.artist_found || 'the artist') + "'s albums"}</button></div>`;
  if (A_.error) return `<span style="font-size:13px;color:var(--clay)">${esc(A_.error)}</span>`;
  let last = '';
  return `<div class="aralbums"><span class="cap">${esc(A_.artist || x.artist_found || '')} · ${plural((A_.albums || []).length, 'release')} · click one to see its tracks</span><button class="btn small ghost" onclick="A.rvArtistClose(${arg(x.id)})">Close</button>${(A_.albums || []).map(g => {
    const hd = g.kind !== last ? `<span class="sub" style="font-size:12px;flex-basis:100%;margin-top:4px">${esc(g.kind)}</span>` : ''; last = g.kind;
    return hd + `<button class="fchip" onclick="A.rvArtistAlbum(${arg(x.id)},${arg(g.id)})">${esc(g.title)}${g.year ? ' · ' + g.year : ''}</button>`; }).join('')}</div>`;
}
function bulkBar(q, headOnly, bodyOnly) {
  const ids = Object.keys(S.rvChecked).filter(id => S.rvChecked[id]);
  const all = q.length && q.every(x => S.rvChecked[x.id]);
  const head = `<label class="selall"><input type="checkbox" ${all ? 'checked' : ''} onclick="A.rvCheckAll(this.checked)"> Select all ${q.length} shown <span class="sub">(Ctrl+A)</span></label>`;
  if (bodyOnly && !ids.length) return '';
  if (!bodyOnly && (!ids.length || headOnly)) return head;
  const items = S.rv.items.filter(x => S.rvChecked[x.id]);
  const nm = items.filter(x => effKind(x) === 'match').length;
  return (bodyOnly ? '' : head) + `<div class="bulk" role="group" aria-label="Group choice"><b>${plural(ids.length, 'song')} selected</b>
    <div class="acts bulkacts">${nm ? `<button class="btn small green" data-pct="${minPct(items.filter(x => effKind(x) === 'match'))}" onclick="A.rvBulk('accept')">Accept ${nm}<span class="key">A</span></button>` : ''}<span class="vsep"></span>
      ${S.rvView === 'albums' ? `<button class="btn small" onclick="A.akSplit()" title="Songs from different albums tagged as one: match each song on its own">Split up</button>` : ''}<button class="btn small" onclick="A.rvBulk('later')">Later<span class="key">L</span></button><span class="vsep"></span>
      <button class="btn small outline" onclick="A.rvBulkSearch()" ${S.rvBS && S.rvBS.running ? 'disabled' : ''}>Search again for all<span class="key">S</span></button>
      <button class="btn small" onclick="A.rvBulk('unverified')" title="Keep my tags exactly (goes to _Unverified)">Keep<span class="key">K</span></button>${nm ? `<button class="btn small" onclick="A.rvBulk('reject')">Not this ${nm}<span class="key">N</span></button>` : ''}
      <span class="bulkr"><button class="btn small ghost" onclick="A.rvBulk('undo')">Undo<span class="key">Z</span></button>
      <button class="btn small ghost" onclick="A.rvCheckAll(false)">Clear<span class="key">Esc</span></button></span></div>
    ${bulkSearchInfo(items)}
    <span class="sub" style="font-size:11px">Accept and Not this apply to the Check songs only. Keep = your tags stay as they are. Shift-click selects a range.</span></div>`;
}
function bulkSearchInfo(items) {
  const B = S.rvBS;
  if (!B) return '';
  if (B.running) return `<div class="row" style="gap:8px;font-size:12px"><span class="spin"></span> Searching ${B.done + 1} of ${B.total}: ${esc(B.cur || '')}
    <button class="btn small ghost" onclick="S.rvBS.cancel=true">Stop</button></div>`;
  const tops = items.filter(x => topPick(x));
  return `<div style="display:flex;flex-direction:column;gap:6px;font-size:12px"><span>Search done: results for ${B.found} of ${B.total} songs (open a song to see them).</span>
    ${tops.length ? `<div><button class="btn small amber" onclick="A.rvBulkTop()">Use the top result for ${plural(tops.length, 'song')}</button></div>
    <span class="sub">Only where the top result is the same version with the same length (±3 s). The others stay for you to check.</span>` : ''}</div>`;
}
function topPick(x) {
  const u = S.rvUI[x.id]; const c = u && u.results && u.results[0];
  return c && !c.other_version && c.len_ok && c.length && Math.abs(c.length - x.duration) <= 3 ? c : null;
}
function digTool(x, u) {
      const SN = { ids: 'MusicBrainz IDs in your tags', classical: 'Classical search (composer + work)', deep: 'Deep text search (title only, no album, file + folder names)', length: 'Same artist + same length (MusicBrainz)', sound: 'Identify by sound (AcoustID)' };
  return `<div class="tool"><span style="font-size:13px">Five levels, one after another, stopping at the first sure result (identify by sound is the last level): ${Object.values(SN).join(' → ')}. Uses only the sites you allowed (names and lengths; the last step also a fingerprint, only if AcoustID is set up).</span>
      <div class="row" style="gap:8px"><button class="btn small outline" aria-label="Play this song" title="Listen to the song while you dig" onclick="A.play(${arg(x.id)})">${S.playing === x.id ? '❚❚ Pause' : '▶ Listen'}</button><button class="btn amber small" onclick="A.rvDig(${arg(x.id)})" ${u.loading ? 'disabled' : ''}>${u.loading === 'dig' ? '<span class="spin"></span> Digging…' : u.dig ? 'Dig again' : 'Dig deeper now'}</button></div>
      ${u.digSteps ? `<div class="digsteps">${u.digSteps.map(s => `<span class="${s.found ? 'ok' : ''}">${s.found ? '✓' : '·'} ${esc(SN[s.step] || s.step)}: ${s.found ? plural(s.found, 'result') : esc(s.note || 'nothing')}</span>`).join('')}</div>` : ''}
      ${u.err ? `<span style="font-size:13px;color:var(--clay)">${esc(u.err)}</span>` : ''}
      ${resultRows(x, u.dig, 'pick')}${u.dig && !u.dig.length ? '<span style="font-size:13px">Nothing found, even digging deeper. Keep it (your tags stay) or try a link.</span>' : ''}</div>`;
}
function toolPanel(x, u) {                    // the Search / Link / Identify-by-sound / Dig deeper panels, for every kind of song
  let tool = '';
    if (u.tool === 'search' || u.tool === 'link') tool = searchTool(x, 'pick', u.tool === 'link' ? 'Paste a link to the album, then pick the track' : 'Search again');
    if (u.tool === 'sound') tool = `<div class="tool">${S.rv.acoustid
      ? `<span style="font-size:13px">Identify by sound sends a fingerprint made on this PC (numbers, not the audio) and the length to AcoustID, then reads the release from MusicBrainz.</span>
         <div class="row"><button class="btn amber small" onclick="A.rvSound(${arg(x.id)})" ${u.loading ? 'disabled' : ''}>${u.loading === 'sound' ? '<span class="spin"></span> Listening…' : 'Identify now'}</button></div>
         ${u.err ? `<span style="font-size:13px;color:var(--clay)">${esc(u.err)}</span>` : ''}
         ${resultRows(x, u.sound, 'pick')}${u.sound && !u.sound.length ? '<span style="font-size:13px">No recording with this fingerprint in AcoustID.</span>' : ''}`
      : `<div class="row"><span style="flex:1 1 260px;font-size:13px">Identify by sound needs a free AcoustID key${S.info && !S.info.fpcalc ? ' and fpcalc.exe' : ''}.</span><button class="btn small" onclick="A.go('settings')">Add AcoustID key in Settings</button></div>`}</div>`;
    if (u.tool === 'dig') tool = digTool(x, u);
  return tool;
}
function digOpenOf(x, u, k, findOpen) { return !!(u.tool === 'search' || u.tool === 'link' || u.tool === 'dig' || u.tool === 'sound' || (k === 'match' && u.edit) || (k === 'place' && findOpen)); }
function songBar(x, k, u, p, findOpen) {      // V2.0.3: Accept (with %) | Edit (tag editor), Dig in (Search / Dig deeper / Identify) | Later, Leave out | ... More
  const id = arg(x.id), sep = '<span class="vsep"></span>', pc = p ? p.match_pct : x.match_pct;
  const editBtn = `<button class="btn c-edit ${u.tagEd ? 'outline' : ''}" aria-expanded="${!!u.tagEd}" onclick="A.rvTagEdit(${id})" data-tip="Change the tags yourself: artist, title, album, year, track, genre">Edit manually<span class="key">E</span></button>`;
  const digBtn = `<button class="btn c-dig ${digOpenOf(x, u, k, findOpen) ? 'outline' : ''}" aria-expanded="${digOpenOf(x, u, k, findOpen)}" onclick="A.rvDigIn(${id})" data-tip="Search by hand, Dig deeper and Identify by sound, all in one place">Dig in<span class="key">D</span></button>`;
  const more = [
    `<button class="btn small ghost" onclick="A.rvTrust(${id})" data-tip="Place it as an album using YOUR tags exactly (album, album artist, year, track). For box sets and bootlegs no site knows.">Trust tags<span class="key">T</span></button>`,
    k === 'match' ? `<button class="btn small ghost" onclick="A.rvReject(${id})" data-tip="The suggestion is wrong">Not this<span class="key">N</span></button>` : '',
    k === 'match' ? `<button class="btn small ghost" onclick="A.rvDigIn(${id},'search')">Find another album<span class="key">F</span></button>` : k === 'place' ? '' : `<button class="btn small ghost" onclick="A.rvTool(${id},'link')">Paste a link</button>`,
    `<button class="btn small ghost" onclick="A.rvUnv(${id})" data-tip="Keep my tags exactly (goes to _Unverified)">Keep in _Unverified<span class="key">K</span></button>`].join('');
  return `<div class="acts songbar">${k === 'match' ? `<button class="btn green" data-pct="${pc == null ? '' : pc}" onclick="A.rvAccept(${id})">${p ? 'Accept your pick' : 'Accept'}<span class="key">A</span></button>` : ''}${digBtn}${sep}${editBtn}<button class="btn" onclick="A.rvLater(${id})">Later<span class="key">L</span></button><button class="btn" onclick="A.rvLeave(${id})" data-tip="Not copied anywhere (not even _Unverified). The original stays where it is. You can undo it.">Leave out<span class="key">O</span></button><span class="grow"></span><button class="btn ${S.songMore ? 'outline' : ''}" aria-expanded="${!!S.songMore}" onclick="A.songMoreToggle()" data-tip="Open or minimize the box with more buttons">More ${S.songMore ? '▴' : '▾'}</button></div>${S.songMore ? `<div class="togbox"><div class="togh"><b>More</b><button class="btn small ghost" onclick="A.songMoreToggle()">Minimize ▴</button></div><div class="togb">${more}</div></div>` : ''}${x.verify ? `<div class="verline">${x.verify.n >= 2 ? '✓ Verified by ' + esc(x.verify.sources.join(' + ')) : 'Only ' + esc((x.verify.sources[0] || 'one source')) + ' agrees' + (x.verify.differ && x.verify.differ.length ? ' · others say: ' + esc(x.verify.differ.join('; ')) : '')}</div>` : ''}`;
}
function tagEditor(x, u) {
  if (!u.tagEd) return '';
  const s = x.suggest || {}, t = x.tags || {}, id = arg(x.id);
  const tr = v => String(v || '').split('/')[0];
  const f = u.tf || (u.tf = { artist: s.artist || t.artist || '', title: s.title || t.title || stem(x.file), album: s.release || t.album || '', albumartist: t.albumartist || '', year: String(s.year || t.year || '').slice(0, 4), track: tr(s.track || t.track), genre: s.genre || t.genre || '' });
  const fld = (k, label, w) => `<label style="flex:${w || '1 1 200px'}">${label}<input id="tf_${x.id}_${k}" value="${esc(f[k] || '')}" oninput="A.rvTf(${id},'${k}',this.value)" onkeydown="if(event.key==='Enter')A.rvTagSave(${id});if(event.key==='Escape')A.rvTagEdit(${id})"><span class="sub" style="font-size:11px">file: ${esc(k === 'year' ? String(t.year || '').slice(0, 4) : k === 'track' ? tr(t.track) : (t[k] || '–'))}</span></label>`;
  return `<div class="tool tagedit"><span style="font-size:13px;font-weight:700">Edit manually</span><span class="sub" style="font-size:12px">What you type here is written exactly as typed into the copy (the original file is never changed). Nothing is looked up.</span>
    <div class="flds">${fld('artist', 'Artist')}${fld('title', 'Title')}${fld('album', 'Album')}${fld('albumartist', 'Album artist')}${fld('year', 'Year', '0 1 90px')}${fld('track', 'Track', '0 1 90px')}${fld('genre', 'Genre')}</div>
    <div class="row" style="gap:8px"><button class="btn green" onclick="A.rvTagSave(${id})">Save these tags</button><button class="btn ghost" onclick="A.rvTagFile(${id})" data-tip="Fill the boxes with the tags of your file">Use my file's tags</button><button class="btn ghost" onclick="A.rvTagEdit(${id})">Cancel</button></div></div>`;
}
function digTabs(x, u, k, findOpen) {
  if (!digOpenOf(x, u, k, findOpen)) return '';
  const cur = (u.tool === 'dig') ? 'dig' : (u.tool === 'sound') ? 'sound' : 'search', id = arg(x.id);
  return `<div class="row digtabs" style="gap:6px"><span class="cap">DIG IN</span><span class="seg small">${[['search', 'Search', 'F'], ['dig', 'Dig deeper', 'D']].map(t => `<button aria-pressed="${cur === t[0]}" onclick="A.rvDigTab(${id},'${t[0]}')">${t[1]}<span class="key">${t[2]}</span></button>`).join('')}</span><span class="sub" style="font-size:12px">search by hand · search harder (the last level identifies by sound)</span></div>`;
}
function focusPanel(x, q) {
  const k = effKind(x), u = rvU(x.id), playing = S.playing === x.id;
  const sub = [x.tags.artist || x.artist_found, x.tags.album, x.file].filter(Boolean).join(' · ');
  const open = q.filter(i => !isDone(i));
  const why = k === 'match' ? `Matched on ${x.suggest.source} by searching${x.reason && !/^matched by song search/.test(x.reason) ? ' (' + x.reason + ')' : ''}. Compare, then accept or reject.`
    : k === 'place' ? `Click the track it belongs to (or drag the song onto it), or find another album.`
    : (x.decision && x.decision.action === 'reject' ? 'You said the suggestion was wrong. Find the right release, or keep the song in _Unverified with its tags.' : x.why);
  let body = '';
  if (k === 'match') {
    const p = u.pending, s = p ? p : x.suggest;
    const pc = p ? p.match_pct : x.match_pct;
    body = `<div class="cmpgrid">${cmpTable(x, s, p)}
      <div class="row" style="gap:8px;margin-top:6px">${coverHtml(s)}<span class="cap">${p ? 'YOUR PICK' : 'SUGGESTION'}</span>${pc != null ? `<span class="srcchip" style="color:${pctColor(pc)}" title="How close the new tags are to your file's tags (artist, title, album, year, track)">${pc}% alike</span>` : ''}<span class="srcchip">${esc(s.source)}</span>${p && p.how ? `<span class="sub" style="font-size:12px">${esc(p.how)}</span>` : ''}
        <span class="sub" style="font-size:12px;margin-left:auto">${esc(x.file)}</span></div></div>
      ${songBar(x, k, u, p)}
      ${tagEditor(x, u)}${digTabs(x, u, k, false)}${toolPanel(x, u)}${u.edit ? searchTool(x, 'pending', 'Find the right release') : ''}`;
  } else if (k === 'place') {
    const sg = u.sugg;
    const cards = (sg || []).map((r, ri) => ({ r, ri, html: releaseCard(x, r, ri, true) }));
    cards.sort((a, b) => (!!b.r._hasTitle - !!a.r._hasTitle) || (a.ri - b.ri));        // V2.0.6: albums that really have your song's title come first
    const noTitle = cards.length > 0 && !cards.some(c => c.r._hasTitle);
    const rels = (noTitle ? `<div class="banner" style="border-color:var(--amber);display:flex;gap:10px;align-items:center;flex-wrap:wrap"><span style="flex:1;min-width:220px">None of these albums has a track called <b>${esc((x.tags.title || stem(x.file)))}</b>. It may be on another album.</span><button class="btn small amber" onclick="A.rvFindTitle(${arg(x.id)})">Search by the song title</button></div>` : '') + cards.map(c => c.html).join('');
    const findOpen = u.find != null ? u.find : (sg && !sg.length);
    body = `${placeTags(x)}${!sg ? '<span class="sub"><span class="spin"></span> Looking up the album from your tags…</span>' : sg.length ? rels : '<span style="font-size:13px;color:var(--amber-text)">Your album was not found from the tags, so there are no tracks to place it on yet. Searching for it below, or pick one of the artist\'s albums.</span>' + artistAlbums(x)}
      ${songBar(x, k, u, null, findOpen)}
      ${tagEditor(x, u)}${digTabs(x, u, k, findOpen)}${toolPanel(x, u)}${findOpen ? searchTool(x, 'pick', 'Find the album this song belongs to') : ''}`;
  } else {
    const dest = 'Keep = your tags stay exactly as they are (folder _Unverified).';
    body = `${myTags(x)}${songBar(x, k, u)}${tagEditor(x, u)}${digTabs(x, u, k, false)}${toolPanel(x, u)}
      ${x.same_folder > 0 ? `<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer"><input type="checkbox" ${u.group ? 'checked' : ''} onchange="A.rvGroup(${arg(x.id)},this.checked)" style="width:18px;height:18px;accent-color:var(--amber)">Same choice for the ${plural(x.same_folder, 'other song')} with no album in this folder</label>` : ''}`;
  }
  const dn = isDone(x);
  return `<div class="row" style="gap:14px">
      <button class="playbtn ${playing ? 'on' : ''}" aria-label="${playing ? 'Pause' : 'Play a preview'}" onclick="A.play(${arg(x.id)})">${playing
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14"/><rect x="14" y="5" width="4" height="14"/></svg>'
        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z"/></svg>'}</button>
      <div style="flex:1 1 240px;min-width:0;display:flex;flex-direction:column;gap:3px"><span style="font-size:20px;font-weight:700;overflow-wrap:anywhere">${esc(x.tags.title || stem(x.file))}</span>
        <span class="sub wrap" style="font-size:13px">${esc(sub)}</span><span class="sub mono wrap" style="font-size:11px">${esc(x.folder)}</span></div>
      <button class="btn small ghost" onclick="A.reveal(${arg(x.id)})" title="Show this file in Windows Explorer (X)">Show in Explorer<span class="key">X</span></button>
      ${S.rvView !== 'album' ? `<button class="btn small ghost" onclick="A.alPage(${arg(albumKeyOf(x))})" title="Open this song's album on its own page">Open album</button>` : ''}
      <span class="kbadge" style="font-size:12px;padding:4px 12px;color:${KCT()[k]}">${KNAME[k]}</span>
      <div style="display:flex;gap:6px"><button class="arrow" aria-label="Previous song" onclick="A.rvMove(-1)">↑</button><button class="arrow" aria-label="Next song" onclick="A.rvMove(1)">↓</button></div></div>
    <span style="font-size:13px;color:${k === 'match' ? 'var(--sub)' : 'var(--amber-text)'}">${esc(why)}</span>
    ${x.dup_possible ? `<div class="banner" style="border-color:var(--amber)">Possible duplicate: another planned song has the same name in the same folder and almost the same length. It is not left out; after you decide, look at it on the Duplicates page. <button class="btn small outline" onclick="A.go('dups')">Open Duplicates</button></div>` : ''}
    ${isLater(x) ? `<div class="banner" style="border-color:${LATER_C};background:var(--panel2)"><span class="ltag">Later</span> You left this for later. Decide any time. <button class="btn small ghost" onclick="A.rvUndo(${arg(x.id)})">Remove the Later tag<span class="key">Z</span></button></div>` : ''}
    ${dn ? `<div class="banner" style="border-color:var(--green);background:var(--ok-bg)">Decided: ${esc(badgeOf(x))}${x.decision.label ? ' · ' + esc(x.decision.label) : ''}. You can change it below. <button class="btn small ghost" onclick="A.rvUndo(${arg(x.id)})">Redo (move back)<span class="key">Z</span></button></div>` : ''}
    ${body}
    <div class="row sub" style="justify-content:space-between;padding-top:12px;border-top:1px solid var(--line);font-size:12px">
      <span>${dn ? 'Already decided · you can change it' : plural(open.length, 'song') + ' left to review'}</span><span>Keys: A accept · D dig deeper · K keep · O leave out · T trust my tags · F find another album · E edit · N not this · L later · P play · X Explorer · Z undo · ↑ ↓ move · Ctrl+A select all</span></div>`;
}

// review actions
async function loadReview() {
  if (S.rvLoading) return;                      // V2.0.5 (#1): one load at a time; the screen starts it by itself if the list is missing
  S.rvLoading = true;
  let r;
  try { r = await call('review_list'); } catch (e) { r = { error: String(e && e.message || e) }; } finally { S.rvLoading = false; }
  if (!r || r.error || !r.items) { S.rv = null; S.rvErr = (r && r.error) || 'no answer'; render(); return; }
  S.rvErr = null; S.rv = r; rvSyncCounts(); S.alMove = store.get('alMove:' + (S.B.library || ''), {}) || {}; render();
  const fx = rvFocus(); if (fx) rvOpened(fx);
  autoAcceptTotals();
}
async function autoAcceptTotals() {          // V2.0.3: no longer automatic (decision 2). The engine places only songs whose tags are already identical.
  return;
  const tn = v => String(v || '').split('/')[0].replace(/^0+/, ''), y4 = v => String(v || '').slice(0, 4);
  const ids = (S.rv.items || []).filter(x => !x.decision && effKind(x) === 'match' && !isAside(x) && x.suggest && x.tags && tn(x.tags.track) && tn(x.tags.track) === tn(x.suggest.track)
    && nkw(x.tags.artist) === nkw(x.suggest.artist) && nkw(x.tags.title) === nkw(x.suggest.title) && nkw(x.tags.album) === nkw(x.suggest.release)
    && (!x.tags.year || !x.suggest.year || y4(x.tags.year) === y4(x.suggest.year))).map(x => x.id);
  if (!ids.length) return;
  const d = { action: 'accept', label: 'automatic: only "of N" was added to the track number' };
  const r = await call('review_decide_many', ids, d); if (r && !r.error) { rvSetLocal(r.ids || [], d); render(); toast(plural((r.ids || []).length, 'song') + ' accepted automatically (only "of N" was added to the track number). Redo brings any back.'); }
}
function saveSpot() { store.set('rvSpot', { sel: S.rvSel, view: S.rvView, filter: S.rvFilter, sort: S.rvSort, alKey: S.alKey, t: Date.now() }); }
function rvOpened(x) {
  const u = rvU(x.id);
  if (x.prep && !u.searched && !u.prepLoading && !u.digLoaded) {
    u.prepLoading = true;
    call('prep_get', x.id).then(r => { if (r && r.dig) { u.dig = r.results || []; u.digSteps = r.steps || []; u.tool = u.tool || 'dig'; u.prepLoading = false; u.searched = u.searched || false; u.digLoaded = true; render(); return; }
      if (!u.searched) { u.results = (r && r.results) || []; u.searched = true;
      const k = effKind(x); if (k === 'place') u.find = true; else if (k === 'none') u.tool = u.tool || 'search'; else u.edit = true; render(); } });
  }
  if (effKind(x) === 'place' && !u.sugg && !u.suggLoading) {
    u.suggLoading = true;
    call('review_suggest', x.id).then(r => {
      u.sugg = r.releases || [];
      if (!u.sugg.length && !u.searched) { u.find = true; A.rvSearch(x.id); }      // nowhere to place it yet: look for the album now
      render();
    });
  }
}
// 1.1.7: the dashboard numbers are fetched once things are quiet, not after every single accept (that made each accept slow)
function dashSoon() { clearTimeout(S._dashT); S._dashT = setTimeout(() => refreshDash(), 2500); }
function rvSetLocal(ids, d) {
  S.rvVer = (S.rvVer || 0) + 1;
  if (d && d.action !== 'undo' && ids.length) { S.rvHist = S.rvHist || []; S.rvHist.push({ ids: ids.slice(), action: d.action }); if (S.rvHist.length > 300) S.rvHist.shift(); }      // V2.0.5 (#9): the order of your decisions, for Z
  ids.forEach(id => { const x = S.rv.items.find(i => i.id === id); if (x) x.decision = d && d.action === 'undo' ? null : Object.assign({ t: Date.now() / 1000 }, d); });
  S.rv.stale = true; setTimeout(() => call('stamp').then(v => { S.rvStamp = v; }), 400);
  rvSyncCounts();
}
// V2.0.5 (#2): one number for 'songs that need you', updated at once after every decision (menu badge, Dashboard, Review list)
function rvSyncCounts() {
  if (!S.rv || !S.rv.items) return;
  const left = S.rv.items.filter(x => !isDone(x)).length;
  S.dash = S.dash || {};
  S.dash.waiting = left;
  S.dash.counts = Object.assign({}, S.dash.counts || {}, { needs_you: left });
  if (typeof renderNav === 'function') renderNav();
}
async function rvDecide(id, d, stay) {
  const x = S.rv.items.find(i => i.id === id);
  const before = rvQueue().filter(i => !isDone(i)).map(i => i.id);
  d.kind0 = x.kind;
  // batch 01: the choice shows at once and the next song opens at once; the app saves it in the background
  // (the answer only adds the other songs of the same folder for "same choice for this folder").
  const saving = call('review_decide', id, Object.assign({}, d));
  rvSetLocal([id], d);
  if (S.rvView === 'albums' || S.rvView === 'album') {                      // Albums and Quick > Album (V2.0.6 fix: the right-hand panel follows too): the next open song of the same album opens (if one was open)
    if (S.alRow === id) {
      const c = albumCards().find(c => c.items.some(i => i.id === id));
      const ok = i => !isDone(i) && !isAside(i) && !isLater(i) && i.id !== id, at = c ? c.items.findIndex(i => i.id === id) : -1;   // V2.0.6: the NEXT song after this one (then from the top), not always the first open one
      const nx = c && (c.items.slice(at + 1).find(ok) || c.items.find(ok));
      S.alRow = nx ? nx.id : null; S.rvSel = S.alRow;
    }
  } else if (!stay) {                               // next song still to do opens by itself
    const idx = before.indexOf(id), rest = before.filter(i => i !== id);
    S.rvSel = rest.length ? (idx >= 0 && idx < rest.length ? rest[idx] : rest[0]) : null;
  }
  if (S.playing && S.playing !== S.rvSel) A.play(null);
  render(); dashSoon(); const fx = rvFocus(); if (fx) rvOpened(fx);
  if (S.rvView === 'library' && d.action === 'pick') toast('Saved. The library on the right shows it after Update plan (top right).');
  const r = await saving;
  if (r && r.error) { rvSetLocal([id], { action: 'undo' }); render(); return toast('The choice could not be saved: ' + r.error, true); }
  const extra = ((r && r.ids) || []).filter(i => i !== id);
  if (extra.length) {
    rvSetLocal(extra, d);
    if (extra.includes(S.rvSel) && !stay) { const nxt = rvQueue().find(i => !isDone(i) && !isAside(i)); S.rvSel = nxt ? nxt.id : null; }
    render(); const f2 = rvFocus(); if (f2) rvOpened(f2);
  }
}
const candLabel = c => `${c.release}${c.year ? ' (' + c.year + ')' : ''}${c.track ? ', track ' + c.track : ''} · ${c.source}`;
const REVIEW_ACTIONS = {
  soloArtist(a) { S.rvSoloAr = a; S.rvFilter = 'all'; store.set('rvFilter', 'all'); S.rvSel = null; S.alRow = null; S.rvGroupSel = null; S.rvView = 'quick'; store.set('rvView2', 'quick'); saveSpot(); render(); window.scrollTo(0, 0); const fx = rvFocus(); if (fx) rvOpened(fx); },
  soloClear() { S.rvSoloAr = ''; S.rvSel = null; render(); const fx = rvFocus(); if (fx && S.rvView !== 'albums') rvOpened(fx); },
  arTog2(a) { S.arOpen[a] = !S.arOpen[a]; render(); },
  arAl(k) { S.alOpen[k] = true; render(); },
  arLayout(m) { S.arLayout = m; store.set('arLayout', m); render(); },
  arHideSet(v) { S.arHide = v; S.arLimit = 0; render(); },
  arSearch(v) { S.arQ = v; S.arLimit = 0; clearTimeout(S._arT); S._arT = setTimeout(() => { render(); const e = document.getElementById('arq'); if (e) { e.focus(); e.setSelectionRange(1e4, 1e4); } }, 250); },
  arToggle(a) { const open = S.arOpen[a] != null ? S.arOpen[a] : true; S.arOpen[a] = !open; render(); },
  alPage(k) { S.alKey = k; store.set('alKey', k); S.rvView = 'album'; store.set('rvView2', 'album'); S.alRow = null; S.rvGroupSel = null; S.alSel = {}; saveSpot(); render(); window.scrollTo(0, 0); },
  quickAlbum() { const fx = rvFocus(), k = fx ? albumKeyOf(fx) : S.alKey; if (k) A.alPage(k); else { S.rvView = 'albums'; render(); } },
  alPageMove(d) { const cs = albumCards('all'); const i = cs.findIndex(c => c.key === S.alKey); const n = cs[Math.max(0, Math.min(cs.length - 1, i + d))]; if (n) A.alPage(n.key); },
  alPageMatch(k) { const g = S.rvGroups[k]; if (!g || !g.ids.length) return toast('No songs to match here.', true); S.rvGroupSel = { key: k }; render(); if (!(S.rvGS[k] && S.rvGS[k].releases)) A.rvGroupSearch(k); },
  async alMixed(k, on) { const c = albumCards('all').find(c => c.key === k); if (!c) return; const ids = c.items.map(x => x.id);
    const r = await call('album_mixed', ids, on); if (r && r.error) return; c.items.forEach(x => x.mixed = on); S.rv.stale = true;
    toast(on ? 'Marked as not one album: each song is matched on its own when you update the plan.' : 'Treated as one album again.'); render(); },
  rvResize(ev) {
    const w = document.querySelector('.rvsplit'); if (!w) return; ev.preventDefault();
    const move = e => { const b = w.getBoundingClientRect(); S.rvSplit = Math.max(220, Math.min(b.width - 380, Math.round(e.clientX - b.left))); w.style.setProperty('--rvL', S.rvSplit + 'px'); };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); store.set('rvSplit', S.rvSplit); };
    document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
  },
  rvSortBy(v) { S.rvSort = v; store.set('rvSort', v); saveSpot(); render(); },
  async resume() { const sp = store.get('rvSpot', null); if (!sp) return A.go('review');
    Object.assign(S, { rvSel: sp.sel, rvView: sp.view || 'songs', rvFilter: sp.filter || 'match', rvSort: sp.sort || 'pct_desc', alKey: sp.alKey || '' });
    S.screen = 'review'; render(); await loadReview(); },
  diffSet(v) { S.diffMode = v; store.set('diffMode', v); render(); },
  rvViewSet(v) { if (v === 'tags') { S.neat = null; } S.rvView = v; store.set('rvView2', v); setTimeout(saveSpot); S.rvGroupSel = null; render(); const fx = v === 'tags' ? null : rvFocus(); if (fx && v !== 'albums') rvOpened(fx); },
  alLayoutToggle() { S.alLayout = S.alLayout === 'classic' ? 'c' : 'classic'; store.set('alLayout', S.alLayout); render(); },
  alToggle(k) { const c = albumCards().find(c => c.key === k); S.alOpen[k] = !(S.alOpen[k] != null ? S.alOpen[k] : !!(c && c.open)); render(); },
  alSortBy(v) { S.alSort = v; store.set('alSort', v); render(); },
  // V2.0.6: Split up really splits: every open song leaves the album, lands in its own box at the END of the list, and each one is searched on its own (Dig deeper, all allowed sites)
  async splitOut(cards, search) {
    S.alMove = S.alMove || {}; const ids = [];
    for (const c of cards) {
      const open = c.items.filter(x => !isDone(x) && !isAside(x));
      if (!open.length) continue;
      const r = await call('album_mixed', c.items.map(x => x.id), true); if (r && r.error) return toast(r.error, true);
      c.items.forEach(x => { x.mixed = true; }); open.forEach(x => { S.alMove[x.id] = 'x|' + x.id; ids.push(x.id); });
    }
    store.set('alMove:' + (S.B.library || ''), S.alMove); S.rv.stale = true; S.alAll = {}; render();
    if (!ids.length) return toast('Nothing to split: every song here is already decided.', true);
    if (!search) return toast('Split up: ' + plural(ids.length, 'song') + ' moved to the end, each one on its own.');
    const r = await call('dig_start', ids, true);
    if (r && r.error) return toast('Split up: ' + plural(ids.length, 'song') + ' moved to the end. Search not started: ' + r.error, true);
    toast('Split up: ' + plural(ids.length, 'song') + ' moved to the end. Searching each one on its own…'); await poll(true);
  },
  alStep(dir) {            // V2.0.6: the next / previous song that is still to do, in the order of the rows on screen; its details open on the right
    const rows = [...document.querySelectorAll('#main .alrow')].map(el => el.dataset.id).filter(id => { const x = S.rv.items.find(i => i.id === id); return x && !isDone(x) && !isAside(x) && !isLater(x); });
    if (!rows.length) return;
    const at = rows.indexOf(S.alRow), i = at < 0 ? (dir > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, at + dir)), id = rows[i];
    S.alRow = id; S.rvSel = id; render();
    const el = [...document.querySelectorAll('#main .alrow')].find(e => e.dataset.id === id); if (el) el.scrollIntoView({ block: 'nearest' });
    const x = S.rv.items.find(i => i.id === id); if (x) rvOpened(x);
  },
  async alSplit(k) {
    const c = albumCards('all').find(c => c.key === k); if (!c) return; const on = !c.items.every(x => x.mixed);
    if (on) { if (S.rvView === 'album') { await A.alMixed(k, true); return A.alPageMove(1); } return A.splitOut([c], true); }
    c.items.forEach(x => { if (S.alMove && String(S.alMove[x.id] || '').startsWith('x|')) delete S.alMove[x.id]; }); store.set('alMove:' + (S.B.library || ''), S.alMove || {});
    await A.alMixed(k, false);
  },
  songMoreToggle() { S.songMore = !S.songMore; store.set('songMore', S.songMore); render(); },
  alTool(id, tool) { S.alRow = id; S.rvSel = id; const u = rvU(id); u.tool = tool; render(); const x = S.rv.items.find(i => i.id === id); if (x) rvOpened(x); },
  alOpenAll(on) { albumCards('all').forEach(c => { S.alOpen[c.key] = !!on; }); render(); },
  async akSplit() { return A.splitOut(albumCards('all').filter(c => c.items.some(x => S.rvChecked[x.id] && !isDone(x))), true); },
  akGroup(key) { return S.rvGroups[key.startsWith('AR|') ? key : 'AL|' + key]; },
  akPaint(key) { const g = A.akGroup(key); if (!g) return; const on = g.ids.length > 0 && g.ids.every(i => S.rvChecked[i]); const ar = g.key.startsWith('AR|'); const el = [...document.querySelectorAll(ar ? '.artblock[data-arkey]' : '.alcard[data-alkey]')].find(e => ar ? 'AR|' + e.dataset.arkey === g.key : e.dataset.alkey === key); if (el) { el.classList.toggle('akon', on); const c = el.querySelector('.akck'); if (c) c.checked = on; } },
  akDown(ev, key) { if (ev.button !== 0) return; ev.preventDefault(); const g = A.akGroup(key); if (!g) return; S.akOn = !g.ids.every(i => S.rvChecked[i]); S.akDrag = true; g.ids.forEach(i => { S.rvChecked[i] = S.akOn; }); A.akPaint(key); },
  akEnter(key) { if (!S.akDrag) return; const g = A.akGroup(key); if (!g) return; g.ids.forEach(i => { S.rvChecked[i] = S.akOn; }); A.akPaint(key); },
  async akSplit() { return A.splitOut(albumCards('all').filter(c => c.items.some(x => S.rvChecked[x.id] && !isDone(x))), true); },
  alCheckAll() { const on = !albumCards().every(c => c.items.every(x => isDone(x) || S.rvChecked[x.id])); albumCards().forEach(c => c.items.forEach(x => { if (!isDone(x)) S.rvChecked[x.id] = on; })); render(); },
  alRowOpen(id) { S.alRow = S.alRow === id ? null : id; S.rvSel = S.alRow || S.rvSel; render(); const x = S.alRow && S.rv.items.find(i => i.id === id); if (x) rvOpened(x); },
  async alDecide(id, action) {
    const x = S.rv.items.find(i => i.id === id); if (!x) return;
    const d = action === 'accept' ? { action, label: [x.suggest.release, x.suggest.source].filter(Boolean).join(' · ') } : action === 'unverified' ? { action, label: 'your tags kept' } : { action };
    await rvDecide(id, d, true);
  },
  async leaveArtist(gkey) {                    // 2.0.2 item 76: first click asks, second click leaves the artist's open songs out
    const g = S.rvGroups[gkey]; if (!g || !g.ids.length) return;
    if (S.arLeaveAsk !== gkey) { S.arLeaveAsk = gkey; render(); return; }
    S.arLeaveAsk = null;
    const d = { action: 'leave', label: 'left out (not copied)' };
    const r = await call('review_decide_many', g.ids, d);
    if (!r || r.error) { render(); return; }
    rvSetLocal(r.ids || [], d);
    toast('Left out ' + (g.artist || 'this artist') + ': ' + plural((r.ids || []).length, 'song'));
    render(); refreshDash();
  },
  async alAll(k, action) {
    const c = albumCards().find(c => c.key === k); if (!c) return;
    let items = c.items.filter(x => !isDone(x));
    if (action === 'accept') items = items.filter(x => effKind(x) === 'match');
    if (!items.length) return;
    const d = { action, label: action === 'accept' ? 'accepted with the album' : action === 'unverified' ? 'your tags kept' : '' };
    const r = await call('review_decide_many', items.map(x => x.id), d);
    if (!r || r.error) return;
    rvSetLocal(r.ids || [], d);
    toast({ accept: 'Accepted', unverified: 'Kept (your tags)', later: 'Tagged Later', leave: 'Left out', trust: 'Placed with your tags' }[action] + ': ' + plural((r.ids || []).length, 'song'));
    render(); refreshDash(); A.alAfter(k);
  },
  // v1.1.4 group place: find the album for a whole group and, when every song fits one album, place them all at once
  async alPlaceAll(k, quiet) {
    const c = albumCards().find(c => c.key === k); if (!c) return 0;
    const items = c.items.filter(x => !isDone(x) && !isAside(x) && effKind(x) !== 'match'); if (!items.length) return 0;
    const ids = items.map(x => x.id), artist = c.artist || items[0].g_artist || '', album = c.album || items[0].g_album || '';
    if (!album) { if (!quiet) toast('This group has no album name: use Match album and type it.', true); return 0; }
    if (!quiet) toast('Looking for “' + album + '”…');
    const r = await call('review_group', ids, artist, album, '');
    const rels = (r && r.releases) || [], best = rels.find(rel => rel.matched === ids.length);
    if (!best) { if (!quiet) { toast('No album matches every song. Opening it so you can check.', true); A.alMatch(k); } return 0; }
    const pairs = ids.map(i => { const t = best.tracks[best.map[i].i];
      return [i, { action: 'pick', match: t.match, label: candLabel({ release: best.title, year: best.year, track: t.track, source: best.source }) + ' (group place)' }]; });
    const rr = await call('review_decide_each', pairs); if (!rr || rr.error) return 0;
    pairs.forEach(([i, d]) => rvSetLocal([i], d));
    if (!quiet) { toast('Placed ' + plural(pairs.length, 'song') + ' on ' + best.title + '. Redo moves them back.'); render(); refreshDash(); }
    return pairs.length;
  },
  async placeAllAlbums() {
    const cards = albumCards().filter(c => c.items.some(x => !isDone(x) && !isAside(x) && effKind(x) === 'place'));
    if (!cards.length) return toast('No albums waiting to be placed.');
    if (S.placeBusy) return; S.placeBusy = true; let songs = 0, albums = 0, n = 0;
    for (const c of cards) { n++; toast(`Placing albums… ${n} of ${cards.length}`); try { const k = await A.alPlaceAll(c.key, true); if (k) { songs += k; albums++; } } catch (e) {} }
    S.placeBusy = false; toast(`Placed ${plural(songs, 'song')} in ${plural(albums, 'album')}. Albums that did not match every song were left for you. Redo moves any back.`); render(); refreshDash();
  },
  async alRedoAll(k) {
    const c = albumCards().find(c => c.key === k); if (!c) return;
    const ids = c.items.filter(isDone).map(x => x.id); if (!ids.length) return;
    const d = { action: 'undo' }; const r = await call('review_decide_many', ids, d); if (!r || r.error) return;
    rvSetLocal(r.ids || [], d); toast('Moved back: ' + plural((r.ids || []).length, 'song') + ' are open again.'); render(); refreshDash();
  },
  async alNot(id) {
    S.alMove = S.alMove || {}; S.alMove[id] = 'x|' + id; store.set('alMove:' + (S.B.library || ''), S.alMove);
    await call('album_mixed', [id], true); toast('Taken out of the album: it is matched on its own.'); render();
  },
  alDropCard(ev, key) {
    ev.preventDefault(); ev.currentTarget && ev.currentTarget.classList.remove('over');
    let id = S.rvDrag; try { id = id || ev.dataTransfer.getData('text/plain'); } catch (e) {} S.rvDrag = null; if (!id) return;
    const x = S.rv.items.find(i => i.id === id); if (!x || albumKeyOf(x) === key) return;
    S.alMove = S.alMove || {}; S.alMove[id] = key; store.set('alMove:' + (S.B.library || ''), S.alMove);
    S.alOpen[key] = true; toast('Moved into this album. Press Match album to find its track.'); render();
  },
  alUnmove(id) { if (S.alMove) { delete S.alMove[id]; store.set('alMove:' + (S.B.library || ''), S.alMove); } call('album_mixed', [id], false); render(); },
  arChip(a, key) { S.arOpen[a] = true; S.alOpen[key] = true; render(); setTimeout(() => { const el = document.querySelector(`[data-alkey="${CSS.escape(key)}"]`); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 30); },
  alMatch(k) {
    const key = 'AL|' + k, g = S.rvGroups[key]; if (!g) return;
    S.alMatchOpen = S.alMatchOpen === k && S.rvGS[key] && !S.rvGS[key].loading ? null : k;
    S.alOpen[k] = true; render();
    if (S.alMatchOpen && !(S.rvGS[key] && S.rvGS[key].releases)) A.rvGroupSearch(key);
  },
  async prepStart() { const r = await call('prep_start'); if (r && r.error) return toast(r.error, true); toast('Preparing Review for ' + plural(r.total, 'song') + '…'); await poll(true); },
  async prepPause(on, which) { await call('prep_pause', on, which || ''); await poll(true); },
  async prepCancel(which) { await call('prep_cancel', which || ''); await poll(true); },
  rvArtistClose(id) { const u = rvU(id); u.arAlbums = null; render(); },
  async rvArtistAlbums(id) { const u = rvU(id); u.arLoading = true; render(); const r = await call('artist_albums', id); u.arLoading = false; u.arAlbums = r || { error: 'no answer' }; render(); },
  rvArtistAlbum(id, rg) { const u = rvU(id); u.find = true; u.link = 'https://musicbrainz.org/release-group/' + rg; A.rvLink(id); },
  sureTier(tr, on) { ((S.sureTiers || {})[tr] || []).forEach(id => { if (on) delete S.dlg.off[id]; else S.dlg.off[id] = true; }); renderLayer(); },
  sureAll(on) { (S.sureOrder || []).forEach(id => { if (on) delete S.dlg.off[id]; else S.dlg.off[id] = true; }); renderLayer(); },
  sureDown(ev, id) {                                // press on a row and drag: every row you pass gets the same state
    if (ev.button !== 0) return; ev.preventDefault();
    const on = !!S.dlg.off[id];                     // currently unticked -> tick it (and the ones dragged over)
    S.sureDrag = { on }; A.sureSet(id, on);
    const up = () => { document.removeEventListener('mouseup', up); S.sureDrag = null; };
    document.addEventListener('mouseup', up);
  },
  sureOver(id) { if (S.sureDrag) A.sureSet(id, S.sureDrag.on); },
  sureSet(id, on) {
    if (on) delete S.dlg.off[id]; else S.dlg.off[id] = true;
    const row = document.querySelector(`.surerow[data-sid="${CSS.escape(id)}"] input`); if (row) row.checked = on;
    const n = (S.sureOrder || []).filter(k => !S.dlg.off[k]).length;
    const c = document.getElementById('surecount'); if (c) c.textContent = plural(n, 'song') + ' selected';
    const b = document.getElementById('suregobtn'); if (b) { b.textContent = 'Accept ' + plural(n, 'song'); b.disabled = !n; }
  },
  rvSureAsk() { const items = sureOnes(); if (!items.length) return; S.dlg = { kind: 'sure', off: {} }; renderLayer(); },
  rvSureQuick() { S.dlg = null; renderLayer(); S.rvFilter = 'sure'; S.rvView = 'quick'; S.rvSel = null; render(); const fx = rvFocus(); if (fx) rvOpened(fx); },
  async rvSureGo() {
    const off = S.dlg.off, items = sureOnes().filter(x => !off[x.id]); S.dlg = null; renderLayer();
    const acc = items.filter(x => effKind(x) === 'match' && (x.sure || x.safe) && !isAside(x)), picks = items.filter(x => !acc.includes(x));
    const ids = [];
    const accV = acc.filter(x => x.safe), accS = acc.filter(x => !x.safe);
    if (accV.length) { const d = { action: 'accept', label: 'verified by two sources' };
      const r = await call('review_decide_many', accV.map(x => x.id), d); if (r && !r.error) { rvSetLocal(r.ids || [], d); ids.push(...(r.ids || [])); } }
    if (accS.length) { const d = { action: 'accept', label: 'sure one (' + sureTxt() + ' alike)' };
      const r = await call('review_decide_many', accS.map(x => x.id), d); if (r && !r.error) { rvSetLocal(r.ids || [], d); ids.push(...(r.ids || [])); } }
    if (picks.length) { const pairs = picks.map(x => [x.id, { action: 'pick', match: x.prep_sure.match, label: candLabel(x.prep_sure) + ' · Prepare Previews' }]);
      const r = await call('review_decide_each', pairs); if (r && !r.error) { pairs.forEach(([i, d]) => rvSetLocal([i], d)); ids.push(...pairs.map(p => p[0])); } }
    S.lastSure = ids; toast('Accepted ' + plural(ids.length, 'sure song') + '. You can undo it.'); render(); refreshDash();
  },
  rvSureBand(on) { S.sureBand = !!on; store.set('sureBand', !!on); S.sureMinUser = false; render(); },
  rvSureMin(v) { S.sureMinUser = true; S.sureMin = +v; store.set('sureMin', +v); render(); },
  async alSelDo(act) {                          // one action for every selected album (one or many)
    const cs = selAlbums(); if (!cs.length) return; const keys = cs.map(c => c.key);
    if (act === 'trust') { S.dlg = { kind: 'trust', keys }; return renderLayer(); }
    if (act === 'match') {
      if (keys.length === 1) { A.alMatch(keys[0]); return; }
      toast('Looking for ' + plural(keys.length, 'album') + '…'); let n = 0, ok = 0;
      for (const k of keys) { const r = await A.alPlaceAll(k, true); if (r) { ok++; n += r; } }
      render(); refreshDash(); toast(ok ? 'Placed ' + plural(n, 'song') + ' on ' + plural(ok, 'album') + '. ' + (ok < keys.length ? plural(keys.length - ok, 'album') + ' did not fit every song: open one and press Match album.' : 'Redo moves them back.') : 'No album matched every song. Open one and press Match album.', !ok); return;
    }
    if (act === 'undo') { for (const k of keys) await A.alRedoAll(k); return; }
    for (const k of keys) await A.alAll(k, act);
    keys.forEach(k => { const c = albumCards('all').find(x => x.key === k); if (c) c.items.forEach(x => { delete S.rvChecked[x.id]; }); }); render();
  },
  alTrustAsk(key) { S.dlg = { kind: 'trust', key }; renderLayer(); },
  async alTrustGo() {
    const keys = S.dlg.keys || [S.dlg.key]; S.dlg = null; renderLayer(); let total = 0;
    for (const key of keys) {
      const c = albumCards('all').find(k => k.key === key); if (!c) continue;
      const ids = c.items.filter(x => !isDone(x)).map(x => x.id); if (!ids.length) continue;
      const d = { action: 'trust', label: 'your tags: ' + (c.album || 'album from your tags') };
      const r = await call('review_decide_many', ids, d); if (r && !r.error) { rvSetLocal(r.ids || ids, d); total += ids.length; }
    }
    toast(plural(total, 'song') + ' placed with your own tags. Update the plan to see it.'); render(); refreshDash();
  },
  alSureAll(on) { (S.sureAlOrder || []).forEach(k => { if (on) delete S.dlg.aoff[k]; else S.dlg.aoff[k] = true; }); if (on) S.dlg.off = {}; renderLayer(); },
  alSureAsk() { if (!sureAlbums().length) return; S.dlg = { kind: 'alsure', off: {}, aoff: {} }; renderLayer(); },
  async alSureGo() {
    const d = S.dlg, cards = sureAlbums(); S.dlg = null; renderLayer();
    const ids = cards.filter(c => !d.aoff[c.key]).flatMap(c => c.items.filter(x => !isDone(x) && !isAside(x) && !d.off[x.id]).map(x => x.id));
    if (!ids.length) return;
    const dd = { action: 'accept', label: 'album accepted (' + sureTxt() + ' alike)' };
    const r = await call('review_decide_many', ids, dd);
    if (r && !r.error) { rvSetLocal(r.ids || ids, dd); S.lastSure = r.ids || ids; toast('Accepted ' + plural(S.lastSure.length, 'song') + '. You can undo it.'); }
    render(); refreshDash();
  },
  async rvSure() {
    const items = sureOnes(); if (!items.length) return;
    const d = { action: 'accept', label: 'sure one (' + sureTxt() + ' alike)' };
    const r = await call('review_decide_many', items.map(x => x.id), d);
    if (!r || r.error) return;
    rvSetLocal(r.ids || [], d); S.lastSure = r.ids || [];
    toast('Accepted ' + plural(S.lastSure.length, 'sure song') + '. You can undo it.'); render(); refreshDash();
  },
  async rvSureUndo() {
    const ids = S.lastSure || []; if (!ids.length) return;
    const r = await call('review_decide_many', ids, { action: 'undo' });
    if (!r || r.error) return;
    rvSetLocal(ids, { action: 'undo' }); S.lastSure = null; toast('Undone.'); render(); refreshDash();
  },
  rvGroupBy(m) { S.rvGroupBy = m; S.rvGroupSel = null; store.set('rvGroupBy', m); render(); },
  rvGroupToggle(k) { S.rvClosed[k] = !S.rvClosed[k]; render(); },
  rvGroupCheck(k, on) { (S.rvGroups[k] || { ids: [] }).ids.forEach(i => S.rvChecked[i] = on); render(); },
  rvGroupOpen(k) { const g = S.rvGroups[k]; if (!g) return; S.rvGroupSel = { key: k }; render(); if (!(S.rvGS[k] && S.rvGS[k].releases)) A.rvGroupSearch(k); },
  rvGroupClose() { S.rvGroupSel = null; render(); },
  async rvGroupSearch(k, byLink) {
    const g = S.rvGroups[k]; if (!g) return;
    const st = S.rvGS[k] || (S.rvGS[k] = { q: [g.artist || '', g.album || ''] });
    if (byLink && !(st.link || '').trim()) return;
    st.loading = true; st.err = ''; render();
    const r = await call('review_group', g.ids, st.q[0], st.q[1], byLink ? st.link : '');
    st.loading = false; st.releases = (r && r.releases) || []; st.err = (r && r.error) || ''; render();
  },
  async rvGroupUse(k, ri) {
    const g = S.rvGroups[k], st = S.rvGS[k], rel = st.releases[ri];
    const pairs = g.ids.filter(i => rel.map[i]).map(i => { const t = rel.tracks[rel.map[i].i];
      return [i, { action: 'pick', match: t.match, label: candLabel({ release: rel.title, year: rel.year, track: t.track, source: rel.source }) }]; });
    const r = await call('review_decide_each', pairs);
    if (!r || r.error) return;
    pairs.forEach(([i, d]) => rvSetLocal([i], d));
    toast('Placed ' + plural(pairs.length, 'song') + ' on ' + rel.title + '.');
    S.rvGroupSel = null; S.alMatchOpen = null; render(); refreshDash(); A.alAfter(k);
  },
  alAfter(k) {                                     // 1.1.5: on the album page, a finished album opens the next album that still has songs to do
    if (S.rvView !== 'album') return;
    const c = albumCards().find(c => c.key === k); if (c && c.open) return;
    const nx = albumCards().find(c => c.open && c.key !== k);
    if (nx) { A.alPage(nx.key); toast('Next album: ' + (nx.album || nx.folder)); } else { S.rvView = 'albums'; render(); toast('No album has songs left to do.'); }
  },
  rvAsideSearch() { S.rvChecked = {}; S.rv.items.filter(isAside).forEach(x => S.rvChecked[x.id] = true); render(); A.rvBulkSearch(); },
  rvAlbum(id, i) {
    const u = rvU(id), c = (u.tool === 'sound' && u.sound ? u.sound : u.tool === 'dig' && u.dig ? u.dig : u.results)[i], m = c.match, rid = String(m.release_id || '');
    const mb = c.mbid || m.mbid || (/^[0-9a-f-]{36}$/.test(rid) ? rid : '');
    const link = mb ? 'https://musicbrainz.org/release/' + mb : rid.startsWith('deezer:') ? 'https://www.deezer.com/album/' + rid.slice(7)
      : rid.startsWith('itunes:') ? 'https://music.apple.com/album/' + rid.slice(7) : rid.startsWith('discogs:') ? 'https://www.discogs.com/release/' + rid.slice(8) : '';
    if (!link) return toast('The tracks of this album cannot be shown.', true);
    u.link = link; A.rvLink(id);
  },
  rvCheck(ev, id) {
    ev.stopPropagation();
    const q = rvQueue(), on = !S.rvChecked[id];
    if (ev.shiftKey && S.rvLastCheck) {
      const a = q.findIndex(x => x.id === S.rvLastCheck), b = q.findIndex(x => x.id === id);
      if (a >= 0 && b >= 0) q.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(x => S.rvChecked[x.id] = on);
    } else S.rvChecked[id] = on;
    S.rvLastCheck = id; render();
  },
  rvCheckAll(on) { S.rvChecked = {}; if (on) rvQueue().forEach(x => S.rvChecked[x.id] = true); render(); },
  async rvBulkSearch() {
    const items = S.rv.items.filter(x => S.rvChecked[x.id]);
    if (!items.length) return toast('Select songs first.', true);
    S.rvBS = { running: true, total: items.length, done: 0, found: 0, cur: '' }; render();
    for (const x of items) {
      if (S.rvBS.cancel) break;
      const u = rvU(x.id), q = u.q || x.q;
      S.rvBS.cur = (q[0] ? q[0] + ' - ' : '') + (q[1] || ''); render();
      if ((q[1] || '').trim()) {
        const r = await call('review_search', x.id, q[0], q[1], q[2]);
        u.searched = true; u.results = (r && r.results) || []; u.err = (r && r.error) || '';
        if (u.results.length) S.rvBS.found++;
        const k = effKind(x);
        if (k === 'match') u.edit = true; else if (k === 'place') u.find = true; else u.tool = 'search';
      }
      S.rvBS.done++;
    }
    S.rvBS.running = false; S.rvBS.cancel = false; render();
    toast('Search done: results for ' + S.rvBS.found + ' of ' + S.rvBS.total + ' songs.');
  },
  async rvBulkTop() {
    const items = S.rv.items.filter(x => S.rvChecked[x.id] && topPick(x));
    for (const x of items) {
      const c = topPick(x);
      const r = await call('review_decide', x.id, { action: 'pick', match: c.match, label: candLabel(c), kind0: x.kind });
      rvSetLocal((r && r.ids) || [x.id], { action: 'pick', match: c.match, label: candLabel(c) });
      S.rvChecked[x.id] = false;
    }
    toast('Used the top result for ' + plural(items.length, 'song') + '.'); S.rvBS = null; render(); refreshDash();
  },
  async rvBulk(action) {
    let items = S.rv.items.filter(x => S.rvChecked[x.id]);
    if (action === 'accept' || action === 'reject') items = items.filter(x => effKind(x) === 'match');
    if (!items.length) return toast(action === 'accept' || action === 'reject' ? 'Accept and Not this work on Check songs only.' : 'Nothing selected.', true);
    const d = { action, label: action === 'unverified' ? 'tags kept exactly' : action === 'accept' ? 'accepted in a group' : '' };
    const r = await call('review_decide_many', items.map(x => x.id), d);
    if (r && r.error) return;
    rvSetLocal(r.ids || [], d);
    toast({ accept: 'Accepted', reject: 'Marked "Not this"', unverified: 'Kept (your tags)', later: 'Tagged Later', undo: 'Undone' }[action] + ': ' + plural((r.ids || []).length, 'song'));
    if (action === 'reject') items.forEach(x => { rvU(x.id).tool = 'search'; });
    S.rvChecked = {}; render(); refreshDash();
  },
  rvPick(id) { if (S.lib) S.lib.info = null; if (S.rvView === 'songs') S.rvCollapsed = S.rvSel === id ? !S.rvCollapsed : false; S.rvSel = id; S.rvGroupSel = null; saveSpot(); render(); const x = S.rv.items.find(i => i.id === id); if (x) rvOpened(x); },
  rvFilter(f) { S.rvFilter = f; S.rvSel = null; store.set('rvFilter', f); saveSpot(); render(); const fx = rvFocus(); if (fx) rvOpened(fx); },
  rvMove(dir) {
    const q = rvQueue(), fx = rvFocus(); if (!q.length) return;
    const todo = q.filter(x => !isDone(x) && !isAside(x) && !isLater(x));        // arrows and auto-advance skip finished songs; a click still opens any song
    if (!todo.length) return;
    const i0 = fx ? todo.findIndex(x => x.id === fx.id) : -1;
    const i = i0 < 0 ? (dir > 0 ? 0 : todo.length - 1) : Math.max(0, Math.min(todo.length - 1, i0 + dir));
    A.rvPick(todo[i].id);
  },
  rvAccept(id) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id);
    if (effKind(x) !== 'match') return;
    if (u.pending) return rvDecide(id, { action: 'pick', match: u.pending.match, label: candLabel(u.pending) });
    rvDecide(id, { action: 'accept', label: [x.suggest.release, x.suggest.source].filter(Boolean).join(' · ') });
  },
  rvLater(id) { rvDecide(id, { action: 'later', same_folder: !!rvU(id).group }); },
  rvLeave(id) { rvDecide(id, { action: 'leave', label: 'left out (not copied)' }); },
  rvTrust(id) { const x = S.rv.items.find(i => i.id === id); rvDecide(id, { action: 'trust', label: 'your tags: ' + ((x && (x.tags.album || x.g_album)) || 'album from your tags') }); },
  rvUnv(id) { rvDecide(id, { action: 'unverified', label: 'tags kept exactly', same_folder: !!rvU(id).group }); },
  rvReject(id) { const u = rvU(id); u.pending = null; u.tool = 'search'; rvDecide(id, { action: 'reject' }); },
  rvUndo(id) { rvDecide(id, { action: 'undo' }, true); },
  // V2.0.5 (#9): Z takes back the LAST decision you made (all its songs if it was a batch), whichever song is selected now,
  // and opens that song so you see what came back. Press Z again for the one before.
  async rvUndoLast() {
    if (!S.rv) return;
    const H = S.rvHist = S.rvHist || [];
    while (H.length) {
      const h = H.pop();
      const ids = h.ids.filter(id => { const x = S.rv.items.find(i => i.id === id); return x && x.decision; });
      if (!ids.length) continue;
      if (ids.length === 1) await rvDecide(ids[0], { action: 'undo' }, true);
      else { const d = { action: 'undo' }; const r = await call('review_decide_many', ids, d); if (!r || r.error) return toast((r && r.error) || 'Could not undo.', true); rvSetLocal(r.ids || ids, d); }
      S.rvSel = ids[0]; if (S.rvView === 'albums' || S.rvView === 'album') S.alRow = ids[0];
      render(); toast(ids.length === 1 ? 'Undone: the last decision is back in Review.' : 'Undone: ' + plural(ids.length, 'song') + ' are back in Review.');
      return;
    }
    toast('Nothing to undo: no decision made in this session.');
  },
  rvEdit(id, f) { const u = rvU(id); u.edit = f ? true : !u.edit; render(); if (u.edit) focus('q_' + id + '_' + (f === 'album' ? 2 : 1)); },
  rvFind(id, f) { const u = rvU(id); u.find = f ? true : !(u.find != null ? u.find : (u.sugg && !u.sugg.length)); render(); if (u.find) focus('q_' + id + '_' + (f === 'title' ? 1 : 2)); },
  rvTool(id, t, f) { const u = rvU(id); u.tool = f ? t : u.tool === t ? '' : t; render(); if (u.tool === 'link') focus('l_' + id); if (u.tool === 'search') focus('q_' + id + '_' + (f === 'album' ? 2 : 1)); },
  rvGroup(id, v) { rvU(id).group = v; },
  rvQ(id, i, v) { const x = S.rv.items.find(j => j.id === id), u = rvU(id); u.q = (u.q || x.q).slice(); u.q[i] = v; },
  async rvGroupCopy(key) {
    const st = S.rvGS[key] || {}, txt = [0, 1, 2].map(i => ((document.getElementById('gq_' + i) || {}).value ?? (st.q || [])[i] ?? '').trim()).filter(Boolean).join(' - ');
    if (!txt) return toast('Nothing to copy yet.', true);
    try { await navigator.clipboard.writeText(txt); toast('Copied: ' + txt); }
    catch (e) { const t = document.createElement('textarea'); t.value = txt; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); toast('Copied: ' + txt); } catch (e2) { toast('Could not copy.', true); } t.remove(); }
  },
  async rvGroupPaste(key) {
    let txt = '';
    try { txt = (await navigator.clipboard.readText() || '').trim(); } catch (e) { const el = document.getElementById('gl'); if (el) el.focus(); return toast('Click the box and press Ctrl+V to paste.', true); }
    if (!txt) return toast('The clipboard is empty.', true);
    S.rvGS[key] = S.rvGS[key] || { q: [] }; S.rvGS[key].link = txt; render(); toast('Link pasted. Press Load album.');
  },
  async rvCopyQ(id) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id), q = u.q || (x && x.q) || [];
    const txt = [0, 1, 2].map(i => ((document.getElementById('q_' + id + '_' + i) || {}).value ?? q[i] ?? '').trim()).filter(Boolean).join(' - ');
    if (!txt) return toast('Nothing to copy yet.', true);
    try { await navigator.clipboard.writeText(txt); toast('Copied: ' + txt); }
    catch (e) { const t = document.createElement('textarea'); t.value = txt; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); toast('Copied: ' + txt); } catch (e2) { toast('Could not copy.', true); } t.remove(); }
  },
  async rvPasteLink(id) {
    let txt = '';
    try { txt = (await navigator.clipboard.readText() || '').trim(); } catch (e) { const el = document.getElementById('l_' + id); if (el) el.focus(); return toast('Click the box and press Ctrl+V to paste.', true); }
    if (!txt) return toast('The clipboard is empty.', true);
    const u = rvU(id); u.link = txt; render(); toast('Link pasted. Press Load release.');
  },
  rvLinkSet(id, v) { const u = rvU(id); const had = !!u.link; u.link = v; if (!had || !v) render(); },
  async rvSearch(id, deep) {
    const x = S.rv.items.find(i => i.id === id), u = rvU(id), q = u.q || x.q;
    if (!(q[1] || '').trim()) return toast('Type the song title first.', true);
    u.loading = 'search'; u.err = ''; render();
    const r = await call('review_search', id, q[0], q[1], q[2], !!deep);
    u.loading = ''; u.searched = true; u.results = r.results || []; u.stats = r.stats || {}; u.err = r.error || ''; render();
  },
  rvLinkGroup(id) {                              // use the loaded album for every song of my album
    const x = S.rv.items.find(i => i.id === id), u = rvU(id);
    const key = 'L|' + x.id;
    const ids = S.rv.items.filter(y => !isDone(y) && (y.g_album || '') === (x.g_album || '') && (y.g_artist || '') === (x.g_artist || '') && (x.g_album || y.id === x.id)).map(y => y.id);
    S.rvGroups[key] = { key, ids, album: x.g_album || x.tags.album || '', artist: x.g_artist || x.tags.artist || '' };
    S.rvGS[key] = { q: [S.rvGroups[key].artist, S.rvGroups[key].album], link: u.link };
    S.rvGroupSel = { key }; S.rvView = S.rvView === 'quick' ? 'songs' : S.rvView; render(); A.rvGroupSearch(key, true);
  },
  async rvLink(id) {
    const u = rvU(id); if (!(u.link || '').trim()) return;
    u.loading = 'link'; u.err = ''; render();
    const r = await call('review_link', u.link);
    u.loading = ''; if (r.error) { u.err = r.error; u.rel = null; } else { u.rel = r; u.err = ''; } render();
    if (u.rel) setTimeout(() => { const e = document.getElementById('relTop_' + id); if (e) e.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }, 60);
  },
  async rvDig(id) {
    const u = rvU(id); u.loading = 'dig'; u.err = ''; render();
    const r = await call('review_dig', id);
    u.loading = ''; u.dig = (r && r.results) || []; u.digSteps = (r && r.steps) || []; u.err = (r && r.error) || ''; render();
  },
  setSv(k, v, quiet) { S.set.services[k] = v; S.setDirty = true; if (quiet) document.querySelectorAll('.setsave').forEach(b => { b.disabled = false; }); else render(); },
  setOrder(which, i, d) { const l = S.set[which === 'alt' ? 'alt_order' : 'cover_order']; [l[i], l[i + d]] = [l[i + d], l[i]]; S.setDirty = true; render(); },
  async setSave() { const G = S.set; const r = await call('save_settings', { services: G.services, alt_order: G.alt_order, cover_order: G.cover_order, sort_mode: G.sort_mode, analyze: G.analyze, tier_style: G.tier_style, tier_name: G.tier_name, dup_place: G.dup_place, classical_mode: G.classical_mode, skip_nested: G.skip_nested, archive_on: G.archive_on });
    if (r && r.error) return toast(r.error, true); S.setDirty = false; S.set = null; S.info = await call('init'); S.mode = 'simple'; toast('Settings saved.'); render(); },
  async neat(ids, action) {                         // 1.1.5: the screen changes at once; the list is no longer re-read (that took ~5 s)
    const set = new Set(ids); S.nRecent = ids.slice().reverse().concat((S.nRecent || []).filter(i => !set.has(i))); (S.neat && S.neat.rows || []).forEach(r => { if (set.has(r.id)) { r.state = action === 'undo' ? '' : action === 'accept_nogenre' ? 'accept' : action; r.t = action === 'undo' ? 0 : Date.now() / 1000; } });
    render(); const r = await call('neat_decide', ids, action); if (r && r.error) { toast(r.error, true); S.neat = await call('neat_list'); render(); } },
  async neatSel(action) { const ids = Object.keys(S.nSel || {}).filter(k => S.nSel[k]); S.nSel = {}; await A.neat(ids, action); },
  async neatEasy() { const min = S.nMin || 90, ids = (S.neat.rows || []).filter(r => !r.state && r.pct >= min && (S.nOrder || []).includes(r.id)).map(r => r.id); if (ids.length) await A.neat(ids, 'accept'); },
  nToggle(id, on) { S.nSel = S.nSel || {}; S.nSel[id] = on; S.nLast = id; nPaint(); },
  nGroupSel(g, on) { const gb = S.nGroup; (S.neat.rows || []).forEach(r => { const k = gb === 'album' ? (r.new.album || '?') + ' — ' + (r.new.albumartist || r.new.artist) : gb === 'artist' ? r.new.artist || '?' : r.folder; if (!r.state && k === g) S.nSel[r.id] = on; }); render(); },
  nDown(ev, id) {
    if (ev.button !== 0 || ev.target.closest('button,input,select,a,label.nck')) return;
    S.nSel = S.nSel || {};
    if (ev.shiftKey && S.nLast && S.nOrder) {                       // select everything between
      const a = S.nOrder.indexOf(S.nLast), b = S.nOrder.indexOf(id);
      if (a >= 0 && b >= 0) S.nOrder.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(k => S.nSel[k] = true);
      ev.preventDefault(); nPaint(); return;
    }
    const on = !S.nSel[id]; S.nSel[id] = on; S.nLast = id;
    S.nSweep = { on };                                              // keep the button down and move: select as you go
    const up = () => { S.nSweep = null; document.removeEventListener('mouseup', up); }; document.addEventListener('mouseup', up);
    ev.preventDefault(); nPaint();
  },
  nEnter(ev, id) { if (!S.nSweep || !(ev.buttons & 1)) return; S.nSel[id] = S.nSweep.on; S.nLast = id; nPaint(); },
  async fFind() { const q = (S.fQ || '').trim(); if (q.length < 2) return toast('Type at least 2 letters.', true); S.fRes = await call('find_search', q); render(); },
  async fLogs() { S.fLogs = null; render(); S.fLogs = await call('restore_logs'); render(); },
  async fLoadLog() { const p = await call('pick_file', 'Choose a restore log');
    const use = async v => { const r = await call('restore_log_info', v); S.fExtra = r; S.fOpen = r.path; render(); };
    if (p) return use(p);
    if (!DESKTOP) { S.dlg = { kind: 'path', title: 'Restore log', text: 'Type or paste the path of a restore log (.json).', ok: 'Load', then: use }; renderLayer(); focus('dlgpath'); } },
  async fRestore(fid) { const r = await call('restore_original', fid); if (r && r.error) return toast(r.error, true); S.fAfter = 'find'; S.screen = 'dash'; render(); await poll(true); },
  async fReverse(path) { const r = await call('reverse_log', path); if (r && r.error) return toast(r.error, true); S.fAfter = 'logs'; S.screen = 'dash'; render(); await poll(true); },
  async boxChoose(key, mode) {
    const b = S.pl.boxes.find(x => x.key === key); if (!b) return;
    const r = await call('box_choose', key, mode, b.ids, b.album); if (r && r.error) return toast(r.error, true);
    S.pl = await call('playlist_data'); render();
    if (mode) toast(mode === 'skip' ? 'Skipped: nothing changes for this one.' : mode === 'together' ? 'Kept together. Update the plan (Review) to see it in Plan preview.' : 'The box set will be saved as a playlist at Copy & tag.');
  },
  async fRestoreAll() { const r = await call('restore_all_archive'); if (r && r.error) return toast(r.error, true); S.screen = 'dash'; render(); await poll(true); },
  async fUndoCopy() { const r = await call('undo_copy'); if (r && r.error) return toast(r.error, true); S.fAfter = 'undo'; S.screen = 'dash'; render(); await poll(true); },
  async digStart(again) { const r = await call('dig_start', null, !!again); if (r && r.error) return toast(r.error, true); toast('Digging deeper for ' + plural(r.total, 'song') + '…'); await poll(true); },
  async rvSound(id) {
    const u = rvU(id); u.loading = 'sound'; u.err = ''; render();
    const r = await call('review_sound', id);
    u.loading = ''; u.sound = r.results || []; u.err = r.error || ''; render();
  },
  rvUse(id, mode, i) {
    const u = rvU(id), x = S.rv.items.find(j => j.id === id);
    const c = (u.tool === 'sound' && u.sound ? u.sound : u.tool === 'dig' && u.dig ? u.dig : u.results)[i];
    rvDecide(id, { action: 'pick', match: c.match, label: candLabel(c) });
  },
  rvSlot(id, ri, ti) {
    const u = rvU(id), x = S.rv.items.find(j => j.id === id);
    const rel = ri < 0 ? u.rel : u.sugg[ri], t = rel.tracks[ti];
    const c = { match: t.match, release: rel.title, year: rel.year, track: t.track, source: rel.source, length: t.length };
    if (false) { u.pending = Object.assign({}, c, { title: t.title, artist: rel.artist, rtype: t.match.rtype, disc: t.disc, len_text: '', how: 'picked from the release' }); u.pendingKey = t.match.release_id + '|' + t.disc + '|' + t.track; render(); toast('Picked "' + t.title + '". Press Accept your pick (A) to use it.'); window.scrollTo({ top: 0, behavior: 'smooth' }); return; }
    rvDecide(id, { action: 'pick', match: t.match, label: candLabel(c) });
  },
  rvSlotR(xid, rid, ti, direct) {
    const rel = S.relReg[rid], t = rel && rel.tracks[ti]; if (!t) return;
    const x = xid && S.rv.items.find(j => j.id === xid);
    if (!x) return toast('Drag one of your songs onto this track.', true);
    const c = { match: t.match, release: rel.title, year: rel.year, track: t.track, source: rel.source, length: t.length };
    if (false) { const u = rvU(xid); u.pending = Object.assign({}, c, { title: t.title, artist: rel.artist, rtype: t.match.rtype, disc: t.disc, len_text: '', how: 'picked from the release' }); u.pendingKey = t.match.release_id + '|' + t.disc + '|' + t.track; render(); toast('Picked "' + t.title + '". Press Accept your pick (A) to use it.'); return; }
    rvDecide(xid, { action: 'pick', match: t.match, label: candLabel(c) }, S.rvView === 'albums');
  },
  rvDropR(ev, rid, ti) {
    ev.preventDefault(); ev.stopPropagation(); ev.currentTarget && ev.currentTarget.classList.remove('over');
    let id = S.rvDrag; try { id = id || ev.dataTransfer.getData('text/plain'); } catch (e) {} S.rvDrag = null; if (!id) return;
    const rel = S.relReg[rid], t = rel && rel.tracks[ti]; if (!t) return;
    rvDecide(id, { action: 'pick', match: t.match, label: candLabel({ release: rel.title, year: rel.year, track: t.track, source: rel.source }) }, S.rvView === 'albums');
    toast('Put on track ' + t.track + ': ' + t.title);
  },
  rvDrop(ev, ri, ti) {
    ev.preventDefault(); ev.currentTarget && ev.currentTarget.classList.remove('over');
    let id = S.rvDrag; try { id = id || ev.dataTransfer.getData('text/plain'); } catch (e) {} S.rvDrag = null; if (!id) return;
    const fx = rvFocus(); const u = rvU(fx.id);
    const rel = ri < 0 ? u.rel : u.sugg[ri], t = rel.tracks[ti];
    rvDecide(id, { action: 'pick', match: t.match, label: candLabel({ release: rel.title, year: rel.year, track: t.track, source: rel.source }) });
  },
  async playUrl(url, dz) {
    const a = S.audio || (S.audio = new Audio()), key = 'u:' + url;
    if (S.playing === key) { a.pause(); S.playing = null; render(); return; }
    S.playing = key; render();
    let src = url;
    if (dz) { const r = await call('preview_url', dz); if (r && r.url) src = r.url; }      // Deezer links expire: ask for a fresh one
    if (S.playing !== key) return;
    a.src = src; a.play().catch(() => { S.playing = null; render(); toast('This preview cannot be played (the site may not offer one for this song).', true); });
    a.onended = () => { S.playing = null; render(); };
    S.playing = key; render();
  },
  pbToggle() { const a = S.audio; if (!a) return; if (a.paused) a.play().catch(() => {}); else a.pause(); playerBar(); },
  play(id) {
    const a = S.audio || (S.audio = new Audio());
    if (!id || (S.playing === id && !a.paused)) { a.pause(); S.playing = null; render(); return; }
    if (!S.info.audio) return toast('Preview is not available.', true);
    // one click is enough: a new song stops the old one first, and a slow start (big FLAC) is waited for, not lost
    a.pause(); a.src = S.info.audio + encodeURIComponent(id); a.load();
    const tok = S.playTok = (S.playTok || 0) + 1;
    a.onended = () => { if (S.playTok === tok) { S.playing = null; render(); } };
    a.onerror = () => { if (S.playTok === tok) { S.playing = null; render(); toast('This file cannot be played here.', true); } };
    S.playing = id; render();
    const go = () => a.play().catch(e => { if (S.playTok !== tok) return; if (e && e.name === 'AbortError') return;
      a.addEventListener('canplay', () => { if (S.playTok === tok) a.play().catch(() => {}); }, { once: true }); });
    go();
  },
  async reveal(id) { const r = await call('reveal', id); if (r && r.error) toast(r.error + (r.path ? ' ' + r.path : ''), true); },
  async updatePlan(mode) {
    // V2.0.5 (#5): remember how many songs this update is about, so the finished toast can say what changed
    const pt = (S.rv && S.rv.plan_time) || 0, items = (S.rv && S.rv.items) || [];
    S.updInfo = { mode: mode || 'fast', changed: items.filter(x => x.decision && (x.decision.t || 0) > pt).length, before: (S.dash && S.dash.counts) || null };
    const r = await call('update_plan', mode || 'fast'); if (r.error) { S.updInfo = null; toast(r.error, true); } await poll(true); },
  async toPlan() {
    if (S.rv && S.rv.stale) { const r = await call('update_plan'); if (r.error) return toast(r.error, true); S.afterUpdate = 'plan'; await poll(true); render(); return; }
    A.go('plan');
  }
};
document.addEventListener('keydown', e => {
  const tag = (e.target && e.target.tagName || '').toLowerCase();
  const typing = tag === 'input' && !['checkbox', 'radio', 'button'].includes((e.target.type || '').toLowerCase());      // 1.1.7: a ticked box must not switch the shortcuts off
  if (S.screen !== 'review' || S.rvView === 'tags' || S.dlg || typing || tag === 'textarea' || tag === 'select' || e.altKey) return;
  if (tag === 'input' && e.key === ' ') return;
  if ((e.ctrlKey || e.metaKey) && !(e.key === 'a' || e.key === 'A')) return;
  if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) { e.preventDefault(); return A.rvCheckAll(true); }
  const fx = rvFocus(), key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (key === 'Escape' && Object.values(S.rvChecked).some(Boolean)) { e.preventDefault(); return A.rvCheckAll(false); }
  const anyCk = Object.values(S.rvChecked).some(Boolean);
  if (!anyCk && key === 's' && S.rv && S.rv.items.some(isAside)) { e.preventDefault(); return A.rvAsideSearch(); }
  if (anyCk) {
    if (key === 's') { e.preventDefault(); return A.rvBulkSearch(); }
    const bm = { a: 'accept', n: 'reject', u: 'unverified', k: 'unverified', l: 'later', z: 'undo' }[key];
    if (bm) { e.preventDefault(); return A.rvBulk(bm); }
  }
  if (S.rvView === 'album' && !S.alRow) {                        // 2.0.1: album shortcuts (Quick > Album)
    const cs = albumCards('all'), c = cs.find(c => c.key === S.alKey);
    const am = { a: () => c && A.alAll(c.key, 'accept'), m: () => c && A.alPageMatch('AP|' + c.key), l: () => c && A.alAll(c.key, 'later'), o: () => c && A.alAll(c.key, 'leave'), t: () => c && A.alTrustAsk(c.key), s: () => c && A.alSplit(c.key), ArrowRight: () => A.alPageMove(1), ArrowLeft: () => A.alPageMove(-1), ArrowDown: () => A.alPageMove(1), ArrowUp: () => A.alPageMove(-1) };
    if (am[key]) { e.preventDefault(); return am[key](); }
  }
  if ((key === 'ArrowDown' || key === 'ArrowUp') && (S.rvView === 'albums' || (S.rvView === 'album' && S.alRow))) { e.preventDefault(); return A.alStep(key === 'ArrowDown' ? 1 : -1); }     // V2.0.6: up / down walk the songs of the albums in the order you SEE them
  if (key === 'ArrowDown' || key === 'ArrowRight' && (S.rvView === 'quick' || S.rvView === 'library')) { e.preventDefault(); return A.rvMove(1); }
  if (key === 'ArrowUp' || key === 'ArrowLeft' && (S.rvView === 'quick' || S.rvView === 'library')) { e.preventDefault(); return A.rvMove(-1); }
  if (key === 'z') { e.preventDefault(); return A.rvUndoLast(); }          // V2.0.5 (#9): works in every view, also with nothing selected
  if (!fx || S.rvView === 'albums' && !S.alRow) return;
  const k = effKind(fx), id = fx.id;
  const map = {
    a: () => A.rvAccept(id),
    k: () => A.rvUnv(id),
    u: () => A.rvUnv(id),
    f: () => A.rvDigIn(id, 'search'),
    e: () => A.rvTagEdit(id),
    n: () => k === 'match' && A.rvReject(id),
    l: () => A.rvLater(id),
    o: () => A.rvLeave(id),
    t: () => A.rvTrust(id),
    p: () => A.play(id),
    ' ': () => A.play(id),
    x: () => A.reveal(id),
    z: () => A.rvUndoLast(),
    i: () => A.rvDigIn(id, 'dig'),
    d: () => A.rvDigIn(id),
    v: () => (k === 'none' ? A.rvTool(id, 'link') : k === 'match' ? (rvU(id).edit || A.rvEdit(id), focus('l_' + id)) : (A.rvFind(id), focus('l_' + id)))
  };
  if (map[key]) { e.preventDefault(); map[key](); }
});

// ---- Find & restore: search any song; reverse any change from a restore log (nothing is ever deleted)

document.addEventListener('mouseup', () => { if (S.akDrag) { S.akDrag = false; render(); } });

// ---- 2.0.1: press a select box and drag down (or up) over the rows to select many; works for the song list and the album boxes
(function () {
  let d = null, quiet = 0;
  const idOf = cb => { const m = /A\.rvCheck\(event,(.*)\)\s*$/.exec(cb.getAttribute('onclick') || ''); if (!m) return null; try { return JSON.parse(m[1]); } catch (e) { return null; } };
  const put = id => {
    if (d.on) S.rvChecked[id] = true; else delete S.rvChecked[id];
    document.querySelectorAll('#main input.qck').forEach(c => { if (idOf(c) === id) { c.checked = d.on; const r = c.closest('.qrow,.alrow'); if (r) r.classList.toggle('sel', d.on); } });
  };
  document.addEventListener('mousedown', e => {
    if (e.button !== 0 || !e.target.closest) return;
    const cb = e.target.closest('input.qck'); if (!cb || cb.classList.contains('akck') || cb.getAttribute('onmousedown')) return;
    const id = idOf(cb); if (id == null) return;
    d = { start: id, on: !cb.checked, moved: false };
  }, true);
  document.addEventListener('mouseover', e => {
    if (!d || !(e.buttons & 1) || !e.target.closest) return;
    const row = e.target.closest('.qrow,.alrow'); if (!row) return;
    const cb = row.querySelector('input.qck'); if (!cb) return;
    const id = idOf(cb); if (id == null) return;
    if (!d.moved) { if (id === d.start) return; d.moved = true; document.body.classList.add('dragsel'); put(d.start); }
    put(id);
  });
  document.addEventListener('mouseup', () => {
    if (!d) return; const moved = d.moved; d = null; document.body.classList.remove('dragsel');
    if (moved) { quiet = Date.now() + 80; render(); }
  }, true);
  document.addEventListener('click', e => { if (Date.now() < quiet && e.target.closest && e.target.closest('input.qck')) { e.stopPropagation(); e.preventDefault(); } }, true);
})();

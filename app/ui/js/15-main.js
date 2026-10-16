/* Midnight 00:01 · Screen list, dialogs, button actions (A), polling, start-up (part of the screens, loaded in order by index.html) */
'use strict';
const LATER = {
  review: 'Review: one list of every song that needs a decision, and a big panel to decide on each one.',
  dups: 'Duplicates: every song found more than once, best copy first, with your choice per copy.',
  neat: 'Neat Picky: before / after tags for every song, with Accept or Keep my tags.',
  analyze: 'Analyze: artists, albums, tiers and almost-complete albums with helpers to find missing songs.',
  plan: 'Plan preview: the folder tree of the new library, with Customize folders.',
  apply: 'Copy & tag: the green Approve button that makes the copies (originals are never changed).',
  archive: 'Archive: moving the originals, only after Approve, choosing a folder and "Are you sure?".',
  search: 'Find & restore: search any song and reverse any change from a restore log.',
  settings: 'Settings: online services, keys, the order of sites and cover art.'
};
function placeholder() {
  const name = (NAV.find(n => n[0] === S.screen) || [, ''])[1];
  return `<header class="bighead"><h1>${esc(name)}</h1><p>${esc(LATER[S.screen] || '')}</p></header>
    <div class="panel empty">This screen is not part of this version yet. Your scan results are saved in the logs folder, so nothing is lost.</div>`;
}
const SCREENS = { sources: sourcesScreen, dash: dashScreen, review: reviewScreen, dups: dupsScreen, apply: copyScreen, archive: archiveScreen, analyze: analyzeScreen, plan: planScreen, search: findScreen, settings: settingsScreen, neat: neatScreen, playlists: playlistScreen, activity: () => activityScreen() };

// ---------------------------------------------------------------- dialogs
const DIALOGS = {
  path() {
    const d = S.dlg;
    return `<h2>${esc(d.title)}</h2><p class="sub" style="margin:0">${esc(d.text)}</p>
      <input class="text mono" id="dlgpath" value="${esc(d.value || '')}" placeholder="C:\\…" oninput="S.dlg.value=this.value" onkeydown="if(event.key==='Enter')A.dlgOk()">
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn amber" onclick="A.dlgOk()">${esc(d.ok || 'OK')}</button></div>`;
  },
  protect() {
    const d = S.dlg;
    return `<h2 style="display:flex;gap:10px;align-items:center">${svg(ICON.shield, 22, '#D9826B')} Protected folder</h2>
      <p style="margin:0">You asked that <b>${esc(d.name)}</b> is never touched unless you say so:</p>
      <p class="mono wrap" style="margin:0;font-size:13px">${esc(d.path)}</p>
      <p class="sub" style="margin:0">${esc(d.why)} Type <b>YES</b> to allow it this time.</p>
      <input class="text" id="dlgyes" value="${esc(d.value || '')}" oninput="S.dlg.value=this.value" onkeydown="if(event.key==='Enter')A.protectOk()">
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Leave it alone</button>
        <button class="btn amber" onclick="A.protectOk()" ${String(d.value || '').trim() === 'YES' ? '' : 'disabled'}>Allow</button></div>`;
  },
  cancelscan() {
    const id = S.B.job && S.B.job.stage !== 'read';
    return `<h2>Cancel the scan?</h2>
      <p class="sub" style="margin:0">Nothing on disk is changed. ${id ? 'Songs already looked up are remembered. What should happen with them?' : 'Reading files has not finished, so there is nothing to keep yet.'}</p>
      ${id ? `<div class="row" style="gap:8px;flex-wrap:nowrap">
        <button class="btn amber grow" data-tip="Build the plan from what was found and open Review. The rest waits in _Unverified." title="Build the plan from what was found and open Review. The rest waits in _Unverified." onclick="A.stopWith('use')">Use the results now</button>
        <button class="btn outline grow" data-tip="Only the songs that were found are added to the plan; the rest is left out for now." title="Only the songs that were found are added to the plan; the rest is left out for now." onclick="A.stopWith('add')">Add found songs to Review</button>
        <button class="btn outline grow" data-tip="Stop now. The next scan reuses everything found, so it is quick." title="Stop now. The next scan reuses everything found, so it is quick." onclick="A.stopWith('later')">Keep for later</button></div>
        <span class="sub" style="font-size:12px">Hover a button to see what it does.</span>` : `<button class="btn outline" onclick="A.stopWith('later')">Cancel the scan</button>`}
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Keep scanning</button></div>`;
  },
  export() {
    const d = S.dlg, I = S.expInfo || {};
    return `<h2>Copy the verified songs?</h2>
      <p style="margin:0"><b>${plural(I.songs || 0, 'song')}</b> · ${human(I.size || 0)} will be copied from your library into:</p>
      <p class="mono wrap" style="margin:0;font-size:13px">${esc(S.expDir || '')}</p>
      <p class="sub" style="margin:0">Your library and your originals are not changed. Files that already exist there are left as they are, nothing is overwritten.</p>
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn green" onclick="A.expGo()">Yes, copy</button></div>`;
  },
  sure() {
    const d = S.dlg; d.sort = d.sort || 'pct';
    const tn = v => String(v || '').split('/')[0].replace(/^0+/, '');
    const info = x => { const ch = sureChange(x); if (!ch) return null; const s = ch.s, t = x.tags;
      const pairs = [['Artist', t.artist, s.artist], ['Title', t.title || stem(x.file), s.title], ['Album', t.album, s.release], ['Year', (t.year || '').slice(0, 4), s.year], ['Track', tn(t.track), tn(s.track)]]
        .filter(p => p[2] && nkw(p[1]) !== nkw(p[2]));
      return { x, ch, pairs, s, t }; };
    let list = sureOnes().map(info).filter(Boolean);
    const cmp = { pct: (a, b) => (b.x.safe ? 100 : b.ch.pct) - (a.x.safe ? 100 : a.ch.pct) ||  a.pairs.length - b.pairs.length,
      changes: (a, b) => a.pairs.length - b.pairs.length || b.ch.pct - a.ch.pct,
      artist: (a, b) => String(a.t.artist || '').localeCompare(String(b.t.artist || '')) || String(a.t.album || '').localeCompare(String(b.t.album || '')),
      album: (a, b) => String(a.t.album || '').localeCompare(String(b.t.album || '')) || String(a.t.artist || '').localeCompare(String(b.t.artist || '')) };
    list.sort(cmp[d.sort] || cmp.pct);
    S.sureOrder = list.map(r => r.x.id);
    const STEPS = [100, 95, 90, 85, 80], tierOf = pc => STEPS.find(v => pc >= v) || 0, tiers = new Map(), tp = r => r.x.safe ? 100 : r.ch.pct;
    list.forEach(r => { const tr = tierOf(tp(r)); (tiers.get(tr) || tiers.set(tr, []).get(tr)).push(r.x.id); });
    S.sureTiers = Object.fromEntries(tiers);
    let lastTier = null;
    const tierHead = tr => { const ids = tiers.get(tr), all = ids.every(i => !d.off[i]);
      return `<div class="suretier"><span class="t">${tr ? tr + '%' : 'below ' + STEPS[STEPS.length - 1] + '%'}</span><span class="sub">${plural(ids.length, 'song')}${tr === 100 ? ' · exactly 100% alike' : tr ? ' · ' + tr + ' to ' + (STEPS[STEPS.indexOf(tr) - 1] - 1) + '% alike' : ''}</span><span style="flex:1"></span><button class="btn small outline" onclick="A.sureTier(${tr},${!all})">${all ? 'Untick this box' : 'Tick this box'}</button></div>`; };
    const rows = list.map(({ x, ch, pairs, t }) => (d.sort === 'pct' && tierOf(x.safe ? 100 : ch.pct) !== lastTier ? tierHead(lastTier = tierOf(x.safe ? 100 : ch.pct)) : '') + `<div class="surerow" data-sid="${esc(x.id)}" onmousedown="A.sureDown(event,${arg(x.id)})" onmouseenter="A.sureOver(${arg(x.id)})"><input type="checkbox" tabindex="-1" style="pointer-events:none" ${d.off[x.id] ? '' : 'checked'}>
        <span class="sr"><b>${esc(t.title || stem(x.file))}</b> <span class="sub">· ${esc(t.artist || '')} · ${ch.pct}% · ${esc(ch.how)}</span>${x.safe ? ` <span class="chip vtag" title="${esc(verifiedTip(x))}">verified ✓</span>` : ''}
        ${pairs.length ? pairs.map(p => `<span class="chg"><span class="sub">${p[0]}:</span> ${p[1] ? diffHtml(p[1], p[2]) : '<i class="sub">empty</i>'} → ${diffHtml(p[2], p[1])}</span>`).join('') : '<span class="chg sub">tags stay the same; it is placed on its album</span>'}</span></div>`).join('');
    const n = list.filter(r => !d.off[r.x.id]).length;
    const sorts = [['pct', 'Match % ↓', 'Surest first'], ['changes', 'Fewest changes', 'The ones that hardly change first (almost zero change)'], ['artist', 'Artist', ''], ['album', 'Album', '']];
    return `<h2>Accept if…</h2><p class="sub" style="margin:0">Only what changes is shown. Untick the songs you want to check yourself: click one, or press and drag over several. Nothing is copied now.</p>
      <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small outline selbtn" onclick="A.sureAll(true)">${svg('M5 12l5 5L20 7', 14)} Select all</button><button class="btn small outline selbtn" onclick="A.sureAll(false)">${svg('M6 6l12 12M18 6L6 18', 14)} Select none</button>
        <span class="sub" style="font-size:12px;margin-left:8px">Sort</span><span class="seg small">${sorts.map(o => `<button aria-pressed="${d.sort === o[0]}" title="${esc(o[2])}" onclick="S.dlg.sort=${arg(o[0])};renderLayer()">${o[1]}</button>`).join('')}</span>
        <span class="sub" style="font-size:12px" id="surecount">${plural(n, 'song')} selected</span></div>
      <div class="surelist" id="surelist" style="user-select:none">${rows}</div>
      <div class="row" style="justify-content:space-between"><button class="btn outline" onclick="A.rvSureQuick()">Go through them in Quick mode</button>
        <span class="row" style="gap:8px"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn green" id="suregobtn" onclick="A.rvSureGo()" ${n ? '' : 'disabled'}>Accept ${plural(n, 'song')}</button></span></div>`;
  },
  report() {
    const d = S.dlg;
    const b = (fmt, t, sub, dis) => `<button class="mode" ${dis || d.busy ? 'disabled' : ''} onclick="A.anReportGo(${arg(fmt)})"><span class="t">${d.busy === fmt ? '<span class="spin"></span> ' : ''}${t}</span><span class="sub" style="font-size:13px">${sub}</span></button>`;
    return `<h2>Report</h2><p class="sub" style="margin:0">Which kind? It is saved in the library's <span class="mono">_Reports</span> folder (a new file every time) and opened.</p>
      <div class="modes" style="grid-template-columns:1fr">${b('pdf', 'PDF', 'Summary, tiers, top artists and every almost complete album — easy to read or print.')}
        ${b('excel', 'Excel', 'Every artist and every album with numbers and missing songs — to sort and filter yourself.')}
        ${b('collection', 'Image · whole collection', 'One picture: the numbers and your biggest artists.')}
        <div class="mode" style="cursor:default"><span class="t">Image · one artist</span><span class="sub" style="font-size:13px">One picture of an artist: tier, numbers and every album with how complete it is.</span>
          <span class="row" style="gap:8px;flex-wrap:wrap"><select id="rep_artist" onchange="S.dlg.artist=this.value" style="max-width:100%">${((S.an && S.an.artists) || []).map(a => `<option value="${esc(a.artist)}" ${a.artist === d.artist ? 'selected' : ''}>${esc(a.artist)}</option>`).join('')}</select>
          <button class="btn small amber" ${d.busy ? 'disabled' : ''} onclick="S.dlg.artist=document.getElementById('rep_artist').value;A.anReportGo('card')">${d.busy === 'card' ? '<span class="spin"></span> ' : ''}Make the image</button></span></div></div>
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Close</button></div>`;
  },
  trust() {
    const keys = S.dlg.keys || [S.dlg.key], cs = keys.map(k => albumCards('all').find(c => c.key === k)).filter(Boolean);
    if (!cs.length) return '<p>Album not found.</p>';
    const one = a => { const open = a.items.filter(x => !isDone(x)), t0 = open[0] ? open[0].tags : {};
      const aa = t0.albumartist || t0.artist || a.artist || 'Unknown Artist', y = (t0.year || '').slice(0, 4);
      return { open, html: `<div class="note mono" style="font-size:12px">${esc(/^(various|various artists|va)$/i.test(aa) ? 'Various Artists' : aa)} / ${esc((y ? y + ' - ' : '') + (a.album || 'Unknown Album'))}</div>
      <div class="surelist" style="max-height:none;overflow:visible">${open.map(x => `<div class="surerow"><span class="sr"><b>${esc((x.tags.track ? String(x.tags.track).split('/')[0] + '. ' : '') + (x.tags.title || stem(x.file)))}</b> <span class="sub">· ${esc(x.tags.artist || '')} · ${mmss(x.duration)}</span></span></div>`).join('')}</div>` }; };
    const parts = cs.map(one), n = parts.reduce((t, p) => t + p.open.length, 0);
    return `<h2>Trust my tags</h2><p class="sub" style="margin:0">${cs.length > 1 ? 'These albums are' : 'This album is'} placed using your own tags exactly — nothing is looked up. ${cs.length > 1 ? 'Each stays' : 'It stays'} together in one folder:</p>
      ${parts.map(p => p.html).join('')}
      <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn green" onclick="A.alTrustGo()">Use my tags for ${plural(n, 'song')}</button></div>`;
  },
  alsure() {
    const d = S.dlg, cards0 = sureAlbums(); d.sort = d.sort || 'pct';
    const pctOf = c => Math.min(...c.items.map(x => x.match_pct || 0)), nOpen = c => c.items.filter(x => !isDone(x) && !isAside(x)).length;
    const cards = cards0.slice().sort(d.sort === 'artist' ? (a, b) => String(a.artist || '').localeCompare(String(b.artist || '')) : d.sort === 'album' ? (a, b) => String(a.album || '').localeCompare(String(b.album || '')) : d.sort === 'songs' ? (a, b) => nOpen(b) - nOpen(a) || pctOf(b) - pctOf(a) : (a, b) => pctOf(b) - pctOf(a));
    if (d.rev) cards.reverse();          // V2.0.6: the arrow button turns any sort around (top to bottom / bottom to top)
    S.sureAlOrder = cards.map(c => c.key);
    const nkw2 = v => String(v || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
    const body = cards.map(c => {
      const open = c.items.filter(x => !isDone(x) && !isAside(x)), s0 = open[0].suggest, aoff = d.aoff[c.key];
      const rows = open.map(x => { const s = x.suggest, t = x.tags, tn = v => String(v || '').split('/')[0].replace(/^0+/, '');
        const pairs = [['Artist', t.artist, s.artist], ['Title', t.title || stem(x.file), s.title], ['Album', t.album, s.release], ['Year', (t.year || '').slice(0, 4), s.year], ['Track', tn(t.track), tn(s.track)]]
          .filter(p => p[2] && nkw2(p[1]) !== nkw2(p[2]));
        return `<label class="surerow" style="margin-left:22px"><input type="checkbox" ${aoff || d.off[x.id] ? '' : 'checked'} ${aoff ? 'disabled' : ''} onchange="S.dlg.off[${arg(x.id)}]=!this.checked;renderLayer()">
          <span class="sr"><b>${esc(t.title || stem(x.file))}</b> <span class="sub">· ${x.match_pct}%</span>
          ${pairs.length ? pairs.map(p => `<span class="chg"><span class="sub">${p[0]}:</span> ${p[1] ? diffHtml(p[1], p[2]) : '<i class="sub">empty</i>'} → ${diffHtml(p[2], p[1])}</span>`).join('') : '<span class="chg sub">tags stay the same</span>'}</span></label>`; }).join('');
      return `<div class="alsure"><label class="surerow"><input type="checkbox" ${aoff ? '' : 'checked'} onchange="S.dlg.aoff[${arg(c.key)}]=!this.checked;renderLayer()">
        <span class="sr"><b>${esc(c.album || c.folder.split(/[\\/]/).pop())}</b> <span class="sub">· ${esc(c.artist || '')} → ${esc(s0.release)}${s0.year ? ' (' + esc(s0.year) + ')' : ''} · ${esc(s0.source)} · ${plural(open.length, 'song')}</span></span></label>${rows}</div>`;
    }).join('');
    const n = cards.reduce((k, c) => k + (d.aoff[c.key] ? 0 : c.items.filter(x => !isDone(x) && !isAside(x) && !d.off[x.id]).length), 0);
    return `<h2>Accept album if…</h2><p class="sub" style="margin:0">Albums where every open song points to the same found album and is ${S.sureBand === false ? 'at least ' + (S.sureMin || 90) + '%' : 'in the band ' + sureTxt()} alike. Only what changes is shown. Untick an album or a single song to check it yourself. Nothing is copied now.</p>
      <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn small outline selbtn" onclick="A.alSureAll(true)">${svg('M5 12l5 5L20 7', 14)} Select all</button><button class="btn small outline selbtn" onclick="A.alSureAll(false)">${svg('M6 6l12 12M18 6L6 18', 14)} Select none</button>
        <span class="sub" style="font-size:12px;margin-left:8px">Sort</span><span class="seg small">${[['pct', 'Match %'], ['songs', 'Most songs'], ['artist', 'Artist'], ['album', 'Album']].map(o => `<button aria-pressed="${d.sort === o[0]}" onclick="S.dlg.sort=${arg(o[0])};renderLayer()">${o[1]}</button>`).join('')}</span>
        <button class="btn small outline" onclick="S.dlg.rev=!S.dlg.rev;renderLayer()" title="Turn the order around: top to bottom / bottom to top">${d.rev ? '↑ Bottom to top' : '↓ Top to bottom'}</button></div>
      <div class="surelist">${body}</div>
      <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button><button class="btn green" onclick="A.alSureGo()" ${n ? '' : 'disabled'}>Accept ${plural(n, 'song')} in ${plural(cards.filter(c => !d.aoff[c.key]).length, 'album')}</button></div>`;
  },
  consent() {
    const d = S.dlg, sv = d.sv, info = S.info;
    const rows = info.service_info.map(s => {
      const on = !!sv[s.key], need = s.needs, missing = on && need && !(sv[need] || '').trim();
      return `<label class="svc"><input type="checkbox" ${on ? 'checked' : ''} onchange="A.svc(${arg(s.key)},this.checked)">
        <span><span class="n">${esc(s.name)}</span> <span class="sub mono" style="font-size:12px">${esc(s.site)}</span></span>
        <span class="d">Sends: ${esc(s.sends)}</span>
        ${s.key === 'mb' && on ? `<span class="field"><span class="sub" style="font-size:12px">Contact for MusicBrainz (optional, email or website; sent with each request)</span><input id="f_contact" value="${esc(sv.contact || '')}" oninput="S.dlg.sv.contact=this.value"></span>` : ''}
        ${on && need ? `<span class="field"><span class="sub" style="font-size:12px">${need === 'discogs_token' ? 'Discogs personal token' : need === 'lastfm_key' ? 'Last.fm API key' : need === 'tidal_id' ? 'Tidal Client ID' : need === 'spotify_id' ? 'Spotify Client ID' : 'AcoustID API key'} — ${missing ? '<b style="color:var(--amber)">empty: this service will not be used</b>' : 'saved in the library settings'}</span>
          <input id="f_${need}" class="${missing ? 'missing' : ''}" value="${esc(sv[need] || '')}" oninput="S.dlg.sv[${arg(need)}]=this.value"></span>` : ''}
        ${on && s.key === 'spotify' ? `<span class="field"><span class="sub" style="font-size:12px">Spotify Client Secret</span><input id="f_spotify_secret" class="${!(sv.spotify_secret || '').trim() ? 'missing' : ''}" value="${esc(sv.spotify_secret || '')}" oninput="S.dlg.sv.spotify_secret=this.value"></span>` : ''}
        ${on && s.key === 'tidal' ? `<span class="field"><span class="sub" style="font-size:12px">Tidal Client Secret</span><input id="f_tidal_secret" class="${!(sv.tidal_secret || '').trim() ? 'missing' : ''}" value="${esc(sv.tidal_secret || '')}" oninput="S.dlg.sv.tidal_secret=this.value"></span>` : ''}
      </label>`;
    }).join('');
    const seg = (key, opts) => `<span class="seg">${opts.map(o => `<button aria-pressed="${sv[key] === o[0]}" onclick="A.svcSet(${arg(key)},${arg(o[0])})">${o[1]}</button>`).join('')}</span>`;
    const none = !sv.mb;
    const speed = S.speed || 'complete';
    const speedRow = `<div class="note">Scan: <b>${speed === 'fast' ? 'Fast' : 'Complete'}</b> (change it on Sources, step 3)${speed === 'fast' ? ' — identify by sound, the discography check and lyrics are skipped this time.' : ''}</div>`;
    return `<h2>Before scanning: online services</h2>
      ${info.set_once ? '<div class="note" style="border:1px solid var(--green)"><span>Your earlier choice is saved and ticked below. Change it for this scan if you like; nothing is sent until you press Start.</span></div>' : ''}
      <p style="margin:0" class="sub">Reading your files happens only on this PC. To identify songs, the app asks these sites. Tick what may be used.
        Every site gets <b>text only</b> (names and lengths) — never your files or folder paths. Nothing is copied or changed in this step.</p>
      <div>${rows}</div>${speedRow}
      ${none ? '<div class="note" style="border:1px solid var(--amber)">Without MusicBrainz nothing can be confirmed: every song would wait in _Unverified.</div>' : ''}
      <div class="row" style="justify-content:flex-end"><button class="btn ghost" onclick="A.closeDlg()">Cancel</button>
        <button class="btn amber" onclick="A.scanGo()">Start scan &amp; identify</button></div>`;
  }
};

// ---------------------------------------------------------------- actions
const A = {
  async saveSession(quiet, toFile) {
    const r = await call(toFile ? 'save_session_file' : 'save_session', { screen: S.screen, theme: S.theme, speed: S.speed });
    if (quiet) return;
    if (r && r.cancelled) return toast('Session kept in the app. No file was saved.');
    toast(r && r.ok ? (r.path ? 'Session saved to ' + r.path : 'Session saved: your keys, settings and this page will be here next time.') : ((r && r.error) || 'Could not save the session.'), !(r && r.ok));
  },
  async loadSession() {
    const r = await call('load_session_file');
    if (!r || r.cancelled) return;
    if (r.error) return toast(r.error, true);
    const t0 = performance.now(); if (r.screen) S.screen = r.screen; S.info = await call('init'); await poll(true); S.dash = null; S.rv = null; const t1 = performance.now(); render(); const t2 = performance.now();
    toast('Session loaded: ' + (r.applied || 0) + ' settings restored. (timing: apply ' + r.t_apply + 's, save ' + r.t_save + 's, init ' + ((t1 - t0) / 1000).toFixed(1) + 's, draw ' + ((t2 - t1) / 1000).toFixed(1) + 's)');
  },
  go(s) { const was = S.screen; S.screen = s; WANT_Y = 0; if (s === 'apply') S.expInfo = null; clearTimeout(A._ssT); A._ssT = setTimeout(() => A.saveSession(true), 1500); if (s === 'dups') S.dups = null; if (s === 'playlists') S.pl = null; if (s === 'activity') S.act = null; if (s === 'neat') { S.neat = null; if (!S.rv) loadReview(); } if (s === 'settings' && !S.setDirty) S.set = null; if (s === 'apply') S.copy = null; if (s === 'archive') S.arch = null; if (s === 'plan') { S.plan = null; S.lay = null; S.laySort = null; S.planOpen = S.planOpen || {}; } if (s === 'lookout' && !S.an) { S.an = null; } if (s === 'analyze') { A.keepIfSame('an', 'anStamp'); call('extra_copies').then(r => { S.extraReq = {}; (r || []).filter(x => !x.done).forEach(x => S.extraReq[x.release_id + '|' + x.disc + '|' + x.track] = true); render(); }); } render(); if (was !== s) window.scrollTo(0, 0); if (s === 'dash') refreshDash(); if (s === 'review') A.reviewOpen(); },
  async keepIfSame(key, stampKey) {                  // keep a loaded screen's data when nothing changed on disk
    const st = await call('stamp');
    if (S[key] && S[stampKey] === st) return;
    S[key] = null; S[stampKey] = st; render();
  },
  async reviewOpen() {
    const st = await call('stamp');
    if (S.rv && S.rvStamp === st && !S.rv.stale0) return;       // nothing changed: the list is already here
    S.rvStamp = st; await loadReview();
  },
  async scPick() {
    const r = await call('site_check_pick'); const C = S.sc || (S.sc = {});
    if (!r || r.cancelled) return; if (r.error) { C.err = r.error; return render(); }
    Object.assign(C, { artist: r.artist, title: r.title, album: r.album, duration: r.duration, path: r.path, rows: null, err: r.error || '' }); render();
  },
  async scRun() {
    const C = S.sc; if (!C || C.busy) return; C.busy = true; C.err = ''; C.rows = null; render();
    const r = await call('site_check', C.artist || '', C.title || '', C.album || '', C.duration || 0, C.path || '');
    C.busy = false; if (!r || r.error) C.err = (r && r.error) || 'The check failed.'; else C.rows = r.rows; render();
  },
  async expBrowse() { const p = await pickDir('Choose the folder for the exported songs'); if (p) { S.expDir = p; await A.expCheck(); }
    else if (!DESKTOP) { S.dlg = { kind: 'path', title: 'Export folder', text: 'Type or paste the folder path.', ok: 'Use', then: async v => { S.expDir = v; await A.expCheck(); } }; renderLayer(); focus('dlgpath'); } },
  async expCheck() { const r = await call('export_check', S.expDir || ''); S.expErr = r && r.error ? r.error : ''; render(); },
  async expAsk() { await A.expCheck(); if (S.expErr) return; S.dlg = { kind: 'export' }; renderLayer(); },
  async expGo() {
    S.dlg = null; renderLayer();
    const r = await call('export_start', S.expDir); if (r && r.error) { S.expErr = r.error; return render(); }
    S.expSt = { running: true, copied: 0, skipped: 0, failed: 0, total: 0 }; render();
    clearInterval(A._expT); A._expT = setInterval(async () => { const st = await call('export_status'); S.expSt = st; if (!st || !st.running) clearInterval(A._expT); if (S.screen === 'apply') render(); }, 1200);
  },
  async expCancel() { await call('export_cancel'); },
  async archBrowse() { const p = await pickDir('Choose the archive folder'); if (p) { S.archDir = p; A.archCheck(); }
    else if (!DESKTOP) { S.dlg = { kind: 'path', title: 'Archive folder', text: 'Type or paste the folder path.', ok: 'Use', then: v => { S.archDir = v; A.archCheck(); } }; renderLayer(); focus('dlgpath'); } },
  async archCheck() { const r = await call('check_archive_folder', S.archDir || ''); S.archErr = r && r.error ? r.error : ''; render(); },
  async archGo() {
    await A.archCheck(); if (S.archErr) return;
    const r = await call('start_archive', S.archDir, !!S.archEmpty, !!S.archFlat);
    if (r && r.error) { S.archErr = r.error; return render(); }
    S.screen = 'dash'; render(); await poll(true);
  },
  async answer(yes) { const c = S.B.confirm; if (!c) return; S.confirmTyped = ''; await call('answer', c.id, yes); await poll(true); },
  copyPickAll(on) { const q = (S.copyQ || '').toLowerCase(); (S.copy.artists || []).filter(a => !q || a.artist.toLowerCase().includes(q)).forEach(a => S.copyPick[a.artist] = on); render(); },
  async copyScan() { S.copyScanning = true; render(); S.copyScan = await call('copy_extras_scan'); S.copyScanning = false; render(); },
  async copyGo() {
    const mode = S.copyMode || 'confirmed', arts = Object.keys(S.copyPick || {}).filter(k => S.copyPick[k]);
    const ex = Object.keys(S.copyEx || {}).filter(k => S.copyEx[k]);
    const r = await call('start_copy', mode, arts, ex, !!S.copyLeft);
    if (r && r.error) return toast(r.error, true);
    S.screen = 'apply'; render(); await poll(true);
  },
  async openLib() { const lib = (S.B.library || (S.info && S.info.library)); const r = await call('open_folder', lib); if (!r) toast('The folder could not be opened here.', true); },
  navToggle() { S.navCol = !S.navCol; store.set('navCol', S.navCol); renderNav(); },
  theme() { S.theme = S.theme === 'dark' ? 'light' : 'dark'; store.set('theme', S.theme); render(); },
  mode(m) { S.mode = m; render(); },
  speed(m) { S.speed = m; store.set('speed', m); render(); },
  closeDlg() { S.dlg = null; renderLayer(); },
  async dlgOk() { const d = S.dlg; S.dlg = null; renderLayer(); if (d && d.then && (d.value || '').trim()) await d.then(d.value.trim()); },

  // sources
  async browse() {
    const p = await pickDir('Choose a music folder');           // V2.0.5 (#4): the same picker in the window and in the browser
    if (p) return addSources([p]);
  },
  async browseSongs() { const ps = await call('pick_songs'); if (ps && ps.length) return addSources(ps);
    if (!DESKTOP) { S.dlg = { kind: 'path', title: 'Add one song', text: 'Type or paste the full path of the song.', ok: 'Add', then: v => addSources([v]) }; renderLayer(); focus('dlgpath'); } },
  async removeAll() { if (!confirm('Remove all music sources from the list?\n\nNothing on disk is changed or deleted. The destination stays.')) return;
    const r = await call('remove_all_sources'); if (r && r.error) toast(r.error, true); await poll(true); toast('All sources removed.'); },
  async removeSource(p) { const r = await call('remove_source', p); if (r.error) toast(r.error, true); await poll(true); },
  async pickOut() {
    const p = await pickDir('Where should the organized library go?');
    if (p) return setLibrary(p);
  },
  protectOk() { const d = S.dlg; if (String(d.value || '').trim() !== 'YES') return; S.dlg = null; renderLayer(); d.then(); },

  // whole computer
  async wholeStart() {
    S.w = { nodes: {}, kids: {}, tops: [], since: 0, sel: {}, open: {}, songs: {}, st: { done: false } };
    await call('whole_start'); render(); wholeLoop();
  },
  async wToggle(id) {
    const W = S.w; W.open[id] = !W.open[id]; render();
    if (W.open[id] && !W.songs[id] && W.nodes[id].own) { W.songs[id] = await call('folder_songs', id); render(); }
  },
  wChoose(id, v) {
    const W = S.w; W.sel[id] = v;
    const clear = i => (W.kids[i] || []).forEach(k => { delete W.sel[k]; clear(k); });
    clear(id);
    // protected folders stay skipped unless you choose them yourself
    const keep = i => (W.kids[i] || []).forEach(k => { if (W.nodes[k].protected && v) W.sel[k] = false; keep(k); });
    keep(id);
    render();
  },
  async wCancel() {
    if (S.w && !S.w.st.done && !S.w.st.cancelled) { await call('whole_cancel'); return; }
    S.w = null; render();
  },
  async wAdd(confirmed) {
    const { sources, excludes } = wholeSelection();
    const r = await call('set_tree_sources', sources, excludes, !!confirmed);
    if (r.needs_confirm) return askProtect(r, 'It would be scanned (read only).', () => A.wAdd(true));
    S.w = null; toast('Added ' + plural(sources.length, 'place') + (excludes.length ? ', skipping ' + plural(excludes.length, 'folder') + ' inside' : '') + '.');
    await poll(true);
  },

  // scan
  scanAsk() {
    const info = S.info, B = S.B;
    if (!(B.library || info.library)) return toast('Choose where the organized library should go (step 2).', true);
    if (!(B.sources || []).length) return toast('Add at least one music folder (step 1).', true);
    const sv0 = Object.assign({}, info.services);
    // v1.1.4: every service you turned on in Settings has its key saved -> no need to ask again before each scan
    const miss = (info.service_info || []).some(x => sv0[x.key] && x.needs && !(sv0[x.needs] || '').trim()) || (sv0.tidal && !(sv0.tidal_secret || '').trim()) || (sv0.spotify && !(sv0.spotify_secret || '').trim());
    // V2.0.5 (#6): Complete mode ALWAYS shows the consent box (it sends more: sound fingerprints, discography checks). Fast mode starts at once
    // when everything was already agreed, and says so.
    if (sv0.mb && !miss && info.set_once && (S.speed || 'complete') === 'fast') {
      S.dlg = { kind: 'consent', sv: sv0 }; toast('Fast scan started with your saved online services (change them in Settings).'); return A.scanGo(); }
    S.dlg = { kind: 'consent', sv: sv0 }; renderLayer();
  },
  svc(k, v) { S.dlg.sv[k] = v; renderLayer(); },
  svcSet(k, v) { S.dlg.sv[k] = v; renderLayer(); },
  async scanGo() {
    const sv = Object.assign({}, S.dlg.sv, { speed: S.speed || 'complete' }); S.dlg = null; renderLayer();
    S.info.services = Object.assign({}, sv);
    const r = await call('start_scan', { mode: S.mode, services: sv });
    if (r.error) return toast(r.error, true);
    S.screen = 'dash'; render(); await poll(true);
  },
  async pendingTake() { const r = await call('take_pending'); if (r && r.error) return toast(r.error, true); await poll(true); toast('Added to the sources. Press Scan & identify when you are ready.'); render(); },
  async newProject() {
    if (!confirm('Start a new project?\n\nThe list of music folders is emptied. The destination stays. Nothing on disk is changed or deleted.')) return;
    const r = await call('new_project'); if (r && r.error) return toast(r.error, true);
    S.dash = null; S.screen = 'sources'; await poll(true); render(); toast('New project: the music folders list is empty. The destination is kept.'); },
  stop() { const j = S.B.job; if (j && j.kind === 'scan') { S.dlg = { kind: 'cancelscan' }; return renderLayer(); } return A.stopWith('later'); },
  async stopWith(mode) { S.dlg = null; renderLayer(); S.afterStop = mode === 'later' ? null : mode; return A.stopNow(); },
  async stopNow() { await call('stop'); toast('Cancelling… nothing has been changed; the last finished results stay.'); await poll(true); },
  async pause(on) { const r = await call('pause', on); if (r && r.error) return toast(r.error, true); await poll(true); },
  tier(t) { S.anTier = t; A.go('analyze'); },
  async dupDecide(g, mode) { await call('dup_choose', g, mode, [], []); S.dupCustom = null; const r = await call('dup_list'); S.dups = r; const nx = r.groups.find(x => !x.choice); S.dupOpen = nx && nx.group; render(); },
  dupToggle(g, fid) { const G = S.dups.groups.find(x => x.group === g); if (!G) return;
    if (!S.dupCustom || S.dupCustom.group !== g) { S.dupCustom = { group: g, keep: {} }; G.copies.forEach(c => S.dupCustom.keep[c.file_id] = dupState(G, c) !== 'out'); }
    S.dupCustom.keep[fid] = !S.dupCustom.keep[fid]; render(); },
  async dupCustomDone(g) { const G = S.dups.groups.find(x => x.group === g), k = S.dupCustom.keep;
    const inc = G.copies.filter(c => c.extra && k[c.file_id]).map(c => c.file_id), leave = G.copies.filter(c => !c.extra && !k[c.file_id]).map(c => c.file_id);
    await call('dup_choose', g, 'custom', inc, leave); S.dupCustom = null; const r = await call('dup_list'); S.dups = r; const nx = r.groups.find(x => !x.choice); S.dupOpen = nx && nx.group; render(); },
  async dupDropFirst(g, i) { const G = S.dups.groups.find(x => x.group === g), fid = S.dupDrag; S.dupDrag = null; if (!G || !fid || i === 0 && G.copies[0].file_id === fid) return render();
    S.dupOrder = S.dupOrder || {}; S.dupOrder[g] = fid; const c = G.copies.find(x => x.file_id === fid); if (!c) return;
    const inc = c.extra ? [fid] : [], leave = G.copies.filter(x => !x.extra && x.kind === c.kind && x.file_id !== fid).map(x => x.file_id);
    await call('dup_choose', g, 'custom', inc, leave); const r = await call('dup_list'); S.dups = r; render(); toast('That copy is now the one you keep.'); },
  async dupClear() { const D = S.dups; if (!D) return; const f = S.dupF || 'all';
    const gs = D.groups.filter(g => g.choice && (f === 'all' || f === 'reviewed' || (f === 'identical' && g.identical) || (f === 'lower' && g.lower) || (f === 'pair' && g.pair) || (f === 'unsure' && g.sure < 90)));
    for (const g of gs) await call('dup_choose', g.group, 'undo', [], []);
    S.dupOrder = {}; S.dups = await call('dup_list'); render(); toast(gs.length + ' choice(s) cleared.'); },
  async dupBestAll() { const r = await call('dup_best_everywhere'); S.dups = await call('dup_list'); if (r && r.skipped) toast(r.skipped + ' not-sure song(s) (under 90%) were left for you to decide.'); render(); },
  async dupQuality(g) { const G = S.dups.groups.find(x => x.group === g); S.dupBusy = S.dupBusy || {}; S.dupBusy[g] = 'q'; render();
    const r = await call('dup_quality', G.copies.map(c => c.file_id)); S.dupBusy[g] = null; if (r && !r.error) G.copies.forEach(c => { if (r[c.file_id]) c.quality = r[c.file_id]; }); else toast((r && r.error) || 'Could not measure.', true); render(); },
  async dupCompare(g) { const G = S.dups.groups.find(x => x.group === g); S.dupBusy = S.dupBusy || {}; S.dupBusy[g] = 'c'; render();
    const r = await call('dup_compare', G.copies.map(c => c.file_id), g); S.dupBusy[g] = null;
    if (r && r.pairs) { const p = r.pairs.map(x => x.pct).filter(x => x != null); if (p.length) { G.sure = Math.min(...p); G.sure_how = 'measured by sound'; } } S.dupCmp = S.dupCmp || {}; if (r && r.pairs) S.dupCmp[g] = r; else toast((r && r.error) || 'Could not compare.', true); render(); },
  async dupCheckAll() {
    const todo = S.dups.groups.filter(g => g.sure < 90 && g.sure_how !== 'measured by sound');
    for (let i = 0; i < todo.length; i++) { S.dupAll = (i + 1) + ' of ' + todo.length; render();
      const g = todo[i], r = await call('dup_compare', g.copies.map(c => c.file_id), g.group);
      if (r && r.pairs) { const p = r.pairs.map(x => x.pct).filter(x => x != null); if (p.length) { g.sure = Math.min(...p); g.sure_how = 'measured by sound'; } }
      if (S.screen !== 'dups') break; }
    S.dupAll = null; render();
  },
  async loonyGo() { const r = await call('start_loonybin', S.loonyMode || 'copy'); if (r && r.error) return toast(r.error, true); S.screen = 'dash'; render(); await poll(true); },
  async planToggle(id) { S.planOpen[id] = !S.planOpen[id]; render(); if (S.planOpen[id] && !S.planKids[id]) { S.planKids[id] = await call('plan_tree', id); render(); } },
  layPreset(js) { S.lay.levels = JSON.parse(js); render(); },
  layMove(i, d) { const l = S.lay.levels, t = l[i]; l[i] = l[i + d]; l[i + d] = t; render(); },
  layDel(i) { S.lay.levels.splice(i, 1); if (!S.lay.levels.length) S.lay.levels = ['artist']; render(); },
  layAdd(k) { if (k && !S.lay.levels.includes(k)) S.lay.levels.push(k); render(); },
  laySet(which, v) {
    S.lay[which] = v;
    if (v === 'custom' && !(S.lay[which + '_pattern'] || []).length) S.lay[which + '_pattern'] = which === 'release' ? ['{year}', ' - ', '{album}'] : ['{track}', ' ', '{title}'];
    render();
  },
  patAdd(which, b) { const k = which + '_pattern'; S.lay[k] = (S.lay[k] || []).concat([b]); render(); },
  patDel(which, i) { const k = which + '_pattern'; S.lay[k] = (S.lay[k] || []).filter((_, n) => n !== i); render(); },
  patDrop(ev, which, at) {
    ev.preventDefault(); ev.currentTarget.classList && ev.currentTarget.classList.remove('over');
    const d = S.patDrag; S.patDrag = null; if (!d || d.which !== which) return;
    const k = which + '_pattern', p = (S.lay[k] || []).slice();
    let item;
    if (d.add) item = d.add; else { item = p.splice(d.from, 1)[0]; if (at > d.from) at--; }
    if (at < 0 || at > p.length) p.push(item); else p.splice(at, 0, item);
    S.lay[k] = p; render();
  },
  setDrag(which, from, to) { const l = S.set[which === 'alt' ? 'alt_order' : 'cover_order']; if (from === to) return; const [x] = l.splice(from, 1); l.splice(to, 0, x); S.setDirty = true; render(); },
  async setSortFastest() { const sp = S.set.speeds || {}; const f = (sp.fastest || []).slice(); S.set.alt_order = f.concat(S.set.alt_order.filter(k => !f.includes(k))); S.setDirty = true; render();
    toast(sp.measured ? 'Sorted by measured speed. Save settings to keep it.' : 'No speeds measured yet: the usual fast-first order is used. Press Measure speed for real numbers.'); },
  async measureSpeed() { if (!confirm('Measure speed?\n\nThis sends ONE word (queen) three times to each site that is turned on in Settings, and nothing else, to see how fast each one answers.')) return;
    S.setMeasuring = true; render(); const r = await call('measure_speeds'); S.setMeasuring = false; if (r && r.error) { render(); return toast(r.error, true); }
    S.set.speeds = r; render(); toast('Speeds measured.'); },
  async setTool(name) { const r = await call('set_tool', name); if (r && r.error) return toast(r.error, true); if (r && r.path) { S.set = null; render(); toast(name + ' set: ' + r.path); } },
  async layApply() { const r = await call('set_layout', S.lay, S.laySort || null); if (r && r.error) return toast(r.error, true); S.plan = null; S.screen = 'dash'; render(); await poll(true); },
  anSongQ() {                       // 1.1.5: typing a song title also finds the artists that have it
    const q = (S.anQ || '').trim().toLowerCase(); clearTimeout(S._anSongT);
    if (q.length < 3) { S.anSongHits = {}; S.anSongHitQ = ''; return; }
    S._anSongT = setTimeout(async () => { const r = await call('song_artists', q); if ((S.anQ || '').trim().toLowerCase() === q && r && !r.error) { S.anSongHits = r; S.anSongHitQ = q; render(); } }, 300);
  },
  anTierSet(t) { S.anTier = S.anTier === t ? '' : t; render(); },
  anOpen(a) {
    S.anOpen = S.anOpen === a ? null : a; S.anAlbums = {}; render();
    // keep the artist you clicked where it is (the one closing above it no longer pushes it off the screen)
    if (S.anOpen) { const el = [...document.querySelectorAll('.anrow.open')][0]; if (el) el.scrollIntoView({ block: 'nearest' }); }
  },
  async anAlbumOpen(k, rid, ev) {
    S.anAlbums = S.anAlbums || {}; S.anTr = S.anTr || {};
    const multi = ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey), was = !!S.anAlbums[k];
    if (!multi) S.anAlbums = {};                      // Ctrl+click keeps the others open
    if (was) delete S.anAlbums[k]; else S.anAlbums[k] = true;
    S.anTrHelp = null; render();
    if (S.anAlbums[k] && !S.anTr[k]) { const r = await call('album_tracks', rid); S.anTr[k] = r && r.tracks ? r : { tracks: [], error: (r && r.error) || 'no answer' }; render(); }
  },
  async anAlmostPlay(i) { const x = (S.an.almost || [])[i]; if (!x) return; if (S.anAlmostOpen === i) { S.anAlmostOpen = null; return render(); } S.anAlmostOpen = i; render();
    const k = x.artist + '|' + x.release_id; S.anTr = S.anTr || {};
    if (!S.anTr[k]) { const r = await call('album_tracks', x.release_id); S.anTr[k] = r && r.tracks ? r : { tracks: [], error: (r && r.error) || 'no answer' }; render(); } },
  anReport(artist) { S.dlg = { kind: 'report', artist: artist || '' }; renderLayer(); },
  async anReportGo(fmt) {
    const d = S.dlg; d.busy = fmt; renderLayer();
    const r = await call('analyze_report', fmt, d.artist || '');
    S.dlg = null; renderLayer();
    if (r && r.error) return toast(r.error, true);
    toast('Saved: ' + r.path);
  },
  anTrHelp(i) { S.anTrHelp = S.anTrHelp === i ? null : i; render(); },
  async anBrowse(js) {
    const d = JSON.parse(js);
    const go = async p => { const r = await call('extra_copy', 'browse:' + p.split(/[\\/]/).pop(), d.release_id, d.disc, d.track, d.title, d.artist, d.album, true, p);
      if (r && r.error) return toast(r.error, true); S.extraReq = S.extraReq || {}; S.extraReq[d.release_id + '|' + d.disc + '|' + d.track] = { browse: true };
      toast('It will be copied into the album in the next Copy & tag (' + r.pending + ' waiting).'); render(); };
    const p = await call('pick_audio'); if (p) return go(p);
    if (!DESKTOP) { S.dlg = { kind: 'path', title: 'Pick the music file', text: 'Type or paste the full path of the file.', ok: 'Use this file', then: go }; renderLayer(); focus('dlgpath'); }
  },
  anHelp(i, ti) { const k = i + ':' + ti; S.anHelp = S.anHelp === k ? null : k; render(); },
  async anExtra(js, on) { const d = JSON.parse(js); const r = await call('extra_copy', d.src, d.release_id, d.disc, d.track, d.title, d.artist, d.album, on);
    if (r && r.error) return toast(r.error, true); S.extraReq = S.extraReq || {}; S.extraReq[d.release_id + '|' + d.disc + '|' + d.track] = on;
    toast(on ? 'It will be copied into the album in the next Copy & tag (' + r.pending + ' waiting).' : 'Removed.'); render(); },
  // v1.1: PC searches run in the background (an index of every drive), several at once; you can click on while they work
  async anFind(k, artist, title) { S.anFind = S.anFind || {}; S.anFind[k] = { loading: true }; render(); await call('pc_find_start', k, artist, title); pcPoll(); },
  async anFindAlbum(ak) { const T = (S.anTr || {})[ak]; if (!T) return; const [artist] = ak.split('|'), rid = ak.split('|').slice(1).join('|');
    S.anFind = S.anFind || {}; const al = (S.an.artists.find(a => a.artist === artist) || { albums: [] }).albums.find(x => (x.release_id || x.album) === rid) || {};
    for (const t of T.tracks.filter(t => !t.have)) { const k = pcKey({ release_id: al.release_id || rid }, t); S.anFind[k] = { loading: true }; call('pc_find_start', k, artist, t.title || t.label); }
    render(); pcPoll(); },
  anBasis(b) { S.anBasis = b; S.an = null; S.anTr = {}; S.anAlbums = {}; render(); },
  async anAddHere(js) { const d = JSON.parse(js), m = d.meta;
    const r = await call('extra_copy', 'browse:' + d.path.split(/[\\/]/).pop(), m.release_id, m.disc, m.track, m.title, m.artist, m.album, true, d.path);
    if (r && r.error) return toast(r.error, true); S.extraReq = S.extraReq || {}; S.extraReq[m.release_id + '|' + m.disc + '|' + m.track] = { browse: true };
    toast('Added to this album: it is copied in the next Copy & tag (' + r.pending + ' waiting).'); render(); return true; },
  async anAddAllFound(ak) { const T = (S.anTr || {})[ak]; if (!T) return; const [artist] = ak.split('|'), rid = ak.split('|').slice(1).join('|');
    const al = (S.an.artists.find(a => a.artist === artist) || { albums: [] }).albums.find(x => (x.release_id || x.album) === rid) || {}; let n = 0;
    for (const t of T.tracks.filter(t => !t.have)) { const f = (S.anFind || {})[pcKey({ release_id: al.release_id || rid }, t)]; if (!f || !f.hits || !f.hits.length) continue;
      const near = f.hits.filter(h => !t.length || Math.abs(h.duration - t.length) <= 5), h = near.find(h => h.suggest) || near[0] || f.hits[0];
      if (await A.anAddHere(JSON.stringify({ path: h.path, meta: { release_id: al.release_id || rid, disc: t.disc, track: t.track, title: t.title || t.label, artist, album: al.album } }))) n++; }
    toast(n ? plural(n, 'song') + ' added to this album.' : 'Nothing to add yet: search the PC first.'); },
  async anScanNow(path) { const r = await call('add_source_folder', path); if (r && r.error) return toast(r.error, true); await poll(true); A.scanAsk(); },
  async anAddFolder(folder, scan) { const r = await call('add_sources', [folder], false); if (r && r.error) return toast(r.error, true);
    if (r && r.needs_confirm) return toast('That folder is protected: add it from Sources.', true); await poll(true);
    if (scan) A.scanAsk(); else toast(r && !(r.added || []).length && (r.already || []).length ? 'That folder is already in your Sources.' : 'Added to Sources.'); },
  async anSongsToggle(name) { S.anSongsOpen = S.anSongsOpen || {}; S.anSongsOpen[name] = !S.anSongsOpen[name]; render();
    if (S.anSongsOpen[name] && !(S.anSongs || {})[name]) { const r = await call('artist_songs', name); S.anSongs = S.anSongs || {}; S.anSongs[name] = Array.isArray(r) ? r : []; render(); } },
  async anFindArtist(name) { S.anFind = S.anFind || {}; S.anFind['artist|' + name] = { loading: true }; render(); await call('pc_find_artist', 'artist|' + name, name); pcPoll(); },
  lookOut(artist) { S.lo = { artist }; A.go('lookout'); },
  async anAddScan(path) { const r = await call('add_source_folder', path); if (r && r.error) return toast(r.error, true); toast('Its folder was added to Sources; it is read in the next scan.'); },
};
Object.assign(A, REVIEW_ACTIONS);
function focus(id) { setTimeout(() => { const e = document.getElementById(id); if (e) { e.focus(); e.select && e.select(); } }, 30); }
function askProtect(r, why, then) { S.dlg = { kind: 'protect', name: r.needs_confirm, path: r.path, why, value: '', then }; renderLayer(); focus('dlgyes'); }
async function addSources(paths, confirmed) {
  const r = await call('add_sources', paths, !!confirmed);
  if (r.needs_confirm) return askProtect(r, 'It would be scanned (read only).', () => addSources(paths, true));
  if (r.error) return toast(r.error, true);
  if (r.problems && r.problems.length) toast(r.problems.join(' · '), true);
  else if (r.added && r.added.length) toast('Added ' + r.added.join(', '));
  await poll(true);
}
async function setLibrary(p, confirmed) {
  const r = await call('set_library', p, !!confirmed);
  if (r.needs_confirm) return askProtect(r, 'The organized library would be written there.', () => setLibrary(p, true));
  if (r.error) return toast(r.error, true);
  S.info.library = r.library; S.info.services = r.services; S.mode = 'simple';
  toast(r.exists ? 'Library: ' + r.library : 'Library: ' + r.library + ' (it will be created when the scan starts)');
  await poll(true); refreshDash();
}

// ---------------------------------------------------------------- live updates
let lastJobDone = null;
async function poll(force) {
  let r;
  try { r = await call('poll', force ? -1 : S.B.rev); } catch (e) { return; }
  if (!r || r.same || r.error) return;
  if (S.rvDrag) return;                                  // never redraw in the middle of a drag
  const wasRunning = S.B.job && !S.B.job.done, prevStage = S.B.job && S.B.job.stage, readTotal = S.B.readTotal;
  const hadConfirm = S.B.confirm && S.B.confirm.id;
  const sig = b => [b.library, b.job && b.job.kind, b.job && b.job.started, b.job && !!b.job.done, b.job && b.job.error, b.job && !!b.job.paused,
    b.prep && b.prep.running, b.prep && b.prep.paused, b.prep && b.prep.cancelled, b.vprep && b.vprep.running, b.vprep && b.vprep.paused, b.vprep && b.vprep.cancelled, b.lookups].join('|');
  const major = !S.B.rev || sig(S.B) !== sig(r);
  S.B = r;
  if ((r.confirm && r.confirm.id) !== hadConfirm) { if (r.confirm) S.confirmTyped = ''; renderLayer(); if (r.confirm) { focus('cfyes'); const l = document.getElementById('cflog'); if (l) l.scrollTop = l.scrollHeight; } }
  S.B.readTotal = r.job && r.job.stage === 'read' && r.progress && r.progress.total ? r.progress.total : (r.job && r.job.done === false ? readTotal : null);
  if (r.job && !r.job.done && prevStage === 'read' && r.job.stage !== 'read') refreshDash();
  if (r.dropped && r.dropped.t !== S.lastDrop) {
    S.lastDrop = r.dropped.t;
    if (r.dropped.folders.length) addSources(r.dropped.folders);
    if (r.dropped.files.length) toast('Drop folders, not single files (' + r.dropped.files.length + ' file' + (r.dropped.files.length > 1 ? 's' : '') + ' ignored).', true);
  }
  if ((r.prep || r.vprep) && S.rv) {                      // Prepare Previews / Verify results arrive: mark the songs (small update, no reload)
    const rp = { done: ((r.prep || {}).done || 0) + ((r.vprep || {}).done || 0), running: !!((r.prep || {}).running || (r.vprep || {}).running) };
    const pd = rp.done + (rp.running ? 0 : 100000);
    if (pd !== S.prepSeen && (!rp.running || Date.now() - (S.prepLoaded || 0) > 6000)) { S.prepSeen = pd; S.prepLoaded = Date.now(); prepFlags(); }
  }
  const doneNow = r.job && r.job.done;
  if ((wasRunning && doneNow) || (doneNow && lastJobDone === false)) {
    if (!r.job.error) S.dashAnim = S.screen === 'dash';
    if (S.afterStop && r.job.kind === 'scan') { const m = S.afterStop; S.afterStop = null; S.afterUpdate = 'review'; const rr = await call('use_cached', m); if (rr && rr.error) { S.afterUpdate = null; toast(rr.error, true); } await poll(true); return; }
    S.copy = null; S.expInfo = null; S.dups = null; S.neat = null; S.an = null; S.arch = null; if (typeof actRefresh === 'function') actRefresh();
    S.dash = await call('dashboard');
    if (S.screen === 'review' || S.rv) await loadReview();
    if (['update', 'fastupdate'].includes(r.job.kind) && S.updInfo) {            // V2.0.5 (#5): say what the update did
      const u = S.updInfo; S.updInfo = null; const c = (S.dash && S.dash.counts) || {};
      if (r.job.error) toast('The plan update stopped: ' + r.job.error, true);
      else toast(`Plan updated${u.mode === 'full' ? ' (full)' : ''}: ${plural(u.changed, 'song')} with your choices went in. ${fmt(c.ready || 0)} ready to copy · ${fmt(c.needs_you || 0)} still need you.`);
    }
    if (S.afterUpdate === 'plan' && ['update', 'fastupdate'].includes(r.job.kind) && !r.job.error) { S.afterUpdate = null; A.go('plan'); }
    if (S.afterUpdate === 'review' && ['update', 'fastupdate'].includes(r.job.kind)) { S.afterUpdate = null; if (!r.job.error) A.go('review'); }
  }
  lastJobDone = r.job ? !!r.job.done : null;
  if (major || LIGHT_SCREENS.has(S.screen)) render();
  else { renderNav(); partialUpdate(); }
  const lg = document.getElementById('log'); if (lg) lg.scrollTop = lg.scrollHeight;
}
// big screens (Review, Neat Picky, Duplicates, Analyze, Plan) are not redrawn for every progress tick:
// only the progress bits are updated, so typing, menus and scrolling stay smooth while something runs
const LIGHT_SCREENS = new Set(['dash', 'sources', 'apply', 'archive', 'search', 'settings']);
function partialUpdate() {
  const pb = document.getElementById('prepbar'); if (pb) { const h = prepBar(); if (h) pb.outerHTML = h; }
  const jb = document.getElementById('jobline'); if (jb && S.B.job && !S.B.job.done) jb.textContent = stageInfo(S.B.job, S.B.progress).line || '';
}
function nPaint() {              // selection changes without redrawing the whole list
  document.querySelectorAll('.nrow[data-nid]').forEach(e => { const on = !!(S.nSel || {})[e.dataset.nid]; e.classList.toggle('sel', on); const c = e.querySelector('.nck input'); if (c) c.checked = on; });
  const b = document.getElementById('nbar'); if (b) b.outerHTML = neatBar();
}
async function prepFlags() {
  const r = await call('prep_flags'); if (!r || !S.rv) return;
  let changed = false;
  S.rv.items.forEach(x => { const f = r[x.id]; if (f) { if (x.prep !== f[0] || x.dig !== !!f[2]) { x.prep = f[0]; x.dig = !!f[2]; changed = true; } if (f[1]) { if (!x.prep_sure) changed = true; x.prep_sure = f[1]; } } });
  const v = await call('verify_flags');
  if (v && !v.error) S.rv.items.forEach(x => { const f = v[x.id]; if (f && (!x.verify || x.verify.n !== f[0] || (x.verify.sources || []).length !== (f[1] || []).length)) { x.verify = { n: f[0], sources: f[1] || [], differ: f[2] || [] }; x.safe = !!(x.kind === 'match' && x.sure && f[0] >= 2 && !x.warn); changed = true; } });
  if (changed && !LIGHT_SCREENS.has(S.screen) && S.screen === 'review' && !(document.activeElement && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName))) render();
}
let _dashAt = 0;
async function refreshDash(force) {                  // 1.1.5: at most every 6 s while you work (it was rebuilt after every single decision)
  if (!force && S.screen !== 'dash' && Date.now() - _dashAt < 6000) return;
  _dashAt = Date.now(); S.dash = await call('dashboard'); if (S.screen === 'dash') render(); }
async function wholeLoop() {
  while (S.w && !S.w.st.done && !S.w.st.cancelled) {
    const r = await call('whole_poll', S.w.since);
    if (!S.w || !r) return;
    for (const n of r.nodes) {
      S.w.nodes[n.id] = n;
      if (n.top || !S.w.nodes[n.parent]) S.w.tops.push(n.id);
      else (S.w.kids[n.parent] = S.w.kids[n.parent] || []).push(n.id);
      if (n.protected || n.junk) S.w.sel[n.id] = false;
    }
    S.w.since = r.count; S.w.st = r;
    if (!S.dlg) render();
    await new Promise(res => setTimeout(res, 450));
  }
}

// drag & drop: the desktop window reads the real folder paths in Python; here we only show the highlight
['dragover', 'drop'].forEach(ev => document.addEventListener(ev, e => e.preventDefault()));
document.addEventListener('dragover', e => { const z = document.getElementById('dropzone'); const over = !!(z && z.contains(e.target)); if (over !== S.dropOver) { S.dropOver = over; z && z.classList.toggle('over', over); } });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) { S.dropOver = false; const z = document.getElementById('dropzone'); z && z.classList.remove('over'); } });
document.addEventListener('drop', () => {
  S.dropOver = false; const z = document.getElementById('dropzone'); z && z.classList.remove('over');
  if (!DESKTOP) toast('In the browser test mode dropped folders cannot be read — use Browse…', true);
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.dlg) A.closeDlg(); });
document.addEventListener('keydown', e => { if (e.key === 'F11') { e.preventDefault(); call('fullscreen'); } });
window.addEventListener('resize', () => { clearTimeout(window._rz); window._rz = setTimeout(render, 150); });      // re-layout after maximize / full screen

// ---------------------------------------------------------------- start
(async function start() {
  document.documentElement.dataset.theme = S.theme;
  await whenReady();
  S.info = await call('init');
  S.mode = 'simple';
  await poll(true);
  await refreshDash();
  const ss = (S.info && S.info.session) || {};
  if (S.info && S.info.library && ss.screen && NAV.some(n => n[0] === ss.screen && n[0] !== 'neat')) S.screen = ss.screen;       // v2.0: back to the page you were on
  if (S.B.job && !S.B.job.done) S.screen = 'dash';
  render();
  setInterval(() => poll(false), 400);
})();

// polls the background PC searches until all are done
let pcTimer = null;
function pcPoll() {
  if (pcTimer) return;
  pcTimer = setInterval(async () => {
    const keys = Object.keys(S.anFind || {}).filter(k => S.anFind[k] && S.anFind[k].loading);
    if (!keys.length) { clearInterval(pcTimer); pcTimer = null; return; }
    const r = await call('pc_find_poll', keys); if (!r || r.error) return;
    keys.forEach(k => { const x = r.searches && r.searches[k]; if (x && !x.loading) S.anFind[k] = x; });
    render();
  }, 1000);
}

document.addEventListener('keydown', e => {
  const tag = (e.target && e.target.tagName || '').toLowerCase();
  if (S.screen !== 'dups' || !S.dups || S.dlg || tag === 'input' || tag === 'textarea' || e.ctrlKey || e.metaKey || e.altKey) return;
  const gs = S.dups.groups, k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  const order = [...document.querySelectorAll('.dupcard')].map(c => c.dataset.g), at = order.indexOf(S.dupOpen);
  if (k === 'ArrowDown' || k === 'ArrowUp') { e.preventDefault(); const n = order[Math.max(0, Math.min(order.length - 1, at + (k === 'ArrowDown' ? 1 : -1)))]; if (n) { S.dupOpen = n; S.dupCustom = null; render(); const el = document.querySelector('.dupcard .duprows'); if (el) el.closest('.dupcard').scrollIntoView({ block: 'nearest' }); } }
  else if (k === 'Enter') { e.preventDefault(); if (S.dupOpen) A.dupDecide(S.dupOpen, 'best'); }
  else if (k === 'a') { if (S.dupOpen) A.dupDecide(S.dupOpen, 'all'); }
  else if (k === 'u') { if (S.dupOpen) A.dupDecide(S.dupOpen, 'undo'); }
  else if (k === ' ') { const G = gs.find(g => g.group === S.dupOpen); if (G) { e.preventDefault(); A.play(G.copies[0].file_id); } }
});

Object.assign(A, {
  // 2.0.2 (item 53): select box sets (click or drag) and choose for all of them at once; uses the same box_choose as one by one
  bxDown(ev, k) { S.boxSel = S.boxSel || {}; S.boxDrag = true; S.boxDragOn = !S.boxSel[k]; S.boxSel[k] = S.boxDragOn; bxPaint(); ev.preventDefault(); ev.stopPropagation(); },
  bxOver(k) { if (!S.boxDrag) return; S.boxSel[k] = S.boxDragOn; bxPaint(); },
  bxAll(on) { S.boxSel = {}; if (on) (S.boxVis || []).forEach(k => { S.boxSel[k] = true; }); render(); },
  async bxChoose(mode) {
    const keys = Object.keys(S.boxSel || {}).filter(k => S.boxSel[k]); let n = 0;
    for (const k of keys) { const b = S.pl.boxes.find(x => x.key === k); if (!b) continue; const r = await call('box_choose', k, mode, b.ids, b.album); if (r && r.error) { toast(r.error, true); break; } n++; }
    S.boxSel = {}; S.pl = await call('playlist_data'); render();
    toast(plural(n, 'box set') + ': ' + (mode === 'skip' ? 'skipped, nothing changes.' : mode === 'together' ? 'kept together. Update the plan (Review) to see it in Plan preview.' : 'will be saved as playlists at Copy & tag.'));
  },
  plDown(ev, k) { S.plSel = S.plSel || {}; S.plDrag = true; S.plDragOn = !S.plSel[k]; S.plSel[k] = S.plDragOn; plPaint(); ev.preventDefault(); },
  plOver(k) { if (!S.plDrag) return; S.plSel[k] = S.plDragOn; plPaint(); },
  plSelAll(key, on) { S.plSel = S.plSel || {}; const b = S.pl.boxes.find(x => x.key === key); (b.list || []).forEach((_, i) => { S.plSel[key + '#' + i] = on; }); render(); },
  plCopyNames(key) { const b = S.pl.boxes.find(x => x.key === key); const t = (b.list || []).filter((_, i) => (S.plSel || {})[key + '#' + i]).join('\n'); try { navigator.clipboard.writeText(t); toast('Names copied.'); } catch (e) { toast('Could not copy.', true); } },
});

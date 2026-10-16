/* 2.0.1 Aurora Glass: info pop-ups (data-tip and the round "!" in page headers) are drawn on top of everything,
   so no glass panel can cover them. One floating tip, placed next to the element under the mouse. */
'use strict';
(function () {
  const t = document.createElement('div'); t.id = 'gtip'; t.setAttribute('role', 'tooltip'); document.body.appendChild(t);
  let cur = null;
  // 2.0.2 (item 77): EVERY button gets a hover tip. Order: its own data-tip, its title, its aria-label, a plain sentence for common labels, then its label.
  const DICT = {
    'cancel': 'Close this without doing anything.', 'see progress': 'Go to the Dashboard to watch the running job.',
    'go to plan preview': 'Open Plan preview: see where every file will go. Nothing is copied yet.', 'undo': 'Take your last choice back.',
    'clear': 'Empty this box.', 'close': 'Close this.', 'open': 'Open it.', 'browse': 'Pick the file or folder yourself.',
    'resume': 'Carry on with the paused job.', 'pause': 'Pause the running job. You can resume it.',
    'open the library folder': 'Show your new library folder in Windows Explorer.', 'open the logs folder': 'Show the folder with the logs in Windows Explorer.',
    'try again': 'Run that step again.', 'explorer': 'Show this folder in Windows Explorer.', 'update the plan now': 'Rebuild the plan with your latest Review choices. Nothing is copied.',
    'choose': 'Choose the folder or file.', 'accept new tags': 'Use the new tags for the selected songs. Your originals are never changed.',
    'later': 'Leave this for later. It stays in Review.', 'select all': 'Tick everything that is shown.', 'select none': 'Untick everything.',
    'no, leave everything as it is': 'Change nothing.', 'yes': 'Confirm and go on.', 'scan whole computer': 'Search every drive for music. Nothing is changed or copied.',
    'remove all': 'Take every folder out of the list. Your files are not touched.', 'scan & identify': 'Read your files and identify the songs. Nothing is changed or copied.',
    'use': 'Use this choice.', 'skip': 'Leave this one alone: nothing changes.', 'see the restore logs': 'Open the list of restore logs.', 'restore logs': 'Open the list of restore logs.',
    'back to duplicates': 'Go back to the Duplicates page.', 'see the archive': 'Open the Archive page.', 'see what was copied': 'Show the files that were copied.',
    'back to review': 'Go back to Review.', 'go to review': 'Open Review: the songs that still need you.', 'back to sources': 'Go back to Sources.', 'go to sources': 'Open Sources: choose your music and library.',
    'scan again': 'Scan the folders again. Nothing is changed or copied.', 'open copy & tag': 'Open Copy & tag. You approve before anything is copied.', 'more analysis': 'Show more of the library analysis.',
    'search the other sites too': 'Also ask the other music sites (asks the sites you allowed; sends only artist and title text).', 'search again for these': 'Search again for the songs you set aside.',
    'show more': 'Show more of the list.', 'use this album for': 'Use this album for the selected songs.', 'load album': 'Load this album and its tracks.',
    'prepare previews': 'Search in the background so results are ready when you open each song.', 'dig deeper': 'Try harder to recognize this song: tags, file names, classical names and sound.',
    'accept if': 'Accept every song whose match is at least the percentage you choose.', 'accept album if': 'Accept every album whose match is at least the percentage you choose.',
    'show all': 'Show every item.', 'accept them': 'Accept all the ones listed.', 'report': 'Make a report (PDF, Excel or artist card). Nothing in your music is changed.',
    'accept': 'Accept this match.', 'leave out': 'Not copied anywhere; the original stays. Undo any time.', 'keep': 'Keep this one as it is.', 'edit': 'Edit the tags yourself.',
    'save session': 'Save your settings and the page you are on into a file. No keys are saved.', 'load session': 'Load a saved session file.'
  };
  const norm = el => { const c = el.cloneNode(true); c.querySelectorAll('.key,svg,.itip').forEach(n => n.remove());
    return (c.textContent || '').replace(/\([^)]*\)/g, '').replace(/[0-9,.]+/g, ' ').replace(/[→←▾▸…▶↑↓✕×]/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase().replace(/ more$/, '').replace(/ left$/, ''); };
  const BTN = 'button,[role=button],summary';
  function autoTip(el) {
    let v = el.getAttribute('data-tip'); if (v) return v;
    const ttl = el.getAttribute('title'), label = (el.textContent || '').replace(/\s+/g, ' ').replace(/\b[A-Z]$/, '').trim();
    if (ttl) el.removeAttribute('title');                       // the page adds title = label to bare buttons; ours replaces it
    if (ttl && ttl !== label) { el.setAttribute('data-tip', ttl); return ttl; }
    v = el.getAttribute('aria-label'); if (v) return v;
    const k = norm(el); if (!k) return ttl || '';
    v = DICT[k] || DICT[k.replace(/ [a-z]$/, '')] || DICT[k.replace(/^show \d* ?more.*/, 'show more')] || (k + '.').replace(/^./, m => m.toUpperCase());
    return v;
  }
  const textOf = el => el.matches('.infoi') ? ((el.querySelector('.itip') || {}).textContent || '') : el.matches(BTN) ? autoTip(el) : (el.getAttribute('data-tip') || '');
  function show(el) {
    const txt = textOf(el); if (!txt) return hide();
    cur = el; t.textContent = txt; t.style.display = 'block'; t.style.maxWidth = el.matches('.infoi') ? 'min(460px,80vw)' : '320px';
    const r = el.getBoundingClientRect(), w = t.offsetWidth, h = t.offsetHeight, vw = innerWidth, vh = innerHeight;
    let x = Math.min(Math.max(8, r.left), vw - w - 8), y = r.bottom + 8;
    if (y + h > vh - 8) y = Math.max(8, r.top - h - 8);
    t.style.left = x + 'px'; t.style.top = y + 'px';
  }
  function hide() { cur = null; t.style.display = 'none'; }
  const find = n => n && n.closest ? n.closest('[data-tip],.infoi,' + BTN) : null;
  document.addEventListener('mouseover', e => { const el = find(e.target); if (el && el !== cur) show(el); else if (!el && cur) hide(); });
  document.addEventListener('mouseout', e => { if (cur && !(e.relatedTarget && cur.contains(e.relatedTarget))) hide(); });
  document.addEventListener('focusin', e => { const el = find(e.target); if (el && (el.matches('.infoi') || el.matches(BTN))) show(el); });
  document.addEventListener('focusout', hide);
  document.addEventListener('mousedown', hide, true);
  addEventListener('scroll', hide, true);
  addEventListener('resize', hide);

  // 2.0.2 (item 81): an icon next to every section title (h2) on the pages. Numbered steps keep their number and get the icon after it.
  const IC = {
    folder: 'M3 7h6l2 2h10v10H3z', check: 'M5 12l5 5L20 7', bolt: 'M13 2L4 14h7l-1 8 9-12h-7z',
    music: 'M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zM20 16a3 3 0 1 1-3-3 3 3 0 0 1 3 3z',
    star: 'M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3l-5.5 2.9 1-6.2L3 9.6l6.2-.9z', user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
    disc: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z', key: 'M7 14a4 4 0 1 1 3.9-5H21v3h-3v3h-3v-3h-4.1A4 4 0 0 1 7 14z',
    sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4', list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01', image: 'M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4',
    copy: 'M9 9h11v11H9zM5 15V5h10', shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z', box: 'M4 7h16v12H4zM4 7l3-3h10l3 3',
    pencil: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4', report: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7', clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
    globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18', info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 8v4M12 16h.01'
  };
  const RULES = [[/music|source/i, 'folder'], [/library go|new library|library$|^library/i, 'folder'], [/fast|speed/i, 'bolt'], [/playlist/i, 'music'], [/box set/i, 'box'],
    [/tier/i, 'star'], [/artist/i, 'user'], [/album/i, 'disc'], [/key|free/i, 'key'], [/order|sites/i, 'list'], [/cover/i, 'image'], [/files?$/i, 'folder'],
    [/customi/i, 'pencil'], [/check|approve/i, 'check'], [/copied|copy/i, 'copy'], [/archive/i, 'box'], [/extras/i, 'list'], [/report|summary/i, 'report'],
    [/needs review|almost/i, 'clock'], [/online|service/i, 'globe']];
  const pick = txt => { for (const r of RULES) if (r[0].test(txt)) return IC[r[1]]; return IC.info; };
  const ico = d => '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + d + '"/></svg>';
  function decorate() {
    document.querySelectorAll('#main h2').forEach(h => {
      if (h.querySelector('.h2i') || h.querySelector('svg')) return;
      const d = pick(h.textContent || ''), num = h.querySelector('.num');
      if (num && !/^[0-9]+$/.test(num.textContent.trim())) { num.innerHTML = ico(d); return; }      // symbol badge (♪ ◉) becomes a real icon
      if (num) return;                                                                                // numbered steps keep just their number
      const i = document.createElement('span'); i.className = 'h2i'; i.innerHTML = ico(d);
      h.insertBefore(i, h.firstChild);
    });
  }
  let raf = 0;
  new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; decorate(); }); }).observe(document.getElementById('main') || document.body, { childList: true, subtree: true });
  decorate();
})();

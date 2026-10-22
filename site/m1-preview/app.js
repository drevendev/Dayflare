/* M1 identity laboratory. Only deterministic, synthetic fixture bytes can be loaded. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const meta = key => document.querySelector(`meta[name="${key}"]`).content;
  const EXPECTED_SHA = meta('dayflare-sha256');
  const PANEL_ID = meta('dayflare-panel-id');
  const SCHEMA = 'dayflare.identity-panel.v1';
  const MAX_FIXTURE_BYTES = 256 * 1024;
  const FIXTURE_LOAD_TIMEOUT_MS = 12000;
  const ids = ['edition','subject','search'];
  let panel = null, chosen = null, incompatible = false;
  let shareEpoch = 0; // Ignore clipboard completions belonging to an older view or click.
  const key = p => `${p.page_ref.project}:${p.page_ref.page_id}`;
  const label = p => p.titles[p.titles.length - 1].title;
  // Announce Wikipedia-edition titles in their source language, not the English UI locale.
  const pageLanguage = p => p.page_ref.project === 'ru.wikipedia' ? 'ru' : 'en';
  const text = (tag, value, className) => {
    const el = document.createElement(tag);
    el.textContent = String(value);
    if (className) el.className = className;
    return el;
  };
  const clear = el => el.replaceChildren();
  const status = (message, error = false) => {
    $('status').textContent = message;
    $('status').classList.toggle('error', error);
  };
  const params = () => new URLSearchParams(location.search);
  const expected = () => ({schema:SCHEMA, panel:PANEL_ID});
  const setControls = enabled => {
    ids.forEach(id => $(id).disabled = !enabled);
    $('copy').disabled = !enabled;
  };
  async function sha256(bytes) {
    const hash = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2,'0')).join('');
  }
  async function readBoundedFixture(res) {
    // Never allocate an arbitrary-sized HTTP body before checking the budget.
    // Browser fetch exposes decoded bytes; Content-Length may cover compressed
    // transfer bytes, so only cross-check declared length for identity encoding.
    const declared = res.headers?.get('content-length');
    const encoding = (res.headers?.get('content-encoding') || '').toLowerCase();
    let headerLength = null;
    if (declared !== null && declared !== undefined) {
      if (!/^(0|[1-9][0-9]*)$/.test(declared)) throw Error('invalid Content-Length');
      headerLength = Number(declared);
      if (!Number.isSafeInteger(headerLength)) throw Error('unsafe Content-Length');
      if ((!encoding || encoding === 'identity') && headerLength > MAX_FIXTURE_BYTES)
        throw Error('fixture exceeds transfer size cap');
    }
    if (!res.body || typeof res.body.getReader !== 'function')
      throw Error('streaming response required to enforce fixture size cap');
    const reader = res.body.getReader();
    const chunks = [];
    let total = 0, done = false;
    try {
      while (true) {
        const piece = await reader.read();
        if (piece.done) { done = true; break; }
        if (!(piece.value instanceof Uint8Array)) throw Error('non-byte fixture chunk');
        if (piece.value.byteLength > MAX_FIXTURE_BYTES - total)
          throw Error('fixture exceeds decoded size cap');
        chunks.push(piece.value);
        total += piece.value.byteLength;
      }
    } finally {
      if (!done) { try { await reader.cancel(); } catch (_) { /* original error wins */ } }
      reader.releaseLock();
    }
    if ((!encoding || encoding === 'identity') && headerLength !== null && headerLength !== total)
      throw Error('incomplete or mismatched Content-Length');
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return bytes;
  }
  function link() {
    const url = new URL(location.pathname, location.href);
    const q = new URLSearchParams({...expected(), sha:EXPECTED_SHA});
    if ($('edition').value !== 'all') q.set('edition', $('edition').value);
    if ($('subject').value !== 'all') q.set('subject', $('subject').value);
    if ($('search').value.trim()) q.set('query', $('search').value.trim());
    if (chosen) q.set('page', chosen);
    url.search = q.toString();
    return url.href;
  }
  function updateShare() {
    if (!panel || incompatible) return;
    ++shareEpoch; // A filter, selection or restored history invalidates pending clipboard feedback.
    const url = link();
    $('share-url').value = url;
    $('share-notice').textContent = 'Local-only share; panel and version are fixed to this synthetic build.';
    history.replaceState(null, '', url);
  }
  function fact(title, value) {
    const div = text('div', '', 'fact');
    div.append(text('span', title, 'label'), text('strong', value));
    return div;
  }
  function listRows(title, rows) {
    $('detail-body').append(text('h3', title));
    const list = text('ul', '', 'events');
    if (!rows.length) list.append(text('li', 'No events observed in this illustrative fixture.'));
    rows.forEach(row => list.append(text('li', row)));
    $('detail-body').append(list);
  }
  function show(page, focus = false) {
    chosen = key(page);
    $('details-title').textContent = label(page);
    $('details-title').setAttribute('lang', pageLanguage(page));
    $('detail-help').textContent = `${page.page_ref.project} · stable page ID ${page.page_ref.page_id}. All fields are synthetic.`;
    const b = $('detail-body');
    clear(b);
    const grid = text('div', '', 'detail-identity');
    grid.append(
      fact('Local identity', chosen),
      fact('Dayflare topic ID', page.topic_id),
      fact('Continuity', page.continuity),
      fact('Topic relationship', page.relation),
      fact('Wikidata status', page.wikidata.state),
      fact('Observed QID', page.wikidata.observed_qid || 'unknown')
    );
    b.append(grid);
    listRows('Title observations', page.titles.map(t => `${t.date} · ${t.title} (fictional)`));
    listRows('Continuity events', page.events.map(e => `${e.date} · ${e.kind}${e.kind === 'move' ? `: ${e.old_title} → ${e.new_title}` : ''}`));
    listRows('Redirect edge', page.redirect_to ? [`${page.redirect_to.observed_at} · ${key({page_ref:page.redirect_to.target_ref})} (separate identity)`] : []);
    b.append(text('p','These fixture URLs, titles and QIDs are not verified upstream evidence. Missing mapping ≠ absence of interest. No pageview or trend values are asserted.','caution'));
    render(false);
    if (focus) $('details').focus({preventScroll: false});
  }
  function filtered() {
    const edition = $('edition').value, subject = $('subject').value, query = $('search').value.trim().toLowerCase();
    return panel.pages.filter(p => (edition === 'all' || p.page_ref.project === edition) &&
      (subject === 'all' || p.subject === subject) &&
      (!query || `${label(p)} ${p.topic_id} ${key(p)}`.toLowerCase().includes(query)));
  }
  function render(sync = true) {
    if (!panel || incompatible) return;
    const rows = filtered();
    const list = $('list');
    clear(list);
    rows.forEach(p => {
      const card = text('button', '', 'card');
      card.type='button'; card.setAttribute('aria-pressed',String(key(p)===chosen));
      const line=text('span','','idline');
      line.append(text('span',p.subject.toUpperCase(),'tag'),text('code',key(p)));
      const title=text('strong',label(p));
      title.setAttribute('lang',pageLanguage(p));
      card.append(line,title,text('span',`${p.page_ref.project} · ${p.continuity} continuity · Wikidata ${p.wikidata.state}`,'sub'));
      card.addEventListener('click',()=>{show(p,true);updateShare();});
      list.append(card);
    });
    $('empty').hidden=rows.length!==0;
    status(`${rows.length} of ${panel.coverage.obtained_count} fictional identities shown. No pageviews measured.`);
    if (sync) updateShare();
  }
  function renderCoverage(coverage) {
    const root = $('coverage-breakdown');
    clear(root);
    const subjects = ['culture','books','games','science','sport','other'];
    const names = {'en.wikipedia':'English Wikipedia','ru.wikipedia':'Russian Wikipedia'};
    for (const edition of ['en.wikipedia','ru.wikipedia']) {
      const card = text('article', '', 'coverage-edition');
      const title = text('h3', names[edition]);
      const grid = text('dl', '', 'coverage-grid');
      const counts = coverage.observed_panel_counts_by_edition_subject[edition] || {};
      for (const subject of subjects) {
        const pair = text('div', '', 'coverage-cell');
        const count = counts[subject] || 0;
        pair.append(text('dt', subject), text('dd', count ? `${count} observed in fixture` : 'Not included'));
        grid.append(pair);
      }
      card.append(title, grid);
      root.append(card);
    }
  }
  function clearSelection() {
    chosen = null;
    $('details-title').textContent = 'Choose a page';
    $('details-title').setAttribute('lang','en');
    $('detail-help').textContent = 'Select a fictional identity to inspect its dated trace.';
    clear($('detail-body'));
  }
  function incompatibleView() {
    ++shareEpoch;
    incompatible=true;
    chosen=null;
    $('empty').hidden=true;
    $('compat').hidden=false;
    // Put the recovery action at the discovery point, not below the entire page.
    $('reset').focus();
    setControls(false);
    $('share-url').value='';
    $('share-notice').textContent='Sharing unavailable for an incompatible view.';
    clear($('list')); clear($('detail-body'));
    $('details-title').textContent='Unavailable requested view';
    $('details-title').setAttribute('lang','en');
    $('detail-help').textContent='The panel or page identifier does not match this fixture.';
    status('Incompatible shared view — no fallback identity substituted.',true);
  }
  function restore() {
    if (!panel) return;
    // A restored URL is the entire source of view state. Never retain a prior
    // selected identity or disabled controls after browser history navigation.
    incompatible = false;
    $('compat').hidden = true;
    setControls(true);
    clearSelection();
    const p=params();
    // Any parameterized share must bind to a complete, unambiguous dataset version.
    // A bare page ID is not safe to restore into a newer fixture with the same key.
    const allowed = new Set(['schema','panel','sha','edition','subject','query','page']);
    if (Array.from(p.keys()).some(name => !allowed.has(name) || p.getAll(name).length !== 1) ||
        (p.size && ['schema','panel','sha'].some(name => !p.has(name))) ||
        (p.size && (p.get('schema') !== SCHEMA || p.get('panel') !== PANEL_ID || p.get('sha') !== EXPECTED_SHA)))
      return incompatibleView();
    const edition = p.get('edition') || 'all', subject = p.get('subject') || 'all';
    if (!['all','en.wikipedia','ru.wikipedia'].includes(edition) ||
        !['all','culture','books','games','science','sport','other'].includes(subject)) return incompatibleView();
    $('edition').value=edition;
    $('subject').value=subject;
    const query=p.get('query') || '';
    if (query.length > 120) return incompatibleView();
    $('search').value=query;
    if (p.has('page')) {
      const page=panel.pages.find(item => key(item)===p.get('page'));
      // The selected page must remain discoverable under every restored filter,
      // including text search; never display a hidden selected identity.
      if (!page || !filtered().some(item => key(item) === key(page))) return incompatibleView();
      chosen=key(page);
      show(page);
    }
    render();
  }
  async function load() {
    // If the local server stalls before or during streaming, expose a retry
    // rather than leaving discovery disabled under an infinite loading state.
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(new Error('fixture request timed out')),
      FIXTURE_LOAD_TIMEOUT_MS);
    ++shareEpoch;
    setControls(false);
    status('Checking local synthetic fixture integrity…');
    $('retry').hidden=true;
    try {
      const res=await fetch('panel.json',{cache:'no-store',signal:controller.signal});
      if (res.status !== 200) throw Error(`fixture HTTP ${res.status}`);
      const raw=await readBoundedFixture(res);
      if (await sha256(raw)!==EXPECTED_SHA) throw Error('dataset SHA-256 mismatch');
      const doc=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
      if (doc.schema_version!==SCHEMA || doc.panel_id!==PANEL_ID ||
          doc.selection?.evidence_kind!=='synthetic' || doc.coverage?.provenance_verification!=='synthetic_only' ||
          !Array.isArray(doc.pages) || doc.pages.some(p=>!p.page_ref || !Array.isArray(p.titles) || !p.titles.length))
        throw Error('unsupported fixture schema or evidence kind');
      panel=doc;
      renderCoverage(doc.coverage);
      $('count').textContent=doc.coverage.obtained_count;
      $('intended').textContent=doc.coverage.intended_count;
      $('unresolved').textContent=doc.coverage.unresolved_count;
      setControls(true);
      restore();
      if (!incompatible) $('share-notice').textContent='Local-only share; panel and version are fixed to this synthetic build.';
    } catch (error) {
      panel=null;chosen=null;
      clear($('coverage-breakdown'));
      $('coverage-breakdown').append(text('p','Coverage unavailable until the fixture passes integrity checks.'));
      for (const id of ['count','intended','unresolved']) $(id).textContent='—';
      $('details-title').textContent='Evidence unavailable';
      $('details-title').setAttribute('lang','en');
      $('detail-help').textContent='No identity is available until this local fixture passes validation.';
      clear($('detail-body'));
      ++shareEpoch;
      $('share-url').value='';
      $('share-notice').textContent='Sharing unavailable until the fixture is validated.';
      setControls(false);
      status(`Fixture unavailable: ${error.message}. Previous identity counts are not treated as zero.`,true);
      $('retry').hidden=false;
      clear($('list'));
      $('empty').hidden=true;
    } finally {
      clearTimeout(deadline);
    }
  }
  ids.forEach(id=>$(id).addEventListener(id==='search'?'input':'change',()=>{
    if (incompatible || !panel) return;
    clearSelection();
    render();
  }));
  $('retry').addEventListener('click',load);
  $('reset').addEventListener('click',()=>{
    incompatible=false;$('compat').hidden=true;
    history.replaceState(null,'',location.pathname);
    if (panel) {ids.forEach(id=>$(id).value=id==='search'?'':'all');setControls(true);restore();}
    else load();
  });
  $('copy').addEventListener('click',async()=>{
    const value=$('share-url').value;
    if (!panel || incompatible || !value) return;
    const epoch=++shareEpoch; // The latest copy attempt alone may update this view.
    $('share-notice').textContent='Copying this synthetic local view…';
    const current=()=>epoch===shareEpoch && panel && !incompatible && $('share-url').value===value;
    try {
      await navigator.clipboard.writeText(value);
      if (current()) $('share-notice').textContent='Copied this synthetic local view.';
    } catch (_) {
      if (!current()) return;
      $('share-url').focus();$('share-url').select();
      $('share-notice').textContent='Copy is unavailable; select and copy the highlighted URL.';
    }
  });
  window.addEventListener('popstate',()=>{if (panel) restore();});
  load();
})();

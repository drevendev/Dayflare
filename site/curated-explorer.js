/* Optional controls for the 20 measured, archived title histories. No network calls. */
(function (root) {
  'use strict';
  const DATASET = 'm1-curated-20261023-d96477427ece';
  const EDITIONS = new Set(['all', 'en.wikipedia', 'ru.wikipedia']);
  const SUBJECTS = new Set(['all', 'culture', 'books', 'games', 'science', 'sport']);
  const KEYS = new Set(['ds', 'q', 'edition', 'subject']);
  function normalize(value) {
    return String(value == null ? '' : value).normalize('NFKC').toLocaleLowerCase().trim();
  }
  function parseState(search) {
    const params = new URLSearchParams(search);
    const invalid = [...params.keys()].some(key => !KEYS.has(key) || params.getAll(key).length !== 1);
    const query = params.get('q') || '';
    const edition = params.get('edition') || 'all';
    const subject = params.get('subject') || 'all';
    return {
      compatible: !invalid && (!params.has('ds') || params.get('ds') === DATASET) &&
        EDITIONS.has(edition) && SUBJECTS.has(subject) && query.length <= 80 &&
        !/[\u0000-\u001f\u007f]/.test(query),
      query, edition, subject
    };
  }
  function makeShareURL(href, state) {
    const url = new URL(href);
    url.search = '';
    url.hash = '#discover';
    url.searchParams.set('ds', DATASET);
    const query = String(state.query || '').slice(0, 80).trim();
    if (query) url.searchParams.set('q', query);
    if (EDITIONS.has(state.edition) && state.edition !== 'all')
      url.searchParams.set('edition', state.edition);
    if (SUBJECTS.has(state.subject) && state.subject !== 'all')
      url.searchParams.set('subject', state.subject);
    return url.href;
  }
  function matches(row, query, edition, subject) {
    return (edition === 'all' || row.edition === edition) &&
      (subject === 'all' || row.subject === subject) &&
      normalize(query).split(/\s+/).filter(Boolean).every(term => row.search.includes(term));
  }
  if (typeof module === 'object' && module.exports)
    module.exports = {DATASET, normalize, parseState, makeShareURL, matches};
  if (typeof document === 'undefined') return;

  function start() {
    const controls = document.querySelector('[data-curated-explorer]');
    const dataset = document.querySelector('meta[name="dayflare-dataset"]');
    if (!controls || !dataset || dataset.content !== DATASET) return;
    const cards = [...document.querySelectorAll('article.topic[data-project]')];
    const areas = [...document.querySelectorAll('section.area[id^="subject-"]')];
    const links = [...document.querySelectorAll('.pill-links a[href^="#subject-"]')];
    if (cards.length !== 20 || areas.length !== 5) return; // readable no-JS fallback
    const query = controls.querySelector('#curated-query');
    const edition = controls.querySelector('#curated-edition');
    const subject = controls.querySelector('#curated-subject');
    const count = controls.querySelector('#curated-count');
    const empty = controls.querySelector('#curated-empty');
    const reset = controls.querySelector('#curated-reset');
    const share = controls.querySelector('#curated-share');
    const shareStatus = controls.querySelector('#curated-share-status');
    const fallback = controls.querySelector('#curated-share-fallback');
    const shareInput = controls.querySelector('#curated-share-url');
    const incompatible = document.querySelector('#curated-incompatible');
    const canonical = document.querySelector('#curated-canonical');
    if ([query, edition, subject, count, empty, reset, share, shareStatus,
         fallback, shareInput, incompatible, canonical].some(x => !x)) return;
    const rows = cards.map(card => {
      const area = card.closest('section.area');
      const title = card.querySelector('h3');
      return {card, area, edition: card.dataset.project,
        subject: area ? area.id.slice(8) : '',
        search: normalize([title && title.textContent, card.dataset.project,
          card.dataset.observedPageId].join(' '))};
    });
    if (rows.some(x => !x.area || !x.search || !EDITIONS.has(x.edition) ||
                      !SUBJECTS.has(x.subject))) return;
    let shareEpoch = 0;
    function invalidate() {
      shareEpoch++;
      shareStatus.textContent = '';
      fallback.hidden = true;
      shareInput.value = '';
    }
    function current() {
      return {query: query.value.slice(0, 80), edition: edition.value, subject: subject.value};
    }
    function render(writeURL) {
      invalidate();
      const state = current();
      if (state.query !== query.value) query.value = state.query;
      let shown = 0;
      for (const row of rows) {
        const visible = matches(row, state.query, state.edition, state.subject);
        row.card.hidden = !visible;
        if (visible) shown++;
      }
      for (const area of areas)
        area.hidden = !rows.some(row => row.area === area && !row.card.hidden);
      for (const link of links) {
        const area = document.getElementById(link.getAttribute('href').slice(1));
        link.hidden = Boolean(area && area.hidden);
      }
      count.textContent = shown + ' of 20 selected measured title histories shown (19 Sep–23 Oct 2026).';
      empty.hidden = shown !== 0;
      if (writeURL) {
        try { root.history.replaceState(null, '', makeShareURL(root.location.href, state)); }
        catch (_) { /* file previews may not support History API */ }
      }
    }
    function restore() {
      const state = parseState(root.location.search);
      const url = new URL(root.location.href);
      url.search = '';
      url.hash = '';
      canonical.href = url.href;
      if (!state.compatible) {
        invalidate();
        controls.hidden = true;
        incompatible.hidden = false;
        cards.forEach(card => { card.hidden = false; });
        areas.forEach(area => { area.hidden = false; });
        links.forEach(link => { link.hidden = false; });
        return; // Never reinterpret an unknown dataset or filter.
      }
      incompatible.hidden = true;
      query.value = state.query;
      edition.value = state.edition;
      subject.value = state.subject;
      render(false);
      controls.hidden = false;
    }
    query.addEventListener('input', () => render(true));
    edition.addEventListener('change', () => render(true));
    subject.addEventListener('change', () => render(true));
    reset.addEventListener('click', () => {
      query.value = ''; edition.value = 'all'; subject.value = 'all';
      render(true); query.focus();
    });
    share.addEventListener('click', async () => {
      const epoch = ++shareEpoch;
      const link = makeShareURL(root.location.href, current());
      shareStatus.textContent = '';
      fallback.hidden = true;
      const target = new URL(link);
      const preview = target.protocol !== 'https:' ||
        ['localhost', '127.0.0.1', '[::1]'].includes(target.hostname);
      try {
        if (preview || !root.navigator || !root.navigator.clipboard ||
            typeof root.navigator.clipboard.writeText !== 'function') throw Error('clipboard unavailable');
        await root.navigator.clipboard.writeText(link);
        if (epoch === shareEpoch) shareStatus.textContent = 'Dated measured-history link copied.';
      } catch (_) {
        if (epoch !== shareEpoch) return;
        shareInput.value = link;
        fallback.hidden = false;
        shareStatus.textContent = preview ?
          'Local preview only: this URL is not a public website.' :
          'Clipboard unavailable. Select and copy the dated link below.';
        shareInput.focus();
        shareInput.select();
      }
    });
    root.addEventListener('popstate', restore);
    restore();
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})(typeof window !== 'undefined' ? window : globalThis);

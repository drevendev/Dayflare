/* Progressive, locally filtered explorer for the dated 20-ID Wikipedia snapshot. */
(function (root) {
  'use strict';
  const EDITIONS = new Set(['all', 'en', 'ru']);
  function normalize(value) {
    return String(value ?? '').normalize('NFKC').toLocaleLowerCase().trim();
  }
  function parseState(search) {
    const params = new URLSearchParams(search);
    const edition = params.get('edition') || 'all';
    return {
      query: (params.get('q') || '').slice(0, 96),
      edition: EDITIONS.has(edition) ? edition : 'all'
    };
  }
  function makeShareURL(href, state) {
    // Retain the dated snapshot path; never propagate unrecognized query keys.
    const url = new URL(href);
    const query = String(state.query ?? '').slice(0, 96);
    const edition = EDITIONS.has(state.edition) ? state.edition : 'all';
    url.search = '';
    url.hash = '#subjects';
    if (query.trim()) url.searchParams.set('q', query);
    if (edition !== 'all') url.searchParams.set('edition', edition);
    return url.href;
  }
  function matches(row, query, edition) {
    if (edition !== 'all' && row.edition !== edition) return false;
    return normalize(query).split(/\s+/).filter(Boolean)
      .every(term => row.search.includes(term));
  }
  if (typeof module === 'object' && module.exports) {
    module.exports = {normalize, parseState, matches, makeShareURL};
  }
  if (typeof document === 'undefined') return;

  function start() {
    const controls = document.querySelector('[data-identity-explorer]');
    if (!controls) return;
    const cards = Array.from(document.querySelectorAll('article.card[data-page-ref]'));
    // Without the expected complete snapshot, preserve the readable no-JS page.
    if (cards.length !== 20) return;
    const input = controls.querySelector('#identity-query');
    const counter = controls.querySelector('#identity-result-count');
    const empty = controls.querySelector('#identity-no-results');
    const reset = controls.querySelector('#identity-reset');
    const share = controls.querySelector('#identity-share');
    const shareStatus = controls.querySelector('#identity-share-status');
    const shareFallback = controls.querySelector('#identity-share-fallback');
    const shareInput = controls.querySelector('#identity-share-url');
    const radios = Array.from(controls.querySelectorAll('input[name="identity-edition"]'));
    if (!input || !counter || !empty || !reset || !share || !shareStatus ||
        !shareFallback || !shareInput || radios.length !== 3) return;
    const groups = Array.from(document.querySelectorAll('.category .group'));
    const categories = Array.from(document.querySelectorAll('.category'));
    const navLinks = Array.from(document.querySelectorAll('.nav a[href^="#"]'));
    const rows = cards.map(card => {
      const ref = card.getAttribute('data-page-ref') || '';
      const qidLink = card.querySelector('a[href^="https://www.wikidata.org/wiki/Q"]');
      const qid = qidLink ? qidLink.getAttribute('href').split('/').pop() : '';
      const title = card.querySelector('h3');
      return {
        card,
        edition: ref.startsWith('en.wikipedia:') ? 'en' : 'ru',
        search: normalize([title ? title.textContent : '', ref, qid].join(' '))
      };
    });
    if (rows.some(row => !row.search || !row.card.closest('.category'))) return;
    let shareEpoch = 0;
    function invalidateShare() {
      shareEpoch += 1;
      shareStatus.textContent = '';
      shareInput.value = '';
      shareFallback.hidden = true;
    }
    function currentState() {
      return {query: input.value, edition: (radios.find(radio => radio.checked) || radios[0]).value};
    }

    function render(writeURL) {
      invalidateShare();
      const edition = (radios.find(radio => radio.checked) || radios[0]).value;
      const query = input.value.slice(0, 96);
      if (input.value !== query) input.value = query;
      let shown = 0;
      for (const row of rows) {
        const show = matches(row, query, edition);
        row.card.hidden = !show;
        if (show) shown += 1;
      }
      for (const group of groups) {
        group.hidden = !Array.from(group.querySelectorAll('article.card[data-page-ref]'))
          .some(card => !card.hidden);
      }
      for (const category of categories) {
        category.hidden = !Array.from(category.querySelectorAll('.group'))
          .some(group => !group.hidden);
      }
      for (const link of navLinks) {
        const target = document.getElementById(link.hash.slice(1));
        link.hidden = Boolean(target && target.hidden);
      }
      counter.textContent = shown + ' of ' + rows.length + ' observed page IDs shown (24 Oct 2026).';
      empty.hidden = shown !== 0;
      if (writeURL) {
        const url = new URL(root.location.href);
        if (query.trim()) url.searchParams.set('q', query);
        else url.searchParams.delete('q');
        if (edition === 'all') url.searchParams.delete('edition');
        else url.searchParams.set('edition', edition);
        // Unavailable History API must not break local filtering.
        try { root.history.replaceState(null, '', url); } catch (_) { /* local-only fallback */ }
      }
    }
    function restore() {
      const state = parseState(root.location.search);
      input.value = state.query;
      radios.forEach(radio => { radio.checked = radio.value === state.edition; });
      render(false);
    }
    input.addEventListener('input', () => render(true));
    radios.forEach(radio => radio.addEventListener('change', () => render(true)));
    reset.addEventListener('click', () => {
      input.value = '';
      radios.forEach(radio => { radio.checked = radio.value === 'all'; });
      render(true);
      input.focus();
    });
    share.addEventListener('click', async () => {
      const epoch = ++shareEpoch;
      const link = makeShareURL(root.location.href, currentState());
      shareStatus.textContent = '';
      shareFallback.hidden = true;
      const previewOnly = new URL(link).protocol !== 'https:';
      try {
        if (previewOnly || !root.navigator || !root.navigator.clipboard ||
            typeof root.navigator.clipboard.writeText !== 'function') {
          throw new Error('clipboard not available for this preview');
        }
        await root.navigator.clipboard.writeText(link);
        if (epoch === shareEpoch) shareStatus.textContent = 'Dated snapshot link copied.';
      } catch (_) {
        if (epoch !== shareEpoch) return; // Search changed during an async clipboard attempt.
        shareInput.value = link;
        shareFallback.hidden = false;
        shareStatus.textContent = previewOnly ?
          'Local preview: this URL is not a public website. Copy it only for local testing.' :
          'Clipboard unavailable. Select and copy the dated snapshot link below.';
        shareInput.focus();
        shareInput.select();
      }
    });
    root.addEventListener('popstate', restore);
    restore();
    controls.hidden = false;
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})(typeof window !== 'undefined' ? window : globalThis);

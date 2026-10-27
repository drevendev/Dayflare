/* Optional controls for the 20 measured, archived title histories. No network calls. */
(function (root) {
  'use strict';
  const DATASET = 'm1-curated-20261023-d96477427ece';
  const EDITIONS = new Set(['all', 'en.wikipedia', 'ru.wikipedia']);
  const SUBJECTS = new Set(['all', 'culture', 'books', 'games', 'science', 'sport']);
  const KEYS = new Set(['ds', 'q', 'edition', 'subject', 'a', 'b']);
  const TOPIC_ID = /^topic-(en|ru)-[1-9][0-9]*$/;
  function normalize(value) {
    return String(value == null ? '' : value).normalize('NFKC').toLocaleLowerCase().trim();
  }
  function parseState(search) {
    const params = new URLSearchParams(search);
    const invalid = [...params.keys()].some(key => !KEYS.has(key) || params.getAll(key).length !== 1);
    const query = params.get('q') || '';
    const edition = params.get('edition') || 'all';
    const subject = params.get('subject') || 'all';
    const compareA = params.get('a') || '';
    const compareB = params.get('b') || '';
    const pairValid = (!compareA && !compareB) ||
      (TOPIC_ID.test(compareA) && TOPIC_ID.test(compareB) && compareA !== compareB &&
       compareA.length <= 32 && compareB.length <= 32);
    return {
      compatible: !invalid && (!params.has('ds') || params.get('ds') === DATASET) &&
        EDITIONS.has(edition) && SUBJECTS.has(subject) && pairValid && query.length <= 80 &&
        !/[\u0000-\u001f\u007f]/.test(query),
      query, edition, subject, compareA, compareB
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
    if (TOPIC_ID.test(state.compareA || '') && TOPIC_ID.test(state.compareB || '') &&
        state.compareA !== state.compareB) {
      url.searchParams.set('a', state.compareA);
      url.searchParams.set('b', state.compareB);
    }
    return url.href;
  }
  function matches(row, query, edition, subject) {
    return (edition === 'all' || row.edition === edition) &&
      (subject === 'all' || row.subject === subject) &&
      normalize(query).split(/\s+/).filter(Boolean).every(term => row.search.includes(term));
  }
  // Only complete, identical, consecutive UTC days permit comparison.
  function compareRows(left, right) {
    if (!Array.isArray(left) || !Array.isArray(right) ||
        left.length !== 35 || right.length !== 35) return null;
    const dates = [], a = [], b = [];
    let previous = null;
    for (let i = 0; i < 35; i++) {
      const x = left[i], y = right[i];
      if (!Array.isArray(x) || !Array.isArray(y) || x.length !== 2 || y.length !== 2 ||
          x[0] !== y[0] || typeof x[0] !== 'string' ||
          !/^\d{4}-\d{2}-\d{2}$/.test(x[0]) ||
          !Number.isSafeInteger(x[1]) || !Number.isSafeInteger(y[1]) ||
          x[1] < 0 || y[1] < 0) return null;
      const at = Date.parse(x[0] + 'T00:00:00Z');
      if (!Number.isFinite(at) || new Date(at).toISOString().slice(0, 10) !== x[0] ||
          (previous !== null && at - previous !== 86400000)) return null;
      dates.push(x[0]); a.push(x[1]); b.push(y[1]); previous = at;
    }
    const sumWeek = values => Array.from({length: 5}, (_, i) =>
      values.slice(i * 7, (i + 1) * 7).reduce((sum, value) => sum + value, 0));
    return {dates, left: a, right: b, weeksLeft: sumWeek(a), weeksRight: sumWeek(b)};
  }
  if (typeof module === 'object' && module.exports)
    module.exports = {DATASET, normalize, parseState, makeShareURL, matches, compareRows};
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
    // Optional comparison is derived only from the exact values already in source HTML.
    const compareArea = document.createElement('section');
    compareArea.id = 'curated-compare';
    compareArea.className = 'curated-compare';
    compareArea.setAttribute('aria-labelledby', 'curated-compare-heading');
    compareArea.innerHTML =
      '<h2 id="curated-compare-heading">Compare two measured histories</h2>' +
      '<p>Choose two of the 20 selected titles. Both cover the same 35 complete UTC days ' +
      '(19 Sep–23 Oct 2026). These are all-access/user-filtered page requests; ' +
      'different editions are not comparable populations, and shared titles/subjects ' +
      'do not prove entity equivalence. Archived title histories, not live interest.</p>' +
      '<div class="curated-compare-fields">' +
      '<label for="curated-compare-a">First measured title<select id="curated-compare-a">' +
      '<option value="">Choose first history</option></select></label>' +
      '<label for="curated-compare-b">Second measured title<select id="curated-compare-b">' +
      '<option value="">Choose second history</option></select></label></div>' +
      '<p id="curated-compare-status" role="status" aria-live="polite">Choose two different titles to see exact values.</p>' +
      '<div id="curated-compare-results" hidden>' +
      '<p>Weekly totals are raw page requests to separate titles, not people or national ' +
      'popularity. Original source links and all 700 daily values remain in the cards.</p>' +
      '<div class="curated-compare-scroll"><table id="curated-compare-weeks">' +
      '<caption>Five equivalent seven-day totals (UTC)</caption><thead><tr>' +
      '<th scope="col">UTC week</th><th scope="col">First title</th>' +
      '<th scope="col">Second title</th></tr></thead><tbody></tbody></table></div>' +
      '<details><summary>Show all 35 exact daily pairs</summary>' +
      '<div class="curated-compare-scroll"><table id="curated-compare-days">' +
      '<caption>Exact daily page requests from the original measured cards</caption>' +
      '<thead><tr><th scope="col">UTC date</th><th scope="col">First title</th>' +
      '<th scope="col">Second title</th></tr></thead><tbody></tbody></table></div>' +
      '</details></div>';
    controls.after(compareArea);
    const compareA = compareArea.querySelector('#curated-compare-a');
    const compareB = compareArea.querySelector('#curated-compare-b');
    const compareStatus = compareArea.querySelector('#curated-compare-status');
    const compareResults = compareArea.querySelector('#curated-compare-results');
    const weekBody = compareArea.querySelector('#curated-compare-weeks tbody');
    const dayBody = compareArea.querySelector('#curated-compare-days tbody');
    const cardById = new Map(cards.map(card => [card.id, card]));
    const num = new Intl.NumberFormat('en-US');
    for (const card of cards) {
      const title = card.querySelector('h3');
      for (const select of [compareA, compareB]) {
        const option = document.createElement('option');
        option.value = card.id;
        option.textContent = (title ? title.textContent : card.id) + ' · ' +
          card.dataset.project + ' · observed ID ' + card.dataset.observedPageId;
        select.append(option);
      }
    }
    let shareEpoch = 0;
    function invalidate() {
      shareEpoch++;
      shareStatus.textContent = '';
      fallback.hidden = true;
      shareInput.value = '';
    }
    function current() {
      return {query: query.value.slice(0, 80), edition: edition.value, subject: subject.value,
        compareA: compareA.value, compareB: compareB.value};
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
    function readDaily(card) {
      return [...card.querySelectorAll('.history tbody tr')].map(line => {
        const date = line.querySelector('th'), value = line.querySelector('td');
        const raw = value ? value.textContent.replace(/,/g, '').trim() : '';
        return [date ? date.textContent.trim() : '', /^\d+$/.test(raw) ? Number(raw) : NaN];
      });
    }
    function addRow(body, values) {
      const tr = document.createElement('tr');
      values.forEach((value, i) => {
        const cell = document.createElement(i === 0 ? 'th' : 'td');
        if (i === 0) cell.scope = 'row';
        cell.textContent = String(value);
        tr.append(cell);
      });
      body.append(tr);
    }
    function renderComparison(writeURL) {
      invalidate();
      compareResults.hidden = true;
      weekBody.replaceChildren();
      dayBody.replaceChildren();
      const a = compareA.value, b = compareB.value;
      if (!a || !b) {
        compareStatus.textContent = 'Choose two different titles to see exact values.';
      } else if (a === b) {
        compareStatus.textContent = 'Choose two different histories; a title cannot compare with itself.';
      } else {
        const leftCard = cardById.get(a), rightCard = cardById.get(b);
        const result = leftCard && rightCard && compareRows(readDaily(leftCard), readDaily(rightCard));
        if (!result) {
          compareStatus.textContent = 'Comparison unavailable: incomplete or incompatible daily windows.';
        } else {
          const first = leftCard.querySelector('h3').textContent;
          const second = rightCard.querySelector('h3').textContent;
          compareStatus.textContent = 'Exact 35-day comparison: ' + first + ' (' +
            leftCard.dataset.project + ') and ' + second + ' (' +
            rightCard.dataset.project + ').';
          for (const table of [compareArea.querySelector('#curated-compare-weeks'),
                               compareArea.querySelector('#curated-compare-days')]) {
            const headings = table.querySelectorAll('thead th');
            headings[1].textContent = first + ' · ' + leftCard.dataset.project;
            headings[2].textContent = second + ' · ' + rightCard.dataset.project;
          }
          for (let i = 0; i < 5; i++)
            addRow(weekBody, [result.dates[i * 7] + '–' + result.dates[i * 7 + 6],
              num.format(result.weeksLeft[i]), num.format(result.weeksRight[i])]);
          for (let i = 0; i < 35; i++)
            addRow(dayBody, [result.dates[i], num.format(result.left[i]), num.format(result.right[i])]);
          compareResults.hidden = false;
        }
      }
      if (writeURL) {
        try { root.history.replaceState(null, '', makeShareURL(root.location.href, current())); }
        catch (_) { /* file previews may not support History API */ }
      }
    }
    function restore() {
      const state = parseState(root.location.search);
      const url = new URL(root.location.href);
      url.search = '';
      url.hash = '';
      canonical.href = url.href;
      if (!state.compatible ||
          (state.compareA && (!cardById.has(state.compareA) || !cardById.has(state.compareB)))) {
        invalidate();
        controls.hidden = true;
        compareArea.hidden = true;
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
      compareA.value = state.compareA;
      compareB.value = state.compareB;
      render(false);
      renderComparison(false);
      controls.hidden = false;
      compareArea.hidden = false;
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
    compareA.addEventListener('change', () => renderComparison(true));
    compareB.addEventListener('change', () => renderComparison(true));
    root.addEventListener('popstate', restore);
    restore();
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})(typeof window !== 'undefined' ? window : globalThis);

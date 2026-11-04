'use strict';
const assert = require('node:assert/strict');
const {normalize, parseState, matches, isVisible, makeFilterURL, makeShareURL} = require('../site/identity-explorer.js');
const en = {edition: 'en', ref: 'en.wikipedia:5134', pageId: '5134',
  qid: 'q718', search: normalize('Chess en.wikipedia:5134 Q718')};
const ru = {edition: 'ru', ref: 'ru.wikipedia:10646', pageId: '10646',
  qid: 'q718', search: normalize('Шахматы ru.wikipedia:10646 Q718')};
const prefixCollision = {edition: 'en', ref: 'en.wikipedia:51345', pageId: '51345',
  qid: 'q7180', search: normalize('Chess variants en.wikipedia:51345 Q7180')};
assert.equal(normalize('  ШАХМАТЫ  '), 'шахматы');
assert.equal(matches(en, 'cHeSs', 'all'), true);
assert.equal(matches(en, 'EN.WIKIPEDIA:5134', 'en'), true);
assert.equal(matches(en, 'Q718 chess', 'en'), true);
assert.equal(matches(en, 'chess', 'ru'), false);
assert.equal(matches(ru, 'шахматы', 'ru'), true);
assert.equal(matches(ru, 'Q718', 'ru'), true);
assert.equal(matches(ru, 'Q718', 'en'), false);
assert.equal(matches(ru, 'football', 'ru'), false);
// Identifier queries are exact within their namespace, not substring matches.
assert.equal(matches(en, '5134', 'en'), true);
assert.equal(matches(en, 'en.wikipedia:5134', 'en'), true);
assert.equal(matches(en, 'ru.wikipedia:5134', 'en'), false);
assert.equal(matches(en, 'Q718 Chess', 'en'), true);
assert.equal(matches(en, 'Q71', 'en'), false);
assert.equal(matches(en, '513', 'en'), false);
assert.equal(matches(prefixCollision, '5134', 'en'), false);
assert.equal(matches(prefixCollision, 'en.wikipedia:5134', 'en'), false);
assert.equal(matches(prefixCollision, 'Q718', 'en'), false);
assert.equal(matches(prefixCollision, '51345 Q7180', 'en'), true);
assert.equal(matches(prefixCollision, 'chess variants', 'en'), true);
assert.equal(matches(ru, '5134', 'ru'), false);
assert.deepEqual(parseState('?q=%D0%A8%D0%B0%D1%85%D0%BC%D0%B0%D1%82%D1%8B&edition=ru'),
                 {query: 'Шахматы', edition: 'ru'});
// An invalid shared filter must not silently substitute the complete panel.
for (const query of ['?edition=fr', '?edition=', '?edition=ru&edition=en',
                     '?q=Chess&q=Football', '?q=' + 'x'.repeat(200)]) {
  const invalid = parseState(query);
  assert.deepEqual(invalid, {query: '', edition: 'all', invalid: true});
  assert.equal(isVisible(en, invalid), false);
  assert.equal(isVisible(ru, invalid), false);
}
assert.deepEqual(parseState('?edition=ru&q=' + 'x'.repeat(96)),
                 {query: 'x'.repeat(96), edition: 'ru'});
assert.equal(isVisible(en, parseState('?edition=en&q=Chess')), true);
assert.equal(isVisible(ru, parseState('?edition=en&q=Chess')), false);
const filtered = makeShareURL('https://drevendev.github.io/Dayflare/identities-m1-20261024.html?noise=1#obsolete',
  {query: 'Шахматы', edition: 'ru'});
const parsed = new URL(filtered);
assert.equal(parsed.pathname, '/Dayflare/identities-m1-20261024.html');
assert.equal(parsed.hash, '#subjects');
assert.deepEqual([...parsed.searchParams.entries()], [['q', 'Шахматы'], ['edition', 'ru']]);
assert.equal(makeShareURL('https://example.org/identities-m1-20261024.html?edition=fr&tracking=1',
  {query: '', edition: 'fr'}), 'https://example.org/identities-m1-20261024.html#subjects');
const limited = new URL(makeShareURL('https://example.org/snapshot.html',
  {query: 'x'.repeat(300), edition: 'en'}));
assert.equal(limited.searchParams.get('q').length, 96);
assert.equal(limited.searchParams.get('edition'), 'en');
assert.equal(limited.searchParams.has('tracking'), false);
// Filtered address-bar and copied Share URLs must be identical.
const stale = 'https://drevendev.github.io/Dayflare/identities-m1-20261024.html?noise=1&q=old&edition=en#culture';
const current = {query: 'Шахматы', edition: 'ru'};
const filterUrl = makeFilterURL(stale, current);
assert.equal(filterUrl, makeShareURL(stale, current));
assert.equal(new URL(filterUrl).pathname, '/Dayflare/identities-m1-20261024.html');
assert.equal(new URL(filterUrl).hash, '#subjects');
assert.deepEqual([...new URL(filterUrl).searchParams.entries()],
                 [['q', 'Шахматы'], ['edition', 'ru']]);
assert.deepEqual(parseState(new URL(filterUrl).search), current);
assert.equal(makeFilterURL(filterUrl, {query: '', edition: 'all'}),
             'https://drevendev.github.io/Dayflare/identities-m1-20261024.html#subjects');
assert.equal(makeFilterURL(stale, {query: 'x'.repeat(200), edition: 'invalid'}),
             'https://drevendev.github.io/Dayflare/identities-m1-20261024.html?q=' + 'x'.repeat(96) + '#subjects');
const explorerSource = require('node:fs').readFileSync(
  require('node:path').join(__dirname, '../site/identity-explorer.js'), 'utf8');
assert.ok(explorerSource.includes('const url = makeFilterURL(root.location.href, {query, edition});'));
assert.ok(explorerSource.includes("root.history.replaceState(null, '', url)"));
assert.ok(explorerSource.includes('invalidLink = Boolean(state.invalid);'));
assert.ok(explorerSource.includes('share.disabled = invalidLink;'));
assert.ok(explorerSource.includes('if (writeURL) invalidLink = false;'));
console.log('PASS identity explorer search, editions, URL restoration, share sanitization and length bound');

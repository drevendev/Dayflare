'use strict';
const assert = require('node:assert/strict');
const {normalize, parseState, matches, makeShareURL} = require('../site/identity-explorer.js');
const en = {edition: 'en', search: normalize('Chess en.wikipedia:5134 Q718')};
const ru = {edition: 'ru', search: normalize('Шахматы ru.wikipedia:10646 Q718')};
assert.equal(normalize('  ШАХМАТЫ  '), 'шахматы');
assert.equal(matches(en, 'cHeSs', 'all'), true);
assert.equal(matches(en, 'EN.WIKIPEDIA:5134', 'en'), true);
assert.equal(matches(en, 'Q718 chess', 'en'), true);
assert.equal(matches(en, 'chess', 'ru'), false);
assert.equal(matches(ru, 'шахматы', 'ru'), true);
assert.equal(matches(ru, 'Q718', 'ru'), true);
assert.equal(matches(ru, 'Q718', 'en'), false);
assert.equal(matches(ru, 'football', 'ru'), false);
assert.deepEqual(parseState('?q=%D0%A8%D0%B0%D1%85%D0%BC%D0%B0%D1%82%D1%8B&edition=ru'),
                 {query: 'Шахматы', edition: 'ru'});
assert.equal(parseState('?edition=fr').edition, 'all');
assert.equal(parseState('?q=' + 'x'.repeat(200)).query.length, 96);
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
console.log('PASS identity explorer search, editions, URL restoration, share sanitization and length bound');

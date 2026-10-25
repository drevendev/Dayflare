'use strict';
const assert = require('node:assert/strict');
const {normalize, parseState, matches} = require('../site/identity-explorer.js');
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
console.log('PASS identity explorer search, editions, URL restore and length bound');

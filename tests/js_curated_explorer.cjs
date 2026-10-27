'use strict';
const assert = require('node:assert/strict');
const {DATASET, normalize, parseState, makeShareURL, matches, compareRows} = require('../site/curated-explorer.js');
assert.equal(normalize('  ФУТБОЛ  '), 'футбол');
assert.equal(parseState('').compatible, true);
assert.deepEqual(parseState('?ds='+DATASET+'&q=%D0%A4%D1%83%D1%82%D0%B1%D0%BE%D0%BB&edition=ru.wikipedia&subject=sport'), {
  compatible:true, query:'Футбол', edition:'ru.wikipedia', subject:'sport', compareA:'', compareB:''
});
for (const bad of ['?ds=obsolete','?ds='+DATASET+'&ds='+DATASET,
 '?edition=fr.wikipedia','?subject=unknown','?q='+ 'x'.repeat(81),
 '?tracking=1','?q=%00evil','?edition=ru.wikipedia&edition=en.wikipedia',
 '?a=topic-en-3921','?b=topic-ru-7963','?a=topic-en-3921&b=topic-en-3921',
 '?a=topic-en-bad&b=topic-ru-7963','?a=topic-en-3921&b=topic-ru-0']) {
  assert.equal(parseState(bad).compatible, false, bad);
}
const row = {edition:'ru.wikipedia', subject:'sport', search:normalize('Футбол ru.wikipedia 7963')};
assert.equal(matches(row, 'ФУТБОЛ', 'ru.wikipedia', 'sport'), true);
assert.equal(matches(row, '7963', 'all', 'sport'), true);
assert.equal(matches(row, 'Футбол', 'en.wikipedia', 'sport'), false);
assert.equal(matches(row, 'Футбол', 'ru.wikipedia', 'books'), false);
const link = new URL(makeShareURL('https://drevendev.github.io/Dayflare/m1-curated-20261023.html?junk=1#obsolete',
  {query:' Футбол ', edition:'ru.wikipedia', subject:'sport'}));
assert.equal(link.pathname, '/Dayflare/m1-curated-20261023.html');
assert.equal(link.hash, '#discover');
assert.deepEqual([...link.searchParams.entries()], [
  ['ds',DATASET],['q','Футбол'],['edition','ru.wikipedia'],['subject','sport']]);
assert.equal(parseState(link.search).compatible,true);
const clean = new URL(makeShareURL('http://127.0.0.1:8080/Dayflare/m1-curated-20261023.html?bad=1',
  {query:'', edition:'xx', subject:'xx'}));
assert.deepEqual([...clean.searchParams.keys()], ['ds']);
assert.equal(parseState(clean.search).compatible, true);
const pair = new URL(makeShareURL('https://drevendev.github.io/Dayflare/m1-curated-20261023.html',
  {query:'', edition:'all', subject:'all', compareA:'topic-en-3921', compareB:'topic-ru-7963'}));
assert.equal(pair.searchParams.get('a'), 'topic-en-3921');
assert.equal(pair.searchParams.get('b'), 'topic-ru-7963');
assert.equal(pair.hash, '#discover');
assert.equal(parseState(pair.search).compatible, true);
assert.deepEqual([parseState(pair.search).compareA, parseState(pair.search).compareB],
  ['topic-en-3921', 'topic-ru-7963']);
const days = Array.from({length: 35}, (_, i) =>
  new Date(Date.UTC(2026, 8, 19 + i)).toISOString().slice(0, 10));
const left = days.map((d, i) => [d, i + 1]);
const right = days.map((d, i) => [d, (i + 1) * 2]);
const compared = compareRows(left, right);
assert.equal(compared.dates.length, 35);
assert.deepEqual(compared.weeksLeft, [28, 77, 126, 175, 224]);
assert.deepEqual(compared.weeksRight, [56, 154, 252, 350, 448]);
assert.equal(compared.dates[0], '2026-09-19');
assert.equal(compared.dates[34], '2026-10-23');
assert.equal(compareRows(left.slice(1), right), null);
assert.equal(compareRows(left, right.slice(1)), null);
const changedDate = right.map(([d, v]) => [d, v]);
changedDate[3][0] = '2026-09-20';
assert.equal(compareRows(left, changedDate), null);
const missing = right.map(([d, v]) => [d, v]);
missing[10][1] = null;
assert.equal(compareRows(left, missing), null);
const negative = right.map(([d, v]) => [d, v]);
negative[10][1] = -1;
assert.equal(compareRows(left, negative), null);
assert.equal(compareRows(left, right.map(([d]) => [d, Number.NaN])), null);
const invalidDate = right.map(([d, v]) => [d, v]);
invalidDate[3][0] = '2026-09-31';
assert.equal(compareRows(invalidDate, invalidDate), null);
console.log('PASS 20-title discovery, exact comparable 35-day history, negatives and version-bound pair restoration');

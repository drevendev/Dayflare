'use strict';
const assert = require('node:assert/strict');
const {DATASET, normalize, parseState, makeShareURL, matches} = require('../site/curated-explorer.js');
assert.equal(normalize('  ФУТБОЛ  '), 'футбол');
assert.equal(parseState('').compatible, true);
assert.deepEqual(parseState('?ds='+DATASET+'&q=%D0%A4%D1%83%D1%82%D0%B1%D0%BE%D0%BB&edition=ru.wikipedia&subject=sport'), {
  compatible:true, query:'Футбол', edition:'ru.wikipedia', subject:'sport'
});
for (const bad of ['?ds=obsolete','?ds='+DATASET+'&ds='+DATASET,
 '?edition=fr.wikipedia','?subject=unknown','?q='+ 'x'.repeat(81),
 '?tracking=1','?q=%00evil','?edition=ru.wikipedia&edition=en.wikipedia']) {
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
console.log('PASS measured 20-title subject/edition search, fail-closed dataset binding and sanitized links');

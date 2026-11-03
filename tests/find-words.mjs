// "Describe what you want" (js/find-words.mjs readWords): plain words read into Find areas' own choices, in the
// browser (Bill, 2026-11-02: a search "like other websites", "without imposing on privacy concerns").
// Held here: each everyday phrase reaches its choice; a region by name or by a city in it; a price to the largest
// step not above it, said when it is not exact and never stretched; "quiet" is both noises; a want said with "not"
// is never read as the want; words nothing matched are given back, never guessed at; empty text changes nothing.
//
//   node tests/find-words.mjs

import assert from 'node:assert/strict';
import { readWords } from '../js/find-words.mjs';

const OPTS = {
  regions: [['london', 'London'], ['manchester', 'Greater Manchester'], ['westmidlands', 'West Midlands'],
    ['westyorkshire', 'West Yorkshire'], ['bristol', 'Bristol'], ['leicester', 'Leicester']],
  budgets: [200000, 250000, 300000, 400000, 500000, 600000, 750000, 1000000],
  keys: ['planes', 'roads', 'flood', 'air', 'rail', 'schools'],
};
const read = (t) => readWords(t, OPTS);

let passed = 0;
const check = (name, fn) => { fn(); passed += 1; console.log(`  ok  ${name}`); };

check('a whole sentence: region, price and choices', () => {
  const r = read('Quiet area near a station under £500k in Manchester with good schools');
  assert.equal(r.where, 'manchester');
  assert.equal(r.budget, 500000);
  assert.deepEqual(r.keys, ['planes', 'roads', 'rail', 'schools']);
  assert.deepEqual(r.said, ['Greater Manchester', 'under £500,000']);
  assert.deepEqual(r.unread, []);
});

check('each choice answers to its everyday words', () => {
  const k = (t) => read(t).keys;
  assert.deepEqual(k('no planes'), ['planes']);
  assert.deepEqual(k('not under a flight path'), ['planes']);
  assert.deepEqual(k('away from the airport'), ['planes']);
  assert.deepEqual(k('quiet skies'), ['planes']);
  assert.deepEqual(k('no busy roads'), ['roads']);
  assert.deepEqual(k('low traffic'), ['roads']);
  assert.deepEqual(k('low flood risk'), ['flood']);
  assert.deepEqual(k('not flooding'), ['flood']);
  assert.deepEqual(k('clean air'), ['air']);
  assert.deepEqual(k('low pollution'), ['air']);
  assert.deepEqual(k('close to the tube'), ['rail']);
  assert.deepEqual(k('walking distance to a train station'), ['rail']);
  assert.deepEqual(k('easy commute'), ['rail']);
  assert.deepEqual(k('great secondary schools'), ['schools']);
  assert.deepEqual(k('peaceful'), ['planes', 'roads']); // "quiet" and its kin: both noises, shown as two chips
});

check('a region by its name or by a city in it, and only one the tab offers', () => {
  assert.equal(read('somewhere in West Yorkshire').where, 'westyorkshire');
  assert.equal(read('Leeds').where, 'westyorkshire');
  assert.equal(read('greater manchester').where, 'manchester');
  assert.equal(read('Birmingham, clean air').where, 'westmidlands');
  assert.equal(read('Liverpool').where, null); // Merseyside is not offered here, so not read
  assert.deepEqual(read('Liverpool').unread, ['liverpool']); // and is given back, not dropped
});

check('a price goes to the largest step not above it, says so, and is never stretched', () => {
  assert.equal(read('under 450k').budget, 400000);
  assert.deepEqual(read('under 450k').said, ['under £400,000 (the nearest step under £450,000)']);
  assert.equal(read('up to £1m').budget, 1000000);
  assert.equal(read('max 600,000').budget, 600000);
  assert.equal(read('£1.2 million').budget, 1000000);
  assert.equal(read('budget of 750 thousand').budget, 750000);
  const low = read('under £150k');
  assert.equal(low.budget, null);
  assert.deepEqual(low.said, ['no price set: the lowest step is £200,000']);
  assert.equal(read('2 bedrooms').budget, null); // a bare small number is not a price
  // ...and one after a price word is given back as not understood, never dropped without a word.
  const odd = read('under 450');
  assert.equal(odd.budget, null);
  assert.deepEqual(odd.said, []);
  assert.deepEqual(odd.unread, ['450']);
});

check('a want said with "not" is never read as the want, and is given back', () => {
  const r = read('not near a station, no planes');
  assert.deepEqual(r.keys, ['planes']);
  assert.ok(r.unread.includes('not near a station'), JSON.stringify(r.unread));
  assert.deepEqual(read('away from schools').keys, []);
});

check('words nothing matched are given back; empty text changes nothing', () => {
  const r = read('near a park with a big garden');
  assert.deepEqual(r.keys, []);
  assert.deepEqual(r.unread, ['park', 'big', 'garden']);
  assert.deepEqual(read(''), { where: null, budget: null, keys: [], said: [], unread: [] });
  assert.deepEqual(read('   '), { where: null, budget: null, keys: [], said: [], unread: [] });
  // A choice the tab does not offer is never set, and its words are given back as not understood.
  const notOffered = readWords('clean air', { ...OPTS, keys: ['planes'] });
  assert.deepEqual(notOffered.keys, []);
  assert.deepEqual(notOffered.unread, ['clean', 'air']);
});

console.log(`find words: ${passed} checks passed`);

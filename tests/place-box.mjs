// What the postcode box offers (js/place-box.mjs suggest()): pure, so every branch is read here without a browser.
//
//   node tests/place-box.mjs

import assert from 'node:assert/strict';
import { NOTHING_SENT, suggest } from '../js/place-box.mjs';

const PLACES = [{ name: 'Camden', kind: 'Council area' }, { name: 'Greater Manchester', kind: 'City region' }, { name: 'Manchester', kind: 'Council area' }];
const EXAMPLES = [{ value: 'TW9 3PZ', note: 'a postcode' }, { value: 'Hounslow', note: 'a council area' }];
let passed = 0;
const check = (name, fn) => { fn(); passed++; console.log(`  ok  ${name}`); };

check('an empty box shows the examples and says nothing is sent', () => {
  const s = suggest('  ', PLACES, EXAMPLES);
  assert.deepEqual(s.items.map((i) => i.value), ['TW9 3PZ', 'Hounslow']);
  assert.equal(s.foot, NOTHING_SENT);
});

check('a place that starts with the words comes before one that holds them', () => {
  assert.deepEqual(suggest('man', PLACES, EXAMPLES).items.map((i) => i.value), ['Manchester', 'Greater Manchester']);
});

check('what was typed is picked out, in the place\'s own spelling', () => {
  assert.deepEqual(suggest('CAM', PLACES, EXAMPLES).items[0].parts, ['', 'Cam', 'den']);
});

check('a full postcode is offered as itself, in capitals, with or without its space', () => {
  assert.equal(suggest('sw5 9hp', PLACES, EXAMPLES).items[0].value, 'SW5 9HP');
  assert.equal(suggest('sw59hp', PLACES, EXAMPLES).items[0].value, 'SW59HP');
});

check('part of a postcode asks for the rest; an unknown word says so; neither offers a guess', () => {
  assert.match(suggest('SW5', PLACES, EXAMPLES).foot, /full postcode/);
  const none = suggest('atlantis', PLACES, EXAMPLES);
  assert.equal(none.items.length, 0);
  assert.match(none.foot, /No place by that name/);
});

check('the list is short', () => {
  const many = Array.from({ length: 20 }, (_, i) => ({ name: `Place ${i}`, kind: 'Council area' }));
  assert.equal(suggest('place', many, EXAMPLES).items.length, 6);
});

console.log(`place box: ${passed} checks passed`);

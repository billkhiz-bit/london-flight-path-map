// What the postcode box offers (js/place-box.mjs suggest()): pure, so every branch is read here without a browser.
//
//   node tests/place-box.mjs

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { EXAMPLE, askable, postcodeCompletions, startsLikePostcode, suggest } from '../js/place-box.mjs';

const PLACES = [{ name: 'Camden', kind: 'Council area' }, { name: 'Greater Manchester', kind: 'City region' }, { name: 'Manchester', kind: 'Council area' }];
const EXAMPLES = [{ value: 'TW9 3PZ', note: 'a postcode' }, { value: 'Hounslow', note: 'a council area' }];
let passed = 0;
const check = (name, fn) => { fn(); passed++; console.log(`  ok  ${name}`); };

check('an empty box shows the examples, and makes no promise about what is sent', () => {
  const s = suggest('  ', PLACES, EXAMPLES);
  assert.deepEqual(s.items.map((i) => i.value), ['TW9 3PZ', 'Hounslow']);
  assert.equal(s.foot, undefined);
});

check('a box with no examples opens on nothing, not on a heading alone', () => {
  assert.deepEqual(suggest('', [], []), { items: [] });
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

check('only the start of a postcode may be asked about', () => {
  for (const text of ['SW5', 'sw5 ', 'SW5 9', 'SW5 9H', 'SW59', 'SW59H', 'W1', 'M1 1A', 'EC1A', 'EC1A 1', 'EC1A 1B']) assert.equal(askable(text), true, text);
  for (const text of ['', 's', 'SW', 'camden', 'kew', '94301', 'b1 flat 3, high street', 'SW5 9HP extra', 'palo alto']) assert.equal(askable(text), false, text);
});

check('a whole postcode is not asked about: there is nothing left to suggest', () => {
  for (const text of ['SW5 9HP', 'sw59hp', 'M1 1AE', 'EC1A 1BB']) assert.equal(askable(text), false, text);
});

// The full map's box reads this one rule while typing (audit M-6, 2026-11-09): it sent any 2-8 letters and digits.
check('the full map asks only about text shaped like a postcode or its start', () => {
  for (const text of ['SW5', 'sw5 9', 'SW5 9HP', 'sw59hp', 'EC1A 1BB', 'M1']) assert.equal(startsLikePostcode(text), true, text);
  for (const text of ['', 'SW', 'Hounslow', 'HOUNSLOW', 'Flat3', 'flat 3', 'kew', '94066', 'palo alto', null, undefined]) {
    assert.equal(startsLikePostcode(text), false, String(text));
  }
});

check('postcodes found are offered, with what was typed picked out, spaced or not', () => {
  const found = ['SW5 9AA', 'SW5 9AB'];
  const spaced = suggest('sw5 9', PLACES, EXAMPLES, { postcodes: found });
  assert.deepEqual(spaced.items.map((i) => i.value), found);
  assert.deepEqual(spaced.items[0].parts, ['', 'SW5 9', 'AA']);
  assert.equal(spaced.items[0].note, 'Postcode');
  assert.deepEqual(suggest('sw59', PLACES, EXAMPLES, { postcodes: found }).items[1].parts, ['', 'SW5 9', 'AB']);
});

check('ten postcodes found still make a short list', () => {
  const ten = Array.from({ length: 10 }, (_, i) => `SW5 9A${i}`);
  assert.equal(suggest('sw5', PLACES, EXAMPLES, { postcodes: ten }).items.length, 6);
});

check('a box that takes only postcodes holds real choices or nothing, so it never covers its button for nothing', () => {
  const only = { postcodeBox: true };
  assert.deepEqual(suggest('sw5 9hp', [], [], only), { items: [] });
  assert.deepEqual(suggest('sw5', [], [], only), { items: [] });
  assert.deepEqual(suggest('hello', [], [], only), { items: [] });
  const [item] = suggest('sw5', [], [], { ...only, postcodes: ['SW5 9AA'] }).items;
  assert.equal(item.value, 'SW5 9AA');
  assert.equal(item.note, '', 'every option is a postcode, and the word pushes it onto two lines at 320 wide');
});

const answering = (body, ok = true) => { globalThis.fetch = async () => ({ ok, json: async () => body }); };
const realFetch = globalThis.fetch;
await (async () => {
  answering({ status: 200, result: ['SW5 9AA'] });
  assert.deepEqual(await postcodeCompletions('sw5 9'), ['SW5 9AA']);
  answering({ status: 200, result: null }); // what postcodes.io really answers for a start it does not know (read 2026-11-06)
  assert.deepEqual(await postcodeCompletions('zz9'), []);
  answering({ status: 500 }, false);
  assert.deepEqual(await postcodeCompletions('sw5'), []);
  let asked = '';
  globalThis.fetch = async (url) => { asked = url; return { ok: true, json: async () => ({ result: [] }) }; };
  await postcodeCompletions('sw5 9');
  assert.equal(asked, 'https://api.postcodes.io/postcodes/SW59/autocomplete');
  globalThis.fetch = realFetch;
  passed++;
  console.log('  ok  postcodes.io is asked for the text with no space, and null, or a failure, is no postcodes');
})();

check('the held example is postcodes.io\'s own answer, and the front page names it', () => {
  const real = JSON.parse(readFileSync(new URL('./fixtures/api-demo-env.json', import.meta.url), 'utf8')).TW93PZ.geo;
  assert.deepEqual(EXAMPLE, real);
  // A page naming another example has no point held for it, so the example would quietly vanish.
  const named = /id="ans-example" data-pc="([^"]+)"/.exec(readFileSync(new URL('../home/index.html', import.meta.url), 'utf8'))?.[1];
  assert.equal(named, EXAMPLE.postcode);
});

check('neither page opens a connection to postcodes.io on arriving: a preconnect reaches it as surely as a request', () => {
  for (const page of ['../home/index.html', '../api/index.html']) {
    assert.doesNotMatch(readFileSync(new URL(page, import.meta.url), 'utf8'), /<link\b[^>]*postcodes\.io/i, page);
  }
});

console.log(`place box: ${passed} checks passed`);

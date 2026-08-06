// Coverage for the browser extension's Rightmove coordinate extraction.
//
// WHY THIS EXISTS. extension/content/extract.js is the riskiest file in the
// extension: it reads a third party's markup, it cannot be exercised by any
// other test, and when it breaks it breaks SILENTLY — a page redesign turns
// every listing into "no panel" with no error anywhere. The extension shipped
// with a note that testing it "needs jsdom, which is not a dependency". It does
// not. extract.js touches exactly four DOM surfaces, so a ~30-line shim covers
// it with no new dependency at all.
//
// WHAT THIS CAN AND CANNOT TELL YOU. It proves the four strategies fire on
// representative markup, attribute themselves correctly, and reject bad
// coordinates. It CANNOT tell you whether Rightmove's real pages still look
// like these fixtures — only a browser can, via
// `sh scripts/build_extraction_probe.sh`. Treat a green run here as "the code
// is not broken", never as "the extension works".
//
// It already earned its place: it caught fromScriptBlob() matching JSON-LD text
// and reporting itself as `page-model`. Coordinates were right, the strategy
// label was wrong, and that label is the only drift signal the panel has.
//
//   node tests/extension-extraction.mjs

import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = join(HERE, '..', 'extension', 'content', 'extract.js');

// Load the REAL extraction source. Deliberately not a copy: a duplicated
// fixture of the code under test drifts the moment either side changes, and
// then reports confidence about something that is not running.
const src = readFileSync(SOURCE, 'utf8').replace(/^\/\* exported[^\n]*\n/, '');

// Minimal DOM: only the four surfaces extract.js actually reads. Anything more
// would be modelling a browser rather than testing this file.
function makeDoc({ scripts = [], jsonld = [], imgs = [], h1 = '', metas = {} }) {
  const node = (text, type) => ({
    textContent: text,
    getAttribute: (attr) => (attr === 'type' ? type || null : null),
  });
  return {
    querySelectorAll(sel) {
      // A real querySelectorAll('script') returns ld+json blocks too. Modelling
      // that is the whole reason the strategy-attribution bug was findable.
      if (sel === 'script') {
        return [
          ...scripts.map((t) => node(t)),
          ...jsonld.map((t) => node(t, 'application/ld+json')),
        ];
      }
      if (sel.includes('ld+json')) return jsonld.map((t) => node(t, 'application/ld+json'));
      if (sel === 'img') return imgs.map((s) => ({ src: s, getAttribute: () => null }));
      return [];
    },
    querySelector(sel) {
      if (sel === 'h1') return h1 ? node(h1) : null;
      const hit = Object.entries(metas).find(([k]) => sel.includes(k));
      return hit ? { getAttribute: () => hit[1] } : null;
    },
  };
}

// node:vm rather than new Function(src). Two reasons, both real:
//
// Interpolating a file's contents into a function body is the shape of a code
// injection even when the file is first-party, and a test harness is a poor
// place to normalise that shape. runInContext takes the script as a script.
//
// It also sandboxes properly. The context below exposes exactly one global,
// `document`, so if extract.js ever reaches for `window`, `fetch`, `chrome` or
// anything else the extension does not have in a content script's isolated
// world, this fails loudly here instead of at runtime in someone's browser.
//
// A fresh context per case keeps fixtures from leaking into one another.
function extractWith(doc) {
  const context = createContext({ document: doc });
  runInContext(src, context);
  return context.extractListing();
}

// A realistic page model is tens of kilobytes; extract.js skips scripts under
// 50 chars to avoid scanning tiny analytics snippets. Pad so fixtures exercise
// the regex rather than the length guard.
const pad = 'x'.repeat(80);

const CASES = [
  {
    name: 'page-model blob',
    doc: {
      scripts: [`window.PAGE_MODEL={"pad":"${pad}","location":{"latitude":51.4613,"longitude":-0.1656}}`],
      h1: 'Battersea Park Road, London SW11',
    },
    want: { source: 'page-model', lat: 51.4613, outcode: 'SW11', inLondon: true },
  },
  {
    name: 'page-model, reversed key order',
    doc: {
      scripts: [`window.PAGE_MODEL={"pad":"${pad}","longitude":-0.1656,"latitude":51.4613}`],
      h1: 'Clapham, London SW4 7AA',
    },
    want: { source: 'page-model', lat: 51.4613, outcode: 'SW4', inLondon: true },
  },
  {
    name: 'json-ld attributes to json-ld, not page-model',
    doc: {
      jsonld: [JSON.stringify({ '@type': 'Residence', geo: { latitude: 51.5, longitude: -0.12 } })],
      h1: 'Soho, London W1',
    },
    want: { source: 'json-ld', lat: 51.5, outcode: 'W1', inLondon: true },
  },
  {
    name: 'static map image URL',
    doc: {
      imgs: ['https://maps.googleapis.com/maps/api/staticmap?center=51.5074,-0.1278&zoom=15'],
      h1: 'Westminster, London SW1',
    },
    want: { source: 'static-map', lat: 51.5074, outcode: 'SW1', inLondon: true },
  },
  {
    name: 'geo.position meta tag',
    doc: { metas: { 'geo.position': '51.52;-0.09' }, h1: 'Barbican, London EC1A 1BB' },
    want: { source: 'meta', lat: 51.52, outcode: 'EC1A', inLondon: true },
  },
  {
    name: 'non-London coords resolve but flag inLondon false',
    doc: {
      scripts: [`{"pad":"${pad}","latitude":53.4808,"longitude":-2.2426}`],
      h1: 'Deansgate, Manchester M1 4BT',
    },
    // The panel suppresses transport for these — TfL has no coverage, and a
    // bare "0 stations" would state an absence of transport while only knowing
    // an absence of data.
    want: { source: 'page-model', lat: 53.4808, outcode: 'M1', inLondon: false },
  },
  { name: 'nothing extractable returns null', doc: { h1: 'A house somewhere' }, want: null },
  {
    name: 'coords outside the UK are rejected',
    doc: { scripts: [`{"pad":"${pad}","latitude":40.7128,"longitude":-74.0060}`], h1: 'New York' },
    want: null,
  },
  {
    // Honest name: this asserts the OUTCOME, not the mechanism. (0, 0) is
    // caught by UK_BOUNDS before the dedicated zero guard is reached, so
    // deleting that guard leaves this case green — verified, not assumed.
    // The guard is kept anyway; see the comment on it in extract.js.
    name: 'null island is rejected (via bounds, not the zero guard)',
    doc: { scripts: [`{"pad":"${pad}","latitude":0,"longitude":0}`], h1: 'Nowhere' },
    want: null,
  },
];

let failed = 0;

for (const { name, doc, want } of CASES) {
  let got;
  try {
    got = extractWith(makeDoc(doc));
  } catch (err) {
    console.log(`FAIL  ${name}\n      threw: ${err.message}`);
    failed += 1;
    continue;
  }

  if (want === null) {
    if (got === null) {
      console.log(`PASS  ${name}`);
    } else {
      console.log(`FAIL  ${name}\n      expected null, got ${JSON.stringify(got)}`);
      failed += 1;
    }
    continue;
  }

  const mismatches = Object.entries(want).filter(([k, v]) => got?.[k] !== v);
  if (!got) {
    console.log(`FAIL  ${name}\n      expected a result, got null`);
    failed += 1;
  } else if (mismatches.length) {
    console.log(`FAIL  ${name}`);
    for (const [k, v] of mismatches) console.log(`      ${k}: got ${JSON.stringify(got[k])}, want ${JSON.stringify(v)}`);
    failed += 1;
  } else {
    console.log(`PASS  ${name}`);
  }
}

console.log(
  failed === 0
    ? `\n${CASES.length} extraction cases passed.`
    : `\n${failed} of ${CASES.length} FAILED.`
);
process.exit(failed === 0 ? 0 : 1);

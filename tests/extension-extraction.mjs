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
      //
      // 'script:not([src])' is what the page-model unpacker asks for. Every
      // fixture here is inline, so it resolves to the same set — but it must be
      // handled explicitly, or the selector falls through to [] and the
      // strategy silently sees an empty page.
      if (sel === 'script' || sel === 'script:not([src])') {
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
    want: { source: 'page-model', lat: 51.4613, outcode: 'SW11' },
  },
  {
    name: 'page-model, reversed key order',
    doc: {
      scripts: [`window.PAGE_MODEL={"pad":"${pad}","longitude":-0.1656,"latitude":51.4613}`],
      h1: 'Clapham, London SW4 7AA',
    },
    want: { source: 'page-model', lat: 51.4613, outcode: 'SW4' },
  },
  {
    // Rightmove serves coordinates as quoted STRINGS. The fixture above uses
    // that form because it is what a live page actually returned on
    // 2026-08-06; this case keeps the numeric form covered, since other
    // portals serialise that way and the pattern accepts both.
    name: 'page-model with unquoted numeric values',
    doc: {
      scripts: [`window.PAGE_MODEL={"pad":"${pad}","latitude":51.4613,"longitude":-0.1656}`],
      h1: 'Battersea, London SW11',
    },
    want: { source: 'page-model', lat: 51.4613 },
  },
  {
    // Keys present but not adjacent — the third-attempt split path. Scoped to a
    // single script so a latitude from one object cannot pair with a longitude
    // from another; reported under its own strategy name so the debug line
    // still says which route won.
    name: 'page-model with non-adjacent keys uses the split path',
    doc: {
      scripts: [
        `window.PAGE_MODEL={"latitude":"51.4613","displayAddress":"${pad}","propertyType":"flat","longitude":"-0.1656"}`,
      ],
      h1: 'Battersea, London SW11',
    },
    want: { source: 'page-model-split', lat: 51.4613, lon: -0.1656 },
  },
  {
    name: 'json-ld attributes to json-ld, not page-model',
    doc: {
      jsonld: [JSON.stringify({ '@type': 'Residence', geo: { latitude: 51.5, longitude: -0.12 } })],
      h1: 'Soho, London W1',
    },
    want: { source: 'json-ld', lat: 51.5, outcode: 'W1' },
  },
  {
    name: 'static map image URL',
    doc: {
      imgs: ['https://maps.googleapis.com/maps/api/staticmap?center=51.5074,-0.1278&zoom=15'],
      h1: 'Westminster, London SW1',
    },
    want: { source: 'static-map', lat: 51.5074, outcode: 'SW1' },
  },
  {
    name: 'geo.position meta tag',
    doc: { metas: { 'geo.position': '51.52;-0.09' }, h1: 'Barbican, London EC1A 1BB' },
    want: { source: 'meta', lat: 51.52, outcode: 'EC1A' },
  },
  {
    // Was 'non-London coords resolve but flag inLondon false' until 2026-08-23.
    // The flag is deleted - the panel now reads coverage out of the
    // /v1/environment response rather than out of a bounding box here - but the
    // half of this case worth keeping is the half that never depended on it:
    // UK_BOUNDS must accept a coordinate 260 km north of London, and the
    // outcode must come off the heading rather than off any London assumption.
    // Narrowing UK_BOUNDS to something London-shaped is the regression.
    name: 'coordinates far outside London still extract',
    doc: {
      scripts: [`{"pad":"${pad}","latitude":53.4808,"longitude":-2.2426}`],
      h1: 'Deansgate, Manchester M1 4BT',
    },
    want: { source: 'page-model', lat: 53.4808, outcode: 'M1' },
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

// --- The real page --------------------------------------------------------
//
// Every case above is synthetic, and synthetic fixtures are exactly how this
// suite went green for a day while the extension found nothing on a single
// real listing: the fixtures used the serialisation I ASSUMED rather than the
// one Rightmove ships.
//
// rightmove-real-sw5.html carries the `window.__PAGE_MODEL` script verbatim
// from a listing saved on 2026-08-06 (Collingham Road, SW5) — untrimmed and
// unreformatted, because normalising it would reintroduce the same problem.
// If this case ever fails, Rightmove changed their page model and the
// unpacker needs re-deriving. Nothing else in the suite can tell you that.
// TWO real pages, because one of them can only prove half of it. SW5 is a sale;
// the letting path was built and shipped against that same file with BUY
// rewritten to LET — a fixture that tests my model of Rightmove twice over, and
// which (found later) also rewrote strings in their cookie manifest I did not
// know were there. rightmove-real-letting-nw2.html is a genuine To Rent listing
// saved on 2026-08-08, trimmed to this shape and otherwise verbatim.
const loadReal = (file) => {
  const html = readFileSync(join(HERE, 'fixtures', file), 'utf8');
  return {
    script: html.slice(html.indexOf('>', html.indexOf('<script')) + 1, html.indexOf('</script>')),
    h1: (html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/) || [])[1] || '',
  };
};

const REAL_PAGES = [
  {
    name: 'real Rightmove page (SW5, sale)',
    file: 'rightmove-real-sw5.html',
    want: {
      source: 'rightmove-page-model',
      lat: 51.49423,
      lon: -0.18825,
      outcode: 'SW5',
      // Reached through the same index-reference indirection as the
      // coordinates: the node says {"price":233} and flat[233] is 34000000.
      askingPrice: 34000000,
      // Computed and discarded until it only gated the price; it now decides
      // which sections render at all, so it is asserted directly.
      channel: 'sale',
    },
  },
  {
    name: 'real Rightmove page (NW2, letting)',
    file: 'rightmove-real-letting-nw2.html',
    want: {
      source: 'rightmove-page-model',
      lat: 51.556473,
      lon: -0.218428,
      outcode: 'NW2',
      // THE ASSERTION THIS FIXTURE EXISTS FOR. A letting's `price` is a monthly
      // figure; withholding it is what stops £1,800 pcm being plotted against
      // completed sales. Proven now on a real To Rent page rather than on a
      // sale page with a string substituted.
      askingPrice: null,
      channel: 'letting',
    },
  },
];

// Kept for the variant tests below, which need a page to mutate.
const { script: realScript, h1: realH1 } = loadReal('rightmove-real-sw5.html');

for (const page of REAL_PAGES) {
  const { script, h1 } = loadReal(page.file);
  const got = extractWith(makeDoc({ scripts: [script], h1 }));
  const mismatches = Object.entries(page.want).filter(([k, v]) => got?.[k] !== v);
  if (!got) {
    console.log(`FAIL  ${page.name}\n      extraction returned null`);
    failed += 1;
  } else if (mismatches.length) {
    console.log(`FAIL  ${page.name}`);
    for (const [k, v] of mismatches) {
      console.log(`      ${k}: got ${JSON.stringify(got[k])}, want ${JSON.stringify(v)}`);
    }
    failed += 1;
  } else {
    console.log(`PASS  ${page.name}`);
  }
}

// --- The sale/letting guard ----------------------------------------------
//
// THE DANGEROUS PATH. The panel draws askingPrice against Land Registry sold
// prices. On a letting Rightmove's `price` is a MONTHLY figure, so £2,400 pcm
// would land at the far left of a range of completed sales and read as the
// bargain of the century. One field separates those two renderings.
//
// These fixtures are the REAL page with exactly the channel strings rewritten -
// derived from real markup rather than authored, so they cannot encode an
// assumption about Rightmove's shape. "BUY" -> "LET" also rewrites "RES_BUY"
// to "RES_LET", which is precisely the pair the guard reads.
// The synthetic BUY->LET variant that used to live here is GONE, superseded by
// the real NW2 letting page above. It asserted the same thing against a fixture
// I had written by substitution, which is the circularity this file exists to
// avoid; keeping both would have implied two independent proofs where there was
// one. What remains is the case no real page can supply.
const variants = [
  {
    // Neither BUY nor LET anywhere. Both outputs must default to withholding:
    // a missing channel is not evidence of a sale, and the damaging direction
    // is the one that guesses. A null channel keeps the SALE layout, so this
    // case is also what stops an unreadable page silently losing Sold nearby.
    name: 'no channel signal: neither price nor channel assumed',
    script: realScript.replace(/BUY/g, 'XXX'),
    wantPrice: null,
    wantChannel: null,
  },
];

let variantFails = 0;
for (const v of variants) {
  const got = extractWith(makeDoc({ scripts: [v.script], h1: realH1 }));
  const priceOk = (got?.askingPrice ?? null) === v.wantPrice;
  const channelOk = (got?.channel ?? null) === v.wantChannel;
  // Coordinates must survive: the price guard must not cost us the panel.
  const coordsOk = got?.lat === 51.49423;
  if (priceOk && channelOk && coordsOk) {
    console.log(`PASS  ${v.name}`);
  } else {
    console.log(
      `FAIL  ${v.name}\n      askingPrice ${JSON.stringify(got?.askingPrice ?? null)} ` +
        `(want ${JSON.stringify(v.wantPrice)}), channel ${JSON.stringify(got?.channel ?? null)} ` +
        `(want ${JSON.stringify(v.wantChannel)}), lat ${JSON.stringify(got?.lat)}`
    );
    variantFails += 1;
  }
}
failed += variantFails;

const total = CASES.length + REAL_PAGES.length + variants.length;
console.log(
  failed === 0 ? `\n${total} extraction cases passed.` : `\n${failed} of ${total} FAILED.`
);
process.exit(failed === 0 ? 0 : 1);

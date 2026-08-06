#!/usr/bin/env sh
# Emit a self-contained DevTools probe for the Rightmove extraction.
#
# WHY THIS IS GENERATED AND NOT CHECKED IN. The probe has to run the REAL
# extraction, otherwise a green probe says nothing about the extension. Keeping
# a hand-copied duplicate of extract.js next to extract.js would drift the first
# time either changed, and a diagnostic that tests a stale copy of the code is
# worse than no diagnostic — it reports confidence about something that is not
# running. So the probe is concatenated from the shipped source at build time.
#
#   sh scripts/build_extraction_probe.sh > probe.js
#
# Then paste the contents into DevTools on a Rightmove property page. Nothing is
# sent anywhere: it reads the DOM and prints to the console. It does not call
# the API, so it costs nothing and touches no upstream.

set -eu

SRC="$(dirname "$0")/../extension/content/extract.js"

if [ ! -r "$SRC" ]; then
  echo "cannot read $SRC" >&2
  exit 1
fi

# Wrapped in an IIFE so pasting twice does not throw "already declared" on the
# const bindings — a real annoyance when you are stepping through several
# listings in one tab.
echo '(() => {'

# The /* exported */ directive is for ESLint and means nothing here; strip it so
# the paste is clean.
grep -v '^/\* exported' "$SRC"

cat <<'PROBE'

// --- probe reporter -----------------------------------------------------
const listing = extractListing();

console.log('%c cubitt33 extraction probe ', 'background:#12263f;color:#fff;font-weight:700');

if (!listing) {
  console.error('RESULT: null — every strategy missed.');
  console.log('Strategy-by-strategy:');
  console.log('  page-model :', fromScriptBlob());
  console.log('  json-ld    :', fromJsonLd());
  console.log('  static-map :', fromStaticMap());
  console.log('  meta       :', fromMetaTags());
  console.log('If all four are null, the coordinates are not reachable from the');
  console.log('DOM at all and the extension needs a different approach on this page.');
} else {
  console.table({
    strategy: listing.source,
    latitude: listing.lat,
    longitude: listing.lon,
    outcode: listing.outcode || '(none found)',
    inLondon: listing.inLondon,
    address: listing.address,
  });

  console.log(
    'Check this pin is the right property:',
    `https://www.openstreetmap.org/?mlat=${listing.lat}&mlon=${listing.lon}#map=17/${listing.lat}/${listing.lon}`
  );

  if (listing.source !== 'page-model') {
    console.warn(
      `Fell through to "${listing.source}". page-model is the expected winner;`,
      'this means the primary strategy has drifted and should be re-derived.'
    );
  }

  // Report the others too. Knowing which strategies are ALSO working tells you
  // how much fallback margin there is before the extension goes dark.
  console.log('Other strategies (fallback margin):', {
    'page-model': !!fromScriptBlob(),
    'json-ld': !!fromJsonLd(),
    'static-map': !!fromStaticMap(),
    meta: !!fromMetaTags(),
  });
}
PROBE

echo '})();'

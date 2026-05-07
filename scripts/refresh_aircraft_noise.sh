#!/usr/bin/env bash
# Refresh the locally-cached DEFRA aircraft noise PNG.
#
# When to run: whenever DEFRA publishes a new round of strategic noise
# mapping. As of 2026-05-07 we are on Round 4 (2022 data); Round 5 is
# expected ~2027.
#
# What this does:
#   1. Fetches the PNG from DEFRA's WMS at the LONDON_AIRCRAFT_BBOX
#      coordinates and resolution defined in index.html
#   2. Saves to data/aircraft-noise-london-lden.png
#   3. Prints next-step instructions for deploying to S3 + CloudFront
#
# Run from repo root: bash scripts/refresh_aircraft_noise.sh
#
# DO NOT change the bbox or resolution without also updating
# LONDON_AIRCRAFT_BBOX + AIRCRAFT_RASTER_PX in index.html — the PNG must
# be projected at the same coords as the JS expects.

set -euo pipefail

WMS_URL="https://environment.data.gov.uk/spatialdata/airport-noise-all-metrics-england-round-4/wms"
LAYER="Airport_Noise_ALL_Lden"
BBOX="51.25,-0.55,51.72,0.35"   # minLat,minLon,maxLat,maxLon (WMS 1.3.0 + EPSG:4326 axis order)
WIDTH="4096"
HEIGHT="2139"                    # = round(WIDTH / aspect), aspect = (0.35 - -0.55) / (51.72 - 51.25) = 1.915

OUT="data/aircraft-noise-london-lden.png"

echo "Fetching DEFRA aircraft noise raster…"
curl -s --fail \
  "${WMS_URL}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${LAYER}&STYLES=&CRS=EPSG:4326&BBOX=${BBOX}&WIDTH=${WIDTH}&HEIGHT=${HEIGHT}&FORMAT=image/png&TRANSPARENT=true" \
  -o "${OUT}"

if [ ! -s "${OUT}" ]; then
  echo "ERROR: fetched PNG is empty. Check the WMS URL and Round version." >&2
  exit 1
fi

SIZE=$(stat -c%s "${OUT}" 2>/dev/null || stat -f%z "${OUT}")
DIMS=$(file "${OUT}" | grep -oE '[0-9]+ x [0-9]+' || echo 'unknown')
echo "Saved ${OUT} — ${SIZE} bytes, ${DIMS}"

cat <<EOF

Next steps to deploy:

  AWS_PROFILE=flightmap aws s3 cp ${OUT} \\
    s3://london-flight-map-frontend/${OUT} \\
    --content-type "image/png" \\
    --cache-control "public, max-age=86400" \\
    --region eu-west-2

  AWS_PROFILE=flightmap aws cloudfront create-invalidation \\
    --distribution-id EGSSPJKLFL33M \\
    --paths "/${OUT}"

Then commit the new PNG so CI / fresh clones pick it up.

EOF

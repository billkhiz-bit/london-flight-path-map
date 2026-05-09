# Deep linking setup (iOS Universal Links + Android App Links)

## What this gives you

When deep linking is configured, tapping `https://skyscore.co.uk/<anything>` from another app on a device that has Sky Score installed launches *the app* directly with that URL, rather than the browser. Without it, the link opens in Safari / Chrome and the user has to manually navigate to the app.

The two files that drive this:

- **`.well-known/apple-app-site-association`** (no file extension; served as `application/json`) — iOS reads this when the app is installed, then handles matching URLs natively
- **`.well-known/assetlinks.json`** — Android equivalent

Both files must be served from `https://skyscore.co.uk/.well-known/` over HTTPS with the right MIME type. Apple and Google fetch them automatically when the app is installed; you don't trigger anything yourself.

---

## Apple — what to fill in

Open `.well-known/apple-app-site-association` and replace `TEAMID` with your Apple Developer Team ID.

**Where to find your Team ID**:
1. Go to [developer.apple.com/account](https://developer.apple.com/account)
2. Top-right, click **Membership Details**
3. The 10-character alphanumeric "Team ID" is what to paste

After replacing, the file should look like (Team ID example only):

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["A1B2C3D4E5.uk.co.skyscore.app"],
        "components": [{"/": "/*"}]
      }
    ]
  }
}
```

---

## Android — what to fill in

Open `.well-known/assetlinks.json` and replace the placeholder fingerprint with the SHA-256 of your release keystore.

**How to get the fingerprint** (after running `keytool -genkey ...` per CODEMAGIC_SETUP.md §3a):

```bash
keytool -list -v -keystore sky-score-release.jks \
  -alias sky-score | grep "SHA256:"
```

Copy the colon-separated hex string after `SHA256:` (40 bytes / 60 chars with colons) and paste into the `sha256_cert_fingerprints` array.

---

## Verifying after deploy

Once both files are live at `https://skyscore.co.uk/.well-known/...`, you can verify the configuration with:

**Apple validation tool**: <https://search.developer.apple.com/appsearch-validation-tool/>
- Enter `https://skyscore.co.uk` → click "Test"
- Should show your `apple-app-site-association` parsed correctly

**Android verification**:
```bash
curl https://skyscore.co.uk/.well-known/assetlinks.json | jq
# Should return valid JSON with your real fingerprint
```

Or use Google's [Statement List Generator and Tester](https://developers.google.com/digital-asset-links/tools/generator).

---

## Native side

Capacitor doesn't need any additional config — once the apps are built with the correct `appId` (`uk.co.skyscore.app`) and signed with the matching keystore (Android) / Team ID (iOS), the OS handles deep-link routing automatically as long as the .well-known files are valid.

If you want the app to handle specific deep-link routes differently (e.g. `https://skyscore.co.uk/postcode/SW11-1AA` opens the app on the score page), that's `App.addListener('appUrlOpen', ...)` in JS — needed only if you have routes the web app doesn't already handle. Sky Score's main app handles every path via the search input, so the default behaviour is fine for v1.

---

## When to ship these files

- **Don't deploy the placeholder files**. They'd parse as invalid (TEAMID isn't a real team ID, REPLACE:WITH:... isn't a real fingerprint), and Apple/Google will silently disable deep linking until they're fixed.
- **Deploy after** you have the real Team ID + keystore fingerprint
- **Deploy before** the apps go live in stores; otherwise users tap a link, get sent to Safari, and the app-vs-web inconsistency is jarring

The deploy is the same as any other static file:

```bash
AWS_PROFILE=flightmap aws s3 cp .well-known/apple-app-site-association \
  s3://london-flight-map-frontend/.well-known/apple-app-site-association \
  --content-type "application/json" --region eu-west-2

AWS_PROFILE=flightmap aws s3 cp .well-known/assetlinks.json \
  s3://london-flight-map-frontend/.well-known/assetlinks.json \
  --content-type "application/json" --region eu-west-2

AWS_PROFILE=flightmap aws cloudfront create-invalidation \
  --distribution-id EGSSPJKLFL33M --paths "/.well-known/*"
```

The MIME type `application/json` matters — Apple specifically refuses to consume the AASA file if the `Content-Type` header is `text/plain` or `application/octet-stream` (the S3 default for files without an extension).

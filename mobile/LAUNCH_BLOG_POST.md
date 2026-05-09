# Sky Score is now on iOS and Android (draft)

**Status**: draft, written 2026-05-09 ahead of store approval. Don't publish until both apps are actually live in the stores. Update the dates and store links when ready.

**Where to publish**: as a post on skyscore.co.uk, plus a Twitter / LinkedIn thread excerpting the highlights.

---

## Headline (pick one)

- "Sky Score is now in the App Store"
- "The hidden noise + livability data your listings site won't show, now on your home screen"
- "Sky Score: now on iOS and Android"

## Subheadline

The independent UK property-data tool now installs as a real app — same code, same scores, same independence. Plus a new feature only the native app can do.

---

## Post body

### What changed

Sky Score has been a website since launch. Today it's also an iOS app and an Android app, available in both stores:

- iOS: [App Store link]
- Android: [Play Store link]

The web version at skyscore.co.uk continues to work exactly as before. Nothing has been moved to "app only." The native apps just give the same experience a permanent home on your device, with one new feature that only works on a real phone.

### What the apps do that the website can't

Sky Score's core question is: how noisy and liveable is this postcode? On the website, you type the postcode in. In the native apps, you can also tap **Score where I am** — the app uses your phone's GPS to identify your current location, finds the nearest UK postcode, and returns the score in one tap.

This matters because the moment most useful for a Sky Score is when you're actually standing in a place: viewing a flat, walking through a neighbourhood you might move to, or visiting a friend in an area you're considering. The native GPS path collapses "find your postcode, then look it up" into a single tap.

Beyond that, the apps offer:

- A standalone window with no browser chrome
- Native splash screen + status bar styling
- OS-level share sheet integration (tap a score, share via your usual share targets)
- Faster cold start than the web version, especially on slow connections
- Continued offline access to the app shell after first install

### What hasn't changed

- **Independence**: we still don't sell ads, push leads, or tilt scores toward any sponsor. The methodology is the same one published in `METHODOLOGY.md`
- **Free**: no in-app purchases, no subscriptions, no premium tier
- **Data sources**: same DEFRA, Land Registry, EPC, NHS, TfL feeds under the Open Government Licence v3.0
- **No tracking**: the apps collect anonymous analytics via GoatCounter (no cookies, no profiles, EU-hosted) and nothing else. Full privacy policy at <https://skyscore.co.uk/privacy>

### Why we built native apps instead of just the PWA

Most of the value of "having an app" is genuinely just an installable shortcut + standalone window. Modern browsers offer this via the PWA install flow, which Sky Score also supports — desktop Chrome and Android Chrome show an Install button, iOS Safari does Share → Add to Home Screen.

We built native apps anyway for three reasons:

1. **GPS hardware access** is materially better through the native CoreLocation / FusedLocationProvider APIs than through the browser's Geolocation API. The "Score where I am" feature is significantly more reliable on native
2. **Discoverability**: people search the App Store and Play Store for tools they'd never type a URL for. Listing in the stores opens a path to users who would never visit skyscore.co.uk directly
3. **Trust signal**: for some users — especially older home-buyers — an App Store listing is the line between "real product" and "random website." Sky Score is independent, but we want to look as legitimate as the listings sites we critique

### How it was built (for the technically curious)

The same `index.html` you see at skyscore.co.uk is what runs inside both apps. There's no separate codebase, no React Native rewrite, no Flutter port. We wrap the web app in [Capacitor](https://capacitorjs.com/) — a thin native shell from the Ionic team — and ship it to TestFlight + Play Console via [Codemagic](https://codemagic.io/), a cloud CI service that builds iOS apps without us needing a Mac.

The cost of this approach: ~3 days of engineering for the wrapper + CI setup, plus a one-off £79/year Apple Developer fee. The benefit: web changes (CSS tweaks, new datasets, copy edits) deploy instantly via CloudFront and *also* propagate to the apps' next binary release, which we cut every 2–4 weeks. The shell is ~200 lines of config and platform-specific manifest; everything else is the existing web codebase.

### Source code

Sky Score is fully open-source. The main app, the Capacitor wrapper config, the Codemagic CI config — all of it lives in [the public GitHub repo](https://github.com/billkhiz-bit/london-flight-path-map). If you're building something similar and want to know how the wrapper works, look at the `mobile/` directory and `codemagic.yaml`.

### What's next

- The 3D Sky Score Radar prototype (currently at /prototype/) will eventually merge into the main app as a "3D view" mode. That'll bring volumetric noise visualisation to the apps too — but only if your phone can handle the WebGL load.
- Push notifications for "noise alert when you walk into a high-noise area" — currently being scoped, would require user opt-in and shouldn't be misused
- More UK coverage: currently strongest in Greater London, with national fill-in via DEFRA's national strategic noise maps and ONS LSOA-level demographics

If you've used Sky Score and have feedback — what's wrong, what's missing, what should we build next — `support@skyscore.co.uk` reads every email.

---

— Bilal Khizar
Sky Score · independent UK property data

---

## Twitter / LinkedIn thread (excerpts)

For social posts, abridge to:

> Sky Score is now on iOS and Android. The independent UK property-data tool that shows the noise + livability listings sites won't.
>
> [App Store link] [Play Store link]
>
> Same code as skyscore.co.uk, with one new thing: tap "Score where I am" → instant noise/livability score for your current location via GPS.
>
> Why native, not just PWA?
> 1) GPS is more reliable through native APIs
> 2) Discoverability — App Store search reaches users who'd never type the URL
> 3) Trust signal for older home-buyers
>
> Built with @CapacitorJS + @codemagicio. ~3 days of work to wrap an existing web app, ship to TestFlight + Play Console internal track.
>
> Source: github.com/billkhiz-bit/london-flight-path-map (mobile/ directory + codemagic.yaml)
>
> Free, no ads, no IAP, no tracking.

## Press / outreach hooks

If reaching out to journalists or specific communities:

- **The case against listings sites** — angle: "the data Rightmove won't show you, now on your phone"
- **Open-source story** — angle: "tiny solo project quietly shipped real iOS + Android apps using just web tools"
- **Halal home-buying angle** — angle: "Sharia-compliant property data for the 4M UK Muslim population, now mobile-first" (target: Muslim Lifestyle, BeyondMagazine, Hyphen, alongside Buildathon)
- **Health angle** — angle: "aircraft noise causes measurable cardiovascular harm; Sky Score puts the data in your pocket" (target: New Scientist, Wired UK)

Save these as separate outreach drafts in `OUTREACH_DRAFTS.md` when launching.

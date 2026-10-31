/**
 * Page views and events for GoatCounter, sent by our own code (2026-10-11, audit 2026-10-09 I-1).
 *
 * WHY NOT GOATCOUNTER'S SCRIPT. Its count.v5.js sends `q: location.search` with every page view
 * and event, a literal inside its get_data() that no setting and no count() argument reaches. So
 * every free-report check link and QR (?postcode=&made=&ref=), every /?postcode= and
 * /map/?postcode= deep link, and every front-page event after a search sent the visitor's
 * postcode, while privacy s2c says GoatCounter "stores aggregate counts only (page views,
 * referrers, screen sizes)". Two more fields could carry it too, which the audit did not name:
 *   - `r`, document.referrer: a same-origin move (/?postcode=TW9+3PZ to /map/) keeps the full
 *     URL under strict-origin-when-cross-origin. Sent here as origin + path only.
 *   - `t`, document.title: the full map writes the postcode into the title once a deep link
 *     resolves, and an async script could count after that. Sent here as the title the page
 *     had when this module ran, before any search.
 *
 * WHAT IS SENT, to GoatCounter's documented /count endpoint (the one its own script calls):
 * the page's path (the canonical link's when it has one, never a query or fragment), that
 * title, the referrer's origin and path, screen size, an event flag, a cache-buster, and with a
 * page view the CAMPAIGN TAGS alone (see CAMPAIGN_KEYS). Nothing that identifies a person, no
 * cookie, no storage but GoatCounter's own opt-out flag.
 *
 * KEPT FROM count.v5.js, on purpose: window.goatcounter.count(vars) with the same `path`,
 * `title` and `event` arguments, so no event caller changes; nothing is counted from localhost,
 * a private address, file: or a frame (the tests and the native app send nothing); a prerendered
 * page counts when it becomes visible; and #toggle-goatcounter switches counting off or on in
 * this browser, as GoatCounter documents, so an owner's own visits stay excluded.
 */

export const ENDPOINT = 'https://cubitt33.goatcounter.com/count';
const LOCAL = /(localhost$|^127\.|^10\.|^172\.(1[6-9]|2[0-9]|3[0-1])\.|^192\.168\.|^0\.0\.0\.0$)/;
// The title as the page was served: read when this module runs, before any search can change it.
const TITLE = document.title;

/** origin + path of a URL string, or '' for anything that does not parse. Never a query. */
export function withoutQuery(href) {
  try {
    const u = new URL(href);
    return u.origin + u.pathname;
  } catch {
    return '';
  }
}

// THE CAMPAIGN TAGS, AND ONLY THESE (OUTREACH_DRAFTS.md "UTM convention"). Every outreach link
// carries utm_source=outreach-<org>, utm_medium and utm_campaign, and GoatCounter files the visit
// under that campaign in its Referrers tab by reading them from `q`. The first version of this
// module sent no `q` at all and so lost every one (found the same day, sweeping the docs). Named,
// never "everything but the postcode": our own pages write city, postcode, made and ref into
// their addresses, and `ref` is the free report's reference, which GoatCounter would ALSO read
// as a campaign source.
export const CAMPAIGN_KEYS = ['utm_source', 'utm_medium', 'utm_campaign'];

/** `?utm_source=..&..` holding only CAMPAIGN_KEYS from a query string, or '' when it has none. */
export function campaignQuery(search) {
  const from = new URLSearchParams(search);
  const kept = new URLSearchParams();
  for (const key of CAMPAIGN_KEYS) {
    const value = from.get(key);
    if (value) kept.set(key, value.slice(0, 100));
  }
  const s = kept.toString();
  return s ? `?${s}` : '';
}

/** The path to count: the canonical link's when it is on this host, else this page's. No query. */
function pagePath() {
  const canonical = document.querySelector('link[rel="canonical"][href]');
  if (canonical) {
    try {
      const u = new URL(canonical.href, location.href);
      if (u.hostname.replace(/^www\./, '') === location.hostname.replace(/^www\./, '')) return u.pathname || '/';
    } catch {
      /* fall through to this page's own path */
    }
  }
  return location.pathname || '/';
}

/** What this page would send, read from the live page. Exported for tests/front-page.mjs. */
export function pageContext() {
  return {
    path: pagePath(),
    title: TITLE,
    referrer: withoutQuery(document.referrer),
    campaign: campaignQuery(location.search),
    screen: [window.screen.width, window.screen.height, window.devicePixelRatio || 1],
    bot: navigator.webdriver ? 153 : 0,
  };
}

/** The /count URL for one hit. Pure: every input is an argument, so a test can hold it. */
export function countUrl(vars = {}, ctx = pageContext()) {
  const data = {
    p: vars.path ?? ctx.path,
    t: vars.title ?? ctx.title,
    r: vars.event ? '' : ctx.referrer,
    e: vars.event ? 'true' : '',
    s: ctx.screen.join(','),
    b: ctx.bot, // 0, or count.v5.js's 153 for a webdriver; sent as 0 when 0, as its script does
    // A page view carries its campaign; an event is a click, already filed under the view.
    q: vars.event ? '' : ctx.campaign || '',
    rnd: Math.random().toString(36).slice(2, 7),
  };
  const query = Object.entries(data)
    .filter(([, v]) => v !== '' && v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
  return `${ENDPOINT}?${query}`;
}

function skipped() {
  if (document.visibilityState === 'prerender') return true;
  if (window !== window.parent) return true;
  if (LOCAL.test(location.hostname) || location.protocol === 'file:') return true;
  try {
    return localStorage.getItem('skipgc') === 't';
  } catch {
    return false; // storage blocked: count, as GoatCounter's own script would
  }
}

function count(vars = {}) {
  try {
    if (skipped()) return;
    const url = countUrl(vars);
    if (navigator.sendBeacon && navigator.sendBeacon(url)) return;
    const img = new Image(1, 1);
    img.alt = '';
    img.src = url;
  } catch {
    /* analytics must never break the page */
  }
}

window.goatcounter = Object.assign(window.goatcounter || {}, { count });

// GoatCounter's documented way to exclude your own browser: visit any page with this fragment.
if (location.hash === '#toggle-goatcounter') {
  try {
    const off = localStorage.getItem('skipgc') === 't';
    if (off) localStorage.removeItem('skipgc');
    else localStorage.setItem('skipgc', 't');
    alert(`GoatCounter counting is now ${off ? 'ENABLED' : 'DISABLED'} in this browser.`);
  } catch {
    /* storage blocked: nothing to toggle */
  }
}

/** The top bar's name for a link: its path without slashes ('/how-it-works/' -> 'how-it-works'), or '' for home.
 *  '' too for a link off this site (2026-10-29): the bar's Book a demo goes to Calendly, and a booking page named
 *  `calendly.com/<slug>` would otherwise have been counted as `nav-<slug>`. It is counted below, by its destination.
 *  "This site" is every host that serves it (2026-10-30 review): www answers too, so an absolute www or CloudFront
 *  link in a bar is still ours and must not drop out of the ~20 Nov read. */
const OWN_HOSTS = new Set(['skyscore.co.uk', 'www.skyscore.co.uk', 'd1oe4ftwutjpf.cloudfront.net']);
export function navSlug(href) {
  try {
    const url = new URL(href, 'https://skyscore.co.uk');
    if (!OWN_HOSTS.has(url.hostname)) return '';
    const slug = url.pathname.replace(/^\/+|\/+$/g, '');
    return /^[a-z][a-z-]{0,30}$/.test(slug) ? slug : '';
  } catch {
    return '';
  }
}

// THE TOP BAR'S CLICKS (2026-10-23, Bill: count them, and order the bar by them around 20 Nov). Every page that
// counts carries the same bar, so one listener here counts all of them: `nav-<where it goes>`, with `-menu` when
// it was picked from the phone menu (a list is read top to bottom, a row left to right), and `nav-menu` when the
// menu is opened. Through window.goatcounter.count, the public call, so a test can see it; nothing identifies
// a person, and the bar's links carry no query to leak.
document.addEventListener('click', (ev) => {
  try {
    const el = ev.target instanceof Element ? ev.target : null;
    const nav = document.getElementById('site-nav');
    if (!el || !nav) return;
    let open = false;
    try {
      open = nav.matches(':popover-open'); // throws where popovers are unknown: then there is no menu
    } catch {
      open = false;
    }
    let name = '';
    if (el.closest('.menu-btn')) name = open ? '' : 'nav-menu'; // the click that opens it, not the one that shuts it
    else {
      const a = el.closest('#site-nav a[href]');
      const slug = a ? navSlug(a.getAttribute('href')) : '';
      if (slug) name = `nav-${slug}${open ? '-menu' : ''}`;
    }
    if (name) window.goatcounter?.count?.({ path: `event/${name}`, title: name, event: true });
  } catch {
    /* analytics must never break the page */
  }
});

// THE EMAIL BUTTONS (2026-10-23, Bill: count them before deciding whether a "book a demo" page is worth building).
// Counted as `email-<page>-<what>`, the what from this ALLOW-LIST of our own fixed subjects and never from the link
// itself: the full map's correction link puts the visitor's postcode in its subject, so a subject is never sent,
// only the name it maps to. No subject is `support`, a correction is `correction`, anything unlisted is `other`;
// front-page.mjs 16e fails if a page a buyer writes from carries a fixed subject this list does not know. A link
// with its own `data-event` is SKIPPED: /pricing has counted seven of its buttons that way (`pricing-pilot-cta`...)
// with its own script, and counting them twice would double the very clicks this exists to read.
const EMAIL_SUBJECTS = {
  'Area summary': 'area-summary',
  'Reports for a firm': 'reports-for-a-firm',
  'Area study for a council': 'council-area-study',
  '90-day pilot for a council': 'council-pilot',
  'Annual licence for a council': 'council-licence',
  'Sky Score 90-day pilot': 'api-pilot',
  'Sky Score Professional tier': 'api-professional',
  'Sky Score Enterprise licence': 'api-enterprise',
  'Sky Score API integration': 'api-integration',
  'Sky Score API status': 'api-status',
};

/** A mailto link's counted name ('support', 'correction', an allow-listed name or 'other'); '' for any other link. */
export function emailName(href) {
  try {
    const url = new URL(href);
    if (url.protocol !== 'mailto:') return '';
    const subject = (url.searchParams.get('subject') || '').trim();
    if (!subject) return 'support';
    if (/^correction\b/i.test(subject)) return 'correction';
    return EMAIL_SUBJECTS[subject] || 'other';
  } catch {
    return '';
  }
}

/** The page a click came from: the first part of its path ('/api/' -> 'api', '/pricing' -> 'pricing'), else 'home'. */
function pageSlug() {
  const first = (location.pathname.split('/').filter(Boolean)[0] || '').replace(/\.html$/, '');
  return /^[a-z][a-z-]{0,30}$/.test(first) ? first : 'home';
}

document.addEventListener('click', (ev) => {
  try {
    const a = ev.target instanceof Element ? ev.target.closest('a[href^="mailto:"]:not([data-event])') : null;
    const what = a ? emailName(a.getAttribute('href')) : '';
    if (!what) return;
    const name = `email-${pageSlug()}-${what}`;
    window.goatcounter?.count?.({ path: `event/${name}`, title: name, event: true });
  } catch {
    /* analytics must never break the page */
  }
});

// THE ABOUT PAGE'S FILM AND PROTOTYPE (2026-10-24, Bill: count them, to learn whether anyone watches the hackathon
// film or tries the 3D prototype before either is used to market anything). Counted as `<page>-<what>`, the what
// from this ALLOW-LIST of exact destinations, so only these links count and nothing is read from the link itself.
// front-page.mjs 16f clicks every link on /about/ and fails if any other link counts, or either of these does not.
const WATCHED_LINKS = {
  'https://youtu.be/xbR9cP4Ad4A': 'film',
  '/prototype/': 'prototype',
};

/** A watched link's counted name ('film', 'prototype'); '' for any other link. */
export function watchedName(href) {
  return Object.prototype.hasOwnProperty.call(WATCHED_LINKS, href) ? WATCHED_LINKS[href] : '';
}

document.addEventListener('click', (ev) => {
  try {
    const a = ev.target instanceof Element ? ev.target.closest('a[href]') : null;
    const what = a ? watchedName(a.getAttribute('href')) : '';
    if (!what) return;
    const name = `${pageSlug()}-${what}`;
    window.goatcounter?.count?.({ path: `event/${name}`, title: name, event: true });
  } catch {
    /* analytics must never break the page */
  }
});

// THE BOOK A DEMO BUTTON (2026-10-29, Bill: on /pricing, /api/ and /score-demo/ only; the site-wide bar waits on the
// ~20 Nov read of the bar's clicks). DEMO_BOOKING_URL is the ONE holder of the booking link: every page's link must
// read exactly this (tests/test_demo_booking_link.py), and while it is the placeholder `make booking-link-check`, which
// web-deploy and demo-deploy run first, refuses to deploy. Counted by that exact destination, like WATCHED_LINKS, as
// `book-demo-<page>-<where>`: `bar` from the top bar's row, `bar-menu` from the phone menu, `page` from the page's own
// line, so the read says which placement earned the booking. The pages' own listeners count `data-event` links only,
// and the booking links carry none, so each click is counted once (front-page.mjs 16g clicks every one).
export const DEMO_BOOKING_URL = 'https://calendly.com/bilalkhizar-skyscore/30min';

/** Where a booking link sits: 'bar', 'bar-menu' (the phone menu, open), the spot a page with several names on the
 *  link (`data-book-place`, 2026-10-30: the front page's line is `who`, so a second spot there would read apart), or
 *  'page'. A spot is a short lower-case word, never free text. */
function bookingPlace(a) {
  const nav = a.closest('#site-nav');
  if (!nav) {
    const spot = a.getAttribute('data-book-place') || '';
    return /^[a-z]{2,12}$/.test(spot) ? spot : 'page';
  }
  try {
    return nav.matches(':popover-open') ? 'bar-menu' : 'bar';
  } catch {
    return 'bar'; // popovers unknown: the plain bar, which has no menu
  }
}

document.addEventListener('click', (ev) => {
  try {
    const a = ev.target instanceof Element ? ev.target.closest('a[href]') : null;
    if (!a || a.getAttribute('href') !== DEMO_BOOKING_URL) return;
    const name = `book-demo-${pageSlug()}-${bookingPlace(a)}`;
    window.goatcounter?.count?.({ path: `event/${name}`, title: name, event: true });
  } catch {
    /* analytics must never break the page */
  }
});

// One page view, when the page is visible (a prerendered page counts when it is shown).
if (document.visibilityState === 'visible' || !('visibilityState' in document)) count();
else {
  const onShow = () => {
    if (document.visibilityState !== 'visible') return;
    document.removeEventListener('visibilitychange', onShow);
    count();
  };
  document.addEventListener('visibilitychange', onShow);
}

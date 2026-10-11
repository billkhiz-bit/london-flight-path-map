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

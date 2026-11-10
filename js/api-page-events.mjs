// /api/'s own click counts (Wave 12.7: B2B funnel events), moved out of an inline <script> so the page's policy can refuse
// inline script (audit M-8, 2026-11-09): /api/ now writes typed text and API answers into the page, and an inline tracker
// was the one reason it still allowed `'unsafe-inline'` for scripts. Unchanged in what it counts.
//
// Methodology clicks signal real diligence (someone reading the maths vs just kicking tyres). Demo/spec clicks signal
// someone wanting to actually try or integrate. UTM parameters in incoming traffic flow through to the GoatCounter
// referrer log automatically; see OUTREACH_DRAFTS.md for the per-prospect convention. Counting goes through
// window.goatcounter.count, which js/count.mjs provides (never GoatCounter's own script).

function trackEvent(name) {
  try {
    if (window.goatcounter && typeof window.goatcounter.count === 'function') {
      window.goatcounter.count({ path: `event/${name}`, title: name, event: true });
    }
  } catch {
    /* never break the UI for analytics */
  }
}

document.addEventListener('click', (e) => {
  const a = e.target instanceof Element ? e.target.closest('a') : null;
  if (!a) return;
  if (a.hasAttribute('data-event')) {
    trackEvent(a.getAttribute('data-event'));
    return;
  }
  const href = a.getAttribute('href') || '';
  if (href.includes('METHODOLOGY.md')) trackEvent('api-methodology-click');
  else if (href.includes('LICENSING.md')) trackEvent('api-licensing-click');
  else if (href === '/score-demo/' || href.startsWith('/score-demo/?')) trackEvent('api-demo-click');
  else if (href.includes('api-docs.html')) trackEvent('api-spec-click');
});

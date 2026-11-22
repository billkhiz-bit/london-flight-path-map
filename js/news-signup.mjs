// NEWS BY EMAIL (Bill, 2026-11-22; mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6, colour A). The front page's
// strip under the hero (home/index.html #news): one form, the button is the consent, and after a real search ONE
// unticked box adds that postcode. It joins through /v1/signup (source 'updates'), which emails a confirmation link
// first and adds nobody until it is pressed. It grew out of the area updates card built 2026-11-10 (Bill's pick A then),
// which it replaces: one form on the page, not two.
//
// The words are the Lambda's, word for word (backend/lambdas/signup/app.py NEWS_PROMISE and AREA_PROMISE, stored with
// every member as what they agreed to; tests/test_news_flags.py holds them, and the strip's own text, equal). Change
// one, change all, and the Lambda's NEWS_CONSENT_VERSION.
export const PROMISE = 'News by email. New cities and new data. At most one email a month.';
export const AREA_LINE = 'Also tell me when the figures for {postcode} change.';

/** A full UK postcode, exactly as the Lambda checks it (`UK_POSTCODE` in backend/lambdas/signup/app.py, after its
 *  strip and upper-case; tests/news-signup.mjs holds the two equal): an outcode or a place name offers no box. */
export const FULL_POSTCODE = /^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$/;

/** As the box shows and sends it: trimmed, upper case, one space at most. */
export const normalisePostcode = (postcode) => String(postcode ?? '').trim().toUpperCase().replace(/\s+/g, ' ');

/** Ask to join: the address goes in the POST body, never a URL. `postcode` is '' for news only. Resolves to
 *  { ok, message } in words for the visitor; never throws. `fetchFn` is the browser's fetch, replaceable in tests. */
export async function requestNews(apiBase, email, postcode = '', fetchFn = globalThis.fetch) {
  const address = String(email || '').trim();
  if (!address || !address.includes('@')) return { ok: false, message: 'Enter your email address so we know where to send the link.' };
  const pc = normalisePostcode(postcode);
  try {
    const res = await fetchFn(`${apiBase}/v1/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: address, source: 'updates', postcode: FULL_POSTCODE.test(pc) ? pc : '' }),
    });
    if (res.status === 201) return { ok: true, message: 'Check your inbox: we have sent a link to confirm. Nothing more comes until you press it.' };
    if (res.status === 429) return { ok: false, message: 'Busy just now. Wait a moment and try again.' };
    const data = await res.json().catch(() => ({}));
    return { ok: false, message: typeof data.error === 'string' && data.error ? data.error : 'That did not go through. Try again in a moment.' };
  } catch {
    return { ok: false, message: 'That did not go through. Check your connection and try again.' };
  }
}

/** Offer the postcode box for the place the visitor searched, or hide it ('' or anything short of a full postcode).
 *  A NEW place starts unticked: a tick given for one postcode never carries to another. */
export function offerPostcode(root, postcode) {
  const row = root && root.querySelector('#news-pc-row');
  if (!row) return;
  const pc = normalisePostcode(postcode);
  const offer = FULL_POSTCODE.test(pc);
  const name = row.querySelector('#news-pc-name');
  const box = row.querySelector('#news-pc');
  const moved = name.textContent !== (offer ? pc : '');
  if (!offer || moved) box.checked = false;
  name.textContent = offer ? pc : '';
  row.hidden = !offer;
  // A new place is a new question: last answer's line goes, and the button is offered again (code review 2026-11-22:
  // "Check your inbox" sat under the next postcode's box, reading as though it had been asked for).
  if (moved) afresh(root);
}

/** Clear the result line and, after a sign-up went through, offer the button again. Never while one is on its way. */
function afresh(root) {
  const form = root.querySelector('#news-form');
  const out = root.querySelector('#news-result');
  if (out) out.textContent = '';
  if (form && form.dataset.sent) {
    delete form.dataset.sent;
    form.querySelector('button[type=submit]').disabled = false;
  }
}

/** Bind the strip once. `count(name)` records only that it was used (never the address or the postcode).
 *  The button ships DISABLED in the page (code review 2026-11-22): without this module the form would post the address
 *  to the site itself, which the privacy text does not name, so it can be pressed only once this has bound it.
 *  After a sign-up goes through it stays off until the address or the box changes: a second press would send a second
 *  confirmation email and spend the inbox's daily allowance. */
export function wireNews(root, { apiBase, count = () => {}, fetchFn } = {}) {
  const form = root && root.querySelector('#news-form');
  if (!form || form.dataset.wired) return;
  form.dataset.wired = '1';
  const out = root.querySelector('#news-result');
  const button = form.querySelector('button[type=submit]');
  const email = form.querySelector('input[type=email]');
  button.disabled = false;
  email.addEventListener('input', () => afresh(root));
  root.querySelector('#news-pc')?.addEventListener('change', () => afresh(root));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (button.disabled) return;
    const row = root.querySelector('#news-pc-row');
    const ticked = row && !row.hidden && root.querySelector('#news-pc').checked;
    const postcode = ticked ? root.querySelector('#news-pc-name').textContent : '';
    button.disabled = true;
    out.textContent = 'Sending...';
    count('news-requested');
    const result = await requestNews(apiBase, email.value, postcode, fetchFn);
    out.textContent = result.message;
    if (result.ok) {
      count('news-link-sent');
      form.dataset.sent = '1';
    } else {
      button.disabled = false;
    }
  });
}

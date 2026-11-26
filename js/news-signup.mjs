// NEWS BY EMAIL (Bill, 2026-11-22; mock-up claude.ai/artifact/XFr75aGp5ziqBEeFFNCCmu v6, colour A). The front page's
// strip under the hero (home/index.html #news): one form, the button is the consent. It joins through /v1/signup
// (source 'updates'), which emails a confirmation link first and adds nobody until it is opened.
//
// NEWS ONLY since news-v2 (Bill's pick the same evening, claude.ai/artifact/8v4FMpDJ9Eq8N24zEGhVHz): the postcode tick
// box is gone. The page opens on an example and suggests places, so most searches are someone looking around, and two
// offers in one strip confused. Following a place may come back from the full map's result, as its own version.
//
// After pressing, the strip says where the link went (the address mostly hidden), what to do if it is not there, and
// offers ONE way to send it again and one to change the address. The Lambda sends at most three a day to one inbox
// (SEND_CAP_PER_DAY) and answers a capped request with the same 201 as a real send, so the page counts its own sends and
// says so in words after the third: it never claims a send it cannot know happened.
//
// The words are the Lambda's, word for word (backend/lambdas/signup/app.py NEWS_PROMISE, stored with every member as
// what they agreed to; tests/test_news_flags.py holds them, and the strip's own text, equal). Change one, change both,
// and the Lambda's NEWS_CONSENT_VERSION.
export const PROMISE = 'News by email. New cities and new data. At most one email a month.';

/** Sends one page may ask for: the Lambda's SEND_CAP_PER_DAY (tests/news-signup.mjs reads it from app.py). */
export const SENDS_PER_DAY = 3;

/** The address as the strip shows it after sending: its first letter, then dots, then the domain in full, so the person
 *  can tell which address it went to and a passer-by learns little. */
export function maskAddress(address) {
  const text = String(address || '').trim();
  const at = text.lastIndexOf('@');
  if (at < 1) return '';
  return `${text.slice(0, 1)}•••••${text.slice(at)}`;
}

/** The same address as a screen reader should say it (audit M-20, 2026-11-25): the dots were read aloud as "bullet bullet
 *  bullet". The masked form stays on screen, hidden from the reader; this goes beside it, hidden from the eye. */
export function spokenAddress(address) {
  const text = String(address || '').trim();
  const at = text.lastIndexOf('@');
  if (at < 1) return '';
  return `your address beginning ${text.slice(0, 1)}, at ${text.slice(at + 1)}`;
}

// The inbox an address reaches, as the Lambda counts its three sends a day (signup/app.py mailbox_key, audit M-6,
// 2026-11-25): lower case, any +tag dropped, and Gmail's dots ignored. "Use a different address" reset the page's count,
// so typing the same inbox again let the strip offer sends the Lambda then skipped while it said "Sent again".
// backend/tests/test_mailbox_key_parity.py holds this equal to the Lambda's on the same addresses.
export const DOT_BLIND_DOMAINS = { 'gmail.com': 'gmail.com', 'googlemail.com': 'gmail.com' };
export function mailboxKey(address) {
  const text = String(address || '').trim().toLowerCase();
  const at = text.lastIndexOf('@');
  if (at < 0) return text;
  let local = text.slice(0, at).split('+', 1)[0];
  let domain = text.slice(at + 1);
  if (Object.hasOwn(DOT_BLIND_DOMAINS, domain)) {
    local = local.replaceAll('.', '');
    domain = DOT_BLIND_DOMAINS[domain];
  }
  return `${local}@${domain}`;
}

/** Ask to join: the address goes in the POST body, never a URL, and nothing else goes with it. Resolves to
 *  { ok, message } in words for the visitor; never throws. `fetchFn` is the browser's fetch, replaceable in tests. */
export async function requestNews(apiBase, email, fetchFn = globalThis.fetch) {
  const address = String(email || '').trim();
  if (!address || !address.includes('@')) return { ok: false, message: 'Enter your email address so we know where to send the link.' };
  try {
    const res = await fetchFn(`${apiBase}/v1/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: address, source: 'updates' }),
    });
    if (res.status === 201) return { ok: true, message: '' };
    if (res.status === 429) return { ok: false, message: 'Busy just now. Wait a moment and try again.' };
    const data = await res.json().catch(() => ({}));
    return { ok: false, message: typeof data.error === 'string' && data.error ? data.error : 'That did not go through. Try again in a moment.' };
  } catch {
    return { ok: false, message: 'That did not go through. Check your connection and try again.' };
  }
}

/** Bind the strip once. `count(name)` records only that it was used (never the address).
 *  The button ships DISABLED in the page (code review 2026-11-22): without this module the form would post the address
 *  to the site itself, which the privacy text does not name, so it can be pressed only once this has bound it. */
export function wireNews(root, { apiBase, count = () => {}, fetchFn } = {}) {
  const form = root && root.querySelector('#news-form');
  if (!form || form.dataset.wired) return;
  form.dataset.wired = '1';
  const out = root.querySelector('#news-result');
  const button = form.querySelector('button[type=submit]');
  const email = form.querySelector('input[type=email]');
  const sent = root.querySelector('#news-sent');
  const to = root.querySelector('#news-sent-to');
  const again = root.querySelector('#news-again');
  const other = root.querySelector('#news-other');
  const said = root.querySelector('#news-again-said');
  let address = '';
  let sends = 0;
  // Sends this page has made, by inbox (M-6): "Use a different address" starts a new address, never a new count.
  const sentTo = new Map();
  button.disabled = false;
  email.addEventListener('input', () => { out.textContent = ''; });

  const showSent = () => {
    // Masked on screen, said in words to a screen reader (M-20).
    const shown = Object.assign(document.createElement('span'), { textContent: maskAddress(address) });
    shown.setAttribute('aria-hidden', 'true');
    const spoken = Object.assign(document.createElement('span'), { className: 'sr', textContent: spokenAddress(address) });
    to.replaceChildren(shown, spoken);
    said.textContent = '';
    again.hidden = sends >= SENDS_PER_DAY;
    form.hidden = true;
    sent.hidden = false;
    // Focus moves to the panel's heading: a keyboard or screen reader user lands on what just changed.
    root.querySelector('#news-sent-h')?.focus();
  };

  // The first press is busy through aria-disabled too (code review 2026-11-24): M-11 fixed "Send it again" but this button
  // still went `disabled` while it sent, so on any failure (busy, offline) a keyboard user was left on <body> beside the
  // message. It ships `disabled` only until this module binds it (above).
  let sending = false;
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (sending || button.disabled) return;
    if ((sentTo.get(mailboxKey(email.value)) || 0) >= SENDS_PER_DAY) {
      // This page has already sent this inbox the most the Lambda sends in a day; sending would answer 201 and send nothing.
      out.textContent = 'We have sent that address three links today, the most we send. Look in Junk or Spam, or come back tomorrow.';
      return;
    }
    sending = true;
    button.setAttribute('aria-disabled', 'true');
    out.textContent = 'Sending...';
    count('news-requested');
    const result = await requestNews(apiBase, email.value, fetchFn);
    sending = false;
    button.removeAttribute('aria-disabled');
    if (!result.ok) {
      out.textContent = result.message;
      return;
    }
    out.textContent = '';
    address = email.value.trim();
    sends = (sentTo.get(mailboxKey(address)) || 0) + 1;
    sentTo.set(mailboxKey(address), sends);
    count('news-link-sent');
    showSent();
  });

  // BUSY, NOT `disabled` (audit M-11, 2026-11-23): a focused button that becomes disabled loses focus to <body>
  // (Chromium's focus fixup), so every press of "Send it again" dropped a keyboard user's place while it sent.
  // aria-disabled says the same to a screen reader and keeps focus where it was.
  let busy = false;
  again.addEventListener('click', async () => {
    if (busy || sends >= SENDS_PER_DAY) return;
    busy = true;
    again.setAttribute('aria-disabled', 'true');
    said.textContent = 'Sending...';
    count('news-resend');
    const result = await requestNews(apiBase, address, fetchFn);
    busy = false;
    again.removeAttribute('aria-disabled');
    if (!result.ok) {
      said.textContent = result.message;
      return;
    }
    sends += 1;
    sentTo.set(mailboxKey(address), sends);
    if (sends >= SENDS_PER_DAY) {
      // Hiding the button that has focus dropped focus to <body> (audit M-11, 2026-11-23: WCAG 2.4.3), at the moment
      // the strip says "three today". Focus goes to what is left to do: a different address.
      const hadFocus = again.ownerDocument.activeElement === again;
      again.hidden = true;
      if (hadFocus) other.focus();
      said.textContent = 'Sent again. That is three today, the most we send to one address. If none arrives, try a different address or come back tomorrow.';
    } else {
      said.textContent = 'Sent again.';
    }
  });

  other.addEventListener('click', () => {
    sent.hidden = true;
    form.hidden = false;
    email.value = '';
    address = '';
    sends = 0; // the next address's count comes from sentTo when it is sent (M-6)
    email.focus();
  });
}

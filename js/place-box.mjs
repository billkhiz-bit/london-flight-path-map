// The postcode box's suggestions (Bill's pick B of the mock-up, 2026-11-04; it replaces a native <datalist>): a first click
// shows one of each kind of thing the box takes, typing lists the places it answers by name and says what each is, and a
// full postcode is offered as itself. Places come from what the page already holds, so a place name is not sent while typing.
// A search is made only when the visitor chooses one or presses Check. The list is a WAI-ARIA combobox, so Up, Down, Enter and
// Escape do what a screen reader says they do.
//
// THE START OF A POSTCODE IS ASKED ABOUT (Bill's yes, 2026-11-05: "as the full map has them"). The page cannot hold 1.8 million
// postcodes, so after a pause, text shaped like the start of one goes to postcodes.io, as privacy s2b says of the search box.
// Nothing else is sent while typing, nothing typed is stored or counted, and with no answer the box still takes any postcode.

// The example both pages open on, HELD so that arriving asks postcodes.io nothing: the privacy policy covers a postcode someone
// searches, not a lookup nobody asked for. postcodes.io's own answer (tests/place-box.mjs holds it to the one on file).
export const EXAMPLE = { postcode: 'TW9 3PZ', latitude: 51.476982, longitude: -0.285639, admin_district: 'Richmond upon Thames' };

export const POSTCODE = /^[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}$/i;
const PARTLY = /^[a-z]{1,2}\d/i;
// The start of a postcode from end to end, so "b1 flat 3, high street" is not sent while typing.
const STARTING = /^[a-z]{1,2}\d[a-z\d]?(\s*\d[a-z]{0,2})?$/i;
const PAUSE_MS = 250; // the full map's

/** Whether the text in the box may be asked about: the start of a postcode, and not yet a whole one. */
export const askable = (text) => STARTING.test(text.trim()) && !POSTCODE.test(text.trim());

/** The postcodes starting with this text. postcodes.io answers 200 with a null result when it knows none. */
export async function postcodeCompletions(text, signal) {
  const res = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(text.replace(/\s+/g, '').toUpperCase())}/autocomplete`, { signal });
  if (!res.ok) return [];
  const body = await res.json();
  return Array.isArray(body?.result) ? body.result : [];
}

// What was typed, picked out of a postcode whose space it may not have.
function typedPart(value, text) {
  const want = text.replace(/\s+/g, '').length;
  let end = 0;
  for (let seen = 0; end < value.length && seen < want; end += 1) if (value[end] !== ' ') seen += 1;
  return ['', value.slice(0, end), value.slice(end)];
}

/**
 * What to offer for the text in the box: { items: [{ value, parts, note }], foot }. `postcodes` are those found for this text.
 * A `postcodeBox` takes nothing else, so it offers real choices only (a hint would only sit in the way of its button) and
 * names no kind (every option is the same one, and at 320 wide the word pushes the postcode onto two lines).
 * Pure, so it can be tested.
 */
export function suggest(text, places, examples, { postcodes = [], limit = 6, postcodeBox = false } = {}) {
  const q = text.trim();
  if (!q) return examples.length ? { heading: 'Try one', items: examples.map((e) => ({ value: e.value, parts: [e.value, '', ''], note: e.note })) } : { items: [] };
  if (POSTCODE.test(q)) return postcodeBox ? { items: [] } : { items: [{ value: q.toUpperCase(), parts: ['Check ', q.toUpperCase(), ''], note: 'press Enter' }] };
  const lower = q.toLowerCase();
  const starts = places.filter((p) => p.name.toLowerCase().startsWith(lower));
  const inside = places.filter((p) => !p.name.toLowerCase().startsWith(lower) && p.name.toLowerCase().includes(lower));
  const named = [...starts, ...inside].map((p) => {
    const at = p.name.toLowerCase().indexOf(lower);
    return { value: p.name, parts: [p.name.slice(0, at), p.name.slice(at, at + q.length), p.name.slice(at + q.length)], note: p.kind };
  });
  const items = [...named, ...postcodes.map((value) => ({ value, parts: typedPart(value, q), note: postcodeBox ? '' : 'Postcode' }))].slice(0, limit);
  if (items.length) return { items };
  if (postcodeBox) return { items: [] };
  return { items: [], foot: PARTLY.test(q) ? 'Keep typing the full postcode, like SW5 9HP.' : 'No place by that name yet. A full postcode works anywhere we cover.' };
}

/**
 * Wires the box to its list. `places` may be swapped later with the returned setter, once the page has its rows.
 * `lookup(text, signal)`, if given, finds the postcodes starting with the text; `postcodeBox` is suggest()'s.
 */
export function bindPlaceBox(input, list, examples, onChoose, { lookup = null, postcodeBox = false } = {}) {
  const doc = input.ownerDocument;
  let places = [];
  let active = -1;
  let found = { text: '', postcodes: [] }; // what the lookup gave, and for which text
  let waiting = null; // the pause before asking
  let asking = null; // the request on its way
  const options = () => [...list.querySelectorAll('[role="option"]')];
  // Ends whatever is waiting or on its way. The status goes too, so the same words are announced again next time.
  const hush = () => {
    clearTimeout(waiting);
    asking?.abort();
    live.textContent = '';
  };
  const close = () => {
    hush();
    list.hidden = true;
    active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  };
  const node = (tag, className, text) => {
    const n = doc.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;
    return n;
  };
  // The options arrive after the keystroke, so a screen reader is told. Beside the list, which is hidden when it is empty.
  const live = node('span', 'pc-live');
  live.setAttribute('role', 'status');
  list.after(live);
  const open = () => {
    const { heading, items, foot } = suggest(input.value, places, examples, { postcodes: found.text === input.value.trim() ? found.postcodes : [], postcodeBox });
    active = -1;
    input.removeAttribute('aria-activedescendant');
    const kids = [];
    if (heading) kids.push(node('p', 'pc-head', heading));
    items.forEach((item, i) => {
      const o = node('div', 'pc-opt');
      o.id = `pc-opt-${i}`;
      o.setAttribute('role', 'option');
      o.setAttribute('aria-selected', 'false');
      o.dataset.value = item.value;
      const name = node('span');
      name.append(item.parts[0], node('mark', null, item.parts[1]), item.parts[2]);
      o.append(name);
      if (item.note) o.append(node('small', null, item.note));
      kids.push(o);
    });
    if (foot) kids.push(node('p', 'pc-foot', foot));
    list.replaceChildren(...kids);
    list.hidden = !kids.length;
    input.setAttribute('aria-expanded', String(kids.length > 0));
  };
  const move = (by) => {
    const all = options();
    if (!all.length) return;
    active = (active + by + all.length) % all.length;
    all.forEach((o, i) => o.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', all[active].id);
    all[active].scrollIntoView({ block: 'nearest' });
  };
  // After a pause, so a postcode typed quickly is asked about once. Anything newer cancels what is waiting or on its way, so
  // the list only ever answers the text in the box. A failure changes nothing: the box still takes any postcode.
  const ask = () => {
    hush();
    const text = input.value.trim();
    if (!lookup || !askable(text) || found.text === text) return;
    waiting = setTimeout(async () => {
      const mine = new AbortController();
      asking = mine;
      try {
        const postcodes = await lookup(text, mine.signal);
        if (mine.signal.aborted) return;
        found = { text, postcodes };
        open();
        const n = options().length;
        live.textContent = n ? `${n} suggestion${n === 1 ? '' : 's'}.` : '';
      } catch { /* a help, never a failure */ }
    }, PAUSE_MS);
  };
  input.addEventListener('focus', open);
  input.addEventListener('click', () => { if (list.hidden) open(); });
  input.addEventListener('input', () => { open(); ask(); });
  input.addEventListener('blur', close);
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (list.hidden) open();
      move(ev.key === 'ArrowDown' ? 1 : -1);
    } else if (ev.key === 'Escape') {
      // Even with the list shut: a lookup may be waiting, and Escape must not be followed by a list opening.
      if (!list.hidden) ev.preventDefault();
      close();
    } else if (ev.key === 'Enter') {
      const chosen = options()[active];
      if (chosen) {
        ev.preventDefault();
        close();
        onChoose(chosen.dataset.value);
      } else {
        close();
      }
    }
  });
  // mousedown, not click: a click would blur the box and close the list before it landed.
  list.addEventListener('mousedown', (ev) => {
    ev.preventDefault();
    const chosen = ev.target.closest('[role="option"]');
    if (!chosen) return;
    close();
    onChoose(chosen.dataset.value);
  });
  return (next) => { places = next; };
}

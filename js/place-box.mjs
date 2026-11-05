// The postcode box's suggestions (Bill's pick B of the mock-up, 2026-11-04; it replaces a native <datalist>): a first click
// shows one of each kind of thing the box takes, typing lists the places it answers by name and says what each is, and a
// full postcode is offered as itself. All of it is read in the browser from what the page already holds: nothing typed is
// fetched, sent, stored or counted. A search is made only when the visitor chooses one or presses Check. The list is a
// WAI-ARIA combobox, so Up, Down, Enter and Escape do what a screen reader says they do.

export const NOTHING_SENT = 'Nothing you type is sent until you search.';
export const POSTCODE = /^[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}$/i;
const PARTLY = /^[a-z]{1,2}\d/i;

/** What to offer for the text in the box: { items: [{ value, parts, note }], foot }. Pure, so it can be tested. */
export function suggest(text, places, examples, limit = 6) {
  const q = text.trim();
  if (!q) return { heading: 'Try one', items: examples.map((e) => ({ value: e.value, parts: [e.value, '', ''], note: e.note })), foot: NOTHING_SENT };
  if (POSTCODE.test(q)) return { items: [{ value: q.toUpperCase(), parts: ['Check ', q.toUpperCase(), ''], note: 'press Enter' }] };
  const lower = q.toLowerCase();
  const starts = places.filter((p) => p.name.toLowerCase().startsWith(lower));
  const inside = places.filter((p) => !p.name.toLowerCase().startsWith(lower) && p.name.toLowerCase().includes(lower));
  const items = [...starts, ...inside].slice(0, limit).map((p) => {
    const at = p.name.toLowerCase().indexOf(lower);
    return { value: p.name, parts: [p.name.slice(0, at), p.name.slice(at, at + q.length), p.name.slice(at + q.length)], note: p.kind };
  });
  if (items.length) return { items };
  return { items: [], foot: PARTLY.test(q) ? 'Keep typing the full postcode, like SW5 9HP.' : 'No place by that name yet. A full postcode works anywhere we cover.' };
}

/** Wires the box to its list. `places` may be swapped later with the returned setter, once the page has its rows. */
export function bindPlaceBox(input, list, examples, onChoose) {
  const doc = input.ownerDocument;
  let places = [];
  let active = -1;
  const options = () => [...list.querySelectorAll('[role="option"]')];
  const close = () => {
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
  const open = () => {
    const { heading, items, foot } = suggest(input.value, places, examples);
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
  input.addEventListener('focus', open);
  input.addEventListener('click', () => { if (list.hidden) open(); });
  input.addEventListener('input', open);
  input.addEventListener('blur', close);
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (list.hidden) open();
      move(ev.key === 'ArrowDown' ? 1 : -1);
    } else if (ev.key === 'Escape' && !list.hidden) {
      ev.preventDefault();
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

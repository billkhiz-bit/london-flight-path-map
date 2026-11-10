// Where one value sits among others, highest first, with a tie said as a tie (audit M-16, 2026-11-09). The outreach
// sheets ranked by a sort's position, and a sort leaves equal values in the list's order: Hammersmith and Fulham, level
// with Newham at 20.4 ug/m3 of NO2, was printed "11th-highest" though nothing in the data puts it below Newham.

/** { rank, tied, of } for `value` among `values` (numbers, highest first): rank is 1 + how many are strictly higher. */
export function placeAmong(values, value) {
  const above = values.filter((v) => v > value).length;
  const level = values.filter((v) => v === value).length;
  return { rank: above + 1, tied: level > 1, of: values.length };
}

export function ordinal(n) {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

/** "10th", or "joint 10th" when another value is level with it. */
export function placeWords(place) {
  return `${place.tied ? 'joint ' : ''}${ordinal(place.rank)}`;
}

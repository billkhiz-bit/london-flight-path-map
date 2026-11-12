// The full map's panel leads with its findings, and every section it had sits in the "All the detail" fold (#panel-all,
// 2026-11-04). A test of what is IN a section reads it open, as a reader who opened it would: a closed <details> keeps
// its text out of innerText, so the section would read empty and prove nothing. What the panel shows before anything
// is opened is held in tests/uk-city-panel.mjs, "Findings first", on a page that does not call this.

/**
 * Keeps the fold, the answer card's score, every finding's tile (2026-11-08: closed until tapped), the fold's cards
 * (2026-11-09) and the air charts' "About these readings" open on a page or a whole context.
 */
export function keepPanelOpen(target) {
  return target.addInitScript(() => {
    new MutationObserver(() => {
      const fold = document.getElementById('panel-all');
      if (fold && !fold.open) fold.open = true;
      const score = document.getElementById('ac-score');
      if (score && !score.open) score.open = true;
      for (const tile of document.querySelectorAll('#sidebar-content details.tile:not([open])')) tile.open = true;
      // "All the detail"'s cards (2026-11-09): each list the loaders fill sits in one, closed until tapped.
      for (const card of document.querySelectorAll('#panel-all details.dcard:not([open]), #panel-all details.drow:not([open])')) card.open = true;
      for (const about of document.querySelectorAll('#postcode-air-section details:not([open])')) about.open = true;
    }).observe(document, { childList: true, subtree: true });
  });
}

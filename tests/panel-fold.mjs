// The full map's panel leads with its findings, and every section it had sits in the "All the detail" fold (#panel-all,
// 2026-11-04). A test of what is IN a section reads it open, as a reader who opened it would: a closed <details> keeps
// its text out of innerText, so the section would read empty and prove nothing. What the panel shows before anything
// is opened is held in tests/uk-city-panel.mjs, "Findings first", on a page that does not call this.

/** Keeps the fold, and the air charts' "About these readings", open on a page or a whole context. */
export function keepPanelOpen(target) {
  return target.addInitScript(() => {
    new MutationObserver(() => {
      const fold = document.getElementById('panel-all');
      if (fold && !fold.open) fold.open = true;
      for (const about of document.querySelectorAll('#postcode-air-section details:not([open])')) about.open = true;
    }).observe(document, { childList: true, subtree: true });
  });
}

/**
 * THE ANSWER AS A HEADLINE: one sentence for one place, wherever the site says it (moved here 2026-11-08 from
 * js/home-sections.mjs, so the full map's answer card can say exactly what the front page says without loading the
 * front page's modules). js/home-sections.mjs re-exports it, so its callers and tests are unchanged.
 */
import { planesBandLead, planesLead } from './planes.mjs';

const finite = (v) => typeof v === 'number' && Number.isFinite(v);

/**
 * OPTION C, the answer as the headline (review prototype, 2026-11-07; ROADMAP "answer first", option C; Bill's calls on
 * the review the same day): the hero's h1 for an answer on show, so the first thing read is what this place is like, or
 * null to keep the question. In order, the first that has something true to say:
 *   1. the planes, from planesLead() (js/planes.mjs, the one writer of how often planes pass), where the full map's planes
 *      layer would colour the figure (`steps`, from layerSteps()): "On most days, about 310 Heathrow planes a day pass
 *      over TW9 3PZ" (Bill: planes first);
 *   2. DEFRA's aircraft noise against its WHO guideline: "Aircraft noise at TW3 3QL is over the WHO guideline". Ahead of
 *      the quiet band below, so a postcode a little off a flight path, few planes overhead but inside DEFRA's contour, is
 *      never headlined as quiet;
 *   3. the planes again, as the band the layer leaves blank, from planesBandLead(): "Fewer than ... Heathrow planes a day
 *      pass over SW5 9HP" (Bill: answer the planes question before road noise);
 *   4. DEFRA's road noise against its WHO guideline, a surveyed-quiet bound counting as under it, as the full map's panel
 *      words it (js/panel-findings.mjs roadFinding), and ONLY where we hold no planes data for the postcode at all.
 * Air never leads: the WHO 2021 guidelines sit under the modelled figure almost everywhere in the UK, so "over" would say
 * nothing about this place in particular. The routes' estimate never leads either: it is a score, not a finding against a
 * yardstick. Words only, then the figures under it say how much: a headline carries no number of its own but the planes'.
 * No caveat can ride in a headline, so anything whose caveat changes its meaning is left to the answer below.
 */
export function answerLead(e, postcode, model = null, steps = []) {
  const planes = planesLead(model, steps);
  if (planes) return planes;
  if (!e || !postcode) return null;
  const side = (v, who) => (v > who ? 'is over' : v < who ? 'is under' : 'is level with');
  if (finite(e.aircraftNoiseLdenDb) && finite(e.aircraftNoiseWhoGuidelineDb)) {
    return `Aircraft noise at ${postcode} ${side(e.aircraftNoiseLdenDb, e.aircraftNoiseWhoGuidelineDb)} the WHO guideline`;
  }
  const band = planesBandLead(model, steps);
  if (band) return band;
  // We hold planes figures here but none can lead: the planes question is answered below, never displaced by the roads.
  if (model) return null;
  if (finite(e.roadNoiseLdenDb) && finite(e.roadNoiseWhoGuidelineDb)) {
    return `Road noise at ${postcode} ${side(e.roadNoiseLdenDb, e.roadNoiseWhoGuidelineDb)} the WHO guideline`;
  }
  if (finite(e.roadNoiseBelowDb) && finite(e.roadNoiseWhoGuidelineDb) && e.roadNoiseBelowDb <= e.roadNoiseWhoGuidelineDb) {
    return `Road noise at ${postcode} is under the WHO guideline`;
  }
  return null;
}

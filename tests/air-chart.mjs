/**
 * The full map's air comparison chart (js/street_report.mjs airChart; Bill, 2026-11-03, "refined B" of the mock-ups at
 * claude.ai/artifact/6ysdR2AJvPbWhi8PR3UVGc), held without a browser: it is a pure function returning SVG text.
 *
 * What is held, each from the SVG the function returns (never from a flag it sets):
 *   - every mark sits TO SCALE: x0 + value / (4 x guideline) x width, and the WHO line at the guideline;
 *   - a reading beyond the scale sits at its end, keeps its own figure, and says so (text and tooltip);
 *   - a value label that would leave the picture moves to the mark's left; one in the middle stays right;
 *   - a source that does not measure the pollutant has no mark and says "not measured here";
 *   - DEFRA's model is a hollow ring, a sensor a filled circle, a monitor a square: shape, not colour alone;
 *   - every name is escaped, and a long one is shortened with the full name kept in the tooltip;
 *   - AIR_WHO_2021 equals the API's own guidelines in backend/lambdas/score/app.py (read, never retyped);
 *   - the sentence the front page and the reports print is unchanged by the period helpers it now uses.
 * Where the panel puts it, and the live figures it shows, is tests/uk-city-panel.mjs.
 *
 *   node tests/air-chart.mjs
 */
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const ROOT = process.cwd();
const m = await import(pathToFileURL(join(ROOT, 'js', 'street_report.mjs')).href);

let failures = 0;
let passed = 0;
const ok = (cond, name, detail = '') => {
  if (cond) {
    passed += 1;
    console.log(`  ok   ${name}`);
  } else {
    failures += 1;
    console.log(`  FAIL ${name}${detail ? `: ${detail}` : ''}`);
  }
};
const attr = (svg, name) => {
  const r = new RegExp(`${name}="([^"]*)"`).exec(svg);
  return r ? r[1] : null;
};
// Each row's group: kind, printed value, the mark's centre (data-cx) and the value label's anchor and text.
const groups = (svg) =>
  [...svg.matchAll(/<g data-kind="(\w+)" data-value="([^"]*)">([\s\S]*?)<\/g>(?=<g data-kind|<line data-axis)/g)].map(([, kind, value, inner]) => {
    const mark = /<g data-mark="(\w+)" data-cx="([\d.]+)">([\s\S]*?)<\/g>/.exec(inner);
    const label = [...inner.matchAll(/<text[^>]*text-anchor="(start|end)"[^>]*>([^<]*)<\/text>/g)].pop();
    const title = /<title>([^<]*)<\/title>/.exec(inner);
    return { kind, value, inner, cx: mark ? Number(mark[2]) : null, shape: mark ? mark[3] : '', anchor: label && label[1], text: label && label[2], title: title && title[1] };
  });

const ROWS = [
  { kind: 'model', label: "DEFRA's model", sub: 'this 1 km square · 2024', v: 20.8 },
  { kind: 'sensor', label: 'Chesterton Primary School', sub: 'sensor · 340 m', v: 22.5 },
  { kind: 'monitor', label: 'London Westminster', sub: 'monitor · 3.3 km', v: 20.1 },
];
const svg = m.airChart('no2', ROWS, 10);
const x0 = Number(attr(svg, 'data-x0'));
const x1 = Number(attr(svg, 'data-x1'));
const max = Number(attr(svg, 'data-max'));
ok(max === 10 * m.AIR_SCALE_TIMES && max === 40, 'the NO2 scale runs to 4x the guideline, 40 (also the UK legal limit)', String(max));
const at = (v) => x0 + (Math.min(v, max) / max) * (x1 - x0);
const g = groups(svg);
ok(g.length === 3 && g.map((r) => r.kind).join() === 'model,sensor,monitor', 'one row per source, in the order given', g.map((r) => r.kind).join());
ok(g.every((r, i) => Math.abs(r.cx - at(ROWS[i].v)) < 0.02), 'every mark sits to scale on the shared axis', g.map((r) => r.cx).join(', '));
ok(Math.abs(Number(/data-who="([\d.]+)"/.exec(svg)[1]) - at(10)) < 0.02, 'the WHO line sits at the guideline');
ok(g.every((r, i) => r.value === ROWS[i].v.toFixed(1) && r.text === ROWS[i].v.toFixed(1)), 'each row prints its own figure to one decimal', g.map((r) => r.text).join());
ok(/fill="none"/.test(g[0].shape) && /<circle/.test(g[0].shape), "DEFRA's model is a HOLLOW ring (modelled, not measured)", g[0].shape);
ok(/<circle/.test(g[1].shape) && !/fill="none"/.test(g[1].shape), 'a sensor is a filled circle', g[1].shape);
ok(/<rect/.test(g[2].shape), 'a monitor is a square', g[2].shape);
ok(g.every((r) => /× the WHO guideline of 10/.test(r.title || '')), 'each mark says, on hover, its multiple of the guideline');

// Beyond the scale, near the end, and missing.
const edge = groups(m.airChart('no2', [
  { kind: 'sensor', label: 'Marylebone Road', sub: 'sensor · 1 km', v: 52.3 },
  { kind: 'monitor', label: 'Near the end', sub: 'monitor · 2 km', v: 38 },
  { kind: 'model', label: "DEFRA's model", sub: 'this 1 km square · 2024', v: 12 },
  { kind: 'monitor', label: 'No PM here', sub: 'monitor · 3 km', v: null },
], 10));
ok(Math.abs(edge[0].cx - x1) < 0.02 && edge[0].text === '52.3 ▸' && /beyond this scale of 40/.test(edge[0].title),
  'a reading beyond the scale sits at its end, keeps its figure and says so', JSON.stringify({ cx: edge[0].cx, text: edge[0].text }));
ok(edge[0].anchor === 'end' && edge[1].anchor === 'end', 'a value label near the end moves to the mark\'s left', `${edge[0].anchor}, ${edge[1].anchor}`);
ok(edge[2].anchor === 'start', 'a value label in the middle stays on the right', edge[2].anchor);
ok(edge[3].cx === null && edge[3].value === '' && /not measured here/.test(edge[3].inner), 'a source without this pollutant has no mark and says "not measured here"');

// Words: escaped, shortened, and the zero edge.
const hostile = m.airChart('pm25', [{ kind: 'sensor', label: '<img src=x onerror=alert(1)> & a very long school name indeed', sub: '"quoted" <b>', v: 0 }], 5);
ok(!/<img|<b>/.test(hostile) && /&lt;img/.test(hostile), 'every name and line is escaped, never markup', hostile.slice(0, 0));
const hg = groups(hostile)[0];
ok(/…<\/text>/.test(hg.inner) && /a very long school name indeed/.test(hg.title), 'a long name is shortened in the row, whole in the tooltip');
ok(Math.abs(hg.cx - x0) < 0.02 && Number(attr(hostile, 'data-max')) === 20, 'zero sits at the axis start; the PM2.5 scale runs to 20');
ok(!/ fill="var\(| stroke="var\(/.test(svg + hostile), 'colours come through style, never a var() in an SVG attribute (not every browser reads those)');

// The guideline is the API's: read from the backend, never retyped.
const app = await readFile(join(ROOT, 'backend', 'lambdas', 'score', 'app.py'), 'utf8');
const lit = (k) => Number((new RegExp(`env\\['${k}'\\] = (\\d+(?:\\.\\d+)?)`).exec(app) || [])[1]);
ok(lit('no2WhoGuidelineUgm3') === m.AIR_WHO_2021.no2 && lit('pm25WhoGuidelineUgm3') === m.AIR_WHO_2021.pm25,
  'AIR_WHO_2021 equals the guidelines the API sends', `${lit('no2WhoGuidelineUgm3')}/${lit('pm25WhoGuidelineUgm3')} vs ${m.AIR_WHO_2021.no2}/${m.AIR_WHO_2021.pm25}`);

// The front page and the reports print the same sentences as before the period helpers.
const s = { name: 'X', to: '2026-09-30', classification: 'Urban Background', kerbDistanceM: 28, no2: { mean: 22.5 }, pm25: { mean: 8.6 } };
const mon = { name: 'Y', year: 2024, type: 'Urban Background', no2: { mean: 20.1 }, pm25: null };
ok(m.sensorReadings(s) === 'nitrogen dioxide 22.5 µg/m³ and fine particles 8.6 µg/m³ over the 12 months to September 2026', 'the sensor sentence is unchanged', m.sensorReadings(s));
ok(m.monitorReadings(mon) === 'nitrogen dioxide 20.1 µg/m³ in 2024', 'the monitor sentence is unchanged', m.monitorReadings(mon));
ok(m.sensorPeriod(s) === '12 months to September 2026' && m.monitorPeriod(mon) === '2024', 'the periods the map\'s key prints');

console.log(failures ? `FAIL: ${failures} of ${passed + failures} checks` : `air chart: ${passed} checks passed`);
process.exit(failures ? 1 : 0);

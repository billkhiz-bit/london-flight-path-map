/* Hydrate a static Stitch mockup with live Sky Score data.
 *
 * WHY A HYDRATOR AND NOT A REWRITE
 * --------------------------------
 * Two Stitch exports of the same dashboard differ in chrome (icon rail against
 * top nav) but agree on what they display. Rewriting each body by hand would
 * duplicate the same logic twice more and let the two drift, which is the
 * "second list of the same facts" failure this repo keeps paying for. So the
 * markup stays EXACTLY as Stitch produced it - that is the thing under
 * evaluation - and this script finds the pieces and drives them.
 *
 * It reports what it could not find, loudly and on the page. A hydrator that
 * silently does nothing looks identical to a design that simply has no data,
 * and telling those apart by eye is the failure mode this product is built to
 * avoid.
 */
(function () {
  'use strict';

  var DATA = '/data/';
  var GEO = '/design/airports-paths.json';
  var RAW = '/design/borough-raw.json';

  var CITIES = [
    ['london', 'London'], ['manchester', 'Greater Manchester'], ['westmidlands', 'West Midlands'],
    ['westyorkshire', 'West Yorkshire'], ['southyorkshire', 'South Yorkshire'],
    ['merseyside', 'Merseyside'], ['tyneandwear', 'Tyne and Wear'], ['bristol', 'Bristol'],
    ['leicester', 'Leicester'], ['teesside', 'Teesside'], ['nyc', 'New York']
  ];

  // The rows these mockups draw, mapped onto the fields we actually hold.
  // `invert` marks a row whose LABEL names a bad thing while our stored value
  // is a good-thing score, or vice versa - direction must follow the label, and
  // Stitch's "Aircraft Noise" over a quiet score is exactly that trap.
  // Each row is mapped to a value we ACTUALLY HOLD. Composite scores are the
  // Lambda's to compute - reimplementing the ramps here would make a third
  // scoring holder, which this repo has already paid for twice - so a composite
  // row shows its dominant measured INPUT and labels it as such. That is a
  // qualified real number rather than an invented score.
  var ROWS = {
    'quiet skies':    { kind: 'impact' },
    'aircraft noise': { kind: 'impact' },
    'affordability':  { kind: 'price' },
    'liveability':    { kind: 'input', field: 'transportWithin800mPct', dp: 1, unit: '% rail <800m', max: 100 },
    'environment':    { kind: 'input', field: 'airQualityWhoRatio',     dp: 2, unit: 'x WHO air',    max: 4 },
    'road noise':     { kind: 'input', field: 'roadNoiseAboveWhoPct',   dp: 1, unit: '% over WHO',   max: 100 },
    'air quality':    { kind: 'input', field: 'airQualityWhoRatio',     dp: 2, unit: 'x WHO',        max: 4 },
    'flood risk':     { kind: 'input', field: 'floodMediumOrHighPct',   dp: 2, unit: '% med/high',   max: 20 },
    'crime':          { kind: 'input', field: 'crimeRate',              dp: 1, unit: 'per 1,000',    max: 200 },
    'healthcare':     { kind: 'input', field: 'healthcareWithin1kmPct', dp: 1, unit: '% GP <1km',    max: 100 }
  };

  var IMPACT_PCT = { low: 15, 'low-moderate': 35, moderate: 55, 'moderate-high': 72, high: 85, severe: 96 };

  var LABEL_PX = { london: 6, nyc: 8 };
  var RAMP = ['#d7e5d2', '#a8c9a0', '#e3c778', '#e2924e', '#b8453a'];

  var state = { city: 'london', extra: null, geo: null, raw: null, sel: null, notes: [] };

  function note(msg) {
    state.notes.push(msg);
    // eslint-disable-next-line no-console
    console.warn('[hydrate] ' + msg);
  }

  function textOf(el) { return (el.textContent || '').trim().toLowerCase(); }
  function nameOf(f) { var p = f.properties || {}; return p.name || p.LAD13NM || p.NAME || ''; }
  function num(v) { return typeof v === 'number' && isFinite(v) ? v : null; }

  /* ---------------------------------------------------------------- map --- */

  // The map is a div whose background-image points at Google's generated
  // imagery. Found by inspecting computed style rather than by a selector,
  // because the two exports name it differently.
  function findMapEl() {
    var best = null, bestArea = 0;
    var all = document.querySelectorAll('div, section, figure');
    for (var i = 0; i < all.length; i++) {
      var bg = getComputedStyle(all[i]).backgroundImage || '';
      if (bg.indexOf('googleusercontent') === -1) continue;
      var r = all[i].getBoundingClientRect();
      var area = r.width * r.height;
      if (area > bestArea) { best = all[i]; bestArea = area; }
    }
    return best;
  }

  function renderMap(host) {
    var w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    host.style.backgroundImage = 'none';
    host.style.backgroundColor = '#e4e3e0';
    host.style.position = host.style.position || 'relative';

    var old = host.querySelector('svg[data-hydrated]');
    if (old) old.remove();

    var svg = d3.select(host).append('svg')
      .attr('data-hydrated', '1')
      .attr('width', w).attr('height', h)
      .style('position', 'absolute').style('inset', '0')
      .style('display', 'block');

    d3.json(DATA + state.city + '-boroughs.json').then(function (gj) {
      var fc = (gj && gj.type === 'FeatureCollection') ? gj : { type: 'FeatureCollection', features: gj };
      var recs = (state.extra && state.extra[state.city]) || {};
      var proj = d3.geoMercator().fitExtent([[16, 16], [w - 16, h - 16]], fc);
      var path = d3.geoPath(proj);

      // Shade by air quality where we hold it; a borough without a reading is
      // drawn hollow, never given a mid-range colour.
      var vals = [];
      fc.features.forEach(function (f) {
        var v = num((recs[nameOf(f)] || {}).airQualityWhoRatio);
        if (v !== null) vals.push(v);
      });
      var sorted = vals.slice().sort(function (a, b) { return a - b; });
      var cuts = [];
      for (var i = 1; i < 5 && sorted.length; i++) cuts.push(sorted[Math.floor(i * sorted.length / 5)]);

      svg.append('g').selectAll('path').data(fc.features).enter().append('path')
        .attr('d', path)
        .attr('stroke', '#9d9a94').attr('stroke-width', 0.6)
        .attr('fill', function (f) {
          var v = num((recs[nameOf(f)] || {}).airQualityWhoRatio);
          if (v === null) return 'none';
          var bi = 0; while (bi < cuts.length && v >= cuts[bi]) bi++;
          return RAMP[bi];
        })
        .attr('fill-opacity', 0.8)
        .attr('stroke-dasharray', function (f) {
          return num((recs[nameOf(f)] || {}).airQualityWhoRatio) === null ? '3 3' : null;
        })
        .style('cursor', 'pointer')
        .on('click', function (ev, f) {
          state.sel = nameOf(f);
          svg.selectAll('path').attr('stroke-width', 0.6).attr('stroke', '#9d9a94');
          d3.select(this).attr('stroke-width', 2.4).attr('stroke', '#141414').raise();
          paintRows();
        })
        .append('title').text(function (f) { return nameOf(f); });

      // Airports and flight paths, from the file generated out of index.html.
      var g = state.geo && state.geo[state.city];
      if (g) {
        var line = d3.line().x(function (d) { return proj(d)[0]; }).y(function (d) { return proj(d)[1]; });
        var pg = svg.append('g');
        (g.flightPaths || []).forEach(function (fp) {
          if (!fp.coordinates || !fp.coordinates.length) return;
          var d = line(fp.coordinates);
          pg.append('path').attr('d', d).attr('fill', 'none')
            .attr('stroke', '#fafaf9').attr('stroke-width', 3.6).attr('stroke-opacity', 0.9);
          pg.append('path').attr('d', d).attr('fill', 'none')
            .attr('stroke', (fp.type === 'departure') ? '#267df2' : '#f27d26')
            .attr('stroke-width', 1.8).attr('stroke-opacity', 0.75);
        });
        (g.airports || []).forEach(function (a) {
          if (!a.coords) return;
          var xy = proj(a.coords);
          if (!xy || !isFinite(xy[0])) return;
          svg.append('circle').attr('cx', xy[0]).attr('cy', xy[1]).attr('r', 4)
            .attr('fill', '#141414').attr('stroke', '#fafaf9').attr('stroke-width', 1.4);
          svg.append('text').attr('x', xy[0] + 7).attr('y', xy[1] + 3)
            .attr('font-family', 'monospace').attr('font-size', '9px').attr('font-weight', '700')
            .attr('fill', '#141414').attr('stroke', '#fafaf9').attr('stroke-width', '3px')
            .attr('paint-order', 'stroke').text(a.code);
        });
      }

      // Borough names, with the halo the live site uses so they read on any fill.
      var px = LABEL_PX[state.city] || 7;
      var lg = svg.append('g');
      fc.features.forEach(function (f) {
        var c = path.centroid(f);
        if (!c || !isFinite(c[0])) return;
        lg.append('text').attr('x', c[0]).attr('y', c[1])
          .attr('text-anchor', 'middle').attr('font-size', px + 'px')
          .attr('font-family', 'monospace').attr('font-weight', '600')
          .attr('fill', '#141414').attr('stroke', '#FAFAF9').attr('stroke-width', '2.5px')
          .attr('paint-order', 'stroke').attr('opacity', 0.9)
          .style('pointer-events', 'none')
          .text(nameOf(f).toUpperCase());
      });

      if (!state.sel) paintRows();
    }).catch(function (e) {
      note('boundaries for ' + state.city + ' failed: ' + e.message);
      banner();
    });
  }

  /* --------------------------------------------------------------- rows --- */

  // A metric row is a label and a number that share a small ancestor. Found by
  // walking up from the label until an element also containing a number-like
  // sibling is reached - the two exports nest them differently.
  function findRows() {
    var out = [];
    var els = document.querySelectorAll('span, p, div, h3, h4');
    for (var i = 0; i < els.length; i++) {
      var t = textOf(els[i]);
      if (!ROWS[t] || els[i].children.length) continue;
      var box = els[i], hops = 0;
      while (box && hops < 4) {
        var valEl = null, valKids = 1e9;
        var kids = box.querySelectorAll('span, p, div');
        for (var k = 0; k < kids.length; k++) {
          if (kids[k] === els[i] || kids[k].contains(els[i])) continue;
          var txt = (kids[k].textContent || '').trim();
          // A value may WRAP its unit: <span>6.8<span>dB(A)</span></span>.
          // Requiring a leaf missed Dashboard 2's road-noise row entirely and
          // reported "not measured" for data we hold - a detector too strict
          // to see a value manufactures an absence. So subtrees count, and the
          // SMALLEST match wins so the row container never does.
          if (/^[£$]?-?[\d.,]+(\s*[^\s].{0,12})?$|^not measured/i.test(txt)) {
            var nk = kids[k].querySelectorAll('*').length;
            if (nk < valKids) { valEl = kids[k]; valKids = nk; }
          }
        }
        if (valEl) {
          var bar = box.querySelector('div[style*="width"], div[class*="rounded-full"] > div, .bg-primary');
          out.push({ key: t, labelEl: els[i], valEl: valEl, barEl: bar });
          break;
        }
        box = box.parentElement; hops++;
      }
    }
    return out;
  }

  var rowCache = null;

  function paintRows() {
    if (!rowCache) rowCache = findRows();
    if (!rowCache.length) { note('no metric rows recognised in this mockup'); banner(); return; }
    var recs = (state.extra && state.extra[state.city]) || {};
    var rec = state.sel ? recs[state.sel] : null;

    var rawRecs = (state.raw && state.raw[state.city]) || {};
    var rawRec = state.sel ? rawRecs[state.sel] : null;

    rowCache.forEach(function (r) {
      var spec = ROWS[r.key];
      var text = 'not measured here', pct = 0, italic = true;

      if (spec.kind === 'impact' && rawRec && rawRec.impact) {
        text = String(rawRec.impact).replace('-', ' to ');
        pct = IMPACT_PCT[rawRec.impact] || 50;
        italic = false;
      } else if (spec.kind === 'price' && rawRec && num(rawRec.avg_price) !== null) {
        text = '£' + Number(rawRec.avg_price).toLocaleString('en-GB');
        pct = Math.max(0, Math.min(100, (rawRec.avg_price / 900000) * 100));
        italic = false;
      } else if (spec.kind === 'input') {
        var v = rec ? num(rec[spec.field]) : null;
        if (v !== null) {
          text = v.toFixed(spec.dp) + ' ' + spec.unit;
          pct = Math.max(0, Math.min(100, (v / spec.max) * 100));
          italic = false;
        }
      }

      r.valEl.textContent = text;
      r.valEl.style.fontStyle = italic ? 'italic' : '';
      r.valEl.style.opacity = italic ? '.7' : '1';
      if (r.barEl) {
        r.barEl.style.width = pct + '%';
        r.barEl.style.transition = 'width .2s ease';
      }
    });

    // The headline number, if this mockup has one.
    var big = document.querySelector('[class*="text-6xl"], [class*="text-5xl"], [class*="display-score"]');
    if (big && !big.children.length) {
      big.textContent = state.sel ? (state.sel.length > 18 ? state.sel.slice(0, 18) : state.sel) : '--';
      big.style.fontSize = state.sel ? '28px' : '';
    }
  }

  /* -------------------------------------------------------------- chips --- */

  function wireCityChips() {
    var wired = 0;
    var els = document.querySelectorAll('button, a, span, div');
    var byName = {};
    CITIES.forEach(function (c) { byName[c[1].toLowerCase()] = c[0]; });
    for (var i = 0; i < els.length; i++) {
      if (els[i].children.length) continue;
      var key = byName[textOf(els[i])];
      if (!key) continue;
      var target = els[i].closest('button, a') || els[i];
      if (target.dataset.hydrated) continue;
      target.dataset.hydrated = '1';
      target.style.cursor = 'pointer';
      (function (k, node) {
        node.addEventListener('click', function (ev) {
          ev.preventDefault();
          state.city = k; state.sel = null; rowCache = null;
          var host = findMapEl() || document.querySelector('svg[data-hydrated]');
          if (host && host.tagName.toLowerCase() === 'svg') host = host.parentElement;
          if (host) renderMap(host);
          paintRows();
        });
      }(key, target));
      wired++;
    }
    if (!wired) note('no city chips recognised');
    return wired;
  }

  /* ------------------------------------------------------------- banner --- */

  function banner() {
    var id = 'hydrate-banner';
    var el = document.getElementById(id);
    if (!state.notes.length) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.style.cssText =
        'position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:8px 14px;' +
        'background:#fff6ed;border-top:2px solid #a85416;color:#6b3a10;' +
        'font:12px/1.4 system-ui,sans-serif';
      document.body.appendChild(el);
    }
    el.textContent = 'Hydration incomplete: ' + state.notes.join('; ') +
      '. The design is showing its own placeholder values where this says so.';
  }

  /* ---------------------------------------------------------------- go --- */

  function start() {
    var host = findMapEl();
    if (!host) { note('no map placeholder found'); }
    Promise.all([
      d3.json(DATA + 'borough-extra.json'),
      d3.json(GEO).catch(function () { return null; }),
      d3.json(RAW).catch(function () { return null; })
    ]).then(function (res) {
      state.extra = res[0];
      state.geo = res[1];
      state.raw = res[2];
      if (!state.raw) note('borough-raw.json missing; prices and aircraft bands will read as not measured');
      if (!state.geo) note('airports-paths.json missing');
      wireCityChips();
      if (host) renderMap(host);
      paintRows();
      banner();
      var t;
      window.addEventListener('resize', function () {
        clearTimeout(t);
        t = setTimeout(function () { var h = findMapEl(); if (h) renderMap(h); }, 200);
      });
    }).catch(function (e) {
      note('data load failed: ' + e.message);
      banner();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(start, 250); });
  } else {
    setTimeout(start, 250);
  }
})();

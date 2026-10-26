// Everything that moves is drawn here: London's strip slides under the plane, and the plane sits on the glide path
// for where it is. Positions come from strip.json (C): x along the strip is linear in the distance from the runway,
// and a height z shows z·cos(tilt) above its ground (no perspective). s is the plane's distance from the threshold.
(function () {
  var C = {"mpp": 2.5, "tilt_deg": 15.0, "glide_deg": 3.0, "width": 10320, "height": 612, "s_west": -1800.0, "s_east": 24000.0, "x_west": 0.0, "x_east": 10320.0, "centreline_y": 503.5, "plane": {"file": "strip_plane.png", "frame_m": [50.0, 25.0], "length_m": 37.6}, "places": [{"slug": "westminster", "name": "Westminster", "s": 21615, "radius": 750.0, "north_m": 2633, "measured": false, "noise_min_db": null, "noise_max_db": null, "compare": {"with": "Big Ben", "height_m": 96.0}}, {"slug": "battersea", "name": "Battersea", "s": 19894, "radius": 650.0, "north_m": 241, "measured": true, "noise_min_db": 49, "noise_max_db": 51, "compare": {"with": "Battersea Power Station's chimneys", "height_m": 101.0}}, {"slug": "kew-gardens", "name": "Kew", "s": 9787, "radius": 700.0, "north_m": -83, "measured": true, "noise_min_db": 53, "noise_max_db": 57, "compare": {"with": "the Great Pagoda", "height_m": 50.0}}, {"slug": "hounslow", "name": "Hounslow", "s": 5098, "radius": 650.0, "north_m": -28, "measured": true, "noise_min_db": 57, "noise_max_db": 63, "compare": {"with": "the London Eye", "height_m": 135.0}}], "landmarks": [{"name": "London Eye", "s": 21795, "north_m": 2834, "height_m": 135.0}, {"name": "Palace of Westminster", "s": 21424, "north_m": 2411, "height_m": 98.5}, {"name": "Battersea Power Station", "s": 20067, "north_m": 430, "height_m": 101.0}, {"name": "Kew Pagoda", "s": 9560, "north_m": -720, "height_m": 50.0}], "profile": [[1250, 68.3], [1600, 67.7], [1950, 67.8], [2300, 66.5], [2650, 65.9], [3000, 65.6], [3350, 64.8], [3700, 64.3], [4050, 63.9], [4750, 63.0], [5100, 62.5], [5450, 62.0], [5800, 61.5], [6150, 61.2], [6500, 60.7], [6850, 60.2], [7200, 59.8], [7550, 59.4], [8250, 58.6], [10000, 57.4], [10350, 57.1], [10700, 56.7], [11400, 56.0], [12100, 55.4], [12800, 54.5], [13150, 54.3], [13500, 54.0], [14550, 53.2], [14900, 53.1], [15250, 52.9], [15600, 52.7], [15950, 52.6], [16300, 52.4], [16650, 52.2], [17000, 52.0], [17350, 51.8], [17700, 51.6], [18050, 51.5], [18400, 51.4], [19800, 50.8], [20150, 50.6], [20500, 50.4], [20850, 50.3], [21200, 50.0], [21550, 49.8], [21900, 49.6], [22250, 49.4], [22600, 49.2], [22950, 49.0], [23300, null], [23650, null], [24000, null]], "contours": {"50": [[3700, 1662, 3350, 1560], [4050, 1800, 3700, 1662], [4750, 1850, 4400, 1838], [8600, 1167, 8250, 1108], [8950, 1122, 8600, 1167], [9300, 1156, 8950, 1122], [10350, 1104, 10000, 1143], [14200, 884, 14025, 900], [14375, 900, 14200, 884], [14900, 860, 14667, 900], [15250, 812, 14900, 860], [15600, 794, 15250, 812], [15950, 806, 15600, 794], [16300, 776, 15950, 806], [16650, 793, 16300, 776], [18750, 475, 18400, 570], [20150, 300, 19800, 386], [20500, 200, 20150, 300], [20150, 300, 20150, 300], [20850, 150, 20500, 200], [21200, 0, 20850, 150], [21550, -150, 21200, 0], [21200, 0, 21200, 0], [21900, -300, 21550, -150], [22250, -900, 22133, -600], [22133, -600, 21900, -300], [21900, -300, 21900, -300], [22250, -900, 22250, -900]], "55": [[-150, 829, -500, 892], [2650, 759, 2300, 726], [3000, 714, 2650, 759], [3350, 816, 3000, 714], [3700, 766, 3350, 816], [6850, 592, 6811, 600], [6811, 600, 6500, 680], [7025, 600, 6850, 592], [7025, 600, 7200, 610], [7258, 600, 7200, 610], [8250, 550, 7900, 545], [8600, 571, 8250, 550], [8950, 554, 8600, 571], [10700, 540, 10350, 483], [11050, 400, 10700, 540], [11400, 363, 11050, 400], [11600, 300, 11400, 363]], "60": [[-500, 542, -850, 495], [-150, 554, -500, 542], [200, 461, -150, 554], [550, 380, 200, 461], [2650, -900, 2300, -840], [2650, -473, 2300, -531], [3000, -473, 2650, -473], [3350, -430, 3000, -473], [3350, 369, 3000, 379], [3700, -391, 3350, -430], [3700, 408, 3350, 369], [4050, -426, 3700, -391], [4750, -300, 4750, -300], [4750, -300, 5100, -288], [5450, -261, 5100, -288], [5450, 273, 5333, 300], [5800, -265, 5450, -261], [5800, 265, 5450, 273], [6150, -225, 5800, -265], [6150, 189, 5800, 265], [6500, -124, 6150, -225], [6500, 162, 6150, 189], [6850, -55, 6500, -124], [6850, 40, 6500, 162], [7025, 0, 6850, -55], [7025, 0, 6850, 40]], "65": [[-500, 300, -500, 300], [-150, 346, -500, 300], [-66, 300, -150, 346], [1600, 121, 1250, 155], [1950, -117, 1600, -147], [1950, 145, 1600, 121], [2300, -118, 1950, -117], [2650, -61, 2300, -118], [3000, -49, 2650, -61], [3262, 0, 3000, -49], [3262, 0, 3000, 43]]}, "crossings": {"50": 21200, "55": 12411, "60": 7025, "65": 3262}, "pops": [{"name": "Palace of Westminster", "file": "strip_pop_palace-of-westminster.png", "x": 9259, "y": 195, "w": 61, "h": 80, "ox": 30.7, "oy": 58.8, "s": 21424, "north_m": 2411}, {"name": "London Eye", "file": "strip_pop_london-eye.png", "x": 9421, "y": 143, "w": 49, "h": 81, "ox": 17.2, "oy": 67.1, "s": 21795, "north_m": 2834}, {"name": "Battersea Power Station", "file": "strip_pop_battersea-power-station.png", "x": 8718, "y": 405, "w": 58, "h": 69, "ox": 28.9, "oy": 53.9, "s": 20067, "north_m": 430}, {"name": "Kew Pagoda", "file": "strip_pop_kew-pagoda.png", "x": 4534, "y": 550, "w": 21, "h": 36, "ox": 10.2, "oy": 28.0, "s": 9560, "north_m": -720}], "runway": {"name": "27R", "length_m": 3902.0, "width_m": 50.0}, "notes": ["Seen from the south, 15° down, with no perspective: a pixel is 2.5 m everywhere along the strip, so heights are true", "Roof shapes, house finishes, windows, doors, chimneys, hedges, trees, traffic and people are illustrative", "Landmarks: real positions and heights, simplified models", "Between the four places: OS map, buildings as plain blocks at Hounslow's median height (8 m); their colours are the yearly noise sampled every 350 by 300 m (coarser than the places' own), uncoloured where none is mapped", "As it looks: brick, roof and garden colours are typical of each area, not each building's own; only the noise colours are data", "Noise contours (50, 55, 60, 65 dB) are drawn through the same samples, straight between them; they stop where nothing is mapped", "Runway 3902 m by 50 m at its real position; markings illustrative. The last kilometre bends from the glide path to the touchdown zone (flare and landing drawn, not measured)"], "credits": ["WHO guideline 45 dB  ·  Sky Score  ·  DEFRA noise maps Round 4", "Contains OS data © Crown copyright 2026  ·  © OpenStreetMap contributors", "Building heights: © Environment Agency copyright and/or database right 2022. All rights reserved.", "Map of London: borough outlines from the Office for National Statistics (Open Government Licence v3.0); the Thames from OS OpenMap Local"], "tiles": 11, "chip": {"battersea": "#fdecaa", "kew-gardens": "#fac56f", "hounslow": "#ed7355"}, "band": {"50": "#fdecaa", "55": "#fac56f", "60": "#ed7355", "65": "#ad3050"}, "map": {"t": [68.9, 249.4], "u": [0.009996826571092824, -0.00025190972091698955], "n": [-0.00025190972091698955, -0.009996826571092824]}};
  var PLANE_SCALE = 5, TILE = 1000, TICK_M = 250, FLY_S = 22;
  var rad = Math.PI / 180, cosT = Math.cos(C.tilt_deg * rad), sinT = Math.sin(C.tilt_deg * rad);
  var tanG = Math.tan(C.glide_deg * rad);
  // Height for a distance s (m) from the threshold: the glide path, easing over the last 2 km to cross the threshold
  // at about 15 m (the beam aims ~300 m down the runway), then a flare to touchdown 450 m in. Drawn, not measured.
  var TCH = 300 * tanG, TOUCH = -450;
  function alt(s) {
    if (s >= 0) { var w = Math.min(1, Math.max(0, (2000 - s) / 2000)); w = w * w * (3 - 2 * w); return s * tanG + TCH * w; }
    if (s <= TOUCH) return 0;
    var t = (s - TOUCH) / -TOUCH;
    return (-2 * t * t * t + 3 * t * t) * TCH + (t * t * t - t * t) * tanG * -TOUCH;
  }
  var xOf = function (s) { return C.x_west + (s - C.s_west) * (C.x_east - C.x_west) / (C.s_east - C.s_west); };
  var yOf = function (north, z) { return C.centreline_y - (north * sinT + z * cosT) / C.mpp; };
  // everything is looked up inside the section, which also carries the state classes (still, flying): set into a
  // page of the site, nothing here touches the page around it
  var root = document.querySelector(".approach");
  var q = function (sel) { return root.querySelector(sel); };
  var all = function (sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); };
  var view = q(".view"), track = q(".track"), noise = q(".noise"), drop = q(".drop");
  var plane = q(".plane"), cardsEl = q(".cards"), slider = q("#approach-slider"), fly = q("#approach-fly");
  var mapPlane = q("#approach-map-plane"), ahead = q(".split.ahead"), behind = q(".split.behind"), hint = q(".hint"), grip = q(".grip");
  var west = q(".compass.west"), east = q(".compass.east");
  var band = function (v) {                // a yearly average's 5 dB band on the noise scale; grey under 50 or none
    return v === null || v < 50 ? "var(--quiet)" : C.band[String(Math.min(65, 5 * Math.floor(v / 5)))]; };
  var out = { km: q(".readout .km"), up: q(".readout .up"), below: q(".readout .below"), compare: q(".readout .compare") };
  var pw = C.plane.frame_m[0] * PLANE_SCALE / C.mpp, ph = C.plane.frame_m[1] * PLANE_SCALE / C.mpp;
  plane.style.width = pw + "px"; plane.style.height = ph + "px";
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  root.classList.toggle("still", still);
  var line = q(".glide line");          // the glide path: straight, as the slope is constant
  line.setAttribute("x1", xOf(C.s_west)); line.setAttribute("y1", yOf(0, C.s_west * tanG));
  line.setAttribute("x2", xOf(C.s_east)); line.setAttribute("y2", yOf(0, C.s_east * tanG));

  // the route the slider covers: from east of Westminster to touchdown and a 650 m roll. The slider runs right to
  // left (dir="rtl"), the way the plane flies across the picture and the map: its start is at the right
  var S0 = C.s_east - 600, S_END = TOUCH - 650, SPAN = S0 - S_END, s = S0, k = 1;
  slider.max = String(Math.round(SPAN));
  var frac = function (s_) { return (S0 - s_) / SPAN; };
  // A mark under the slider for each place and touchdown, named for the places between the two ends (the label above
  // names the ends); the page hides the names where there is no room for them (2026-10-26, the physical slider).
  var marks = q(".marks");
  C.places.concat([{ s: 0 }]).forEach(function (p, i, list) {
    var tick = document.createElement("i");
    tick.style.right = (100 * frac(p.s)).toFixed(2) + "%";
    if (i > 0 && i < list.length - 1) {
      var name = document.createElement("span");
      name.textContent = p.name;
      tick.appendChild(name);
    }
    marks.appendChild(tick);
  });
  // the track's colour: the 5 dB band of the sample under the flight line, hard stops between samples
  var stops = [], prev = null;
  C.profile.slice().sort(function (a, b) { return b[0] - a[0]; }).forEach(function (pt) {
    var f = Math.min(100, Math.max(0, 100 * frac(pt[0]))), v = pt[1];
    var c = band(v);
    if (c !== prev) { stops.push((prev || c) + " " + f.toFixed(2) + "%", c + " " + f.toFixed(2) + "%"); prev = c; }
  });
  if (stops.length) slider.style.setProperty("--profile", "linear-gradient(270deg," + stops.join(",") + "," + prev + " 100%)");

  q("#approach-notes").innerHTML = ["Plane drawn " + PLANE_SCALE + "× real size, on the " + C.glide_deg +
    "° glide path to runway 27R; the plane's bob, the landmarks springing up and the clouds are decoration"]
    .concat(C.notes).map(function (n) { return "<p>" + n + ".</p>"; }).join("");
  // the credits stay in sight; what is drawn and how folds away under "About this picture" (details on demand)
  q("#approach-credits").innerHTML = C.credits.join("<br>");

  // speech-bubble cards: each place, and Heathrow
  var cards = C.places.map(function (p) {
    var el = document.createElement("div"), measured = p.noise_min_db !== null;
    el.className = "card";
    el.innerHTML = "<b>" + p.name + "</b><i>" + (measured ? p.noise_min_db + "–" + p.noise_max_db +
      " dB yearly average" : (p.north_m / 1000).toFixed(1) + " km north · no aircraft noise mapped") + "</i>";
    if (measured) el.style.setProperty("--chip", C.chip[p.slug]);
    cardsEl.appendChild(el);
    return { el: el, s: p.s, north: p.north_m, reach: p.radius + 1200 };
  });
  var lhr = document.createElement("div");
  lhr.className = "card"; lhr.innerHTML = "<b>Heathrow</b><i>runway " + C.runway.name + "</i>";
  lhr.style.setProperty("--chip", "#3a3f45");
  cardsEl.appendChild(lhr); cards.push({ el: lhr, s: -700, north: 0, reach: 1600 });

  var ticks = [];                         // height marks on the plane's line, every TICK_M
  for (var h = TICK_M; h < C.s_east * tanG; h += TICK_M) {
    var tk = document.createElement("div");
    tk.className = "tick"; tk.innerHTML = "<span>" + h.toLocaleString("en-GB") + " m</span>";
    track.appendChild(tk); ticks.push({ el: tk, h: h });
  }
  var popEls = all(".pop"), labelEls = all(".contours .lbl"), clouds = all(".cloud");

  function round50(m) { return Math.round(m / 50) * 50; }
  function contour(s) {                // the highest contour the plane has crossed into, on the flight line
    var inside = null;
    Object.keys(C.crossings).forEach(function (lv) { if (s <= C.crossings[lv]) inside = lv; });
    return inside ? " · inside the " + inside + " dB contour" : "";
  }
  function below(s) {                   // [what is under the plane, its colour on the noise scale]
    var none = "var(--quiet)";
    if (s < 0) return ["Runway " + C.runway.name + ", Heathrow", none];
    for (var i = 0; i < C.places.length; i++) {
      var p = C.places[i];
      if (Math.abs(s - p.s) > p.radius) continue;
      if (Math.abs(p.north_m) > p.radius) return ["Passing " + p.name + ", " + (p.north_m / 1000).toFixed(1) +
        " km north: no aircraft noise is mapped there", none];
      return p.noise_min_db === null ? [p.name + ": no aircraft noise mapped", none] :
        ["Below: " + p.name + ", " + p.noise_min_db + "–" + p.noise_max_db + " dB yearly average" + contour(s), C.chip[p.slug]];
    }
    var near = null;                      // between the places: the sample under the flight line nearest s
    C.profile.forEach(function (pt) { if (!near || Math.abs(pt[0] - s) < Math.abs(near[0] - s)) near = pt; });
    if (!near || Math.abs(near[0] - s) > 400) return ["Below: no reading here (no postcode: a park, the river or the airfield)", none];
    return near[1] === null ? ["Below: no aircraft noise mapped here", none] :
      ["Below: about " + Math.floor(near[1]) + " dB yearly average" + contour(s), band(near[1])];
  }
  function compare(s, up) {
    for (var i = 0; i < C.places.length; i++) {
      var p = C.places[i];
      if (Math.abs(s - p.s) > p.radius + 900) continue;
      var n = up / p.compare.height_m;
      return "The plane is about " + (n >= 1.95 ? Math.round(n) : n.toFixed(1)) + "× as high as " + p.compare.with +
        " (" + p.compare.height_m + " m)";
    }
    return "";
  }
  function say(el, text, key) {          // set a line's words; a spring when what it is about changes (a new place,
    if (el.textContent !== text) el.textContent = text;            // a new contour, the runway) - not every metre
    if (key === undefined || key === el.dataset.key) return;
    el.dataset.key = key;
    if (still) return;
    el.classList.remove("boing"); void el.offsetWidth; el.classList.add("boing");
  }
  function topic(s) {                    // what the line under the plane is about, for say()
    if (s < 0) return "runway";
    for (var i = 0; i < C.places.length; i++) if (Math.abs(s - C.places[i].s) <= C.places[i].radius) return C.places[i].slug;
    return contour(s) || "between";
  }

  function load(x0, x1) {                 // fetch the tiles near what is on screen, once
    all(".tile").forEach(function (t) {
      var left = parseFloat(t.style.left);
      if (left + TILE < x0 || left > x1) return;
      var src = t.querySelector("source"), img = t.querySelector("img");
      if (src.dataset.srcset) { src.srcset = src.dataset.srcset; delete src.dataset.srcset; }
      if (img.dataset.src) { img.src = img.dataset.src; delete img.dataset.src; }
    });
  }

  // EASED (Bill, 2026-10-26: "the plane moves too fast when sliding it"): the slider and a drag set where the plane is
  // going (target) and it eases there, about 0.2 s, so a quick flick glides rather than jumps; Fly it, the place
  // buttons' own glide and reduced motion put it there at once.
  var queued = false, landed = false, said = "", target = S0, lastT = 0, EASE_S = 0.2;
  // WHERE THE PLANE IS DRAWN ON SCREEN (Bill, 2026-10-26: the handle on the plane's line is "the main point of contact"):
  // the middle of the view, which follows it; while the handle is held, under the finger, the land scrolling beneath;
  // let go, it eases back to the middle.
  var anchor = null, anchorBack = false, ANCHOR_S = 0.35, camTx = 0;
  function frame(now) {
    queued = false;
    var dt = lastT && now ? Math.min(0.1, (now - lastT) / 1000) : 1 / 60;
    lastT = now || 0;
    s = still || Math.abs(target - s) < 0.5 ? target : s + (target - s) * (1 - Math.exp(-dt / EASE_S));
    var vw = view.clientWidth, vh = view.clientHeight;
    k = Math.min(1, (vh - 16) / C.height);
    var ty = vh - C.height * k;
    if (anchorBack) {                        // let go: back to the middle, eased
      anchor = still || Math.abs(anchor - vw / 2) < 1 ? null : anchor + (vw / 2 - anchor) * (1 - Math.exp(-dt / ANCHOR_S));
      if (anchor === null) anchorBack = false;
    }
    var up = alt(s), x = xOf(s), y = yOf(0, up);
    // the view puts the plane in the middle (or under the finger holding the handle), stopping at the strip's ends;
    // there the plane moves on across the screen
    var tx = Math.min(0, Math.max(vw - C.width * k, (anchor === null ? vw / 2 : anchor) - x * k));
    camTx = tx;
    track.style.transform = "translate(" + tx + "px," + ty + "px) scale(" + k + ")";
    noise.style.clipPath = "inset(0 0 0 " + x + "px)";
    plane.style.left = (x - pw / 2) + "px"; plane.style.top = (y - ph / 2) + "px";
    var pitch = s >= 0 ? 0 : s > TOUCH ? 3 * (1 - up / TCH) : Math.max(-2, -2 * (TOUCH - s) / 150);  // flare, nose down
    plane.style.transform = "rotate(" + pitch + "deg)";
    root.classList.toggle("flying", !still && s > TOUCH);
    if (!still && s <= TOUCH && !landed) plane.classList.add("bump");
    if (s > TOUCH) plane.classList.remove("bump");
    landed = s <= TOUCH;
    drop.style.left = (x - 1) + "px"; drop.style.top = y + "px"; drop.style.height = Math.max(0, C.centreline_y - y) + "px";
    var sx = tx + x * k;                  // the plane on screen: the two halves are named either side of its line,
    ahead.style.left = behind.style.left = sx + "px";        // each only where it fits
    ahead.hidden = sx < 130;
    behind.hidden = sx > vw - 180;
    var py = ty + y * k;                  // a direction's name steps aside while the plane flies behind it
    // THE GRIP (Bill, 2026-10-26: "a slider symbol ... on the vertical line that's attached to the plane"): the knob's
    // sideways-drag symbol rides the plane's line, halfway to the ground, and always just below the plane: low or
    // landed it sits under it (pinned to the ground, it covered the plane on the runway), above the labels at the foot
    var gy = ty + C.centreline_y * k;
    grip.style.left = sx + "px";
    var gripY = Math.min(vh - 62, Math.max(py + ph * k / 2 + 26, (py + gy) / 2));
    grip.style.top = gripY + "px";
    west.hidden = py < 70 && sx < 210;
    east.hidden = py < 70 && sx > vw - 230;
    mapPlane.setAttribute("transform", "translate(" + (C.map.t[0] + C.map.u[0] * s).toFixed(1) + " " +
      (C.map.t[1] + C.map.u[1] * s).toFixed(1) + ")");       // and its dot on the map of London
    ticks.forEach(function (t) {
      t.el.style.left = (x - 5) + "px"; t.el.style.top = (yOf(0, t.h) - 1) + "px";
      // only marks below the plane, and not the one the grip is passing over (it hid "250 m" as "50 m")
      var under = Math.abs(ty + (yOf(0, t.h) - 1) * k - gripY) < 26;
      t.el.style.visibility = t.h < up - 60 && !under ? "visible" : "hidden";
    });
    var km = s >= 0 ? (s / 1000).toFixed(1) + " km to the runway" : s > TOUCH ? "over the runway" :
      "touched down, " + Math.round(TOUCH - s) + " m rolled";
    var height = up >= 100 ? "plane about " + round50(up).toLocaleString("en-GB") + " m up" :
      up >= 1 ? "about " + Math.max(1, Math.round(up)) + " m up" : "on the runway";
    var bl = below(s), under = bl[0], cmp = up >= 60 ? compare(s, up) : "";
    out.below.style.setProperty("--chip", bl[1]);                     // its colour, beside the figure
    say(out.km, km); say(out.up, height); say(out.below, under, topic(s)); say(out.compare, cmp, cmp ? topic(s) : "");
    var text = km + ", " + height + ". " + under;     // what the slider says to a screen reader
    if (text !== said) { slider.setAttribute("aria-valuetext", text); said = text; }
    popEls.forEach(function (el) {                  // landmarks spring up as they come into view, once
      if (still || el.classList.contains("up")) return;
      var sx = tx + parseFloat(el.style.left) * k, w = parseFloat(el.style.width) * k;
      if (sx + w > 0 && sx < vw) { el.classList.remove("down"); el.classList.add("up"); }
      else el.classList.add("down");
    });
    labelEls.forEach(function (el) {               // a contour's label bounces as the plane crosses it
      var crossed = s <= parseFloat(el.dataset.s);
      if (crossed && !el.classList.contains("boing") && !still) el.classList.add("boing");
      if (!crossed) el.classList.remove("boing");
    });
    cards.forEach(function (c) {
      // EMBED FIXES (Sky Score repo, 2026-10-26; carry them into scripts/strip_page.py, or strip_v8 brings both back):
      // a card stays inside the stage (on /how-it-works/ the stage is 984 px, not 1080, and Westminster's was cut
      // at the left edge), and steps up above the plane only while it would cover it (at Hounslow, ~250 m up, the
      // card hid it; lifting every card instead pushed Westminster's out of the top).
      var half = c.el.offsetWidth / 2;
      var cx = Math.min(vw - half - 8, Math.max(half + 8, tx + xOf(c.s) * k));
      var bottom = yOf(c.north, 150) - 14;               // the card's lower edge, above the Eye (135 m)
      var over = Math.abs(tx + x * k - cx) < half + pw * k / 2 &&
        y - ph / 2 < bottom && y + ph / 2 > bottom - c.el.offsetHeight / k;
      if (over) bottom = y - ph / 2 - 10;
      c.el.style.left = cx + "px";
      c.el.style.top = (ty + bottom * k) + "px";
      c.el.classList.toggle("on", Math.abs(s - c.s) < c.reach);
    });
    clouds.forEach(function (c) {                   // drifting at a quarter of the ground's pace, wrapping round;
      var span = vw + 400, x0 = parseFloat(c.dataset.x) * span -     // still: they stay put (motion apart from
        (still ? 0 : (S0 - s) / C.mpp * k * 0.25);                    // the content is what reduced motion avoids)
      c.style.transform = "translateX(" + ((((x0 % span) + span) % span) - 200) + "px)";
    });
    load(x - 2 * vw / k, x + 2 * vw / k);   // two screens either side: one let a quick move outrun the tiles
    if (s !== target || anchorBack) queue(); else lastT = 0;   // still easing: the next frame carries on
  }
  function queue() { if (!queued) { queued = true; requestAnimationFrame(frame); } }
  function go(s_, keepSlider, exact) {     // send the plane to s_ (eased; exact: there at once), and the slider with it
    target = Math.min(S0, Math.max(S_END, s_));
    if (exact) s = target;
    if (!keepSlider) slider.value = String(Math.round(S0 - target));
    queue();
  }

  // Fly it: on to touchdown in about FLY_S seconds, quicker while high (s follows (1-p)^1.35, as the scroll did)
  var raf = 0, t0 = 0, p0 = 0;
  var pOf = function (s_) { return 1 - Math.pow(Math.max(0, (s_ - S_END) / SPAN), 1 / 1.35); };
  var sAt = function (p) { return S_END + SPAN * Math.pow(1 - p, 1.35); };
  function step(now) {
    if (!t0) { t0 = now; p0 = pOf(s); }
    var p = Math.min(1, p0 + (now - t0) / 1000 / FLY_S);
    go(sAt(p), false, true);
    if (p < 1) raf = requestAnimationFrame(step); else halt();
  }
  function halt() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    fly.textContent = s <= S_END + 1 ? "Fly it again" : "Fly it";
    fly.setAttribute("aria-pressed", "false");
  }
  // on the site, each way in is counted once a page view (the site's count.mjs sends GoatCounter an event: a fixed
  // name, nothing about the reader), to learn whether anyone plays with it; in a preview there is no counter
  var sent = {};
  function counted(name) {
    if (sent[name]) return;
    sent[name] = true;
    try { if (window.goatcounter && window.goatcounter.count) window.goatcounter.count({ path: "event/" + name, title: name, event: true }); }
    catch { /* counting must never break the page */ }
  }
  fly.addEventListener("click", function () {
    hint.hidden = true; root.classList.add("used");
    counted("approach-fly");
    if (gl) { cancelAnimationFrame(gl); gl = 0; }
    if (raf) return halt();
    if (s <= S_END + 1) go(S0, false, true);
    t0 = 0; raf = requestAnimationFrame(step);
    fly.textContent = "Pause"; fly.setAttribute("aria-pressed", "true");
  });
  // a place's button: there at once with reduced motion, else a short glide
  var gl = 0;
  function settle() { if (gl) cancelAnimationFrame(gl); gl = 0; halt(); hint.hidden = true; root.classList.add("used"); }  // the hint (and the grip's nudge) go once used
  all(".jump").forEach(function (b) {
    b.addEventListener("click", function () {
      settle();
      counted("approach-jump-" + b.dataset.place);
      var from = s, to = parseFloat(b.dataset.s), t1 = 0;
      if (still) return go(to, false, true);
      gl = requestAnimationFrame(function glide(now) {
        if (!t1) t1 = now;
        var u = Math.min(1, (now - t1) / 700); u = u * u * (3 - 2 * u);
        go(from + (to - from) * u, false, true);
        gl = u < 1 ? requestAnimationFrame(glide) : 0;
      });
    });
  });
  slider.addEventListener("input", function () { settle(); counted("approach-slider"); go(S0 - parseFloat(slider.value), true); });
  // Dragging the handle (Bill, 2026-10-26, four rounds: "not obvious and clunky"; "too fast"; then "I have to drag to
  // the end of the page and still don't reach the end"; then "a bit more ... an ideal level"). LEFT brings the plane in,
  // the way it flies and the slider's knob goes; gentle near where you grab, faster the further you pull, and the
  // window's edge is the end of the route that way: one drag can always land it, or take it back to the start.
  // (Before: the land moved 1:1 the other way, so a leftward drag did nothing; then the whole approach per picture
  // width, a whoosh; then a third of it per width, so no single drag could reach the runway.)
  var drag = null, LINEAR = 0.45, EDGE = 12;
  // The share of the route left that way, for the share u of the room to the window's edge you have pulled:
  // LINEAR*u + (1 - LINEAR)*u^2. A tenth of the way moves ~5% of it, halfway ~36% (Bill, 2026-10-26: "a bit more
  // while dragging, not too much": it was ~15-22% halfway, slow and then a lurch), the edge all of it. Relative to
  // your own reach, so a phone and a desktop feel alike; an even spread (50% halfway) was the "too fast" one.
  function pull(dx) {                       // metres the plane moves for a drag of dx px from where it began
    var left = dx < 0, room = Math.max(40, left ? drag.left : drag.right);
    var need = left ? drag.s - S_END : S0 - drag.s;   // the route left that way
    var u = Math.min(1, Math.abs(dx) / room);
    var m = need * (LINEAR * u + (1 - LINEAR) * u * u);
    // never slower than the ground under the finger, or London slides along with the hand (Bill, 2026-10-26: dragging
    // back to the start "moves the London landscape with it", where little route is left for a lot of screen)
    m = Math.min(need, Math.max(m, Math.abs(dx) * C.mpp / k));
    return left ? -m : m;
  }
  // Only the handle drags (pointer capture keeps the drag on it however the pointer moves); it stays under the finger,
  // offset by wherever it was caught, so it does not jump; the window's edges are the route's ends (pull()).
  grip.addEventListener("pointerdown", function (ev) {
    if (ev.button) return;
    ev.preventDefault();
    settle(); counted("approach-drag");
    var box = view.getBoundingClientRect(), g = grip.getBoundingClientRect();
    drag = { x: ev.clientX, s: target, id: ev.pointerId, left: ev.clientX - EDGE, right: window.innerWidth - ev.clientX - EDGE,
      off: ev.clientX - (g.left + g.right) / 2, viewLeft: box.left };
    anchor = (g.left + g.right) / 2 - box.left; anchorBack = false;
    grip.setPointerCapture(ev.pointerId); grip.classList.add("held");
  });
  grip.addEventListener("pointermove", function (ev) {
    if (!drag || ev.pointerId !== drag.id) return;
    var t = Math.min(S0, Math.max(S_END, drag.s + pull(ev.clientX - drag.x)));
    go(t, false, true);                      // held: exactly where the hand puts it (eased, the land lagged and slid)
    anchor = t >= S0 || t <= S_END
      ? camTx + xOf(t) * k                   // at the start or the runway the handle stops, and London with it
      : Math.min(view.clientWidth - 20, Math.max(20, ev.clientX - drag.viewLeft - drag.off));
  });
  ["pointerup", "pointercancel"].forEach(function (n) {
    grip.addEventListener(n, function () { drag = null; grip.classList.remove("held"); anchorBack = true; queue(); });
  });
  window.addEventListener("resize", queue);
  go(S0, false, true);
})();

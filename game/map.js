/* BeaconHunt's world map: draw the countries, zoom and pan, click to pick one.
 *
 * The shapes come from map/world.js (SINGE's world map, made by
 * tools/import_singe_map.py). They're SVG paths in a Miller projection, so the
 * map is one <svg> and zooming just changes its viewBox (the same way SINGE
 * does it). Small islands also appear, enlarged, in boxes under the main map
 * (the "strip"), shown only when a game can include them.
 *
 *   var map = BeaconMap.create(element, window.BEACON_MAP, {onPick: fn, onPin: fn})
 *   map.setMode("country" | "location")   pick a country, or put a pin anywhere
 *   map.focus(keys, bounds)    fade the countries not in keys and zoom to bounds
 *                              ([west, south, east, north] in degrees); null: the whole world
 *   map.pick(key)              select a country (or null)
 *   map.reveal(answer, guess, lat, lon, pin)   show the answer, the guess (a country, or
 *                              a pin {lat, lon}) and the photo's spot
 *   map.clear()                back to guessing
 *
 * Disputed areas the game leaves out ("off" on the map) are drawn but can't be picked.
 *
 * Countries are known by their code ("key", e.g. SLE). Parts of a country that
 * are drawn separately (Alaska, the Canary Islands...) have their country's key.
 */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var ZOOM_STEP = 1.6;
  var MAX_ZOOM = 40;           // furthest in: 1/40 of the world's width
  var TINY_PX = 14;            // countries smaller than this on screen get a circle to click
  var CIRCLE_PX = 7;           // radius of those circles, in screen pixels

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(e);
    return e;
  }

  function miller(lat) {
    var r = Math.max(-89, Math.min(89, lat)) * Math.PI / 180;
    return 1.25 * Math.log(Math.tan(Math.PI / 4 + 0.4 * r)) * 180 / Math.PI;
  }

  // The "ins" of a region: {box id: piece} or {box id: [pieces]}.
  function pieces(v) { return Array.isArray(v) ? v : (v ? [v] : []); }

  function create(box, data, opts) {
    opts = opts || {};
    var W = data.size[0], H = data.size[1], K = data.projection.k, TOP = miller(data.projection.lat_top);
    var byKey = {};            // key -> [path elements] (main map, boxes and circles)
    var picked = null, revealed = false, inPlay = null, mode = "country", pin = null;

    function xy(lat, lon) { return [(lon + 180) * K, (TOP - miller(lat)) * K]; }
    function millerInverse(m) {
      return (Math.atan(Math.exp(0.8 * m * Math.PI / 180)) - Math.PI / 4) / 0.4 * 180 / Math.PI;
    }
    function latLon(x, y) {          // the inverse of xy()
      return { lat: millerInverse(TOP - y / K), lon: ((x / K - 180) + 540) % 360 - 180 };
    }

    // ---------------------------------------------------------- drawing

    box.innerHTML = "";
    box.classList.add("bmap");
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, "class": "world", role: "img",
                          "aria-label": "World map. Click a country to choose it." }, box);
    el("rect", { x: -W, y: -H, width: 3 * W, height: 3 * H, "class": "sea" }, svg);   // also fills any space around the map
    var land = el("g", { "class": "land" }, svg);
    var circles = el("g", { "class": "circles" }, svg);
    var marks = el("g", { "class": "marks" }, svg);

    function addShape(parent, r, d, s) {
      var cls = "country" + (r.decor ? " decor" : "") + (r.off ? " off" : "") + (s ? " nostroke" : "");
      var p = el("path", { d: d, "class": cls }, parent);
      if (r.key && !r.decor && !r.off) {
        p.setAttribute("data-key", r.key);
        (byKey[r.key] = byKey[r.key] || []).push(p);
      }
      if (s) el("path", { d: s, "class": "outline" }, parent);   // outline without seams (see tools/import_singe_map.py)
      return p;
    }

    var tiny = [];
    data.regions.forEach(function (r) {
      if (r.d) addShape(land, r, r.d, r.s);
      if (r.key && !r.decor && !r.off && r.mk && r.small) tiny.push(r);
    });
    (data.lakes || []).forEach(function (l) { el("path", { d: l.d, "class": "lake" }, land); });
    tiny.forEach(function (r) {
      var c = el("circle", { cx: r.mk[0], cy: r.mk[1], r: 10, "class": "tiny", "data-key": r.key, "data-sz": r.sz || 0 }, circles);
      (byKey[r.key] = byKey[r.key] || []).push(c);
    });

    // The boxes for small islands, under the map. They don't zoom.
    var strip = null;
    if (data.strip && data.insets && data.insets.length) {
      strip = el("svg", { viewBox: "0 0 " + data.strip[0] + " " + data.strip[1], "class": "strip" }, box);
      data.insets.forEach(function (ins) {
        var clip = el("clipPath", { id: "clip-" + ins.id }, strip);
        el("rect", { x: ins.x, y: ins.y, width: ins.w, height: ins.h }, clip);
        el("rect", { x: ins.x, y: ins.y, width: ins.w, height: ins.h, "class": "inbox" }, strip);
        var g = el("g", { "clip-path": "url(#clip-" + ins.id + ")" }, strip);
        data.regions.forEach(function (r) {
          pieces(r.ins && r.ins[ins.id]).forEach(function (p) {
            if (p.d) addShape(g, r, p.d, p.s);
            if (p.mk && r.key && !r.decor && !r.off) {
              var c = el("circle", { cx: p.mk[0], cy: p.mk[1], r: 12, "class": "tiny fixed", "data-key": r.key }, g);
              (byKey[r.key] = byKey[r.key] || []).push(c);
            }
          });
        });
        if (ins.chains) el("path", { d: ins.chains, "class": "chain" }, strip);
        var t = el("text", { x: ins.x + ins.w - 14, y: ins.y + 70, "text-anchor": "end", "class": "intitle" }, strip);
        t.textContent = ins.title;
      });
    }

    var tip = document.createElement("div");
    tip.className = "maptip";
    tip.hidden = true;
    box.appendChild(tip);

    function nameOf(key) { return (data.countries[key] || {}).name || key; }

    // ---------------------------------------------------------- zoom and pan

    // The view always has the same shape as the map's box on screen, so the
    // whole box is used. When the view is bigger than the map one way, the map
    // sits in the middle that way.
    var view = { x: 0, y: 0, w: W, h: H };
    function shape() {
      var r = svg.getBoundingClientRect();
      return r.width && r.height ? r.height / r.width : H / W;
    }
    function clampAxis(pos, size, total) {
      return size >= total ? (total - size) / 2 : Math.max(0, Math.min(total - size, pos));
    }
    function apply() {
      var a = shape();
      view.w = Math.min(Math.max(W, H / a), Math.max(W / MAX_ZOOM, view.w));
      view.h = view.w * a;
      view.x = clampAxis(view.x, view.w, W);
      view.y = clampAxis(view.y, view.h, H);
      svg.setAttribute("viewBox", [view.x, view.y, view.w, view.h].map(function (v) { return v.toFixed(1); }).join(" "));
      sizeCircles();
    }
    function toMap(cx, cy) {
      var pt = svg.createSVGPoint();
      pt.x = cx; pt.y = cy;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }
    function zoomAt(f, mx, my) {
      var w = Math.min(Math.max(W, H / shape()), Math.max(W / MAX_ZOOM, view.w / f)), r = w / view.w;
      view.x = mx - (mx - view.x) * r;
      view.y = my - (my - view.y) * r;
      view.w = w;
      apply();
    }
    function zoomBy(f) { zoomAt(f, view.x + view.w / 2, view.y + view.h / 2); }
    // Show a box of the map (x0, y0, x1, y1), with a margin, keeping the map's shape.
    function fit(x0, y0, x1, y1, pad) {
      pad = pad === undefined ? 0.15 : pad;
      var w = (x1 - x0) * (1 + 2 * pad), h = (y1 - y0) * (1 + 2 * pad), a = shape();
      w = Math.max(w, h / a, W / MAX_ZOOM);
      view.w = w;
      view.x = (x0 + x1) / 2 - w / 2;
      view.y = (y0 + y1) / 2 - (w * a) / 2;
      apply();
    }
    var home = [0, 0, W, H];
    function reset() { fit(home[0], home[1], home[2], home[3], home[2] - home[0] >= W ? 0 : 0.05); }

    // Circles for tiny countries stay the same size on screen, and only show when the country is too small to click.
    function sizeCircles() {
      var m = svg.getScreenCTM(), px = m && m.a > 0 ? m.a : 1;
      var list = circles.querySelectorAll("circle");
      for (var i = 0; i < list.length; i++) {
        var c = list[i], show = +c.getAttribute("data-sz") * px < TINY_PX;
        c.style.display = show ? "" : "none";
        if (show) c.setAttribute("r", (CIRCLE_PX / px).toFixed(2));
      }
      var dots = marks.querySelectorAll("[data-px]");
      for (var j = 0; j < dots.length; j++) {
        var d = dots[j], size = +d.getAttribute("data-px") / px;
        if (d.tagName === "circle") d.setAttribute("r", size.toFixed(2));
        else d.setAttribute("stroke-width", size.toFixed(2));
      }
    }

    var ptrs = {}, moved = false;
    function count() { return Object.keys(ptrs).length; }
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      var m = toMap(e.clientX, e.clientY), d = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
      zoomAt(Math.exp(-d * 0.0025), m.x, m.y);
    }, { passive: false });
    svg.addEventListener("pointerdown", function (e) {
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY };
      if (count() === 1) moved = false;
      tip.hidden = true;
    });
    window.addEventListener("pointermove", function (e) {
      var p = ptrs[e.pointerId];
      if (!p) return;
      var keys = Object.keys(ptrs);
      if (keys.length === 2) {                      // two fingers: pinch and drag
        var a = ptrs[keys[0]], b = ptrs[keys[1]];
        var before = Math.hypot(a.x - b.x, a.y - b.y), cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
        p.x = e.clientX; p.y = e.clientY;
        var after = Math.hypot(a.x - b.x, a.y - b.y), m = toMap(cx, cy);
        moved = true;
        if (before > 0) zoomAt(after / before, m.x, m.y);
        var s = svg.getScreenCTM().a;
        view.x -= ((a.x + b.x) / 2 - cx) / s;
        view.y -= ((a.y + b.y) / 2 - cy) / s;
        apply();
        return;
      }
      var dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (!moved && Math.hypot(p.x - p.sx, p.y - p.sy) < 6) return;   // a small wobble is still a click
      moved = true;
      var sc = svg.getScreenCTM().a;
      view.x -= dx / sc;
      view.y -= dy / sc;
      apply();
    });
    function up(e) { delete ptrs[e.pointerId]; }
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);

    // ---------------------------------------------------------- picking

    function keyAt(target) {
      var t = target;
      while (t && t !== box) {
        if (t.getAttribute && t.getAttribute("data-key")) return t.getAttribute("data-key");
        t = t.parentNode;
      }
      return null;
    }
    // Where a click is, in degrees: on the main map, or in one of the island boxes.
    function clickLatLon(e) {
      var target = e.target, inStrip = strip && (target === strip || target.ownerSVGElement === strip);
      if (!inStrip) {
        var m = toMap(e.clientX, e.clientY);
        return latLon(m.x, m.y);
      }
      var pt = strip.createSVGPoint();
      pt.x = e.clientX; pt.y = e.clientY;
      var q = pt.matrixTransform(strip.getScreenCTM().inverse());
      for (var i = 0; i < data.insets.length; i++) {
        var ins = data.insets[i];
        if (q.x >= ins.x && q.x <= ins.x + ins.w && q.y >= ins.y && q.y <= ins.y + ins.h) {
          var lon = ins.lon0 + (q.x - ins.x) / ins.s;
          return { lat: millerInverse(miller(ins.lat1) - (q.y - ins.y) / ins.s), lon: ((lon + 540) % 360) - 180 };
        }
      }
      return null;
    }
    function drawPin(lat, lon) {
      marks.innerHTML = "";
      var p = xy(lat, lon);
      el("circle", { cx: p[0], cy: p[1], r: 6, "class": "pin", "data-px": 7 }, marks);
      sizeCircles();
    }
    box.addEventListener("click", function (e) {
      if (moved || revealed) return;
      if (mode === "location") {
        var at = clickLatLon(e);
        if (!at) return;
        pin = at;
        drawPin(at.lat, at.lon);
        if (opts.onPin) opts.onPin(at.lat, at.lon);
        return;
      }
      var key = keyAt(e.target);
      if (key) {
        pick(key);
        if (opts.onPick) opts.onPick(key, nameOf(key));
      }
    });
    box.addEventListener("pointermove", function (e) {
      if (e.pointerType === "touch" || count()) return;
      var key = mode === "country" ? keyAt(e.target) : null;
      if (!key) { tip.hidden = true; return; }
      var r = box.getBoundingClientRect();
      tip.textContent = nameOf(key);
      tip.style.left = (e.clientX - r.left + 14) + "px";
      tip.style.top = (e.clientY - r.top + 14) + "px";
      tip.hidden = false;
    });
    box.addEventListener("pointerleave", function () { tip.hidden = true; });

    function mark(key, cls, on) {
      (byKey[key] || []).forEach(function (p) { p.classList.toggle(cls, on); });
    }
    function pick(key) {
      if (picked) mark(picked, "picked", false);
      picked = key;
      if (key) mark(key, "picked", true);
    }

    // Fade the countries not in play and zoom to the map's area (a continent's game).
    function focus(keys, bounds) {
      inPlay = keys && keys.length ? keys : null;
      var x0 = W, y0 = H, x1 = 0, y1 = 0;
      Object.keys(byKey).forEach(function (key) {
        var on = !inPlay || inPlay.indexOf(key) >= 0;
        byKey[key].forEach(function (p) {
          p.classList.toggle("faded", !on);
          if (on && inPlay && p.tagName === "path" && p.ownerSVGElement === svg) {
            var b = p.getBBox();
            x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
            x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
          }
        });
      });
      home = inPlay && x1 > x0 ? [x0, y0, x1, y1] : [0, 0, W, H];
      if (bounds) {
        var a = xy(bounds[3], bounds[0]), b = xy(bounds[1], bounds[2]);
        home = [a[0], a[1], b[0], b[1]];
      }
      // The island boxes only when some country in play is in them.
      if (strip) strip.style.display = !inPlay || inPlay.some(function (k) {
        return (byKey[k] || []).some(function (p) { return p.ownerSVGElement === strip; });
      }) ? "" : "none";
      reset();
    }

    // After a guess: the right country, the guess (if wrong) and a beacon where the photo was taken.
    function reveal(answer, guess, lat, lon, guessPin) {
      revealed = true;
      box.classList.add("revealed");
      tip.hidden = true;
      mark(answer, "answer", true);
      if (guess && guess !== answer) mark(guess, "wrong", true);
      marks.innerHTML = "";
      var p = xy(lat, lon), pts = [p];
      if (guessPin) {
        var g0 = xy(guessPin.lat, guessPin.lon);
        el("line", { x1: g0[0], y1: g0[1], x2: p[0], y2: p[1], "class": "guessline", "data-px": 2 }, marks);
        el("circle", { cx: g0[0], cy: g0[1], r: 6, "class": "pin", "data-px": 7 }, marks);
        pts.push(g0);
      } else if (guess && guess !== answer && data.countries[guess]) {
        var g = data.countries[guess], q = xy(g.lat, g.lon);
        el("line", { x1: q[0], y1: q[1], x2: p[0], y2: p[1], "class": "guessline", "data-px": 2 }, marks);
        pts.push(q);
      }
      el("circle", { cx: p[0], cy: p[1], r: 10, "class": "beacon-ring", "data-px": 16 }, marks);
      el("circle", { cx: p[0], cy: p[1], r: 5, "class": "beacon", "data-px": 6 }, marks);
      var xs = pts.map(function (v) { return v[0]; }), ys = pts.map(function (v) { return v[1]; });
      var span = Math.max(W / 25, Math.max.apply(null, xs) - Math.min.apply(null, xs));
      var cx = (Math.max.apply(null, xs) + Math.min.apply(null, xs)) / 2, cy = (Math.max.apply(null, ys) + Math.min.apply(null, ys)) / 2;
      fit(cx - span / 2, Math.min.apply(null, ys), cx + span / 2, Math.max.apply(null, ys), 0.25);
      if (cy) sizeCircles();
    }

    function clear() {
      revealed = false;
      box.classList.remove("revealed");
      marks.innerHTML = "";
      Object.keys(byKey).forEach(function (k) { mark(k, "answer", false); mark(k, "wrong", false); });
      pick(null);
      pin = null;
      reset();
    }

    window.addEventListener("resize", function () { apply(); });
    apply();
    return {
      zoomIn: function () { zoomBy(ZOOM_STEP); },
      zoomOut: function () { zoomBy(1 / ZOOM_STEP); },
      reset: reset, focus: focus, pick: pick, reveal: reveal, clear: clear, nameOf: nameOf,
      setMode: function (m) { mode = m === "location" ? "location" : "country"; box.setAttribute("data-mode", mode); },
      pointAt: function (lat, lon) {   // where a spot is, in screen pixels (for tests)
        var p = xy(lat, lon), m = svg.getScreenCTM();
        return { x: m.a * p[0] + m.e, y: m.d * p[1] + m.f };
      },
      has: function (key) { return !!byKey[key]; },
      center: function (key) {     // where a country's circle or point is, in screen pixels (for tests)
        var c = data.countries[key], p = xy(c.lat, c.lon), m = svg.getScreenCTM();
        return { x: m.a * p[0] + m.e, y: m.d * p[1] + m.f };
      }
    };
  }

  window.BeaconMap = { create: create };
})();

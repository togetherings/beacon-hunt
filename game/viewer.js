/* BeaconHunt's photo viewer.
 *
 * 360° photos (equirectangular: twice as wide as tall, the whole sphere) are
 * shown with a small WebGL viewer: drag to look around, wheel or pinch to
 * zoom, or use the arrow keys and + and -. Each screen pixel is worked out
 * in the graphics card (a "fragment shader"): which direction it looks in,
 * then which point of the photo that is. No library needed, and it's light
 * enough for old laptops and phones.
 *
 * Ordinary photos are shown whole; click or press Enter to zoom in, and drag
 * to move around.
 *
 *   var v = BeaconViewer.create(element)
 *   v.show(url, isPano)  -> Promise (resolves when the photo has loaded)
 */
(function () {
  "use strict";

  var VERTEX = [
    "attribute vec2 p;",
    "varying vec2 v;",
    "void main() { v = p; gl_Position = vec4(p, 0.0, 1.0); }"
  ].join("\n");

  // v: the pixel's place on screen (-1 to 1). yaw and pitch: where we look; f: tan(half the field of view).
  var FRAGMENT = [
    "precision highp float;",
    "varying vec2 v;",
    "uniform sampler2D img;",
    "uniform float yaw, pitch, f, aspect;",
    "const float PI = 3.14159265358979;",
    "void main() {",
    "  vec3 d = normalize(vec3(v.x * f * aspect, v.y * f, 1.0));",
    "  float cp = cos(pitch), sp = sin(pitch);",
    "  d = vec3(d.x, d.y * cp + d.z * sp, -d.y * sp + d.z * cp);",          // look up or down
    "  float lon = atan(d.x, d.z) + yaw;",
    "  float lat = asin(clamp(d.y, -1.0, 1.0));",
    "  vec2 uv = vec2(fract(lon / (2.0 * PI) + 0.5), 0.5 - lat / PI);",
    "  gl_FragColor = texture2D(img, uv);",
    "}"
  ].join("\n");

  function loadImage(url) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.crossOrigin = "anonymous";       // needed to draw it with WebGL (the server allows it)
      img.onload = function () { resolve(img); };
      img.onerror = function () { reject(new Error("The photo didn't load. Try again.")); };
      img.src = url;
    });
  }

  function Panorama(canvas) {
    var gl = canvas.getContext("webgl", { antialias: false, preserveDrawingBuffer: true }) ||
             canvas.getContext("experimental-webgl");
    if (!gl) throw new Error("no WebGL");
    function shader(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    var prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("WebGL program failed");
    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);  // one big triangle
    var loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var u = {};
    ["yaw", "pitch", "f", "aspect", "img"].forEach(function (n) { u[n] = gl.getUniformLocation(prog, n); });
    var tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    // Photos aren't a power of two wide, so: no mipmaps, and clamp at the edges.
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    var maxSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);

    var self = this, frame = 0;
    this.yaw = 0; this.pitch = 0; this.fov = 90;
    this.setImage = function (img) {
      var src = img;
      if (img.width > maxSize) {         // an old graphics card: draw the photo smaller first
        var c = document.createElement("canvas");
        c.width = maxSize; c.height = Math.round(img.height * maxSize / img.width);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        src = c;
      }
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, src);
      self.yaw = 0; self.pitch = 0; self.fov = 90;
      self.draw();
    };
    this.draw = function () {
      if (frame) return;
      frame = requestAnimationFrame(function () {
        frame = 0;
        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        var w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
        if (!w || !h) return;
        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        gl.viewport(0, 0, w, h);
        self.pitch = Math.max(-1.45, Math.min(1.45, self.pitch));
        self.fov = Math.max(25, Math.min(110, self.fov));
        gl.uniform1f(u.yaw, self.yaw);
        gl.uniform1f(u.pitch, self.pitch);
        gl.uniform1f(u.f, Math.tan(self.fov * Math.PI / 360));
        gl.uniform1f(u.aspect, w / h);
        gl.uniform1i(u.img, 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      });
    };
  }

  function create(box) {
    box.classList.add("viewer");
    box.innerHTML = "";
    var canvas = document.createElement("canvas");
    canvas.className = "pano";
    canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "360° photo. Drag, or use the arrow keys, to look around. + and - zoom.");
    var flatBox = document.createElement("div");
    flatBox.className = "flat";
    flatBox.tabIndex = 0;
    var flat = document.createElement("img");
    flat.alt = "A photo from somewhere in the world. Where is it?";
    flatBox.appendChild(flat);
    var hint = document.createElement("p");
    hint.className = "viewer-hint";
    var loading = document.createElement("p");
    loading.className = "viewer-loading";
    loading.textContent = "Loading the photo…";
    [canvas, flatBox, hint, loading].forEach(function (e) { box.appendChild(e); });

    var pano = null;
    try { pano = new Panorama(canvas); } catch (e) { pano = null; }   // no WebGL: 360° photos are shown flat and can be scrolled
    var mode = null;

    // ---- looking around a 360° photo
    var ptrs = {};
    function degPerPx() { return pano.fov / Math.max(1, canvas.clientHeight); }
    canvas.addEventListener("pointerdown", function (e) {
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture(e.pointerId);
      box.classList.add("dragging");
    });
    canvas.addEventListener("pointermove", function (e) {
      var p = ptrs[e.pointerId];
      if (!p || !pano) return;
      var keys = Object.keys(ptrs);
      if (keys.length === 2) {
        var a = ptrs[keys[0]], b = ptrs[keys[1]], before = Math.hypot(a.x - b.x, a.y - b.y);
        p.x = e.clientX; p.y = e.clientY;
        var after = Math.hypot(a.x - b.x, a.y - b.y);
        if (before > 0 && after > 0) pano.fov *= before / after;
      } else {
        var k = degPerPx() * Math.PI / 180;
        pano.yaw -= (e.clientX - p.x) * k;
        pano.pitch += (e.clientY - p.y) * k;
        p.x = e.clientX; p.y = e.clientY;
      }
      pano.draw();
    });
    function up(e) {
      delete ptrs[e.pointerId];
      if (!Object.keys(ptrs).length) box.classList.remove("dragging");
    }
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
    canvas.addEventListener("wheel", function (e) {
      if (!pano) return;
      e.preventDefault();
      pano.fov *= Math.exp((e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY) * 0.001);
      pano.draw();
    }, { passive: false });
    canvas.addEventListener("keydown", function (e) {
      if (!pano) return;
      var step = 0.15, done = true;
      if (e.key === "ArrowLeft") pano.yaw -= step;
      else if (e.key === "ArrowRight") pano.yaw += step;
      else if (e.key === "ArrowUp") pano.pitch += step;
      else if (e.key === "ArrowDown") pano.pitch -= step;
      else if (e.key === "+" || e.key === "=") pano.fov /= 1.2;
      else if (e.key === "-") pano.fov *= 1.2;
      else done = false;
      if (done) { e.preventDefault(); pano.draw(); }
    });
    window.addEventListener("resize", function () { if (pano && mode === "pano") pano.draw(); });

    // ---- an ordinary photo: click to zoom in (2.5x) and drag around, click again to see it whole
    var zoomed = false, drag = null;
    function setZoom(on, e) {
      zoomed = on;
      flatBox.classList.toggle("zoomed", on);
      if (on && e) {
        var r = flatBox.getBoundingClientRect();
        flatBox.scrollLeft = (e.clientX - r.left) / r.width * flatBox.scrollWidth - r.width / 2;
        flatBox.scrollTop = (e.clientY - r.top) / r.height * flatBox.scrollHeight - r.height / 2;
      }
    }
    flatBox.addEventListener("pointerdown", function (e) { drag = { x: e.clientX, y: e.clientY, moved: false }; });
    flatBox.addEventListener("pointermove", function (e) {
      if (!drag || !zoomed) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      flatBox.scrollLeft -= dx; flatBox.scrollTop -= dy;
      drag.x = e.clientX; drag.y = e.clientY;
    });
    flatBox.addEventListener("pointerup", function (e) {
      if (drag && !drag.moved && mode === "flat") setZoom(!zoomed, e);
      drag = null;
    });
    flatBox.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setZoom(!zoomed); }
    });

    function show(url, isPano) {
      loading.hidden = false;
      box.classList.add("loading");
      return loadImage(url).then(function (img) {
        mode = isPano && pano ? "pano" : "flat";
        canvas.hidden = mode !== "pano";
        flatBox.hidden = mode !== "flat";
        setZoom(false);
        flatBox.classList.toggle("wide", !!isPano && !pano);   // a 360° photo without WebGL: scroll along it
        if (mode === "pano") {
          pano.setImage(img);
          hint.textContent = "360° photo: drag to look around";
        } else {
          flat.src = img.src;
          hint.textContent = isPano ? "360° photo: scroll to see all of it" : "Click the photo to zoom in";
        }
        box.setAttribute("data-mode", mode);
      }).then(function () {
        loading.hidden = true;
        box.classList.remove("loading");
      }, function (err) {
        loading.textContent = err.message;
        throw err;
      });
    }

    return {
      show: show,
      redraw: function () { if (pano && mode === "pano") pano.draw(); },
      hasWebGL: !!pano,
      look: function (yaw) { if (pano) { pano.yaw = yaw; pano.draw(); } }
    };
  }

  window.BeaconViewer = { create: create };
})();

(function () {
  // A small map: tiles from nook (which gets them from OpenStreetMap), drag to move,
  // the buttons or +/- to zoom, the mouse wheel once the map has been clicked.
  var T = 256, MINZ = 2, MAXZ = 18;

  function lonToX(lon, z) { return (lon + 180) / 360 * Math.pow(2, z) * T; }
  function latToY(lat, z) {
    var s = Math.min(Math.max(Math.sin(lat * Math.PI / 180), -0.9999), 0.9999);
    return (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * Math.pow(2, z) * T;
  }
  function xToLon(x, z) { return x / (Math.pow(2, z) * T) * 360 - 180; }
  function yToLat(y, z) {
    var n = Math.PI - 2 * Math.PI * y / (Math.pow(2, z) * T);
    return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  }
  function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

  function init(el) {
    if (el.dataset.ready) return;
    el.dataset.ready = "1";
    var data = {};
    try { data = JSON.parse(el.querySelector(".mapdata").textContent) || {}; } catch (e) {}
    var markers = data.markers || [];
    var lines = data.lines || [];
    var canvas = null;
    if (lines.length) {
      canvas = document.createElement("canvas");
      canvas.className = "lines";
      el.insertBefore(canvas, el.querySelector(".pins"));
    }
    var z = clamp(parseInt(el.dataset.zoom, 10) || 4, MINZ, MAXZ);
    var cx = lonToX(parseFloat(el.dataset.lon) || 0, z);
    var cy = latToY(parseFloat(el.dataset.lat) || 0, z);
    var tiles = el.querySelector(".tiles");
    var pins = el.querySelector(".pins");
    var nodes = {}, pinNodes = [], queued = false, pending = 0;

    markers.forEach(function (m) {
      var pin = document.createElement(m.href ? "a" : "span");
      pin.className = "pin" + (m.on ? " on" : "");
      if (m.href) pin.href = m.href;
      if (m.label) pin.title = m.label;
      pins.appendChild(pin);
      pinNodes.push(pin);
    });

    function drawLines(left, top, w, h) {   // a route, drawn over the tiles
      var dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      var ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = (getComputedStyle(el).getPropertyValue("--link") || "#8a4b2a").trim();
      ctx.lineWidth = 3.5;
      ctx.lineJoin = ctx.lineCap = "round";
      lines.forEach(function (line) {
        ctx.setLineDash(line.dashed ? [2, 9] : []);
        ctx.beginPath();
        line.points.forEach(function (p, i) {
          var x = lonToX(p[1], z) - left, y = latToY(p[0], z) - top;
          if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
        });
        ctx.stroke();
      });
    }
    function sweep() {   // the new tiles are in: the old zoom level's tiles can go
      for (var k in nodes) if (nodes[k].z !== z) { nodes[k].img.remove(); delete nodes[k]; }
    }
    function render() {
      queued = false;
      var w = el.clientWidth, h = el.clientHeight, n = Math.pow(2, z);
      var left = cx - w / 2, top = cy - h / 2;
      var want = {};
      for (var ty = Math.floor(top / T); ty <= Math.floor((top + h) / T); ty++) {
        if (ty < 0 || ty >= n) continue;
        for (var tx = Math.floor(left / T); tx <= Math.floor((left + w) / T); tx++) {
          var key = z + "/" + tx + "/" + ty;
          want[key] = 1;
          if (!nodes[key]) {
            var img = document.createElement("img");
            img.alt = "";
            img.draggable = false;
            pending++;
            var settle = function () { this.classList.add("in"); if (--pending <= 0) { pending = 0; sweep(); } };
            img.addEventListener("load", settle);
            img.addEventListener("error", function () { if (--pending <= 0) { pending = 0; sweep(); } });
            img.src = "/tile/" + z + "/" + (((tx % n) + n) % n) + "/" + ty + ".png";
            tiles.appendChild(img);
            nodes[key] = { img: img, z: z, x: tx, y: ty };
          }
        }
      }
      for (var k in nodes) {
        var t = nodes[k], scale = Math.pow(2, z - t.z);
        if (t.z === z && !want[k]) { t.img.remove(); delete nodes[k]; continue; }
        // a tile from another zoom level is stretched to fit until the right one arrives
        t.img.style.transform = "translate(" + (t.x * T * scale - left).toFixed(1) + "px," +
          (t.y * T * scale - top).toFixed(1) + "px) scale(" + scale + ")";
      }
      if (canvas) drawLines(left, top, w, h);
      markers.forEach(function (m, i) {
        pinNodes[i].style.transform = "translate(" + Math.round(lonToX(m.lon, z) - left) + "px," +
          Math.round(latToY(m.lat, z) - top) + "px)";
      });
    }
    function later() { if (!queued) { queued = true; requestAnimationFrame(render); } }

    function reset() { pending = 0; }   // old tiles stay (stretched) until the new ones have loaded
    function zoomBy(d, mx, my) {
      var nz = clamp(z + d, MINZ, MAXZ);
      if (nz === z) return;
      var dx = (mx === undefined ? el.clientWidth / 2 : mx) - el.clientWidth / 2;
      var dy = (my === undefined ? el.clientHeight / 2 : my) - el.clientHeight / 2;
      var k = Math.pow(2, nz - z);
      cx = (cx + dx) * k - dx;
      cy = (cy + dy) * k - dy;
      z = nz;
      reset();
      render();
    }
    function go(lat, lon, zoom) {
      z = clamp(zoom || z, MINZ, MAXZ);
      cx = lonToX(lon, z);
      cy = latToY(lat, z);
      reset();
      render();
    }
    el.nookMap = { go: go };

    // drag
    var drag = null;
    el.addEventListener("pointerdown", function (e) {
      if (e.target.closest(".ctl, .credit, .pin")) return;
      el.focus({ preventScroll: true });
      drag = { x: e.clientX, y: e.clientY };
      el.classList.add("moving");
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    });
    el.addEventListener("pointermove", function (e) {
      if (!drag) return;
      cx -= e.clientX - drag.x;
      cy -= e.clientY - drag.y;
      drag.x = e.clientX;
      drag.y = e.clientY;
      var size = Math.pow(2, z) * T;
      cx = clamp(cx, 0, size);
      cy = clamp(cy, 0, size);
      later();
    });
    function drop() { drag = null; el.classList.remove("moving"); }
    el.addEventListener("pointerup", drop);
    el.addEventListener("pointercancel", drop);

    // zoom
    el.addEventListener("dblclick", function (e) {
      if (e.target.closest(".ctl, .credit, .pin")) return;
      var r = el.getBoundingClientRect();
      zoomBy(1, e.clientX - r.left, e.clientY - r.top);
    });
    var wheelAt = 0;
    el.addEventListener("wheel", function (e) {
      if (document.activeElement !== el) return;   // the page scrolls until the map has been clicked
      e.preventDefault();
      var now = Date.now();
      if (now - wheelAt < 220) return;
      wheelAt = now;
      var r = el.getBoundingClientRect();
      zoomBy(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    el.querySelectorAll(".ctl button").forEach(function (b) {
      b.addEventListener("click", function () { zoomBy(parseInt(b.dataset.z, 10)); });
    });
    el.addEventListener("keydown", function (e) {
      var step = 80, handled = true;
      if (e.key === "ArrowLeft") cx -= step;
      else if (e.key === "ArrowRight") cx += step;
      else if (e.key === "ArrowUp") cy -= step;
      else if (e.key === "ArrowDown") cy += step;
      else if (e.key === "+" || e.key === "=") { zoomBy(1); return; }
      else if (e.key === "-") { zoomBy(-1); return; }
      else handled = false;
      if (handled) { e.preventDefault(); later(); }
    });

    // the credit: OpenStreetMap's attribution guideline lets it fade after five seconds, or as soon as
    // the map is used (panning, clicking, zooming); the small "i" brings it back
    var credit = el.querySelector(".credit");
    if (credit) {
      var info = credit.querySelector(".info");
      var timer = setTimeout(hideCredit, 5000);
      credit.classList.add("show");
      function hideCredit() {
        clearTimeout(timer);
        credit.classList.remove("show");
        info.setAttribute("aria-expanded", "false");
      }
      el.addEventListener("pointerdown", function (e) { if (!e.target.closest(".credit")) hideCredit(); });
      el.addEventListener("wheel", hideCredit, { passive: true });
      el.addEventListener("keydown", hideCredit);
      el.querySelectorAll(".ctl button").forEach(function (b) { b.addEventListener("click", hideCredit); });
      info.addEventListener("click", function () {
        clearTimeout(timer);
        credit.classList.toggle("show");
        info.setAttribute("aria-expanded", credit.classList.contains("show") ? "true" : "false");
      });
    }

    if (window.ResizeObserver) new ResizeObserver(later).observe(el);
    else window.addEventListener("resize", later);
    render();
  }


  // --- the vector map: smooth, tilting, labels that stay readable. MapLibre draws it, from tiles and
  // fonts that nook fetches; if the browser has no WebGL, the plain picture map above takes over.
  var hasGL = (function () {
    try { var c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch (e) { return false; }
  })();
  var waiting = null;

  function loadLibrary(done, failed) {
    if (window.maplibregl) { done(); return; }
    if (waiting) { waiting.push([done, failed]); return; }
    waiting = [[done, failed]];
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/static/vendor/maplibre-gl.css";
    document.head.appendChild(css);
    var script = document.createElement("script");
    script.src = "/static/vendor/maplibre-gl-csp.js";
    script.onload = function () {
      try { maplibregl.setWorkerUrl("/static/vendor/maplibre-gl-csp-worker.js"); } catch (e) { maplibregl.workerUrl = "/static/vendor/maplibre-gl-csp-worker.js"; }
      waiting.forEach(function (w) { w[0](); });
    };
    script.onerror = function () { waiting.forEach(function (w) { w[1](); }); };
    document.head.appendChild(script);
  }

  var styles = {};
  function styleFor(theme) {
    if (!styles[theme]) {
      styles[theme] = fetch("/mapstyle/" + theme + ".json").then(function (r) { return r.json(); }).then(function (s) {
        s.sources.map.tiles = [location.origin + "/vt/{z}/{x}/{y}"];
        s.glyphs = location.origin + "/glyphs/{fontstack}/{range}";
        return s;
      });
    }
    return styles[theme];
  }
  // dark when the page is dark, whatever made it so (the system, or your own styles)
  function pageTheme() {
    var m = /rgba?\((\d+), ?(\d+), ?(\d+)/.exec(getComputedStyle(document.body).backgroundColor || "");
    return m && (0.299 * m[1] + 0.587 * m[2] + 0.114 * m[3]) < 110 ? "dark" : "light";
  }

  function vector(el) {
    if (el.dataset.ready) return;
    el.dataset.ready = "1";
    var data = {};
    try { data = JSON.parse(el.querySelector(".mapdata").textContent) || {}; } catch (e) {}
    var host = el.querySelector(".tiles");
    host.textContent = "";
    el.classList.add("vector");
    var link = getComputedStyle(el).getPropertyValue("--link").trim() || "#8a4b2a";
    var theme = pageTheme();
    var zoom = Math.max(0, Math.min(18, (parseInt(el.dataset.zoom, 10) || 4) - 1));

    styleFor(theme).then(function (style) {
      var map = new maplibregl.Map({
        container: host, style: style, center: [parseFloat(el.dataset.lon) || 0, parseFloat(el.dataset.lat) || 0],
        zoom: zoom, maxZoom: 19, attributionControl: false, fadeDuration: 150, pitchWithRotate: true, dragRotate: true
      });
      var panel = el.parentNode.querySelector(".panel");      // a details card over the map: centre on what is left visible
      if (panel && window.innerWidth > 680) {
        map.setPadding({ left: panel.offsetWidth + 24, top: 0, right: 0, bottom: 0 });
        map.jumpTo({ center: [parseFloat(el.dataset.lon) || 0, parseFloat(el.dataset.lat) || 0], zoom: zoom });
      }
      map.touchZoomRotate.disableRotation();
      map.scrollZoom.disable();                      // the page scrolls until the map has been clicked
      el.addEventListener("pointerdown", function () { map.scrollZoom.enable(); });
      el.addEventListener("blur", function () { map.scrollZoom.disable(); });

      (data.markers || []).forEach(function (m) {
        var node = document.createElement(m.href ? "a" : "span");
        node.className = "pin" + (m.on ? " on" : "");
        if (m.href) node.href = m.href;
        if (m.label) node.title = m.label;
        new maplibregl.Marker({ element: node, anchor: "center" }).setLngLat([m.lon, m.lat]).addTo(map);
      });

      function drawLines() {                          // a route, over the roads
        (data.lines || []).forEach(function (line, i) {
          var id = "route" + i;
          if (map.getLayer(id + "-line")) map.removeLayer(id + "-line");
          if (map.getLayer(id + "-casing")) map.removeLayer(id + "-casing");
          if (map.getSource(id)) map.removeSource(id);
          map.addSource(id, { type: "geojson", data: { type: "Feature", geometry: { type: "LineString",
            coordinates: line.points.map(function (p) { return [p[1], p[0]]; }) } } });
          map.addLayer({ id: id + "-casing", type: "line", source: id, layout: { "line-cap": "round", "line-join": "round" },
            paint: { "line-color": "#ffffff", "line-width": 9, "line-opacity": 0.95 } });
          map.addLayer({ id: id + "-line", type: "line", source: id, layout: { "line-cap": "round", "line-join": "round" },
            paint: Object.assign({ "line-color": "#2f7bf5", "line-width": 5 }, line.dashed ? { "line-dasharray": [0.1, 2] } : {}) });
        });
      }
      map.on("style.load", drawLines);

      var go = function (b) { return function () { if (b > 0) map.zoomIn(); else map.zoomOut(); }; };
      el.querySelectorAll(".ctl button").forEach(function (b) { b.addEventListener("click", go(parseInt(b.dataset.z, 10))); });
      el.nookMap = { go: function (lat, lon, z) { map.flyTo({ center: [lon, lat], zoom: Math.max(0, (z || 12) - 1), duration: 900 }); }, map: map };

      // the page changes between light and dark: the map follows
      var watch = window.matchMedia("(prefers-color-scheme: dark)");
      var follow = function () {
        var now = pageTheme();
        if (now !== theme) { theme = now; styleFor(now).then(function (s) { map.setStyle(s); }); }
      };
      if (watch.addEventListener) watch.addEventListener("change", function () { setTimeout(follow, 50); });

      // the credit: shown for five seconds (OpenStreetMap's own guideline), or until the map is used
      var credit = el.querySelector(".credit");
      if (credit) {
        var info = credit.querySelector(".info");
        var timer = setTimeout(hide, 5000);
        credit.classList.add("show");
        function hide() { clearTimeout(timer); credit.classList.remove("show"); info.setAttribute("aria-expanded", "false"); }
        map.on("movestart", hide);
        map.on("click", hide);
        el.querySelectorAll(".ctl button").forEach(function (b) { b.addEventListener("click", hide); });
        info.addEventListener("click", function () {
          clearTimeout(timer);
          credit.classList.toggle("show");
          info.setAttribute("aria-expanded", credit.classList.contains("show") ? "true" : "false");
        });
      }
      if (window.ResizeObserver) new ResizeObserver(function () { map.resize(); }).observe(el);
    }).catch(function () { el.dataset.ready = ""; el.classList.remove("vector"); init(el); });
  }

  function boot(el) {
    if (el.dataset.raster === "1" || !hasGL) { init(el); return; }
    loadLibrary(function () { vector(el); }, function () { init(el); });
  }

  document.querySelectorAll(".nmap").forEach(boot);
})();

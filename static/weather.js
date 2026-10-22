(function () {
  // temperature bars: set their position here (a style attribute would be blocked by the content policy)
  document.querySelectorAll(".wdays .bar i").forEach(function (i) {
    var from = parseFloat(i.dataset.from) || 0, to = parseFloat(i.dataset.to) || 0;
    i.style.left = from + "%";
    i.style.width = Math.max(4, to - from) + "%";
  });

  // places you saved, kept in this browser only
  var KEY = "nook.places", row = document.querySelector(".weatherplaces");
  function load() { try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function save(list) { try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, 8))); } catch (e) {} }
  function paint() {
    var list = load();
    if (!row) return;
    row.textContent = "";
    row.hidden = !list.length;
    list.forEach(function (p) {
      var a = document.createElement("a");
      a.textContent = p;
      a.href = "/weather?q=" + encodeURIComponent(p) + (/[?&]u=f/.test(location.search) ? "&u=f" : "");
      row.appendChild(a);
      row.appendChild(document.createTextNode(" "));
    });
  }
  paint();
  var star = document.querySelector(".starplace");
  if (star) {
    var mark = function () { star.textContent = load().indexOf(star.dataset.place) !== -1 ? "saved" : "save place"; };
    star.addEventListener("click", function () {
      var list = load(), p = star.dataset.place;
      list = list.indexOf(p) !== -1 ? list.filter(function (x) { return x !== p; }) : [p].concat(list);
      save(list);
      mark();
      paint();
    });
    mark();
  }

  // "use my location": the browser asks first
  var near = document.querySelector(".nearme"), note = document.querySelector(".nearnote");
  if (near) {
    near.addEventListener("click", function () {
      if (!navigator.geolocation) { note.textContent = "this browser can't share a location."; return; }
      note.textContent = "asking...";
      navigator.geolocation.getCurrentPosition(function (pos) {
        location.href = "/weather?ll=" + pos.coords.latitude.toFixed(3) + "," + pos.coords.longitude.toFixed(3);
      }, function () { note.textContent = "no location shared. type a city instead."; }, { timeout: 10000, maximumAge: 300000 });
    });
  }
})();

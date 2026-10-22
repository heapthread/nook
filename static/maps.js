(function () {
  // clicking a place in the list moves the map there without reloading the page
  var map = document.querySelector(".nmap");
  var list = document.querySelectorAll(".places a");
  if (!map || !list.length) return;
  list.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      if (!map.nookMap || e.ctrlKey || e.metaKey || e.shiftKey) return;
      e.preventDefault();
      map.nookMap.go(parseFloat(a.dataset.lat), parseFloat(a.dataset.lon), parseInt(a.dataset.zoom, 10));
      list.forEach(function (b) { b.parentNode.classList.remove("on"); });
      a.parentNode.classList.add("on");
      map.querySelectorAll(".pin").forEach(function (p, n) { p.classList.toggle("on", n === i); });
      try { history.replaceState(null, "", a.getAttribute("href")); } catch (err) {}
    });
  });
})();

(function () {
  // "use my location": the browser asks first; the position goes to nook for this one search only.
  var button = document.querySelector(".nearme");
  if (!button) return;
  var note = document.querySelector(".nearnote");
  if (!navigator.geolocation) { button.disabled = true; note.textContent = "this browser can't share a location."; return; }
  button.addEventListener("click", function () {
    note.textContent = "asking...";
    navigator.geolocation.getCurrentPosition(function (pos) {
      var spot = pos.coords.latitude.toFixed(3) + "," + pos.coords.longitude.toFixed(3);
      location.href = "/search?q=" + encodeURIComponent(button.dataset.q) + "&ll=" + spot;
    }, function () {
      note.textContent = "no location shared. name a place instead.";
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  });
})();

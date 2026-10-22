(function () {
  // the date, as it is where you are (the server could be anywhere)
  var el = document.getElementById("today-date");
  if (!el) return;
  var d = new Date();
  var h = d.getHours();
  var hello = h < 5 ? "still up" : h < 12 ? "good morning" : h < 18 ? "good afternoon" : "good evening";
  el.textContent = hello + " · " + d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }).toLowerCase();
})();

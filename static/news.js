(function () {
  // Marks the stories that are new since the last time this browser looked at the news.
  var SEEN = "nook.newsSeen", PREV = "nook.newsPrev";
  var stories = document.querySelectorAll(".story[data-when]");
  var note = document.querySelector(".newcount");
  if (!stories.length || !note) return;

  var now = new Date().toISOString();
  var before = null;
  try {
    // the first news page of a visit remembers when you were last here; the pages after it
    // (another wing, a search) keep comparing against that, not against a minute ago
    before = sessionStorage.getItem(PREV);
    if (before === null) {
      before = localStorage.getItem(SEEN) || "";
      sessionStorage.setItem(PREV, before);
      localStorage.setItem(SEEN, now);
    }
  } catch (e) { return; }
  if (!before) return;  // the very first visit: nothing is "new" yet

  var fresh = 0;
  stories.forEach(function (s) {
    var when = new Date(s.dataset.when).getTime();
    if (when > new Date(before).getTime()) { s.classList.add("new"); fresh++; }
  });
  if (fresh) {
    note.textContent = fresh + " new since you last looked.";
    note.hidden = false;
  }
})();

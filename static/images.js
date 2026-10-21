(function () {
  var box = document.querySelector(".lightbox");
  var links = Array.prototype.slice.call(document.querySelectorAll(".grid a"));
  if (!box || !links.length) return;
  var img = box.querySelector("img");
  var cap = box.querySelector(".cap");
  var page = box.querySelector("[data-act=page]");
  var full = box.querySelector("[data-act=full]");
  var at = 0;

  function show(i) {
    at = (i + links.length) % links.length;
    var a = links[at];
    img.src = a.href;
    img.alt = a.dataset.title;
    cap.textContent = a.dataset.title;
    page.href = a.dataset.page;
    full.href = a.href;
    box.hidden = false;
  }
  function close() { box.hidden = true; img.removeAttribute("src"); }

  links.forEach(function (a, i) {
    a.addEventListener("click", function (e) { e.preventDefault(); show(i); });
  });
  box.addEventListener("click", function (e) {
    var act = e.target.dataset && e.target.dataset.act;
    if (act === "prev") show(at - 1);
    else if (act === "next") show(at + 1);
    else if (act === "close" || e.target === box) close();
  });
  document.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowLeft") show(at - 1);
    else if (e.key === "ArrowRight") show(at + 1);
  });
})();

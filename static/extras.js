(function () {
  // --- share: copy this search, with this browser's region, engines and filters in the link
  document.querySelectorAll("[data-share]").forEach(function (b) {
    b.addEventListener("click", function () {
      var u = new URL(location.href);
      ["eng", "per", "reg", "saf"].forEach(function (k) { u.searchParams.delete(k); });
      var extra = b.dataset.share || "";
      var link = u.origin + u.pathname + u.search + (extra ? (u.search ? "&" : "?") + extra : "");
      function done() {
        var was = b.textContent;
        b.textContent = "link copied";
        setTimeout(function () { b.textContent = was; }, 1400);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(done, function () { window.prompt("copy this link", link); });
      } else {
        window.prompt("copy this link", link);
      }
    });
  });

  // --- copy: a small "copy" after a worked-out answer
  document.querySelectorAll("p.answer, .card.small:not(.timer):not(.stopwatch):not(.zones) .big").forEach(function (el) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "copyans";
    b.textContent = "copy";
    b.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(el.textContent.trim()).then(function () {
        b.textContent = "copied";
        setTimeout(function () { b.textContent = "copy"; }, 1200);
      });
    });
    el.appendChild(document.createTextNode(" "));
    el.appendChild(b);
  });

  // --- peek: the opening of a result's page, right under the result
  document.querySelectorAll("main article:not(.story):not(.reader)").forEach(function (node) {
    var read = node.querySelector("a[href^='/read?']");
    var row = node.querySelector(".via");
    if (!read || !row) return;
    var params;
    try { params = new URL(read.getAttribute("href"), location.href).searchParams; } catch (e) { return; }
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "save peekbtn";
    btn.textContent = "peek";
    var box = null, loaded = false;
    btn.addEventListener("click", function () {
      if (box) { box.hidden = !box.hidden; btn.textContent = box.hidden ? "peek" : "hide peek"; return; }
      box = document.createElement("div");
      box.className = "peek";
      box.textContent = "looking...";
      node.appendChild(box);
      btn.textContent = "hide peek";
      if (loaded) return;
      loaded = true;
      fetch("/peek?u=" + encodeURIComponent(params.get("u") || "") + "&s=" + encodeURIComponent(params.get("s") || ""))
        .then(function (r) { return r.ok ? r.json() : { text: "" }; })
        .then(function (d) { box.textContent = d.text || "this site wouldn't give nook a preview."; })
        .catch(function () { box.textContent = "this site wouldn't give nook a preview."; });
    });
    row.appendChild(document.createTextNode(" · "));
    row.appendChild(btn);
  });
})();

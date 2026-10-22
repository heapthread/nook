(function () {
  // ctrl+k (or cmd+k): one box to jump to a page, run an example, use a bang, or open something you saved.
  var box = null, input, list, shown = [], at = 0, data = null, loading = false;

  function load(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(key) || "null"); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function fetchData(then) {
    if (data) return then();
    if (loading) return;
    loading = true;
    fetch("/palette.json").then(function (r) { return r.json(); })
      .then(function (d) { data = d; then(); })
      .catch(function () { data = { pages: [], examples: [], bangs: [] }; then(); });
  }

  function candidates(text) {
    var out = [], q = text.trim();
    function go(label, href, hint) { out.push({ label: label, href: href, hint: hint || "" }); }
    if (q) {
      var enc = encodeURIComponent(q);
      go("search for " + q, "/search?q=" + enc, "web");
      go("images of " + q, "/search?q=" + enc + "&t=images", "images");
      go("videos of " + q, "/search?q=" + enc + "&t=videos", "videos");
      go("news about " + q, "/news?w=all&q=" + enc, "news");
      go("find " + q + " on the map", "/maps?q=" + enc, "maps");
      go("code: " + q, "/code?q=" + enc, "code");
    }
    (data.pages || []).forEach(function (p) { go(p[0], p[1], "page"); });
    load("nook.saved", []).forEach(function (s) {
      if (s && /^https?:\/\//.test(s.url || "")) go(s.title || s.url, s.url, "saved");
    });
    load("nook.recent", []).forEach(function (r) { go(r, "/search?q=" + encodeURIComponent(r), "recent"); });
    (data.examples || []).forEach(function (e) { go(e[1], "/search?q=" + encodeURIComponent(e[1]), e[0]); });
    (data.bangs || []).forEach(function (b) {
      if (q && q.charAt(0) === "!") return;
      go("!" + b, "/search?q=" + encodeURIComponent("!" + b + " " + (q || "")), "jump");
    });
    return out;
  }

  function score(item, q) {
    var l = item.label.toLowerCase();
    if (!q) return item.hint === "page" ? 2 : (item.hint === "recent" || item.hint === "saved") ? 1 : 0;
    if (l === q) return 100;
    if (l.indexOf(q) === 0) return 80;
    var at = l.indexOf(" " + q);
    if (at !== -1) return 60;
    if (l.indexOf(q) !== -1) return 40;
    return 0;
  }

  function refresh() {
    var q = input.value.trim().toLowerCase();
    var all = candidates(input.value);
    var typed = input.value.trim() !== "";
    var ranked = all.map(function (it, i) {
      var s = (typed && i < 6 && it.hint !== "page" && it.hint !== "saved") ? 30 - i : score(it, q);
      if (typed && i < 6 && it.hint !== "page") s = 90 - i;      // the actions for what was typed come first
      return { it: it, s: s, i: i };
    }).filter(function (r) { return typed ? r.s > 0 : r.s > 0; });
    ranked.sort(function (a, b) { return b.s - a.s || a.i - b.i; });
    var seen = {};
    shown = [];
    ranked.forEach(function (r) {
      var key = r.it.href;
      if (seen[key] || shown.length >= 9) return;
      seen[key] = 1;
      shown.push(r.it);
    });
    at = 0;
    paint();
  }

  function paint() {
    list.textContent = "";
    shown.forEach(function (it, i) {
      var li = document.createElement("li");
      li.className = i === at ? "on" : "";
      var a = document.createElement("span");
      a.className = "l";
      a.textContent = it.label;
      var h = document.createElement("span");
      h.className = "h";
      h.textContent = it.hint;
      li.appendChild(a);
      li.appendChild(h);
      li.addEventListener("mousedown", function (e) { e.preventDefault(); location.href = it.href; });
      list.appendChild(li);
    });
    if (!shown.length) {
      var li = document.createElement("li");
      li.className = "none";
      li.textContent = "nothing matches. press enter to search for it.";
      list.appendChild(li);
    }
  }

  function open() {
    if (box) { input.focus(); return; }
    box = document.createElement("div");
    box.className = "palette";
    box.innerHTML = '<div class="pbox"><input type="text" autocomplete="off" spellcheck="false" placeholder="jump to, or search for..." aria-label="jump to"><ul></ul></div>';
    document.body.appendChild(box);
    input = box.querySelector("input");
    list = box.querySelector("ul");
    box.addEventListener("mousedown", function (e) { if (e.target === box) close(); });
    input.addEventListener("input", refresh);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); at = Math.min(shown.length - 1, at + 1); paint(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); at = Math.max(0, at - 1); paint(); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "Enter") {
        e.preventDefault();
        if (shown[at]) location.href = shown[at].href;
        else if (input.value.trim()) location.href = "/search?q=" + encodeURIComponent(input.value.trim());
      }
    });
    fetchData(refresh);
    input.focus();
  }
  function close() { if (box) { box.remove(); box = null; } }

  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (box) close(); else open();
    }
  });
})();

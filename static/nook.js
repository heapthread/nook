(function () {
  var SETTINGS = "nook.home", RECENT = "nook.recent", SAVED = "nook.saved";

  function load(key, fallback) {
    try {
      var v = JSON.parse(localStorage.getItem(key) || "null");
      return v === null ? fallback : v;
    } catch (e) { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  var onPlayer = !!document.querySelector(".player");

  // --- recent searches: only when the visitor switched them on (the pencil on the home page)
  var search = document.querySelector("input[type=search]");
  if (/^\/search/.test(location.pathname) && search && search.value.trim()) {
    var settings = load(SETTINGS, {});
    if (settings.recent) {
      var q = search.value.trim();
      var list = load(RECENT, []).filter(function (x) { return x.toLowerCase() !== q.toLowerCase(); });
      list.unshift(q);
      save(RECENT, list.slice(0, 20));
    }
  }

  // --- read later: a small "save" on every result and news story
  var ITEMS = "main article, main .clip, main .story";

  function itemInfo(node) {
    var head = node.querySelector("h2 a") || node;
    var title = (head.textContent || "").trim();
    var url = head.getAttribute("href") || "", read = "";
    var readLink = node.querySelector("a[href^='/read?']");
    if (readLink) read = readLink.getAttribute("href");
    if (/^\/read\?/.test(url)) {           // a news story: its real address is inside the link
      read = url;
      try { url = new URL(url, location.href).searchParams.get("u") || ""; } catch (e) { return null; }
    }
    if (!/^https?:\/\//.test(url) || !title) return null;
    return { title: title.slice(0, 200), url: url, read: read };
  }

  function isSaved(url) {
    return load(SAVED, []).some(function (s) { return s.url === url; });
  }

  document.querySelectorAll("main article, main .story").forEach(function (node) {
    if (node.classList.contains("reader")) return;
    var info = itemInfo(node);
    var row = node.querySelector(".via");
    if (!info || !row) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "save";
    function paint() { btn.textContent = isSaved(info.url) ? "saved" : "save"; }
    btn.addEventListener("click", function () {
      var items = load(SAVED, []);
      if (isSaved(info.url)) items = items.filter(function (s) { return s.url !== info.url; });
      else items.unshift(info);
      save(SAVED, items.slice(0, 100));
      paint();
    });
    paint();
    row.appendChild(document.createTextNode(" · "));
    row.appendChild(btn);
    // hide everything from this site (kept in a cookie, so nook can leave it out next time)
    var host = "";
    try { host = new URL(info.url).hostname.replace(/^www\./, ""); } catch (e) {}
    if (host && node.tagName === "ARTICLE" && !node.classList.contains("story")) {
      var hide = document.createElement("button");
      hide.type = "button";
      hide.className = "save";
      hide.textContent = "hide site";
      hide.title = "never show " + host;
      hide.addEventListener("click", function () {
        fetch("/sites", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
                          body: "site=" + encodeURIComponent(host) })
          .then(function () { location.reload(); });
      });
      row.appendChild(document.createTextNode(" · "));
      row.appendChild(hide);
    }
  });

  // --- keyboard
  var help = null;
  function typing(e) {
    var t = e.target;
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
  }
  function items() {
    return Array.prototype.slice.call(document.querySelectorAll(ITEMS + ", main .grid a"))
      .filter(function (n) { return !n.closest(".lightbox") && !n.classList.contains("reader"); });
  }
  var at = -1;
  function move(step) {
    var list = items();
    if (!list.length) return;
    if (list[at]) list[at].classList.remove("focused");
    at = Math.min(list.length - 1, Math.max(0, at + step));
    list[at].classList.add("focused");
    list[at].scrollIntoView({ block: "center" });
  }
  function current() { return items()[at] || null; }
  function go(href) { if (href) location.href = href; }
  function tab(name) {
    var links = document.querySelectorAll(".tabs a");
    for (var i = 0; i < links.length; i++) if (links[i].textContent.trim() === name) { go(links[i].href); return; }
  }
  function toggleHelp() {
    if (help) { help.remove(); help = null; return; }
    help = document.createElement("div");
    help.className = "keyhelp";
    var rows = [["/", "search"], ["j  k", "next, previous"], ["enter", "open"], ["r", "read it here"],
                ["s", "save it"], ["1  2  3", "web, images, videos"], ["n", "news"], ["?", "this list"]];
    rows.forEach(function (r) {
      var p = document.createElement("p");
      var key = document.createElement("span");
      key.textContent = r[0];
      p.appendChild(key);
      p.appendChild(document.createTextNode(r[1]));
      help.appendChild(p);
    });
    document.body.appendChild(help);
  }

  document.addEventListener("keydown", function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") {
      if (help) toggleHelp();
      if (typing(e)) e.target.blur();
      return;
    }
    if (typing(e)) return;
    if (e.key === "/") { if (search) { e.preventDefault(); search.focus(); search.select(); } return; }
    if (e.key === "?") { toggleHelp(); return; }
    if (onPlayer || document.querySelector(".lightbox:not([hidden])")) return;  // they have keys of their own
    if (e.key === "j") move(1);
    else if (e.key === "k") move(-1);
    else if (e.key === "n") go("/news");
    else if (e.key === "1") tab("web");
    else if (e.key === "2") tab("images");
    else if (e.key === "3") tab("videos");
    else if (e.key === "Enter" || e.key === "o") {
      var it = current();
      if (!it) return;
      var link = it.tagName === "A" ? it : it.querySelector("h2 a") || it.querySelector("a");
      if (link) go(link.href);
    } else if (e.key === "r") {
      var item = current();
      var rl = item && item.querySelector("a[href^='/read?']");
      if (rl) go(rl.href);
    } else if (e.key === "s") {
      var cur = current();
      var sv = cur && cur.querySelector(".save");
      if (sv) sv.click();
    }
  });
})();

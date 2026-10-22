(function () {
  // Keeps each result's row quiet: only the engines and "read" show; everything else (save, peek,
  // hide the site, favour it, more from it, an archived copy, copy the link) sits behind "more".
  var q = (document.querySelector("input[type=search][name=q]") || {}).value || "";
  var newTab = document.body.dataset.newtab === "1";

  function text(tag, cls, label) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (label !== undefined) n.textContent = label;
    return n;
  }
  function dot() { return document.createTextNode(" · "); }

  document.querySelectorAll("main article:not(.story):not(.reader)").forEach(function (node) {
    var head = node.querySelector("h2 a");
    if (head && newTab) { head.target = "_blank"; head.rel = "noopener noreferrer"; }
    var via = node.querySelector(".via");
    var read = via && via.querySelector("a[href^='/read?']");
    if (!head || !via || !read) return;

    var acts = text("span", "acts");
    acts.hidden = true;
    var next = read.nextSibling;
    while (next) {                      // save, hide site, peek ... added by the other scripts
      var after = next.nextSibling;
      acts.appendChild(next);
      next = after;
    }

    var host = "";
    try { host = new URL(head.href).hostname.replace(/^www\./, ""); } catch (e) {}
    if (host) {
      acts.appendChild(dot());
      var site = text("a", "", "more from " + host);
      site.href = "/search?q=" + encodeURIComponent("site:" + host + " " + q.replace(/\bsite:\S+/g, "").trim());
      acts.appendChild(site);
      acts.appendChild(dot());
      var favour = text("button", "act", "favour site");
      favour.type = "button";
      favour.title = "show " + host + " first from now on";
      favour.addEventListener("click", function () {
        fetch("/sites", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
                          body: "kind=prefer&site=" + encodeURIComponent(host) }).then(function () { location.reload(); });
      });
      acts.appendChild(favour);
    }
    acts.appendChild(dot());
    var archive = text("a", "", "archive");
    archive.href = "https://web.archive.org/web/*/" + head.href;
    archive.rel = "noreferrer";
    archive.title = "an older copy of this page, from the Internet Archive";
    acts.appendChild(archive);
    acts.appendChild(dot());
    var copy = text("button", "act", "copy link");
    copy.type = "button";
    copy.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(head.href).then(function () {
        copy.textContent = "copied";
        setTimeout(function () { copy.textContent = "copy link"; }, 1200);
      });
    });
    acts.appendChild(copy);

    var toggle = text("button", "moretoggle", "more");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.addEventListener("click", function () {
      acts.hidden = !acts.hidden;
      toggle.textContent = acts.hidden ? "more" : "less";
      toggle.setAttribute("aria-expanded", acts.hidden ? "false" : "true");
    });
    via.appendChild(dot());
    via.appendChild(toggle);
    via.appendChild(acts);
  });

  // news stories and everything else with a link to somewhere: also honour "open in a new tab"
  if (newTab) {
    document.querySelectorAll("main .story h2 a, main .clip").forEach(function (a) {
      if (a.tagName === "A" && !/^\/read\?|^\/watch\?/.test(a.getAttribute("href") || "")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    });
  }
})();

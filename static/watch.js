(function () {
  // Watched searches live in this browser only: [{q, l, seen: [addresses], added}].
  // "watch" under a search adds it; /watching asks nook for the search's results again and shows what is new.
  var KEY = "nook.watch";

  function load() {
    try { var v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; }
    catch (e) { return []; }
  }
  function save(list) { try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, 30))); } catch (e) {} }
  function same(a, b) { return a.q.toLowerCase() === b.q.toLowerCase() && (a.l || "") === (b.l || ""); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function params(w) {
    return "q=" + encodeURIComponent(w.q) + (w.l ? "&l=" + encodeURIComponent(w.l) : "");
  }

  // --- the button under a search
  var button = document.querySelector("button.watch");
  if (button) {
    var here = { q: button.dataset.q, l: button.dataset.lens || "" };
    var paint = function () {
      button.textContent = load().some(function (w) { return same(w, here); }) ? "watching" : "watch";
    };
    button.addEventListener("click", function () {
      var list = load();
      if (list.some(function (w) { return same(w, here); })) {
        list = list.filter(function (w) { return !same(w, here); });
      } else {
        var seen = [];
        document.querySelectorAll("main article h2 a").forEach(function (a) { seen.push(a.getAttribute("href")); });
        list.unshift({ q: here.q, l: here.l, seen: seen.slice(0, 60), added: new Date().toISOString() });
      }
      save(list);
      paint();
    });
    paint();
  }

  // --- /watching and the little count on /today
  function fresh(w) {
    return fetch("/search.json?" + params(w)).then(function (r) { return r.ok ? r.json() : null; });
  }

  var holder = document.getElementById("watch-list");
  if (holder) {
    var none = document.querySelector(".none");
    var draw = function () {
      var list = load();
      holder.textContent = "";
      none.hidden = list.length > 0;
      list.forEach(function (w) {
        var box = el("section", "watch");
        var head = el("h2");
        var a = el("a", "", w.q + (w.l ? " (" + w.l + ")" : ""));
        a.href = "/search?" + params(w);
        head.appendChild(a);
        box.appendChild(head);
        var status = el("p", "note", "looking...");
        box.appendChild(status);
        var out = el("ul", "watchnew");
        box.appendChild(out);
        var actions = el("p", "actions");
        var feed = el("a", "", "feed");
        feed.href = "/search.rss?" + params(w);
        var stop = el("button", "", "stop watching");
        stop.type = "button";
        stop.addEventListener("click", function () {
          save(load().filter(function (x) { return !same(x, w); }));
          draw();
        });
        actions.appendChild(feed);
        actions.appendChild(document.createTextNode(" · "));
        actions.appendChild(stop);
        box.appendChild(actions);
        holder.appendChild(box);
        fresh(w).then(function (data) {
          if (!data) { status.textContent = "couldn't ask just now."; return; }
          var known = {};
          (w.seen || []).forEach(function (u) { known[u] = 1; });
          var added = data.results.filter(function (r) { return !known[r.url]; });
          status.textContent = added.length ? added.length + " new since you last looked" : "nothing new";
          added.slice(0, 8).forEach(function (r) {
            var li = el("li");
            var link = el("a", "", r.title);
            link.href = r.url;
            link.rel = "noreferrer";
            li.appendChild(link);
            out.appendChild(li);
          });
          if (added.length) {
            var seen = el("button", "", "mark as seen");
            seen.type = "button";
            seen.addEventListener("click", function () {
              var list2 = load();
              list2.forEach(function (x) {
                if (same(x, w)) x.seen = data.results.map(function (r) { return r.url; }).concat(x.seen || []).slice(0, 80);
              });
              save(list2);
              draw();
            });
            actions.appendChild(document.createTextNode(" · "));
            actions.appendChild(seen);
          }
        }).catch(function () { status.textContent = "couldn't ask just now."; });
      });
    };
    draw();
  }

  var glance = document.getElementById("today-watch");
  if (glance) {
    var all = load();
    if (all.length) {
      glance.hidden = false;
      var line = glance.querySelector(".lines");
      all.slice(0, 5).forEach(function (w) {
        var row = el("p");
        var a = el("a", "", w.q);
        a.href = "/search?" + params(w);
        var count = el("span", "soft", " …");
        row.appendChild(a);
        row.appendChild(count);
        line.appendChild(row);
        fresh(w).then(function (data) {
          if (!data) { count.textContent = ""; return; }
          var known = {};
          (w.seen || []).forEach(function (u) { known[u] = 1; });
          var n = data.results.filter(function (r) { return !known[r.url]; }).length;
          count.textContent = n ? " · " + n + " new" : " · nothing new";
        }).catch(function () { count.textContent = ""; });
      });
    }
  }
})();

(function () {
  var SAVED = "nook.saved", RECENT = "nook.recent", NOTES = "nook.notes", HOME = "nook.home";

  function load(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(key) || "null"); return v === null ? fallback : v; }
    catch (e) { return fallback; }
  }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }
  function host(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // --- saved
  var sec = document.getElementById("shelf-saved");
  var find = sec.querySelector(".shelf-find"), tagsBox = sec.querySelector(".tags");
  var ul = sec.querySelector(".shelf-items"), none = sec.querySelector(".none");
  var tagNow = "";

  function items() { return load(SAVED, []).filter(function (s) { return s && /^https?:\/\//.test(s.url || ""); }); }

  function paintSaved() {
    var all = items(), q = find.value.trim().toLowerCase();
    var tags = [];
    all.forEach(function (s) { if (s.tag && tags.indexOf(s.tag) === -1) tags.push(s.tag); });
    if (tagNow && tags.indexOf(tagNow) === -1) tagNow = "";
    tagsBox.textContent = "";
    tagsBox.hidden = !tags.length;
    if (tags.length) {
      tagsBox.appendChild(el("span", "soft", "tags "));
      tags.forEach(function (t) {
        var b = el("button", t === tagNow ? "tag on" : "tag", t);
        b.type = "button";
        b.addEventListener("click", function () { tagNow = t === tagNow ? "" : t; paintSaved(); });
        tagsBox.appendChild(b);
        tagsBox.appendChild(document.createTextNode(" "));
      });
    }
    var shown = all.filter(function (s) {
      if (tagNow && s.tag !== tagNow) return false;
      return !q || (s.title + " " + s.url + " " + (s.tag || "")).toLowerCase().indexOf(q) !== -1;
    });
    ul.textContent = "";
    shown.forEach(function (s) {
      var li = el("li");
      var a = el("a", "", s.title || s.url);
      a.href = s.url;
      a.rel = "noreferrer";
      li.appendChild(a);
      li.appendChild(el("span", "via", " " + host(s.url)));
      if (/^\/read\?/.test(s.read || "")) {
        var r = el("a", "soft-link", "read");
        r.href = s.read;
        li.appendChild(document.createTextNode(" "));
        li.appendChild(r);
      }
      var tag = el("button", "soft-link", s.tag ? "tag: " + s.tag : "tag");
      tag.type = "button";
      tag.addEventListener("click", function () {
        var field = el("input", "tagfield");
        field.type = "text";
        field.value = s.tag || "";
        field.maxLength = 24;
        field.placeholder = "a word";
        tag.replaceWith(field);
        field.focus();
        function commit() {
          var list = load(SAVED, []);
          list.forEach(function (x) { if (x.url === s.url) x.tag = field.value.trim().toLowerCase().slice(0, 24) || undefined; });
          save(SAVED, list);
          paintSaved();
        }
        field.addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); commit(); }
          else if (e.key === "Escape") paintSaved();
        });
        field.addEventListener("blur", commit);
      });
      li.appendChild(tag);
      var x = el("button", "forget", "×");
      x.type = "button";
      x.title = "remove";
      x.addEventListener("click", function () {
        save(SAVED, load(SAVED, []).filter(function (t) { return t.url !== s.url; }));
        paintSaved();
      });
      li.appendChild(x);
      ul.appendChild(li);
    });
    none.hidden = all.length > 0;
    if (all.length && !shown.length) { none.hidden = false; none.textContent = "nothing saved matches that."; }
  }
  find.addEventListener("input", paintSaved);
  sec.querySelector("[data-act=copy]").addEventListener("click", function (e) {
    var text = items().map(function (s) { return "- [" + (s.title || s.url) + "](" + s.url + ")"; }).join("\n");
    var b = e.target, was = b.textContent;
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(function () {
      b.textContent = "copied";
      setTimeout(function () { b.textContent = was; }, 1200);
    });
  });
  sec.querySelector("[data-act=clear]").addEventListener("click", function () {
    if (items().length && confirm("remove everything you saved?")) { save(SAVED, []); paintSaved(); }
  });
  paintSaved();

  // --- kept copies (articles saved from the reader)
  var keptSec = document.getElementById("shelf-kept");
  var keptList = keptSec.querySelector(".shelf-items"), keptView = keptSec.querySelector(".keptview");
  function paintKept() {
    var list = load("nook.kept", []).filter(function (k) { return k && k.title && Array.isArray(k.paras); });
    keptList.textContent = "";
    keptView.hidden = true;
    keptSec.querySelector(".none").hidden = list.length > 0;
    list.forEach(function (k) {
      var li = el("li");
      var open = el("a", "", k.title);
      open.href = "#";
      open.addEventListener("click", function (e) {
        e.preventDefault();
        keptView.textContent = "";
        keptView.appendChild(el("h1", "", k.title));
        keptView.appendChild(el("p", "via", (k.source || host(k.url)) + " · kept " + (k.when || "").slice(0, 10)));
        k.paras.forEach(function (p) { keptView.appendChild(el("p", "", p)); });
        var back = el("a", "btn", "original page");
        back.href = k.url;
        back.rel = "noreferrer";
        keptView.appendChild(back);
        keptView.hidden = false;
        keptView.scrollIntoView({ block: "start" });
      });
      li.appendChild(open);
      li.appendChild(el("span", "via", " " + (k.source || host(k.url)) + " · " + Math.max(1, Math.round(k.paras.join(" ").split(/\s+/).length / 230)) + " min"));
      var x = el("button", "forget", "×");
      x.type = "button";
      x.title = "remove";
      x.addEventListener("click", function () {
        save("nook.kept", load("nook.kept", []).filter(function (t) { return t.url !== k.url; }));
        paintKept();
      });
      li.appendChild(x);
      keptList.appendChild(li);
    });
  }
  paintKept();

  // --- recent searches
  var rec = document.getElementById("shelf-recent");
  function paintRecent() {
    var list = load(RECENT, []);
    var holder = rec.querySelector(".items");
    holder.textContent = "";
    list.forEach(function (q) {
      var a = el("a", "", q);
      a.href = "/search?q=" + encodeURIComponent(q);
      holder.appendChild(a);
    });
    rec.querySelector(".none").hidden = list.length > 0;
    rec.querySelector(".actions").hidden = !list.length;
  }
  rec.querySelector("[data-act=clear]").addEventListener("click", function () {
    try { localStorage.removeItem(RECENT); } catch (e) {}
    paintRecent();
  });
  paintRecent();

  // --- notes (the same box as on the home page)
  var area = document.querySelector("#shelf-notes textarea"), typing = null;
  try { area.value = localStorage.getItem(NOTES) || ""; } catch (e) {}
  area.addEventListener("input", function () {
    clearTimeout(typing);
    typing = setTimeout(function () { try { localStorage.setItem(NOTES, area.value.slice(0, 20000)); } catch (e) {} }, 300);
  });

  // --- bookmarks (edited with the pencil on the home page)
  var marks = document.querySelector("#shelf-marks .marks"), any = false;
  String((load(HOME, {}).marks) || "").split("\n").forEach(function (line) {
    line = line.trim();
    if (!line) return;
    var at = line.search(/\S+$/), raw = line.slice(at), label = line.slice(0, at).trim();
    if (!/^[a-z][a-z0-9+.-]*:/i.test(raw)) raw = "https://" + raw;
    try {
      var u = new URL(raw);
      if (u.protocol !== "http:" && u.protocol !== "https:") return;
      var li = el("li"), a = el("a", "", label || u.hostname.replace(/^www\./, ""));
      a.href = u.href;
      a.rel = "noreferrer";
      li.appendChild(a);
      marks.appendChild(li);
      any = true;
    } catch (e) {}
  });
  document.querySelector("#shelf-marks .none").hidden = any;
})();

(function () {
  var KEY = "nook.home", RECENT = "nook.recent", SAVED = "nook.saved", NOTES = "nook.notes";
  var COOKIES = ["nook_engines", "nook_region", "nook_safe", "nook_period", "nook_hide", "nook_prefer", "nook_news", "nook_pics", "nook_suggest", "nook_myfeeds", "nook_today", "nook_tab"];
  var pencil = document.querySelector(".pencil");
  var box = document.querySelector(".personal");
  var editor = document.querySelector(".editor");
  var recentBox = document.querySelector(".recent");
  var savedBox = document.querySelector(".saved");
  var notesBox = document.querySelector(".notes");
  if (!pencil || !box || !editor) return;

  function read(key, fallback) {
    try {
      var v = JSON.parse(localStorage.getItem(key) || "null");
      if (v !== null && typeof v === typeof fallback) return v;
    } catch (e) {}
    return fallback;
  }
  function write(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }
  function load() {
    var d = read(KEY, {});
    return {
      on: !!d.on, name: d.name || "", marks: d.marks || "", recent: !!d.recent,
      showSaved: d.showSaved !== false, notes: !!d.notes, daily: !!d.daily
    };
  }

  // "label address" per line; only http(s) addresses are linked
  function parseMarks(text) {
    var out = [];
    text.split("\n").forEach(function (line) {
      line = line.trim();
      if (!line || out.length >= 12) return;
      var at = line.search(/\S+$/);
      var raw = line.slice(at);
      var label = line.slice(0, at).trim();
      if (!/^[a-z][a-z0-9+.-]*:/i.test(raw)) raw = "https://" + raw;
      try {
        var u = new URL(raw);
        if (u.protocol !== "http:" && u.protocol !== "https:") return;
        out.push({ label: label || u.hostname.replace(/^www\./, ""), href: u.href });
      } catch (e) {}
    });
    return out;
  }

  function greeting(name) {
    var h = new Date().getHours();
    var hello = h < 5 ? "still up" : h < 12 ? "good morning" : h < 18 ? "good afternoon" : "good evening";
    return name ? hello + ", " + name : hello;
  }

  function link(text, href) {
    var a = document.createElement("a");
    a.textContent = text;
    a.href = href;
    a.rel = "noreferrer";
    return a;
  }

  function renderRecent(data) {
    var list = data.recent ? read(RECENT, []).slice(0, 8) : [];
    recentBox.hidden = !list.length;
    var holder = recentBox.querySelector(".items");
    holder.textContent = "";
    list.forEach(function (q) {
      var a = link(q, "/search?q=" + encodeURIComponent(q));
      a.rel = "";
      holder.appendChild(a);
    });
  }

  function renderSaved(data) {
    var items = data.showSaved ? read(SAVED, []) : [];
    savedBox.hidden = !items.length;
    var ul = savedBox.querySelector(".items");
    ul.textContent = "";
    items.slice(0, 10).forEach(function (s) {
      if (!/^https?:\/\//.test(s.url || "")) return;
      var li = document.createElement("li");
      li.appendChild(link(s.title || s.url, s.url));
      if (/^\/read\?/.test(s.read || "")) {
        li.appendChild(document.createTextNode(" "));
        var r = link("read", s.read);
        r.rel = "";
        r.className = "soft-link";
        li.appendChild(r);
      }
      var x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.title = "remove";
      x.className = "forget";
      x.addEventListener("click", function () {
        write(SAVED, read(SAVED, []).filter(function (t) { return t.url !== s.url; }));
        renderSaved(data);
      });
      li.appendChild(x);
      ul.appendChild(li);
    });
  }

  function render(data) {
    box.hidden = !data.on;
    if (data.on) {
      box.querySelector(".greeting").textContent = greeting((data.name || "").trim());
      box.querySelector(".date").textContent = new Date()
        .toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }).toLowerCase();
      var marks = box.querySelector(".marks");
      marks.textContent = "";
      parseMarks(data.marks || "").forEach(function (m) {
        var li = document.createElement("li");
        li.appendChild(link(m.label, m.href));
        marks.appendChild(li);
      });
    }
    renderRecent(data);
    renderSaved(data);
    renderNotes(data);
    renderDaily(data);
  }

  // today's word (Wiktionary, through nook), only when it was switched on
  var dailyBox = document.querySelector(".daily");
  function renderDaily(data) {
    if (!dailyBox) return;
    dailyBox.hidden = true;
    if (!data.daily) return;
    fetch("/daily.json").then(function (r) { return r.ok ? r.json() : {}; }).then(function (w) {
      if (!w || !w.word) return;
      dailyBox.textContent = "";
      var a = document.createElement("a");
      a.textContent = w.word;
      a.href = "/search?q=" + encodeURIComponent("define " + w.word);
      dailyBox.appendChild(a);
      if (w.definition) dailyBox.appendChild(document.createTextNode(" — " + w.definition));
      dailyBox.hidden = false;
    }).catch(function () {});
  }

  // a small notes box, saved as you type
  var typing = null;
  function renderNotes(data) {
    if (!notesBox) return;
    notesBox.hidden = !data.notes;
    var area = notesBox.querySelector("textarea");
    if (data.notes && area.dataset.ready !== "1") {
      area.dataset.ready = "1";
      try { area.value = localStorage.getItem(NOTES) || ""; } catch (e) {}
      area.addEventListener("input", function () {
        clearTimeout(typing);
        typing = setTimeout(function () {
          try { localStorage.setItem(NOTES, area.value.slice(0, 20000)); } catch (e) {}
        }, 300);
      });
    }
  }

  function fill(data) {
    editor.elements.on.checked = data.on;
    editor.elements.recent.checked = data.recent;
    editor.elements.showSaved.checked = data.showSaved;
    editor.elements.notes.checked = data.notes;
    editor.elements.daily.checked = data.daily;
    editor.elements.name.value = data.name;
    editor.elements.marks.value = data.marks;
    try { editor.elements.css.value = localStorage.getItem("nook.css") || ""; } catch (e) {}
  }

  var data = load();
  render(data);

  pencil.addEventListener("click", function () {
    editor.hidden = !editor.hidden;
    pencil.classList.toggle("open", !editor.hidden);
    if (!editor.hidden) { fill(load()); editor.elements.on.focus(); }
  });
  editor.addEventListener("submit", function (e) {
    e.preventDefault();
    data = {
      on: editor.elements.on.checked, name: editor.elements.name.value, marks: editor.elements.marks.value,
      recent: editor.elements.recent.checked, showSaved: editor.elements.showSaved.checked,
      notes: editor.elements.notes.checked, daily: editor.elements.daily.checked
    };
    write(KEY, data);
    var css = editor.elements.css.value.slice(0, 20000), before = "";
    try { before = localStorage.getItem("nook.css") || ""; } catch (e) {}
    try { if (css.trim()) localStorage.setItem("nook.css", css); else localStorage.removeItem("nook.css"); } catch (e) {}
    if (css.trim() !== before.trim()) { location.reload(); return; }   // the new styles show straight away
    render(data);
    editor.hidden = true;
    pencil.classList.remove("open");
  });
  editor.querySelector("[data-act=clear]").addEventListener("click", function () {
    try {
      Object.keys(localStorage).filter(function (k) { return k.indexOf("nook.") === 0; })
        .forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) {}
    data = load();
    fill(data);
    render(data);
  });
  editor.querySelector("[data-act=clear-lists]").addEventListener("click", function () {
    try { localStorage.removeItem(RECENT); localStorage.removeItem(SAVED); } catch (e) {}
    render(load());
  });

  // --- back up and restore: everything nook keeps in this browser, in one small file
  var status = editor.querySelector(".status");
  function say(text) { if (status) status.textContent = text; }

  function cookieValue(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? m[1] : null;
  }

  editor.querySelector("[data-act=backup]").addEventListener("click", function () {
    var stored = {}, cookies = {};
    try {
      Object.keys(localStorage).filter(function (k) { return k.indexOf("nook.") === 0; })
        .forEach(function (k) { stored[k] = localStorage.getItem(k); });
    } catch (e) {}
    COOKIES.forEach(function (c) { var v = cookieValue(c); if (v !== null) cookies[c] = v; });
    var file = { nook: 1, saved: new Date().toISOString(), data: stored, cookies: cookies };
    var url = URL.createObjectURL(new Blob([JSON.stringify(file, null, 1)], { type: "application/json" }));
    var a = document.createElement("a");
    a.href = url;
    a.download = "nook-backup.json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    say("saved nook-backup.json");
  });

  var picker = editor.querySelector("input[type=file]");
  editor.querySelector("[data-act=restore]").addEventListener("click", function () { picker.click(); });
  picker.addEventListener("change", function () {
    var file = picker.files && picker.files[0];
    if (!file) return;
    if (file.size > 1000000) { say("that file is too big to be a nook backup"); return; }
    var reader = new FileReader();
    reader.onload = function () {
      var back;
      try { back = JSON.parse(reader.result); } catch (e) { back = null; }
      if (!back || back.nook !== 1 || typeof back.data !== "object" || back.data === null) {
        say("that doesn't look like a nook backup");
        return;
      }
      var count = 0;
      Object.keys(back.data).forEach(function (k) {
        var v = back.data[k];
        if (k.indexOf("nook.") === 0 && typeof v === "string" && v.length < 500000) {
          try { localStorage.setItem(k, v); count++; } catch (e) {}
        }
      });
      var jar = back.cookies && typeof back.cookies === "object" ? back.cookies : {};
      COOKIES.forEach(function (c) {
        var v = jar[c];
        if (typeof v === "string" && /^[A-Za-z0-9.|_%~:\/?&=+@\-]{1,3500}$/.test(v)) {
          document.cookie = c + "=" + v + "; max-age=31536000; path=/; samesite=lax";
          count++;
        }
      });
      say("restored " + count + " things");
      setTimeout(function () { location.reload(); }, 600);
    };
    reader.readAsText(file);
    picker.value = "";
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !editor.hidden) pencil.click();
  });
})();

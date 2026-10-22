(function () {
  var KEY = "nook.reader";
  var box = document.querySelector(".reader");
  var tools = document.querySelector(".tools");
  if (!box || !tools) return;

  function load() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || "{}");
      return { size: Math.max(-1, Math.min(3, parseInt(v.size, 10) || 0)), wide: !!v.wide };
    } catch (e) { return { size: 0, wide: false }; }
  }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {} }

  var state = load();
  var wide = tools.querySelector("[data-act=wide]");

  function apply() {
    for (var i = -1; i <= 3; i++) box.classList.remove("s" + i);
    box.classList.add("s" + state.size);
    box.classList.toggle("wide", state.wide);
    wide.textContent = state.wide ? "narrower" : "wider";
  }
  apply();

  tools.querySelector("[data-act=smaller]").addEventListener("click", function () {
    state.size = Math.max(-1, state.size - 1); save(state); apply();
  });
  tools.querySelector("[data-act=bigger]").addEventListener("click", function () {
    state.size = Math.min(3, state.size + 1); save(state); apply();
  });
  wide.addEventListener("click", function () { state.wide = !state.wide; save(state); apply(); });

  // how far down the article you are: a thin line at the top of the page
  var line = document.createElement("div");
  line.className = "progress";
  document.body.appendChild(line);
  function reading() {
    var room = document.documentElement.scrollHeight - window.innerHeight;
    line.style.width = (room > 0 ? Math.min(100, window.scrollY / room * 100) : 0) + "%";
  }
  window.addEventListener("scroll", reading, { passive: true });
  reading();

  // keep a copy: the article's text, in this browser only (see the shelf)
  var keep = tools.querySelector("[data-act=keep]");
  var KEPT = "nook.kept";
  function kept() { try { var v = JSON.parse(localStorage.getItem(KEPT) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function mine() {
    try { return JSON.parse(document.getElementById("kept-data").textContent); } catch (e) { return null; }
  }
  function paintKeep() {
    var d = mine();
    keep.textContent = d && kept().some(function (k) { return k.url === d.url; }) ? "kept" : "keep a copy";
  }
  if (keep) {
    keep.addEventListener("click", function () {
      var d = mine();
      if (!d) return;
      var list = kept();
      if (list.some(function (k) { return k.url === d.url; })) {
        list = list.filter(function (k) { return k.url !== d.url; });
      } else {
        d.when = new Date().toISOString();
        list.unshift(d);
        // browsers keep only a few megabytes per site: drop the oldest copies when it gets full
        while (list.length > 1 && JSON.stringify(list).length > 2500000) list.pop();
      }
      try { localStorage.setItem(KEPT, JSON.stringify(list.slice(0, 40))); } catch (e) { keep.textContent = "no room"; return; }
      paintKeep();
    });
    paintKeep();
  }

  // listen: the browser's own voice reads the article, so nothing is sent anywhere
  var listen = tools.querySelector("[data-act=listen]");
  var synth = window.speechSynthesis;
  if (!synth || !window.SpeechSynthesisUtterance) return;
  listen.hidden = false;

  var speaking = false;
  function chunks() {
    var parts = [box.querySelector("h1").textContent];
    box.querySelectorAll("p:not(.actions):not(.tools):not(.note)").forEach(function (p) {
      var text = p.textContent.trim();
      if (!text) return;
      // long paragraphs go in sentence-sized pieces, which some voices need
      (text.match(/[^.!?]+[.!?]+["')\]]*\s*|[^.!?]+$/g) || [text]).forEach(function (s) {
        if (s.trim()) parts.push(s.trim());
      });
    });
    return parts;
  }
  function stop() {
    speaking = false;
    synth.cancel();
    listen.textContent = "listen";
  }
  listen.addEventListener("click", function () {
    if (speaking) { stop(); return; }
    var parts = chunks(), at = 0;
    speaking = true;
    listen.textContent = "stop";
    (function next() {
      if (!speaking || at >= parts.length) { if (speaking) stop(); return; }
      var u = new SpeechSynthesisUtterance(parts[at++]);
      u.lang = document.documentElement.lang || "en";
      u.onend = next;
      u.onerror = stop;
      synth.speak(u);
    })();
  });
  window.addEventListener("pagehide", function () { synth.cancel(); });
})();

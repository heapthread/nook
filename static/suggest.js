(function () {
  // Suggestions while typing: nook asks DuckDuckGo for you after a short pause. Switch them off
  // with "suggestions" in the engines dropdown.
  if (document.body.dataset.suggest !== "1") return;
  var inputs = document.querySelectorAll("input[type=search][name=q]");
  if (!inputs.length) return;

  inputs.forEach(function (input) {
    var list = document.createElement("ul");
    list.className = "suggest";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    document.body.appendChild(list);
    var timer = null, asked = 0, typed = "", at = -1, items = [];

    function place() {
      var r = input.getBoundingClientRect();
      list.style.left = (r.left + window.scrollX) + "px";
      list.style.top = (r.bottom + window.scrollY + 2) + "px";
      list.style.width = r.width + "px";
    }
    function close() { list.hidden = true; at = -1; items = []; }
    function paint() {
      list.textContent = "";
      items.forEach(function (text, i) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.textContent = text;
        if (i === at) li.className = "on";
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          choose(text);
        });
        list.appendChild(li);
      });
      list.hidden = !items.length;
      if (items.length) place();
    }
    function recent() {   // only if recent searches were switched on with the pencil on the home page
      try {
        if (!(JSON.parse(localStorage.getItem("nook.home") || "{}").recent)) return [];
        var list = JSON.parse(localStorage.getItem("nook.recent") || "[]");
        return Array.isArray(list) ? list.slice(0, 6) : [];
      } catch (e) { return []; }
    }
    input.addEventListener("focus", function () {
      if (input.value.trim() === "") { items = recent(); at = -1; typed = ""; paint(); }
    });
    function choose(text) {
      input.value = text;
      close();
      if (input.form) input.form.submit();
    }

    input.addEventListener("input", function (e) {
      if (e.isComposing) return;
      typed = input.value;
      clearTimeout(timer);
      if (typed.trim() === "") { items = recent(); at = -1; paint(); return; }
      if (typed.trim().length < 2) { close(); return; }
      timer = setTimeout(function () {
        var mine = ++asked;
        fetch("/suggest?q=" + encodeURIComponent(typed.trim()))
          .then(function (r) { return r.ok ? r.json() : []; })
          .then(function (found) {
            if (mine !== asked || document.activeElement !== input) return;
            items = Array.isArray(found) ? found.slice(0, 6) : [];
            at = -1;
            paint();
          })
          .catch(close);
      }, 130);
    });
    input.addEventListener("keydown", function (e) {
      if (list.hidden) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        at += e.key === "ArrowDown" ? 1 : -1;
        if (at < -1) at = items.length - 1;
        if (at >= items.length) at = -1;
        input.value = at === -1 ? typed : items[at];
        paint();
      } else if (e.key === "Escape") {
        if (at !== -1) input.value = typed;
        close();
      }
    });
    input.addEventListener("blur", function () { setTimeout(close, 120); });
    window.addEventListener("resize", function () { if (!list.hidden) place(); });
  });
})();

(function () {
  // copy buttons: put the text of the element they name on the clipboard
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      var el = document.getElementById(b.dataset.copy);
      if (!el || !navigator.clipboard) return;
      navigator.clipboard.writeText(el.textContent.trim()).then(function () {
        var was = b.textContent;
        b.textContent = "copied";
        setTimeout(function () { b.textContent = was; }, 1200);
      });
    });
  });

  // stopwatch: start, lap, reset (kept in the page, nothing is sent anywhere)
  var watch = document.querySelector(".stopwatch");
  if (watch) {
    var face = watch.querySelector(".big"), laps = watch.querySelector(".laps"), go = watch.querySelector("[data-act=go]");
    var began = 0, before = 0, ticking = null;
    var show = function (ms) {
      var t = Math.floor(ms / 100) / 10, m = Math.floor(t / 60), s = (t - m * 60).toFixed(1);
      return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
    };
    var now = function () { return before + (ticking ? Date.now() - began : 0); };
    go.addEventListener("click", function () {
      if (ticking) { before = now(); clearInterval(ticking); ticking = null; go.textContent = "start"; return; }
      began = Date.now();
      ticking = setInterval(function () { face.textContent = show(now()); }, 50);
      go.textContent = "stop";
    });
    watch.querySelector("[data-act=lap]").addEventListener("click", function () {
      if (!now()) return;
      var li = document.createElement("li");
      li.textContent = show(now());
      laps.insertBefore(li, laps.firstChild);
    });
    watch.querySelector("[data-act=reset]").addEventListener("click", function () {
      clearInterval(ticking); ticking = null; before = 0; go.textContent = "start"; face.textContent = show(0); laps.textContent = "";
    });
  }

  // pronunciation: play the clip nook passed through
  var say = document.querySelector(".say");
  if (say) {
    var clip = null;
    say.addEventListener("click", function () {
      if (!clip) clip = new Audio(say.dataset.audio);
      clip.currentTime = 0;
      clip.play();
    });
  }

  // timer: counts down in the page, beeps when it is done
  var box = document.querySelector(".timer");
  if (!box) return;
  var total = parseInt(box.dataset.seconds, 10);
  var left = total, running = false, tick = null, endAt = 0;
  var big = box.querySelector(".big");
  var start = box.querySelector("[data-act=start]");
  var reset = box.querySelector("[data-act=reset]");
  var title = document.title;

  function show(s) {
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    var two = function (n) { return (n < 10 ? "0" : "") + n; };
    big.textContent = (h ? h + ":" + two(m) : m) + ":" + two(r);
  }
  function beep() {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.35, 0.7].forEach(function (when) {
        var osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.frequency.value = 880;
        gain.gain.value = 0.15;
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(ctx.currentTime + when);
        osc.stop(ctx.currentTime + when + 0.2);
      });
    } catch (e) {}
  }
  function stop() { running = false; clearInterval(tick); start.textContent = "start"; }
  function frame() {
    left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
    show(left);
    document.title = (left ? big.textContent + " · " : "time's up · ") + title;
    if (left === 0) { stop(); beep(); big.textContent = "time's up"; }
  }
  start.addEventListener("click", function () {
    if (running) { stop(); return; }
    if (left === 0) left = total;
    endAt = Date.now() + left * 1000;
    running = true;
    start.textContent = "pause";
    tick = setInterval(frame, 250);
    frame();
  });
  reset.addEventListener("click", function () {
    stop(); left = total; show(left); document.title = title;
  });
  show(left);
})();

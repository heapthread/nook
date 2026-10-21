(function () {
  var root = document.querySelector(".player");
  if (!root) return;
  var $ = function (s) { return root.querySelector(s); };
  var stage = $(".stage"), screen = $(".screen"), veil = $(".veil span"), poster = $(".poster");
  var pp = $(".pp"), time = $(".time"), seek = $(".seek");
  var mute = $(".mute"), vol = $(".vol"), full = $(".full"), oops = $(".oops");
  var kind = root.dataset.kind, source = root.dataset.source;
  var scrubbing = false;
  var started = false;

  // Until play is pressed this does nothing, so nothing is requested from YouTube or the
  // video's host. After that `a` is swapped for an adapter around the real player.
  var idle = {
    play: function () { start(); }, pause: function () {},
    playing: function () { return false; },
    time: function () { return 0; }, duration: function () { return 0; },
    seek: function () {}, volume: function () {},
    muted: function () { return false; }, mute: function () {}
  };
  var a = idle;

  function fmt(s) {
    s = Math.max(0, Math.floor(s || 0));
    var m = Math.floor(s / 60), r = s % 60;
    return m + ":" + (r < 10 ? "0" : "") + r;
  }
  function paint() {
    var d = a.duration(), t = a.time();
    if (!scrubbing) {
      time.textContent = fmt(t) + " / " + fmt(d);
      if (d) seek.value = Math.round((t / d) * 1000);
    }
    var playing = a.playing();
    pp.textContent = playing ? "pause" : "play";
    veil.textContent = playing ? "" : "play";
    stage.classList.toggle("playing", playing);
    mute.textContent = a.muted() ? "muted" : "sound";
  }
  function toggle() { a.playing() ? a.pause() : a.play(); setTimeout(paint, 60); }
  function skip(by) { a.seek(Math.min(a.duration() || 0, Math.max(0, a.time() + by))); paint(); }
  function fail() { oops.hidden = false; stage.hidden = true; $(".controls").hidden = true; }
  function ready(adapter) {
    a = adapter;
    a.volume(vol.value / 100);
    a.play();
    paint();
  }

  function startFile() {
    var v = document.createElement("video");
    v.playsInline = true;
    v.addEventListener("error", fail);
    screen.appendChild(v);
    v.src = source;
    ready({
      play: function () { v.play(); }, pause: function () { v.pause(); },
      playing: function () { return !v.paused && !v.ended; },
      time: function () { return v.currentTime; }, duration: function () { return v.duration || 0; },
      seek: function (t) { v.currentTime = t; },
      volume: function (x) { v.volume = x; }, muted: function () { return v.muted; },
      mute: function (m) { v.muted = m; }
    });
  }

  function startYouTube() {
    // YouTube's own player does the streaming; ours draws every control.
    window.onYouTubeIframeAPIReady = function () {
      var holder = document.createElement("div");
      screen.appendChild(holder);
      var p = new YT.Player(holder, {
        host: "https://www.youtube-nocookie.com",
        videoId: source,
        playerVars: { controls: 0, disablekb: 1, fs: 0, rel: 0, modestbranding: 1, playsinline: 1, iv_load_policy: 3 },
        events: {
          onReady: function () {
            ready({
              play: function () { p.playVideo(); }, pause: function () { p.pauseVideo(); },
              playing: function () { return p.getPlayerState && p.getPlayerState() === 1; },
              time: function () { return p.getCurrentTime ? p.getCurrentTime() : 0; },
              duration: function () { return p.getDuration ? p.getDuration() : 0; },
              seek: function (t) { p.seekTo(t, true); },
              volume: function (x) { p.setVolume(Math.round(x * 100)); },
              muted: function () { return p.isMuted(); },
              mute: function (m) { m ? p.mute() : p.unMute(); }
            });
          },
          onError: function (e) { console.warn("youtube player error", e.data); fail(); }
        }
      });
    };
    var s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = fail;
    document.head.appendChild(s);
  }

  function start() {
    if (started) return;
    started = true;
    if (poster) poster.hidden = true;
    veil.textContent = "";
    if (kind === "file") startFile(); else startYouTube();
  }

  pp.onclick = toggle;
  stage.onclick = toggle;
  seek.oninput = function () {
    scrubbing = true;
    time.textContent = fmt(seek.value / 1000 * a.duration()) + " / " + fmt(a.duration());
  };
  seek.onchange = function () { a.seek(seek.value / 1000 * a.duration()); scrubbing = false; paint(); };
  vol.oninput = function () { a.volume(vol.value / 100); };
  mute.onclick = function () { a.mute(!a.muted()); paint(); };
  full.onclick = function () {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (root.requestFullscreen) root.requestFullscreen();
  };
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT" && e.target.type === "search") return;
    if (e.key === " " || e.key === "k") { e.preventDefault(); toggle(); }
    else if (e.key === "ArrowLeft") skip(-5);
    else if (e.key === "ArrowRight") skip(5);
    else if (e.key === "m") { a.mute(!a.muted()); paint(); }
    else if (e.key === "f") full.onclick();
  });
  setInterval(paint, 250);
  paint();
})();

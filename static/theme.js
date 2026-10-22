(function () {
  // Your own styles, if you wrote any (the pencil on the home page). They are kept in this browser only
  // and applied here, before the page is drawn, as an extra stylesheet after nook's own.
  try {
    var css = localStorage.getItem("nook.css");
    if (!css || !window.CSSStyleSheet || !document.adoptedStyleSheets) return;
    var sheet = new CSSStyleSheet();
    sheet.replaceSync(css.slice(0, 20000));
    document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sheet]);
  } catch (e) { /* bad css is ignored; the page still works */ }
})();

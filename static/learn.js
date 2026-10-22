(function () {
  // each button turns the word in the box into the search it names: "define x", "rhymes with x"...
  var form = document.querySelector(".learnform");
  if (!form) return;
  var input = form.querySelector("input[name=q]");
  form.querySelectorAll("button[data-prefix]").forEach(function (b) {
    b.addEventListener("click", function () {
      var word = input.value.trim();
      if (!word) { input.focus(); return; }
      input.value = b.dataset.prefix + word;
      form.submit();
    });
  });
})();

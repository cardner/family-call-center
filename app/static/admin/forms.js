// Client-side enhancements for the admin UI. These are convenience/defense-in-
// depth only; the server always validates and sanitizes input.
(function () {
  "use strict";

  // Trim leading/trailing whitespace from text inputs and textareas on submit
  // for any form marked with data-trim.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-trim")) {
      return;
    }
    var fields = form.querySelectorAll(
      'input[type="text"], input[type="search"], textarea'
    );
    fields.forEach(function (field) {
      field.value = field.value.trim();
    });
  });

  // Copy-to-clipboard for webhook URL blocks on the connection page.
  document.addEventListener("click", function (event) {
    var row = event.target.closest("[data-row-href]");
    if (row && !event.target.closest("a, button, form, input, textarea, select, label")) {
      window.location.href = row.getAttribute("data-row-href");
      return;
    }

    var button = event.target.closest("[data-copy-btn]");
    if (!button) {
      return;
    }
    var block = button.closest(".code-block");
    var code = block ? block.querySelector("[data-copy]") : null;
    if (!code) {
      return;
    }
    var text = code.getAttribute("data-copy") || code.textContent;
    var done = function () {
      var original = button.textContent;
      button.textContent = "Copied";
      setTimeout(function () {
        button.textContent = original;
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {});
    }
  });
})();

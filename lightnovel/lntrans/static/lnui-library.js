(function () {
  "use strict";

  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function isMobile() {
    return window.matchMedia && window.matchMedia("(max-width: 899px)").matches;
  }

  function apply(root) {
    var cards = qsa("[data-work-card]", root);
    var source = root.getAttribute("data-active-source") || "all";
    var view = root.getAttribute("data-active-view") || "all";
    var needle = (root.getAttribute("data-search-q") || "").trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (card) {
      var ok = source === "all" || card.getAttribute("data-source") === source;
      if (ok && view === "new") ok = card.getAttribute("data-unstarted") === "1";
      if (ok && needle) ok = (card.getAttribute("data-hay") || "").indexOf(needle) >= 0;
      card.hidden = !ok;
      if (ok) shown += 1;
    });
    var grid = root.querySelector("[data-work-grid]");
    var empty = root.querySelector("[data-filter-empty]");
    if (grid && empty) empty.hidden = shown !== 0;
  }

  function setButton(buttons, active, attr) {
    buttons.forEach(function (b) {
      b.classList.toggle("on", b.getAttribute(attr) === active);
    });
  }

  function setup(root) {
    if (root.getAttribute("data-ui-ready") === "1") return;
    root.setAttribute("data-ui-ready", "1");
    var isLibrary = root.getAttribute("data-page") === "library";
    if (isLibrary) {
      var savedView = isMobile() ? "new" : "all";
      root.setAttribute("data-active-view", savedView);
      setButton(qsa("[data-view]", root), savedView, "data-view");
    } else {
      root.setAttribute("data-active-view", "all");
    }
    root.setAttribute("data-active-source", "all");
    root.setAttribute("data-search-q", "");

    qsa("[data-source-filter]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var value = btn.getAttribute("data-source-filter") || "all";
        root.setAttribute("data-active-source", value);
        setButton(qsa("[data-source-filter]", root), value, "data-source-filter");
        apply(root);
      });
    });

    qsa("[data-view]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var value = btn.getAttribute("data-view") || "all";
        root.setAttribute("data-active-view", value);
        setButton(qsa("[data-view]", root), value, "data-view");
        apply(root);
      });
    });

    var input = root.querySelector("[data-search]");
    if (input) {
      input.addEventListener("input", function () {
        root.setAttribute("data-search-q", input.value || "");
        apply(root);
      });
    }

    qsa("[data-import-url]", root).forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.getAttribute("data-busy") === "1") return;
        btn.setAttribute("data-busy", "1");
        btn.disabled = true;
        var old = btn.textContent;
        btn.textContent = "正在导入…";
        fetch("/api/add", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          credentials: "same-origin",
          body: JSON.stringify({url: btn.getAttribute("data-import-url") || ""})
        }).then(function (r) { return r.json(); }).then(function (data) {
          if (!data || !data.ok || !data.slug) {
            throw new Error((data && data.error) || "导入失败");
          }
          if (btn.getAttribute("data-import-read") === "1" ||
              (data.existed && isMobile())) {
            location.href = "/read/" + encodeURIComponent(data.slug);
          } else {
            location.href = "/book/" + encodeURIComponent(data.slug);
          }
        }).catch(function (err) {
          btn.disabled = false;
          btn.removeAttribute("data-busy");
          btn.textContent = old;
          var note = root.querySelector("[data-import-error]");
          if (!note) {
            note = document.createElement("p");
            note.setAttribute("data-import-error", "1");
            note.className = "ui-help";
            root.appendChild(note);
          }
          note.textContent = err.message || "导入失败，请再试一次";
        });
      });
    });

    apply(root);
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    var card = t && t.closest ? t.closest("[data-work-card]") : null;
    if (!card || !card.getAttribute("data-href")) return;
    if (t.closest("a,button,input,select,textarea,summary,label")) return;
    location.href = card.getAttribute("data-href");
  });

  qsa("[data-ui-library]").forEach(setup);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) qsa("[data-ui-library]").forEach(apply);
  });
})();

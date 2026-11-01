(function () {
  "use strict";

  if (!document.body || document.body.getAttribute("data-ui-reader") !== "next") return;
  var body = document.body;
  var top = document.getElementById("ui-reader-top");
  var toast = document.getElementById("ui-chapter-toast");
  var lastY = window.scrollY || 0;
  var lastAt = 0;

  function setTop(hidden) {
    body.classList.toggle("ui-top-hidden", !!hidden);
  }

  function showToast() {
    if (!toast) return;
    toast.classList.add("on");
    setTimeout(function () { toast.classList.remove("on"); }, 2400);
  }

  function tocOpen() {
    return body.classList.contains("ui-toc-open");
  }

  function setToc(open) {
    var box = document.getElementById("tocbox");
    if (!box) return;
    if (open) {
      box.open = true;
      body.classList.add("ui-toc-open");
      setTop(false);
      var close = box.querySelector(".ui-toc-close");
      if (close) close.focus();
    } else {
      body.classList.remove("ui-toc-open");
    }
  }

  function ensureClose() {
    var box = document.getElementById("tocbox");
    if (!box || box.querySelector(".ui-toc-close")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ui-toc-close";
    btn.textContent = "×";
    btn.setAttribute("aria-label", "关闭目录");
    btn.addEventListener("click", function () { setToc(false); });
    box.appendChild(btn);
  }

  // Scroll direction: hide on a clear downward delta, reveal on upward.
  window.addEventListener("scroll", function () {
    if (tocOpen()) return;
    var y = window.scrollY || 0;
    var now = Date.now();
    if (now - lastAt < 70) { lastY = y; return; }
    var delta = y - lastY;
    if (y < 48) {
      setTop(false);
    } else if (delta > 7) {
      setTop(true);
    } else if (delta < -7) {
      setTop(false);
    }
    lastY = y;
    lastAt = now;
  }, {passive: true});

  // Tap left/right thirds to turn; centre toggles the chrome.
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0) return;
    var t = e.target;
    if (t && t.closest && t.closest(
        "a,button,input,select,textarea,summary,label,.gloss,.stale-note,#fbpanel,#readerbar,#translatebar,#tocbox,.tocbox")) {
      return;
    }
    try { if (String(window.getSelection && getSelection() || "").length) return; } catch (err) {}
    var tap = null;
    try { tap = localStorage.getItem("ln-tap"); } catch (e2) {}
    if (tap === "lr" || tap === "ud") return; // legacy handler owns this
    var x = e.clientX / Math.max(1, window.innerWidth || 1);
    if (x >= 0.42 && x <= 0.58) {
      setTop(!body.classList.contains("ui-top-hidden"));
      return;
    }
    var start = Number(window.__START__ || 1);
    var total = Number(window.__TOTAL__ || 0);
    var next = x > 0.58 ? start + 1 : start - 1;
    if (next < 1 || (total && next > total)) return;
    location.href = "/read/" + encodeURIComponent(window.__SLUG__) +
      "?from=" + next + "#c" + next;
  }, {passive: true});

  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[href="#tocbox"],#rb-toc') : null;
    if (!a) return;
    e.preventDefault();
    ensureClose();
    setToc(!tocOpen());
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && tocOpen()) setToc(false);
  });

  var tb = document.getElementById("translatebar");
  function showBar() {
    if (tb) tb.classList.add("is-on");
  }
  if (tb) {
    var job = String(window.__JOB__ || "");
    if (job === "running" || job === "queued" || job === "interrupted" ||
        job === "provider_error" || job === "error" || job === "partial") {
      showBar();
    }
  }
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (t && t.closest && t.closest("#btn-ceil,#btn-more,#btn-auto,#retry,a[href*=\"#need-\"]")) {
      showBar();
    }
  });

  ensureClose();
  showToast();

  // If the user changes the drawer state via the native details summary,
  // keep the body class in sync.
  var box = document.getElementById("tocbox");
  if (box) {
    box.addEventListener("toggle", function () {
      if (!box.open) body.classList.remove("ui-toc-open");
    });
  }
})();

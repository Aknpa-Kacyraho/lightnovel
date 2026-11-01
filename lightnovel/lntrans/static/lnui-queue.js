(function () {
  "use strict";

  var root = document.querySelector("[data-ui-queue]");
  if (!root) return;
  var timer = null;
  var failures = 0;
  var stopped = false;

  function schedule(ms) {
    if (stopped) return;
    clearTimeout(timer);
    timer = setTimeout(poll, ms);
  }

  function setLive(text, bad) {
    var node = root.querySelector("[data-q-live]");
    if (!node) return;
    node.textContent = text;
    node.classList.toggle("is-error", !!bad);
  }

  function countRows(data) {
    var rows = (data.rows || []).concat(data.paused_rows || []);
    var have = 0;
    var total = 0;
    rows.forEach(function (r) {
      have += Number(r.have || 0);
      total += Number(r.total || 0);
    });
    return {rows: rows.length, have: have, total: total,
      pct: total ? Math.round(have / total * 100) : 0};
  }

  function poll() {
    fetch("/api/queue", {credentials: "same-origin", cache: "no-store"})
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        failures = 0;
        var c = countRows(data);
        var status = data.paused ? "已全局暂停" :
          (data.over_budget ? "今日超出预算（仍在继续）" : "运行中");
        var st = root.querySelector("[data-q-status]");
        if (st) st.textContent = status;
        setLive("已刷新 " + new Date().toLocaleTimeString() +
          " · " + c.rows + " 本 · 已译 " + c.have + "/" + c.total +
          " 话（" + c.pct + "%）");
        schedule(7000);
      })
      .catch(function () {
        failures += 1;
        var wait = Math.min(30000, 7000 * Math.pow(2, failures - 1));
        setLive("暂时连不上服务，" + Math.round(wait / 1000) + " 秒后重试", true);
        schedule(wait);
      });
  }

  function post(action, slug, extra) {
    var body = Object.assign({action: action, slug: slug || ""}, extra || {});
    return fetch("/api/queue", {
      method: "POST",
      credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); });
  }

  root.querySelectorAll("[data-q-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      btn.disabled = true;
      post(btn.getAttribute("data-q-action"), btn.getAttribute("data-slug"))
        .then(function () { location.reload(); })
        .catch(function () { btn.disabled = false; });
    });
  });

  var pauseAll = root.querySelector("[data-q-pause-all]");
  if (pauseAll) {
    pauseAll.addEventListener("click", function () {
      var text = pauseAll.textContent || "";
      var paused = text.indexOf("继续") < 0;
      pauseAll.disabled = true;
      post("pause_all", "", {paused: paused})
        .then(function () { location.reload(); })
        .catch(function () { pauseAll.disabled = false; });
    });
  }

  function stop() {
    stopped = true;
    clearTimeout(timer);
  }

  function start() {
    stopped = false;
    poll();
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stop();
    else start();
  });
  window.addEventListener("pagehide", stop);
  start();
})();

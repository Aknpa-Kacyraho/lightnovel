(function () {
  "use strict";

  var root = document.querySelector("[data-ui-import]");
  var file = document.getElementById("imp-file");
  var title = document.getElementById("imp-title");
  var author = document.getElementById("imp-author");
  var go = document.getElementById("imp-go");
  var retry = document.getElementById("imp-retry");
  var status = document.getElementById("imp-status");
  var progress = document.getElementById("imp-progress");
  var fill = document.getElementById("imp-fill");
  var pct = document.getElementById("imp-pct");
  var step = document.getElementById("imp-step");
  var timer = null;
  var jobId = "";

  function say(text, bad) {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("is-error", !!bad);
  }

  function setProgress(value, label) {
    var n = Math.max(0, Math.min(100, Math.round((value || 0) * 100)));
    if (progress) progress.hidden = false;
    if (fill) fill.style.width = n + "%";
    if (pct) pct.textContent = n + "%";
    if (step) step.textContent = label || "";
  }

  function stopPoll() {
    clearTimeout(timer);
    timer = null;
  }

  function poll() {
    if (!jobId) return;
    fetch("/api/import_job?id=" + encodeURIComponent(jobId), {
      credentials: "same-origin", cache: "no-store"
    }).then(function (r) { return r.json(); }).then(function (job) {
      if (!job || !job.ok) throw new Error((job && job.error) || "任务不存在");
      setProgress(job.progress || 0, job.status === "running" ? "正在写章节" :
        job.status === "queued" ? "排队中" : "");
      if (job.status === "done") {
        stopPoll();
        try { localStorage.removeItem("ln-import-job"); } catch (e) {}
        say("已导入 " + (job.chapters || 0) + " 章 · 正在打开阅读页…");
        setProgress(1, "完成");
        if (retry) retry.hidden = true;
        setTimeout(function () {
          location.href = "/read/" + encodeURIComponent(job.slug || "");
        }, 1200);
      } else if (job.status === "error") {
        stopPoll();
        say("导入失败：" + (job.error || "未知错误") + "（原始文件已保留）", true);
        if (retry) retry.hidden = false;
      } else if (job.status === "interrupted") {
        stopPoll();
        say("导入中断，原始文件已保留；可以继续。", true);
        if (retry) retry.hidden = false;
      } else {
        timer = setTimeout(poll, 1000);
      }
    }).catch(function (err) {
      say("查询导入任务失败：" + (err.message || err), true);
      timer = setTimeout(poll, 3000);
    });
  }

  function start() {
    if (!file || !file.files || !file.files[0]) {
      say("先选择一个 .epub 或 .txt 文件", true);
      return;
    }
    var f = file.files[0];
    var q = "?name=" + encodeURIComponent(f.name);
    if (title && title.value.trim()) q += "&title=" + encodeURIComponent(title.value.trim());
    if (author && author.value.trim()) q += "&author=" + encodeURIComponent(author.value.trim());
    go.disabled = true;
    if (retry) retry.hidden = true;
    setProgress(0, "上传中");
    say("正在上传 " + f.name + "…");
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/import_async" + q, true);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) setProgress(0.05 + 0.25 * (e.loaded / e.total), "上传中");
    };
    xhr.onload = function () {
      go.disabled = false;
      var data = {};
      try { data = JSON.parse(xhr.responseText || "{}"); } catch (e) { data = {}; }
      if (!data.ok || !data.id) {
        say("导入失败：" + (data.error || ("HTTP " + xhr.status)), true);
        return;
      }
      jobId = data.id;
      try { localStorage.setItem("ln-import-job", jobId); } catch (e) {}
      say("已收到文件，后台导入中…");
      poll();
    };
    xhr.onerror = function () {
      go.disabled = false;
      say("上传失败，请检查网络后重试", true);
    };
    xhr.send(f);
  }

  function resume() {
    if (!jobId) return;
    fetch("/api/import_retry", {
      method: "POST", credentials: "same-origin",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: jobId})
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (!data || !data.ok) throw new Error((data && data.error) || "继续失败");
      say("继续导入中…");
      if (retry) retry.hidden = true;
      poll();
    }).catch(function (err) { say("继续失败：" + (err.message || err), true); });
  }

  if (go) go.onclick = start;
  if (retry) retry.onclick = resume;
  try { jobId = localStorage.getItem("ln-import-job") || ""; } catch (e) { jobId = ""; }
  if (jobId) {
    say("发现上次的导入任务，正在查询…");
    poll();
  }
})();

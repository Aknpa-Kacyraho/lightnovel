(function () {
  "use strict";

  function initRoot(root) {
    if (!root || root.getAttribute("data-tags-ready") === "1") return;
    root.setAttribute("data-tags-ready", "1");
    var node = root.querySelector("script[data-tags-json]") ||
      root.querySelector("script#ui-tags-data");
    var data = {};
    try { data = JSON.parse((node && node.textContent) || "{}"); } catch (e) { data = {}; }
    var all = Array.isArray(data.tags) ? data.tags : [];
    var recent = Array.isArray(data.recent) ? data.recent : [];
    var works = Array.isArray(data.works) ? data.works : [];
    var selected = [];
    var needle = "";
    var shown = 60;

    var selectedWrap = root.querySelector("[data-tag-selected-wrap]");
    var selectedBox = root.querySelector("[data-tag-selected]");
    var recentBox = root.querySelector("[data-tag-recent]");
    var allBox = root.querySelector("[data-tag-all]");
    var more = root.querySelector("[data-tag-more]");
    var clear = root.querySelector("[data-tag-clear]");
    var open = root.querySelector("[data-tag-open-result]");
    var empty = root.querySelector("[data-tag-empty]");
    var zeno = root.querySelector("[data-tag-zeno]");
    var search = root.querySelector("[data-tag-search]");

    function chip(tag) {
      var name = tag.name || tag;
      var n = tag.count || 0;
      var on = selected.indexOf(name) >= 0;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "ui-chip ui-tag-chip" + (on ? " on" : "");
      b.setAttribute("data-tag-name", name);
      b.appendChild(document.createTextNode(name));
      var span = document.createElement("span");
      span.className = "ui-chip-n";
      span.textContent = n;
      b.appendChild(span);
      b.addEventListener("click", function () { toggle(name); });
      return b;
    }

    function tagOf(name) {
      return all.filter(function (x) { return (x.name || x) === name; })[0] ||
        {name: name, count: 0};
    }

    function renderSelected() {
      selectedBox.innerHTML = "";
      selectedWrap.hidden = selected.length === 0;
      if (clear) clear.hidden = selected.length === 0;
      var n = root.querySelector("[data-tag-selected-n]");
      if (n) n.textContent = selected.length + " 个";
      selected.forEach(function (name) { selectedBox.appendChild(chip(tagOf(name))); });
      var hit = works.filter(function (tags) {
        return selected.every(function (t) { return tags.indexOf(t) >= 0; });
      }).length;
      if (open) {
        open.hidden = selected.length === 0;
        if (selected.length) {
          open.href = "/library?tags=" + encodeURIComponent(selected.join(","));
          open.textContent = "在书库中查看命中 " + hit + " 本";
        }
      }
      if (zeno) zeno.hidden = !(selected.length > 0 && hit === 0);
    }

    function renderRecent() {
      if (!recentBox) return;
      recentBox.innerHTML = "";
      recent.forEach(function (name) { recentBox.appendChild(chip(tagOf(name))); });
      if (recentBox.parentElement) recentBox.parentElement.hidden = recent.length === 0;
    }

    function renderAll() {
      if (!allBox) return;
      allBox.innerHTML = "";
      var rows = all.filter(function (t) {
        var name = String(t.name || t);
        return !needle || name.toLowerCase().indexOf(needle) >= 0;
      });
      rows.slice(0, shown).forEach(function (t) { allBox.appendChild(chip(t)); });
      if (more) more.hidden = rows.length <= shown;
      if (empty) empty.hidden = rows.length !== 0;
      var total = root.querySelector("[data-tag-total]");
      if (total) total.textContent = rows.length + " 个";
    }

    function toggle(name) {
      var i = selected.indexOf(name);
      if (i >= 0) selected.splice(i, 1);
      else selected.push(name);
      renderSelected();
      renderAll();
      renderRecent();
    }

    if (search) {
      search.addEventListener("input", function () {
        needle = (search.value || "").trim().toLowerCase();
        shown = 60;
        renderAll();
      });
    }
    if (more) {
      more.addEventListener("click", function () { shown += 60; renderAll(); });
    }
    if (clear) {
      clear.addEventListener("click", function () {
        selected = [];
        renderSelected();
        renderAll();
        renderRecent();
      });
    }

    renderSelected();
    renderRecent();
    renderAll();
  }

  function openDrawer() {
    var drawer = document.getElementById("ui-tag-drawer");
    if (!drawer) return;
    drawer.hidden = false;
    document.body.classList.add("ui-drawer-open");
  }

  function closeDrawer() {
    var drawer = document.getElementById("ui-tag-drawer");
    if (!drawer) return;
    drawer.hidden = true;
    document.body.classList.remove("ui-drawer-open");
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest("[data-tag-open]")) {
      e.preventDefault();
      openDrawer();
    } else if (t.closest("[data-tag-close]")) {
      e.preventDefault();
      closeDrawer();
    } else if (document.body.classList.contains("ui-drawer-open") &&
               !t.closest("#ui-tag-drawer")) {
      closeDrawer();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeDrawer();
  });

  Array.prototype.slice.call(document.querySelectorAll("[data-ui-tags]"))
    .forEach(initRoot);
})();

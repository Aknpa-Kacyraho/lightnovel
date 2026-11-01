(function () {
  var r = document.documentElement;

  function saved(k) {
    try { return localStorage.getItem(k); } catch (e) { return null; }
  }
  function setItem(k, v) {
    try { localStorage.setItem(k, v); } catch (e) {}
  }
  function themeOf() {
    var s = saved('ln-theme');
    return (s === 'dark' || s === 'light') ? s : 'system';
  }
  function applyTheme(mode) {
    var d = mode === 'system'
      ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : mode;
    r.setAttribute('data-theme', d);
    r.setAttribute('data-t', d);
    r.style.colorScheme = d;
    try {
      if (mode === 'system') localStorage.removeItem('ln-theme');
      else localStorage.setItem('ln-theme', mode);
    } catch (e) {}
    document.querySelectorAll('[data-set-theme]').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute('data-set-theme') === mode);
    });
  }
  document.querySelectorAll('[data-set-theme]').forEach(function (b) {
    b.onclick = function () { applyTheme(b.getAttribute('data-set-theme')); };
  });
  applyTheme(themeOf());
  try {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (themeOf() === 'system') applyTheme('system');
    });
  } catch (e) {}

  function mark(attr, val) {
    document.querySelectorAll('[' + attr + ']').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute(attr) === val);
    });
  }
  function applyFs(v) {
    if (v === 'm') r.removeAttribute('data-fs');
    else r.setAttribute('data-fs', v);
    setItem('ln-fs', v);
    mark('data-fs-set', v);
  }
  function applyLh(v) {
    if (v === 'normal') r.removeAttribute('data-lh');
    else r.setAttribute('data-lh', v);
    setItem('ln-lh', v);
    mark('data-lh-set', v);
  }
  document.querySelectorAll('[data-fs-set]').forEach(function (b) {
    b.onclick = function () { applyFs(b.getAttribute('data-fs-set')); };
  });
  document.querySelectorAll('[data-lh-set]').forEach(function (b) {
    b.onclick = function () { applyLh(b.getAttribute('data-lh-set')); };
  });
  var fsNow = saved('ln-fs');
  if (fsNow !== 's' && fsNow !== 'l') fsNow = 'm';
  var lhNow = saved('ln-lh');
  if (lhNow !== 'tight' && lhNow !== 'loose') lhNow = 'normal';
  applyFs(fsNow);
  applyLh(lhNow);

  function applyChoice(attr, key, fallback) {
    var v = saved(key);
    if (v !== fallback && !document.querySelector('[' + attr + '="' + v + '"]')) {
      v = fallback;
    }
    document.querySelectorAll('[' + attr + ']').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute(attr) === v);
    });
    return v;
  }
  function bindChoice(attr, key) {
    document.querySelectorAll('[' + attr + ']').forEach(function (b) {
      b.onclick = function () {
        setItem(key, b.getAttribute(attr));
        document.querySelectorAll('[' + attr + ']').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
      };
    });
  }
  bindChoice('data-jp', 'ln-jp');
  bindChoice('data-tap', 'ln-tap');
  bindChoice('data-speak', 'ln-speak');
  applyChoice('data-jp', 'ln-jp', 'hide');
  applyChoice('data-tap', 'ln-tap', 'off');
  applyChoice('data-speak', 'ln-speak', 'zh');

  var lu = document.getElementById('lanurl');
  var lp = document.getElementById('lanpeers');
  if (lu) fetch('/api/net').then(function (resp) { return resp.json(); }).then(function (d) {
    var u = (d.ap_urls && d.ap_urls[0]) || (d.urls && d.urls[0]);
    lu.textContent = u || '暂时无法获取（请开启热点后刷新本页）';
    if (lp) {
      var ps = d.peers || [];
      lp.textContent = ps.length
        ? ('已连接过的设备：' + ps.map(function (p) { return p.ip; }).join('、'))
        : '暂无其他设备连接记录。';
    }
  }).catch(function () {});
})();

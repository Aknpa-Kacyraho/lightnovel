// 阅读页校对面板。只负责触发和展示；报告/经验均由服务端按书隔离。
(function () {
  const slug = window.__SLUG__;
  const ch = window.__START__ || 1;
  const box = document.getElementById('reviewbox');
  const list = document.getElementById('review-list');
  const status = document.getElementById('review-status');
  if (!box || !list || !status) return;
  const btnOpen = document.getElementById('review-open');
  const btnRules = document.getElementById('review-rules');
  const btnAI = document.getElementById('review-ai');
  const btnClose = document.getElementById('review-close');
  let polling = false;

  const SEV = {blocker: '阻断', suggestion: '建议', observation: '观察'};
  const TYPE = {
    para_count: '段落数', omission: '漏译', japanese: '日文残留',
    term_missing: '术语缺失', term_old: '旧译名', term: '术语',
    number: '数字', emotion: '情绪反义', rhythm: '段落节奏',
    style: '翻译腔', voice: '角色语气', reference: '指代',
    mistranslation: '疑似错译', llm_format: 'AI 输出格式', other: '其它'
  };

  function text(tag, cls, value) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value != null) el.textContent = value;
    return el;
  }

  function show(open) {
    box.style.display = open ? '' : 'none';
    if (open) box.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  function setStatus(msg, kind) {
    status.textContent = msg || '';
    status.dataset.kind = kind || '';
  }

  function render(report) {
    list.textContent = '';
    if (!report) return;
    const c = report.counts || {};
    const head = text('div', 'review-summary',
      `规则${report.mode === 'rules+ai' ? ' + AI' : ''}校对 · ` +
      `阻断 ${c.blocker || 0} · 建议 ${c.suggestion || 0} · 观察 ${c.observation || 0}` +
      (report.tokens ? ` · ${report.tokens} tok` : ''));
    list.appendChild(head);
    if (report.escalate) {
      list.appendChild(text('div', 'review-escalate',
        '观察池已达到阈值，建议人工复核。'));
    }
    const issues = report.issues || [];
    if (!issues.length) {
      list.appendChild(text('div', 'review-empty', '未发现明显问题。'));
      return;
    }
    issues.forEach(function (it) {
      const card = text('div', 'review-item review-' + (it.severity || 'observation'));
      const title = text('div', 'review-head',
        `${it.para ? '第' + it.para + '段' : '全章'} · ` +
        `${TYPE[it.type] || it.type || '问题'} · ` +
        `${SEV[it.severity] || it.severity || '观察'}`);
      card.appendChild(title);
      if (it.quote_jp) card.appendChild(text('div', 'review-q', '原文：' + it.quote_jp));
      if (it.quote_zh) card.appendChild(text('div', 'review-q', '译文：' + it.quote_zh));
      if (it.evidence) card.appendChild(text('div', 'review-ev', '依据：' + it.evidence));
      if (it.suggestion) card.appendChild(text('div', 'review-sug', '建议：' + it.suggestion));
      list.appendChild(card);
    });
  }

  async function loadSaved() {
    try {
      const r = await fetch('/api/reviewreport?slug=' + encodeURIComponent(slug) +
        '&chapter=' + ch);
      const d = await r.json();
      if (d && d.ok && d.report) {
        render(d.report);
        setStatus('这是上次保存的校对报告。', 'ok');
      } else {
        setStatus('还没有这一章的校对报告；先点「规则检查」即可，不花 token。', '');
      }
    } catch (e) { /* 没有历史报告是正常的 */ }
  }

  async function run(useAI) {
    if (useAI && !window.confirm('AI 校对会调用模型并消耗 token，只报告问题、不改译文。继续？')) return;
    if (polling) return;
    polling = true;
    show(true);
    render(null);
    setStatus(useAI ? '正在排队（AI 校对可能需要几十秒）…' : '正在做规则检查…', 'busy');
    try {
      const r = await fetch('/api/review', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          slug: slug, chapter: ch, llm: useAI,
          fix: false, learn: true
        })
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || '启动校对失败');
      poll();
    } catch (e) {
      polling = false;
      setStatus('校对失败：' + (e.message || e), 'error');
    }
  }

  async function poll() {
    try {
      const r = await fetch('/api/reviewstate?slug=' + encodeURIComponent(slug) +
        '&chapter=' + ch);
      const j = await r.json();
      if (j.status === 'queued' || j.status === 'running') {
        setStatus(j.message || '校对中…', 'busy');
        setTimeout(poll, 1500);
        return;
      }
      if (j.status === 'error') {
        polling = false;
        setStatus('校对失败：' + (j.error || '未知错误'), 'error');
        return;
      }
      if (j.status === 'done' && j.report) {
        polling = false;
        render(j.report);
        setStatus('校对完成。报告已保存；本次发现会进入本书经验。', 'ok');
        return;
      }
      polling = false;
      setStatus('校对任务已结束，但没有报告。', 'error');
    } catch (e) {
      setTimeout(poll, 2000);
    }
  }

  if (btnOpen) btnOpen.onclick = function () { show(true); loadSaved(); };
  if (btnRules) btnRules.onclick = function () { run(false); };
  if (btnAI) btnAI.onclick = function () { run(true); };
  if (btnClose) btnClose.onclick = function () { show(false); };
  loadSaved();
})();

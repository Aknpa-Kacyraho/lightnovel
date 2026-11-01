/*
 * 前端"真点一遍"的仿真器（Node，零依赖，不需要浏览器）。
 *
 * 为什么需要它：用户报过 4 次「按钮点了没反应」，而服务端 API 全绿、
 * Python 自检也全绿 —— 因为那些 bug 全在**浏览器里**：
 *   1) 详情页 ★收藏 的 class 写死 on → 前端永远发 value:false（收藏开不了）
 *   2) 「更新了 +N 话 · 点我翻译」不在 .ctrls 里 → 从来没人给它绑 handler
 *   3) 一条 getElementById(...).onclick 抛异常 → 后面的绑定全废
 *   4) 打开阅读页把"已移出书架"的书又标回在读
 * 只编译 JS 是查不出这些的（语法合法、行为错），所以这里：
 *   · 用最小 DOM 桩把页面里的 <script> **真的执行**一遍；
 *   · 拿到事件委托的 click 处理器，按 HTML 里每个按钮**真的点一次**；
 *   · 断言"点下去到底发了什么请求"和"按钮 on 状态是否等于服务端状态"。
 *
 * 用法：node test_click_dom.js <payload.json>   → stdout 输出 JSON 结果
 */
'use strict';
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

// ----------------------------------------------------------------- 最小 DOM
function matchesSimple(el, part) {
  if (!el) return false;
  // :not(...) —— 真浏览器支持，桩也必须支持
  // （阅读页用了 section.ch:not(.pending)；不支持的话元素数会被算成 0）
  const negs = [];
  part = String(part).replace(/:not\(([^()]*)\)/g, (mm, inner) => {
    negs.push(inner);
    return '';
  });
  for (const n of negs) { if (matchesSimple(el, n.trim())) return false; }
  const m = part.match(/^([a-zA-Z]*)((?:\.[\w-]+)*)((?:\[[^\]]+\])*)$/);
  if (!m) return false;
  const [, tag, cls, attrs] = m;
  if (tag && el.tagName !== tag.toUpperCase()) return false;
  for (const c of (cls.match(/\.[\w-]+/g) || [])) {
    if (!el.classList.contains(c.slice(1))) return false;
  }
  for (const a of (attrs.match(/\[[^\]]+\]/g) || [])) {
    const body = a.slice(1, -1);
    const eq = body.indexOf('=');
    if (eq < 0) { if (!(body in el._attrs)) return false; continue; }
    const k = body.slice(0, eq);
    const v = body.slice(eq + 1).replace(/^["']|["']$/g, '');
    if (String(el._attrs[k]) !== v) return false;
  }
  return true;
}
function matches(el, sel) {
  for (const group of sel.split(',')) {
    const parts = group.trim().split(/\s+/);
    if (!matchesSimple(el, parts[parts.length - 1])) continue;
    // 前面的部分必须是祖先（允许中间隔层级）
    let need = parts.length - 2, node = el._parent;
    while (need >= 0 && node) {
      if (matchesSimple(node, parts[need])) need--;
      node = node._parent;
    }
    if (need < 0) return true;
  }
  return false;
}
class ClassList {
  constructor(cls) { this._s = new Set(String(cls || '').split(/\s+/).filter(Boolean)); }
  contains(c) { return this._s.has(c); }
  add(...c) { c.forEach(x => this._s.add(x)); }
  remove(...c) { c.forEach(x => this._s.delete(x)); }
  toggle(c, on) { const v = (on === undefined) ? !this._s.has(c) : !!on; v ? this._s.add(c) : this._s.delete(c); return v; }
  get value() { return [...this._s].join(' '); }
}
class El {
  constructor(tag, attrs, cls, text) {
    this.tagName = String(tag || 'div').toUpperCase();
    this._attrs = Object.assign({}, attrs || {});
    this.dataset = {};
    for (const k of Object.keys(this._attrs)) {
      if (k.indexOf('data-') === 0) {
        this.dataset[k.slice(5).replace(/-([a-z])/g, (m, c) => c.toUpperCase())] = this._attrs[k];
      }
    }
    this.classList = new ClassList(cls);
    this.style = {};
    this.textContent = text || '';
    this.innerHTML = text || '';
    this.value = '';
    this.disabled = false;
    this._parent = null;
    this._children = [];
    this._desc = [];
  }
  get className() { return this.classList.value; }
  set className(v) { this.classList = new ClassList(v); }
  get id() { return this._attrs.id || ''; }
  get tag() { return this.tagName; }
  closest(sel) { let n = this; while (n) { if (matches(n, sel)) return n; n = n._parent; } return null; }
  querySelector(sel) { return this._desc.find(d => matches(d, sel)) || null; }
  querySelectorAll(sel) { return this._desc.filter(d => matches(d, sel)); }
  appendChild(c) { this._children.push(c); c._parent = this; return c; }
  removeChild(c) { const i = this._children.indexOf(c); if (i >= 0) this._children.splice(i, 1); c._parent = null; }
  remove() { if (this._parent) this._parent.removeChild(this); }
  replaceWith(other) {
    const par = this._parent;
    if (!par) return;
    const i = par._children.indexOf(this);
    if (i >= 0) {
      par._children.splice(i, 1, other);
      other._parent = par;
      par._desc.push(other);
      for (const d of (other._desc || [])) par._desc.push(d);
    }
    this._parent = null;
  }
  insertBefore(node, ref) {
    const i = this._children.indexOf(ref);
    if (i < 0) this._children.push(node); else this._children.splice(i, 0, node);
    node._parent = this;
    this._desc.push(node);
    for (const d of (node._desc || [])) this._desc.push(d);
    return node;
  }
  setAttribute(k, v) { this._attrs[k] = v; }
  getAttribute(k) { return (k in this._attrs) ? this._attrs[k] : null; }
  addEventListener() { }
  removeEventListener() { }
  focus() { }
  blur() { }
  contains() { return false; }
  // 记录滚到了哪一章（data-ch）：序列断言能区分「真的逐章前进」与「原地打转」
  scrollIntoView() { REC.scrollCalls++; if (this._attrs && ('data-ch' in this._attrs)) REC.scrollTargets.push(this._attrs['data-ch']); }
  getBoundingClientRect() { return { top: 0, left: 0, width: 0, height: 0 }; }
  get firstChild() { return this._children[0] || null; }
}

// ----------------------------------------------------------------- 桩环境
// 每个页面一个**全新的上下文**：真实浏览器里换页就是换一份全局变量，
// 共用 context 会让第二张阅读页的 `const slug` 撞上第一张（Identifier already declared），
// 也会让上一页注册的 click 处理器继续响应这一页的点击（假通过）。
const REC = { requests: [], reloads: 0, hrefs: [], loadErrors: [], clickHandlers: [], keyHandlers: [], touchHandlers: [], scrollCalls: 0, scrollTargets: [], timers: 0, pending: [], _tid: 0, timerErrors: [] };
const FAKE = payload.fake || {};
function makeFetch(rec) {
  return function (url, opts) {
    const method = ((opts && opts.method) || 'GET').toUpperCase();
    let bodyObj = null;
    if (opts && opts.body) { try { bodyObj = JSON.parse(opts.body); } catch (e) { bodyObj = opts.body; } }
    rec.requests.push({ url: String(url), method: method, body: bodyObj });
    const key = String(url).split('?')[0];
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve(FAKE[String(url)] || FAKE[key] || { ok: true }),
      text: () => Promise.resolve(''),
    });
  };
}
const vm = require('vm');
function newPage(ids, chapters) {
  const body = new El('body');
  // 页面里真实的 section.ch[data-ch]（连续阅读的"章"）。桩不解析 HTML，
  // 由 payload 显式给出；reader.js 靠 querySelectorAll 找它们做翻章。
  for (const ch of (chapters || [])) {
    const s = new El('section', { 'data-ch': String(ch) }, 'ch');
    body._desc.push(s); s._parent = body;
  }
  const known = new Set(ids || []);
  const doc = {
    documentElement: new El('html'),
    body: body,
    _byId: {},
    // **真实语义**：getElementById 对 HTML 里不存在的 id 返回 null。
    // 踩过（高手审出来的）：桩原来对任何 id 都返回一个稳定对象，于是
    // `document.getElementById('btn-fav').onclick=...`（元素早就不存在）
    // 在真实浏览器里是 "Cannot set properties of null" → **整段脚本后续绑定全废**
    // （日文折叠开关、主题按钮集体失灵），而桩里一路绿灯。
    // 现在只有 HTML 里真的有的 id 才返回元素，其余返回 null（和浏览器一致）。
    getElementById(id) {
      if (!known.has(id)) return null;
      if (!this._byId[id]) this._byId[id] = new El('div', { id: id });
      return this._byId[id];
    },
    querySelector() { return null; },
    querySelectorAll(sel) { return body._desc.filter(d => matches(d, sel)); },
    createElement(tag) { return new El(tag); },
    createTextNode(t) { return { textContent: t }; },
    addEventListener(type, fn) {
      if (type === 'click') REC.clickHandlers.push(fn);
      else if (type === 'keydown') REC.keyHandlers.push(fn);
      else if (type === 'touchstart' || type === 'touchend') REC.touchHandlers.push(fn);
    },
    removeEventListener() { },
  };
  const sandbox = {
    document: doc, window: null, console: console,
    // location.href 的**赋值**要真记下来：阅读页章末翻章越过本页边界时
    // 走的是 location.href='/read/...?from=N'（不是 reload）。桩若不记录，
    // "单章页 ←/→ 到底翻没翻"这类就只能靠肉眼看代码了。
    location: (function () {
      const loc = {
        hash: '', pathname: '/', search: '', _href: 'http://127.0.0.1/',
        reload() { REC.reloads++; }, replace(u) { REC.reloads++; if (u) loc._href = String(u); },
        assign(u) { REC.hrefs.push(String(u)); },
      };
      Object.defineProperty(loc, 'href', {
        get() { return loc._href; },
        set(v) { loc._href = String(v); REC.hrefs.push(String(v)); },
      });
      return loc;
    })(),
    history: { replaceState() { }, pushState() { }, scrollRestoration: 'auto' },
    // 翻页/换页后回到列表顶部靠 sessionStorage 传目标 id（action.js 写、lib.js 读）
    sessionStorage: (function () {
      const s = {};
      return { getItem: k => (k in s ? s[k] : null), setItem: (k, v) => { s[k] = String(v); }, removeItem: k => { delete s[k]; } };
    })(),
    matchMedia: () => ({ matches: false, addEventListener() { } }),
    // 朗读按钮用 Web Speech；桩要声明这个能力，否则 IIFE 提前 return，
    // #btn-speak 会被判成「死按钮」（真实浏览器有 speechSynthesis）。
    speechSynthesis: {
      speak() { }, cancel() { }, pause() { }, resume() { },
      getVoices() { return []; },
    },
    SpeechSynthesisUtterance: class {
      constructor(text) { this.text = text; }
    },
    // 主题色脚本用 MutationObserver 跟 data-t；桩要像浏览器一样能构造，
    // 否则 `new MutationObserver` 抛错会废掉后面整段内联脚本（假红）。
    MutationObserver: class {
      constructor(cb) { this.cb = cb; }
      observe() { }
      disconnect() { }
      takeRecords() { return []; }
    },
    addEventListener() { }, removeEventListener() { },
  // 可控时钟：默认**只记账不执行**（避免轮询把测试挂住，也保持既有页面行为不变）；
  // 页面带 flush>0 时由 flushTimers() 手动推进若干轮。这是唯一能覆盖"异步轮询链"
  // （tick↔poll 靠 setTimeout 自我调度）的手段 —— 空实现定时器会让整条链静默不跑，
  // reader.js「读到哪翻到哪」的死锁（tick 设锁→poll 被自己挡回）正是藏在这里，
  // 由 test_click.py 的 B3b 段在 flush 后断言 /api/job 确实被调用过来兜住。
  setTimeout(fn, ms) { REC.timers++; const id = ++REC._tid; REC.pending.push({ id, fn, ms: ms || 0 }); return id; },
  clearTimeout(id) { const i = REC.pending.findIndex(t => t.id === id); if (i >= 0) REC.pending.splice(i, 1); },
  setInterval() { REC.timers++; return 0; }, clearInterval() { },
  fetch: makeFetch(REC),
  alert() { }, confirm: () => true, prompt: () => null,
  encodeURIComponent: encodeURIComponent, decodeURIComponent: decodeURIComponent,
  JSON: JSON, Math: Math, Date: Date, Object: Object, Array: Array, String: String,
  Number: Number, Boolean: Boolean, RegExp: RegExp, Error: Error, Promise: Promise,
  parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN, Set: Set, Map: Map,
  requestAnimationFrame(fn) { return 0; },
  // 阅读页用 IntersectionObserver 做"读到哪"的进度上报；桩掉即可
  IntersectionObserver: class { constructor() { } observe() { } unobserve() { } disconnect() { } },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;
  return { doc: doc, ctx: vm.createContext(sandbox) };
}

// ----------------------------------------------------------------- 跑页面
const sleep = () => new Promise(r => setImmediate(r));
// 可控时钟推进：执行 N 轮"当前挂起的定时器回调"，每轮后把 microtask（fetch 的 .then）
// 跑完，从而让自我调度的异步链（tick→poll→tick）真正往前走。
// 有界（每轮先清空快照再执行），不会挂死。
async function flushTimers(rounds) {
  for (let r = 0; r < rounds; r++) {
    const due = REC.pending.slice();
    REC.pending.length = 0;
    for (const t of due) {
      try { t.fn(); } catch (e) { REC.timerErrors.push(String((e && e.message) || e)); }
    }
    for (let i = 0; i < 8; i++) await sleep();
  }
}
(async () => {
  const out = { pages: [], summary: {} };
  for (const page of payload.pages) {
    const p = { name: page.name, loadError: null, clicks: [] };
    const reqBase = REC.requests.length;
    // 换页 = 新的全局环境 + 新的监听器（上一页的处理器不该响应这一页的点击）
    REC.clickHandlers.length = 0;
    REC.keyHandlers.length = 0;
    REC.touchHandlers.length = 0;
    REC.pending.length = 0;              // 上一页未执行的定时器不该推进到这一页
    REC.scrollTargets.length = 0;        // 本页的翻章目标序列，从零开始记
    REC.hrefs.length = 0;                // 本页 location.href 跳转序列，从零开始记
    const pg = newPage(page.ids, page.chapters);
    const doc = pg.doc, ctx = pg.ctx;
    // 1) 先把页面里所有内联脚本**真的执行**一遍（这一步就能抓住"某处抛异常
    //    导致后面所有绑定失效"这类 bug）
    try {
      for (const src of page.scripts) {
        vm.runInContext(src, ctx, { filename: page.name + '.js', timeout: 5000 });
      }
    } catch (e) {
      p.loadError = String(e && e.message || e);
      REC.loadErrors.push(page.name + ': ' + p.loadError);
    }
    p.clickHandlers = REC.clickHandlers.length;
    p.keyHandlers = REC.keyHandlers.length;
    p.chapters = (page.chapters || []).slice();   // 本页真实渲染出来的章号（供断言"几章一页"）
    // 脚本执行期间**自己**发出去的请求（不是点出来的）。
    // 阅读页就是靠这个证明"落地章没译文 → 一进页面就自己去翻"，
    // 而不是等用户滚到底 —— 用户报过"译好了还得我手动刷新"。
    for (let i = 0; i < 6; i++) await sleep();
    // 页面要求推进异步轮询链时，手动 flush 定时器（默认不 flush = 行为与旧桩完全一致）
    if (page.flush) await flushTimers(page.flush);
    p.loadRequests = REC.requests.slice(reqBase);
    // 页面上「状态条」实际被脚本写成了什么（阅读页的状态/进度断言要用）
    p.statusText = (doc._byId['tb-status'] || {}).innerHTML || '';
    p.segText = (doc._byId['tb-seg'] || {}).textContent || '';
    p.progText = (doc._byId['tb-prog'] || {}).textContent || '';
    p.idHandlers = {};
    for (const id of Object.keys(doc._byId)) {
      const el = doc._byId[id];
      p.idHandlers[id] = !!(el.onclick || el.oninput || el.onchange || el.onkeydown);
    }
    // 2) 按 HTML 里的按钮逐个"点一次"
    for (const spec of page.buttons) {
      const before = REC.requests.length;
      const reloadsBefore = REC.reloads;
      // 组装 DOM：button（含祖先 .ctrls / .card）
      const btn = new El('button', spec.attrs, spec.cls, spec.text);
      let host = btn;
      if (spec.card) {
        const card = new El('div', Object.assign({ 'data-slug': spec.card.slug, 'data-wid': spec.card.wid }, {}), 'card');
        card._desc.push(btn); btn._parent = card;
        const ctrls = new El('div', {}, 'ctrls');
        ctrls._desc.push(btn); ctrls._parent = card; card._desc.push(ctrls);
        btn._parent = ctrls;
        card._desc.push(new El('div', {}, 't', 'title'));
        host = card;
      }
      try {
        const ev = { target: btn, currentTarget: btn, preventDefault() { }, stopPropagation() { } };
        for (const h of REC.clickHandlers) h(ev);
        for (let i = 0; i < 12; i++) await sleep();
      } catch (e) {
        p.clicks.push({ label: spec.label, error: String(e && e.message || e) });
        continue;
      }
      p.clicks.push({
        label: spec.label, attrs: spec.attrs, cls: spec.cls, card: spec.card,
        requests: REC.requests.slice(before),
        reloaded: REC.reloads > reloadsBefore,
        btnClassAfter: btn.classList.value,
        btnTextAfter: btn.textContent,
      });
    }
    // 3) 连续阅读：派发 keydown，验证翻章 handler 健壮、且不抢输入框
    if (page.keys || page.keysInInput) {
      p.keys = [];
      for (const spec of (page.keys || [])) {
        const scrBefore = REC.scrollCalls, reqBefore = REC.requests.length;
        let err = null;
        try {
          const ev = { key: spec, target: doc.body, preventDefault() { }, stopPropagation() { } };
          for (const h of REC.keyHandlers) h(ev);
          for (let i = 0; i < 4; i++) await sleep();
        } catch (e) { err = String((e && e.message) || e); }
        p.keys.push({ key: spec, inInput: false, error: err,
                      scroll: REC.scrollCalls - scrBefore, reqs: REC.requests.length - reqBefore });
      }
      // 在输入框里按键：必须**不**翻章（反馈浮层的 textarea 要能正常打字）
      const ta = new El('textarea', { id: 'fb-note' });
      const scrBefore = REC.scrollCalls, reqBefore = REC.requests.length;
      let err = null;
      try {
        for (const spec of (page.keysInInput || [])) {
          const ev = { key: spec, target: ta, preventDefault() { }, stopPropagation() { } };
          for (const h of REC.keyHandlers) h(ev);
        }
        for (let i = 0; i < 4; i++) await sleep();
      } catch (e) { err = String((e && e.message) || e); }
      p.keyInInput = { error: err, scroll: REC.scrollCalls - scrBefore,
                       reqs: REC.requests.length - reqBefore };
    }
    p.scrollTargets = REC.scrollTargets.slice();   // 本页翻章滚过的章节序列（按 data-ch）
    p.hrefs = REC.hrefs.slice();                   // 本页 location.href 跳转过（跨页翻章）的 URL
    out.pages.push(p);
  }
  out.summary = {
    loadErrors: REC.loadErrors,
    totalRequests: REC.requests.length,
    timers: REC.timers,
    timerErrors: REC.timerErrors,
  };
  process.stdout.write(JSON.stringify(out));
})().catch(e => {
  process.stdout.write(JSON.stringify({ fatal: String(e && e.stack || e) }));
});

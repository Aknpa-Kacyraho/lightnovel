
const slug=window.__SLUG__, total=window.__TOTAL__;
let done=window.__DONE__, job=window.__JOB__, polling=false;
// renderedChapters：页面实际渲染了几章；nextFrom：下一页该从第几章取。
// 分开计数是因为"翻译进度"和"页面渲染进度"在有空洞时会不一致。
let renderedChapters=document.querySelectorAll('section.ch:not(.pending)').length;
let nextFrom=(window.__START__||1)+renderedChapters;
// need：落地那一章还没译文时=那一章（服务端只渲染了占位块）。
// 只要 need 还在，前端就一直在等它 —— 译好当场替换，不让读者看到空洞。
let need=window.__NEED__||0;
// 一页默认只渲染**一章**（用户嫌 3 章一页太长）。所以本页不再往后追加章节，
// 而是把章末的「下一章」在译好后点亮成真链接：读完这一章，点一下翻到下一章。
// nextCh = 下一章章号（0=没有下一章）；nextHave = 它是否已经有译文。
let nextCh=window.__NEXT__||0;
let nextHave=window.__NEXTHAVE__||false;      // 章末「下一章」是否可点（没译文也能点=催翻译）
let nextTrans=window.__NEXTTRANS__||false;    // 下一章**现在就有译文**（预翻看这个）
const jobInfo=window.__JOB_INFO__||{};
let recoveryPending=job==='interrupted'||!!jobInfo.read_only;
let currentHasGap=false;
const bar=document.getElementById('bar');
function prog(){const h=document.documentElement;
  if(!bar) return;
  bar.style.width=(h.scrollTop/(h.scrollHeight-h.clientHeight||1)*100).toFixed(1)+'%';}
addEventListener('scroll',prog,{passive:true});prog();

// —— 进度上报：服务端由此知道"你读到哪了" ——
// 初值用落地章（__START__），不要写死 1：从第 N 章打开、在 IntersectionObserver
// 首次回调落地前就离开页面时，sendBeacon 会把 curCh=1 上报 → 进度被误写成"读到第 1 章"。
let lastSent=0, curCh=window.__START__||1;
// 手动翻章用独立的 navCh：IntersectionObserver 在短章节下可能把"下一章"
// 判成当前章（它的观察带在屏幕中部），快速连按两次就会被这个旧值卡住。
let navCh=window.__START__||1;
function report(ch){
  curCh=ch; const now=Date.now();
  if(now-lastSent<3000 && ch===report._c) return;
  report._c=ch; lastSent=now;
  fetch('/api/progress',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slug:slug,chapter:ch,scroll:chapterScroll(ch)})}).catch(()=>{});
}
// 当前章节内已滚动的比例（用于下次回到原处，而不是章首）
function chapterScroll(ch){
  const el=document.querySelector('section.ch[data-ch="'+ch+'"]');
  if(!el) return null;
  const top=el.offsetTop, h=el.offsetHeight||1;
  const p=(window.scrollY-top)/h;
  return Math.max(0, Math.min(1, p));
}
// —— 续读：打开时跳回上次的位置 ——
window.addEventListener('load',function(){
  if(!window.__RESUME__) return;
  const ch=window.__START__;
  const el=document.querySelector('section.ch[data-ch="'+ch+'"]');
  if(!el) return;
  const ratio=window.__SCROLL__||0;
  if(ratio<=0.02) return;
  const y=el.offsetTop + el.offsetHeight*ratio;
  window.scrollTo({top:y,behavior:'auto'});
  tbar('已回到上次读到的位置（第 '+ch+' 章 '+(ratio*100).toFixed(0)+'%）');
});
// 离开页面前把精确位置存一次
addEventListener('visibilitychange',function(){
  if(document.visibilityState==='hidden'){
    try{navigator.sendBeacon('/api/progress',
      new Blob([JSON.stringify({slug:slug,chapter:curCh,scroll:chapterScroll(curCh)})],
               {type:'application/json'}));}catch(e){}
  }
});
const io=new IntersectionObserver(es=>{
  for(const e of es) if(e.isIntersecting){ report(parseInt(e.target.dataset.ch,10)); }
},{rootMargin:'-45% 0px -45% 0px'});
document.querySelectorAll('section.ch').forEach(s=>io.observe(s));

// —— 读到章末自动续译 ——
// 用户报过两件事，都出在这段：
//  1.「自动翻译完成某章后怎么不刷新，我还要手动刷新？」—— 原来 tick() 只由
//     滚动到底触发，poll() 也只往后**追加**章；落地那一章译好后没人管；
//  2.「我还没开始看，怎么就第二话了」—— 落地章没译文时服务端会偷偷跳到后面。
// 现在：need = 落地那一章（0 = 已就位）；译好后就地替换占位块，不用刷新。
// —— 底部翻译条：**一条状态 + 一条进度**，不做"每 2 秒换一句话" ——
// 用户报过「下面的翻译提示一直在反复变化，有点怪异」，而且「希望能看到翻译进度」。
// 病因：tick() 和 poll() 各自写不同的文案（"正在请求翻译…" / "后台正在翻译…" /
// "正在补译…"），轮询每 1.5~2.5 秒在两者间来回切 → 一句话在三四种说法间闪。
// 现在：状态文案只有**一套模板**（只有章号会变），进度单独一行、只随真实数字变。
// ---- 状态栏：**唯一写入入口**（架构约束，不只靠断言） --------------------
// 病因：tick() 和 poll() 各自写不同文案（"正在请求翻译…" / "后台正在翻译…"），
// 后来 v4.5 又把服务端的「第 N 章 · 段 x/y」整句塞进同一个槽，于是两句话
// 每 1.5~2.5 秒互相覆盖。修了两次都只是"把文案改一致"，因为谁都能拿到那个 DOM。
// 现在把元素关进闭包：外面只拿到 5 个函数，**没有别的方式**写到状态栏/进度槽。
// 新功能想显示状态，只能调这些函数 —— 结构上不可能再出现第二个写入方。
const TB = (function(){
  const elStatus=document.getElementById('tb-status');
  const elProg=document.getElementById('tb-prog');
  const elFill=document.getElementById('tb-fill');
  const elSeg=document.getElementById('tb-seg');
  const elStop=document.getElementById('tb-stop');
  let last='';
  function setStop(on){ if(elStop) elStop.classList.toggle('on', !!on); }
  function setStatus(html){
    if(html===last) return;
    last=html;
    if(elStatus) elStatus.innerHTML=html;
  }
  // 「段 x/y」写进自己的槽，**不进状态文案** —— 它每几秒变一次，混在状态里
  // 就会和「正在翻译第 N 章」互相覆盖（用户报过两次，别再合并回去）。
  function setSeg(txt){ if(elSeg) elSeg.textContent = txt || ''; }
  // 正在翻译时**唯一**的写法：状态只说"第 N 章"，段进度进 tb-seg。
  function transStatus(ch, seg){
    setStatus(`正在翻译第 <b>${ch}</b> 章…`);
    setSeg(seg || '');
  }
  function setProgress(d,t){
    if(d==null) return;
    if(typeof d==='number') done=d;
    // total 是 const（一本书的总章数不会变），别在这里赋值（以前写过会抛 TypeError）
    const p=total?Math.min(100,Math.round(done/total*100)):0;
    if(elFill) elFill.style.width=p+'%';
    if(elProg) elProg.textContent=`已译 ${done}/${total}（${p}%）`;
  }
  // 停止按钮的点击绑定也留在闭包里：交出去的是**回调注册**，不是元素本身。
  function onStop(handler){ if(elStop) elStop.onclick = handler; }
  return {setStop, setStatus, setSeg, transStatus, setProgress, onStop};
})();
const setStop=TB.setStop, setStatus=TB.setStatus, setSeg=TB.setSeg,
      transStatus=TB.transStatus, setProgress=TB.setProgress;
function escHtml(s){
  return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;',
    '>':'&gt;','"':'&quot;'}[c]));
}
// 兼容旧调用点（续读提示、译好提示等一次性消息）
function tbar(txt){ setStatus(txt); setSeg(''); }
function tocRefresh(){
  const box=document.getElementById('toc-list');
  if(!box) return;
  const onpage=[...document.querySelectorAll('section.ch[data-ch]:not(.pending)')]
    .map(s=>s.dataset.ch).join(',');
  fetch('/api/toc?slug='+encodeURIComponent(slug)+'&onpage='+onpage)
    .then(r=>r.json()).then(d=>{
    if(typeof d.html!=='string') return;
    box.innerHTML=d.html;
    if(d.count!=null) done=d.count;
    const n=document.getElementById('toc-count');
    if(n && d.count!=null) n.textContent=d.count+'/'+(d.total||total);
    const nav=document.getElementById('toc');
    if(nav) nav.style.display = d.count ? '' : 'none';
    const sd=document.getElementById('stat-done');
    if(sd && d.count!=null) sd.textContent=d.count;
  }).catch(()=>{});
}
// 「↑ 目录」指向折叠的 <details id="tocbox">；只改 hash 不会自动展开它。
// 点一下就把目录打开，避免用户以为按钮没反应。
document.querySelectorAll('a[href="#tocbox"]').forEach(a=>{
  a.addEventListener('click',()=>{
    const box=document.getElementById('tocbox');
    if(box) box.open=true;
  });
});
// 落地章译好了 → 把占位块换成真正的正文（不重新加载、不动阅读位置）
async function fillNeed(){
  if(!need) return false;
  try{
    const r=await fetch('/api/chapter?slug='+encodeURIComponent(slug)+'&ch='+need);
    const d=await r.json();
    if(!d.html) return false;
    const holder=document.createElement('div');
    holder.innerHTML=d.html;
    const sec=holder.querySelector('section.ch');
    if(!sec) return false;
    const ph=document.getElementById('need-'+need);
    if(ph) ph.replaceWith(sec);
    else document.getElementById('anchor').parentNode.insertBefore(
      sec, document.getElementById('anchor'));
    io.observe(sec);
    renderedChapters++;
    nextFrom=Math.max(nextFrom, need+1);
    const got=sec.dataset.ch;
    need=0; window.__NEED__=0;
    if(d.done!=null){ done=d.done; setProgress(done, total); }
    setStatus(`第 <b>${got}</b> 章已译好`); setSeg('');
    tocRefresh();
    return true;
  }catch(e){ return false; }
}
async function poll(){
  if(polling) return; polling=true;
  try{
    const r=await fetch('/api/job?slug='+encodeURIComponent(slug));
    const j=await r.json();
    if(j.status==='running'||j.status==='queued'){
      // j.done 是本次任务进度（补译第 50 章时可能=1），j.translated 才是全书累计。
      // 拿 j.done 写进度条会让"已译 50/100"瞬间倒退成 1/100。
      setProgress(j.translated!=null ? j.translated : done, total);
      setStop(true);
      // 服务端 message 是**真实进度**（抓取第 N 章 / 第 N 章 · 段 x/y）。
      // 拆开写：状态槽只说"正在翻译第 N 章"（一套模板），段进度进 tb-seg。
      const _msg = j.message || '';
      const _m = /第\s*(\d+)\s*章[^0-9]*段\s*(\d+)\s*\/\s*(\d+)/.exec(_msg);
      if(_m) transStatus(_m[1], `段 ${_m[2]}/${_m[3]}`);
      else if(/第\s*(\d+)\s*章/.test(_msg)) transStatus(RegExp.$1, '');
      else if(_msg) { setStatus(escHtml(_msg)); setSeg(''); }
      else transStatus(need||nextFrom, '');
      // ⚠ 必须清 polling 再排下一次 tick：tick() 开头是 `if(polling) return;`，
      // 不清的话"任务运行中"这条**最常**走的分支会把自己锁死 ——
      // /api/translate 只是入队立即返回，后端一在翻（status=running 是常态），
      // 轮询就永久停摆，译好的章节永不追加，读者必须手动刷新才能继续读
      // （核心承诺"读到哪翻到哪"直接失效）。下面几个分支都清了，这里漏了。
      polling=false;
      // 自动翻译关着时也可能是手动「继续翻译」排的任务：继续轮询到完成，
      // 不要交回 tick()（tick 只会显示"未开启自动翻译"然后停住）。
      setTimeout(TRANS.enabled ? tick : poll, 2500);
      return;
    }
    setStop(false);
    if(j.status==='cancelled'){
      // 与点「停止」**同一套** UI：都给「继续」入口。
      // 以前这里只写一行状态（没有继续），用户从别的设备/另一页停下后，
      // 回到这页只能刷新 —— 同一个状态两种待遇。
      stopped=true; showStopped();
      return;
    }
    if(j.status==='interrupted'){
      showInterrupted(j);
      return;
    }
    if(j.status==='provider_error'||j.status==='error'){
      tbar(`翻译出错：${j.error||''} · <a href="#" id="retry" style="color:var(--accent)">重试</a>`);
      const rt=document.getElementById('retry');
      if(rt) rt.onclick=(e)=>{e.preventDefault(); polling=false; resumeTranslate();};
      return;
    }
    if(j.status==='budget_exhausted'){
      tbar(`已到本章预算上限 · <a href="#" id="retry" style="color:var(--accent)">继续</a>`);
      const rt=document.getElementById('retry');
      if(rt) rt.onclick=(e)=>{e.preventDefault(); polling=false; resumeTranslate();};
      return;
    }
    if(j.status==='partial'){
      tbar('部分章节已译好 · <a href="#" id="retry" style="color:var(--accent)">补齐</a>');
      const rt=document.getElementById('retry');
      if(rt) rt.onclick=(e)=>{e.preventDefault(); polling=false; resumeTranslate();};
      return;
    }
    // 先看"你正等着的那一章"好了没 —— 好了就当场补上（不用手动刷新）
    if(await fillNeed()){ polling=false; if(nextFrom<=total) setTimeout(tick,600); return; }
    if(j.translated!=null){ done=j.translated; setProgress(done,total); }
    // 再看"下一章"译好了没 —— 好了就把章末的「下一章」点亮成真链接。
    // 一页只渲染一章，所以**不往本页追加**后续章节；读到章末点「下一章」翻页即可。
    const r2=await fetch('/api/next?slug='+encodeURIComponent(slug)+'&from='+nextFrom);
    const d=await r2.json();
    if(d.done!=null){ done=d.done; setProgress(done, total); }
    if(d.html){ setNextReady(); tocRefresh(); polling=false; return; }
    // 别再换说法：同一句模板，只有章号变（"正在补译"和"正在请求"以前各写一遍，
    // 轮询一来一回就是闪烁）。
    transStatus(d.need||nextFrom, '');
    polling=false; setTimeout(tick,1500);
  }catch(e){ polling=false; setTimeout(tick,2000); }
}
// 「下一章」译好 → 把章末那个占位 span 换成可点链接（不刷新、不跳动阅读位置）。
function setNextReady(){
  if(!nextCh || nextCh>total) return;
  nextHave=true; nextTrans=true;
  const box=document.getElementById('nav-next');
  if(!box) return;
  if(box.querySelector('a')) return;              // 服务端已渲染成链接
  box.innerHTML='<a class="navbtn" href="/read/'+encodeURIComponent(slug)
    +'?from='+nextCh+'#c'+nextCh+'">下一章 →</a>';
    tbar(`第 <b>${nextCh}</b> 章已译好`);
}
const TRANS={enabled:window.__TENABLED__,ceiling:window.__CEIL__||0};
let stopped=false;
// 「已停止 + 继续」只写一份：点停止、以及轮询到 cancelled（别的设备/标签页停的）
// 走同一条渲染，避免两种入口两种待遇。
function showStopped(){
  setStop(false); setSeg('');
  // 短文案：手机上状态槽会被进度条挤压，太长会把「继续」链接截掉。
  setStatus('已停止翻译 · '
    +'<a href="#" id="btn-resume" style="color:var(--accent)">继续</a>');
  const br=document.getElementById('btn-resume');
  if(br) br.onclick=async(e)=>{e.preventDefault(); stopped=false;
    await post('/api/translate',{slug:slug,resume:true,count:2,
      after:need||nextFrom||curCh,reason:'resume'});
    TRANS.enabled=true; polling=false; tick();};
}
function resumeTranslate(){
  recoveryPending=false;
  const r=jobInfo.requested||{};
  post('/api/translate',{
    slug:slug,
    count:r.count||2,
    after:r.after||need||nextFrom,
    fill:!!r.fill,
    ceiling:r.ceiling||null,
    reason:'resume',
    resume:true
  }).then(()=>{polling=false; setTimeout(poll,900);})
    .catch(()=>{recoveryPending=true; setStatus('恢复失败，请刷新后重试');});
}
function showInterrupted(j){
  recoveryPending=true;
  setStop(false); setSeg('');
  const doneN=(j.completed||0), left=(j.remaining||0);
  setStatus(`上次翻译中断（完成 ${doneN} 章，剩 ${left} 章） · `
    +'<a href="#" id="btn-recover" style="color:var(--accent)">确认恢复</a>');
  const b=document.getElementById('btn-recover');
  if(b) b.onclick=e=>{e.preventDefault(); resumeTranslate();};
}
if(TB.onStop) TB.onStop(async()=>{
  // 按钮名字就是承诺：点了就**停**，并暂停这本书的持续翻译 ——
  // 只取消任务的话，调度器 2 秒后又会把下一章排回来。
  setStop(false);
  stopped=true; polling=false;
  try{ await post('/api/stop',{slug:slug,disable:true}); }catch(e){}
  TRANS.enabled=false;
  showStopped();
});
function tick(){
  if(polling) return;
  if(stopped) return;
  if(recoveryPending) return;
  if(!TRANS.enabled){
    tbar('本书翻译已暂停 · <a href="#" id="btn-en" style="color:var(--accent)">点此继续</a>');
    const be=document.getElementById('btn-en');
    if(be) be.onclick=async(e)=>{e.preventDefault();
      await fetch('/api/transcfg',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({slug:slug,enabled:true})}); location.reload();};
    return;
  }
  const want=need||nextFrom;                // 先要"你正等着的那一章"
  // 只有**真有译文**才停手。以前看 nextHave（=链接可点）→ 永远为真 → 预翻从不触发。
  if(!need && nextTrans){ setStatus('下一章已就绪'); return; }
  if(TRANS.ceiling && (want>TRANS.ceiling)){
    tbar(`已达自动翻译上限（第 ${TRANS.ceiling} 章）`);
    return;
  }
  if(!need && nextFrom>total){ tbar('已全部译完'); return; }
  polling=true;
  transStatus(want, '');
  fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slug:slug,count:2,reason:'reader',after:want})})
    // tick 进来时设了 polling=true（挡滚动重复触发），但 poll() 开头就是 `if(polling) return;`
    // —— 不在交给 poll 前解锁的话，tick 调度的**第一个** poll 会被自己的锁挡回，
    // 轮询链在启动瞬间就断，poll() 整个函数体（含"任务运行中"分支）永远是死代码，
    // 译好的章节永不追加、必须手动刷新（实测：tick 发 1 次 translate 后 /api/job 0 次）。
    // 与 poll() 各分支"先清 polling 再 setTimeout(tick,…)"对称：清锁后再交给对方。
    .then(r=>r.json().catch(()=>({})))
    .then(d=>{
      polling=false;
      if(d && (d.budget_exhausted || d.ok===false && /预算/.test(d.error||''))){
        budgetBanner(); return;
      }
      setTimeout(poll,1200);
    }).catch(()=>{polling=false;});
}
// 滚到接近底部就自动触发（并给手动兜底按钮）
addEventListener('scroll',()=>{
  const h=document.documentElement;
  if(h.scrollTop+h.clientHeight > h.scrollHeight-900 && (need||nextFrom<=total) && !polling) tick();
},{passive:true});
document.getElementById('btn-more').onclick=async()=>{
  // 手动"继续翻译"应当突破自动上限：直接请求到当前页之后的一段
  stopped=false;
  const up=Math.min(TRANS.ceiling|| (nextFrom+5), total);
  await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slug:slug,count:5,reason:'manual',ceiling:up,
      after:need||nextFrom,resume:true})});
  if(!polling){
    // 自动翻译关着时也要轮询这次手动任务，否则按钮点了像没反应。
    if(TRANS.enabled) tick(); else setTimeout(poll,800);
  }
};
setProgress(done, total);
if(need) transStatus(need, '');
else if(nextCh && !nextTrans) { transStatus(nextCh, ''); }
else if(nextCh) setStatus('下一章已就绪');
else setStatus('已全部译完');
// 预算用尽时不要每轮 tick 都撞一次 409：先把话说清楚，给一个能动的入口。
function budgetBanner(){
  setStatus('今日翻译预算已用尽 · <a href="/queue" style="color:var(--accent)">去提高预算</a>');
}
if(window.__BUDGET_LEFT__<=0){
  budgetBanner();
}else if(need) tick();      // 落地章还没译文：一进页面就开始翻，不等用户滚到底
// 落地章有译文、但**下一章还没有**：一进页面就开始翻下一章，别等用户读到章末。
// 踩过（用户报"翻译速度变慢"）：一页只渲染一章之后，只有滚到底才触发翻译，
// 于是每翻一章都要干等 30~45 秒；提前开工就能在读者读完本章前把下一章备好。
else if(nextCh && !nextTrans && window.__BUDGET_LEFT__>0) tick();
// 页面加载时已经有后台任务：把「停止」显示出来并开始轮询，
// 不要因为下一章已有译文就看不到当前任务（__JOB__ 以前只注入、没人读）。
if(jobInfo.read_only){
  setStop(false); setStatus('只读恢复模式：任务日志损坏，暂不翻译');
}else if(job==='running'||job==='queued'){
  setStop(true);
  setTimeout(poll,500);
}else if(job==='cancelled'){
  stopped=true; showStopped();
}else if(job==='interrupted'){
  showInterrupted(jobInfo);
}else if(job==='provider_error'||job==='error'){
  tbar(`上次翻译出错：${jobInfo.error||''} · `
    +'<a href="#" id="retry" style="color:var(--accent)">重试</a>');
  const rt=document.getElementById('retry');
  if(rt) rt.onclick=e=>{e.preventDefault(); resumeTranslate();};
}else if(job==='budget_exhausted'){
  tbar('上次翻译到预算上限 · '
    +'<a href="#" id="retry" style="color:var(--accent)">继续</a>');
  const rt=document.getElementById('retry');
  if(rt) rt.onclick=e=>{e.preventDefault(); resumeTranslate();};
}else if(job==='partial'){
  tbar('上次有部分章节未译全 · '
    +'<a href="#" id="retry" style="color:var(--accent)">补齐</a>');
  const rt=document.getElementById('retry');
  if(rt) rt.onclick=e=>{e.preventDefault(); resumeTranslate();};
}
// 章末「下一章」还没译好时可点：点它就催翻译（短章不滚动时也能推进）。
document.addEventListener('click',e=>{
  const t=e.target;
  if(t&&t.closest&&t.closest('#nav-next')&&!nextTrans){ e.preventDefault(); tick(); }
});

// —— 连续阅读：键盘 / 触屏手势翻章 ——
// 本页是从 start 起连续渲染的若干章（section.ch[data-ch]）。左右滑 / ←→ / j k：
// 批内平滑滚到上/下一章；越过批边界则整页跳到相邻批（下一批仍由 /read?from=N 渲染，
// 依旧是"读到哪翻到哪"的一部分）；已是最后一章只提示、不硬跳。
function chapterEls(){ return [...document.querySelectorAll('section.ch[data-ch]')]; }
// 滚动时把 navCh 对齐到"视口顶部那一章"；手动翻章也走这个口径。
// 与 observer 的"屏幕中部章"分开，避免短章节下键盘/手势原地打转。
addEventListener('scroll',()=>{
  const els=chapterEls();
  if(!els.length) return;
  // 页面到底时，最后一章可能永远滚不到视口顶部（页面高度不够）。
  // 这时应把 navCh 认成最后一章，否则会一直退回上一章 → 右键卡死。
  const maxY=document.documentElement.scrollHeight-window.innerHeight;
  if(window.scrollY>=maxY-2){
    const last=parseInt(els[els.length-1].dataset.ch,10);
    if(Number.isFinite(last)) navCh=last;
    return;
  }
  let i=0;
  for(let k=0;k<els.length;k++){
    if(els[k].getBoundingClientRect().top<=80) i=k; else break;
  }
  const n=parseInt(els[i].dataset.ch,10);
  if(Number.isFinite(n)) navCh=n;
},{passive:true});
function gotoChapter(delta){
  const els=chapterEls();
  if(!els.length) return;
  const nums=els.map(s=>parseInt(s.dataset.ch,10));
  let idx=nums.indexOf(navCh);
  if(idx<0){                       // navCh 不在本批：优先"刚划过"的上一章，其次下一章
    let above=-1,below=-1,atop=-Infinity,btop=Infinity;
    els.forEach((s,i)=>{const top=s.getBoundingClientRect().top;
      if(top<=0){ if(top>atop){atop=top;above=i;} }
      else if(top<btop){btop=top;below=i;} });
    idx = above>=0 ? above : (below>=0 ? below : 0);
  }
  const t=idx+delta;
  // 自洽：翻章后就把 curCh 推到位，不等 IntersectionObserver 回调。
  // 否则快速连按两次 → 第二次仍用旧的 curCh → idx 未变，两下并成一下；
  // 且在"看第 4 章但 observer 尚未回调"时 ← 会误走越批跳转（实测桩里 curCh 恒=__START__）。
  if(t>=0 && t<els.length){
    navCh=nums[t]; curCh=navCh;
    els[t].scrollIntoView({behavior:'smooth',block:'start'}); return;
  }
  const edge = delta>0 ? nums[nums.length-1]+1 : nums[0]-1;
  if(edge>=1 && edge<=total){
    // 下一章没译文时页面渲染的是 #need-N 占位块；有译文才是 #cN。
    const anchor=(delta>0 && !nextTrans) ? 'need-'+edge : 'c'+edge;
    location.href='/read/'+encodeURIComponent(slug)+'?from='+edge+'#'+anchor;
  }else if(delta>0){ tbar('已经是最后一章了'); }
}
document.addEventListener('keydown',e=>{
  const t=e.target;
  // 别抢输入框的按键（反馈浮层里就有 textarea）
  if(t&&(t.tagName==='INPUT'||t.tagName==='TEXTAREA'||t.tagName==='SELECT'||t.isContentEditable)) return;
  if(e.key==='ArrowRight'||e.key==='j'||e.key==='J'){ e.preventDefault(); gotoChapter(1); }
  else if(e.key==='ArrowLeft'||e.key==='k'||e.key==='K'){ e.preventDefault(); gotoChapter(-1); }
});
// 触屏：单指横向滑动（|dx|>70 且明显大于纵向位移）翻章，左滑=下一章
let _sw_x=0,_sw_y=0,_sw_on=false;
document.addEventListener('touchstart',e=>{
  const t=e.target;
  // 反馈浮层、主题/反馈按钮、输入框里的横向滑动是用户操作，不是翻章。
  const interactive=!!(t&&t.closest&&(t.closest('#fbpanel')||t.closest('#readerbar')||
    t.closest('#translatebar')||t.closest('button')||t.closest('a')||
    t.closest('input')||t.closest('textarea')||t.closest('select')));
  if(e.touches.length===1&&!interactive){_sw_x=e.touches[0].clientX;_sw_y=e.touches[0].clientY;_sw_on=true;}
  else _sw_on=false;
},{passive:true});
document.addEventListener('touchend',e=>{
  if(!_sw_on||e.changedTouches.length!==1) return;
  _sw_on=false;
  const dx=e.changedTouches[0].clientX-_sw_x, dy=e.changedTouches[0].clientY-_sw_y;
  if(Math.abs(dx)>70 && Math.abs(dy)<70 && Math.abs(dx)>Math.abs(dy)*1.6) gotoChapter(dx<0?1:-1);
},{passive:true});

// —— 反馈：入口在「阅读与翻译设置」里，浮层自动带上"你当前正在看的章" ——
const panel=document.getElementById('fbpanel');
let vote='';
function openFeedback(){
  if(!panel) return;
  panel.classList.toggle('open');
  document.getElementById('fb-where').textContent='当前：第 '+curCh+' 章';
  const t=document.getElementById('fb-status'); t.textContent='';
}
const feedBtn=document.getElementById('open-feedback');
if(feedBtn) feedBtn.onclick=openFeedback;
document.getElementById('fb-close').onclick=()=>panel.classList.remove('open');
panel.querySelectorAll('button[data-v]').forEach(b=>{
  b.onclick=()=>{panel.querySelectorAll('button[data-v]').forEach(x=>x.classList.remove('on'));
    b.classList.add('on'); vote=b.dataset.v;};
});
document.getElementById('fb-send').onclick=async()=>{
  const note=document.getElementById('fb-note').value.trim();
  if(!vote&&!note){document.getElementById('fb-status').textContent='请选择一项或填写反馈内容';return;}
  await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({slug:slug,chapter:curCh,vote:vote,note:note})});
  document.getElementById('fb-note').value='';
  document.getElementById('fb-status').innerHTML='<span class="sent">已记录（第 '+curCh+' 章）</span>';
};
// 浮层打开时把当前章显示同步一次
setInterval(()=>{const w=document.getElementById('fb-where');
  if(w&&panel.classList.contains('open')) w.textContent='当前：第 '+curCh+' 章';},1500);
async function post(url,payload){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)});
  return r.json();
}
// 暂停 / 继续本书的持续翻译（v5.1：没有"自动翻译开关"了——
// 在读就一直翻；这个按钮只表达"我现在不想让它翻"）。
document.getElementById('btn-auto').onclick=async()=>{
  const el=document.getElementById('btn-auto');
  const resuming=el.textContent.indexOf('继续')>=0;
  if(resuming){
    await post('/api/translate',{slug:slug,resume:true,count:2,
      after:need||nextFrom||curCh,reason:'resume'});
  }else{
    await post('/api/stop',{slug:slug,disable:true});
  }
  location.reload();
};
const ceilEl=document.getElementById('ceil');
function readCeil(){
  let n=parseInt(ceilEl.value,10);
  if(!Number.isFinite(n)){
    flashMsg('请输入有效的章号'); ceilEl.focus(); return null;
  }
  n=Math.max(1,Math.min(total,n));
  ceilEl.value=String(n);
  return n;
}
document.getElementById('btn-ceil').onclick=async()=>{
  const n=readCeil();
  if(n===null) return;
  // 手动"翻到第 N 章"：一次性任务（after=当前章，ceiling=n）。
  // 持续翻译由调度器负责，这里只是插一个更高优先级的批次。
  await post('/api/translate',{slug:slug,count:Math.max(1,n-curCh),fill:false,
    reason:'manual-ceiling',ceiling:n,after:curCh,resume:true});
  location.reload();
};
ceilEl.onkeydown=e=>{
  if(e.key==='Enter'){ e.preventDefault(); document.getElementById('btn-ceil').click(); }
};
function flashMsg(m){
  const t=document.getElementById('policy-note');
  if(t){ t.textContent=m; t.style.color='var(--accent)'; }
}
// 旧版遗留已删：原先这里有对 btn-fav/btn-fin/btn-drop 逐个 .onclick=，但那三个按钮
// 早已并入 data-act 事件委托（见 ACTION_JS）。元素不存在 → getElementById 返回 null
// → "Cannot set properties of null" 抛出 → 后面所有绑定（日文折叠、主题切换）集体失效。

// —— 阅读页的小交互（日文折叠 / 主题 / 排版 / 常驻工具栏）——
// 这些原来内嵌在 lnserve.py 的 f-string 模板里，花括号要写双份转义，
// 改一次错一次；外置后受 node --check 保护，渲染仍是内联注入（逐字节不变）。
// 一律先判空：桩/半渲染页面缺元素时不许抛异常（抛了会废掉后面所有绑定）。
(function(){
  // 日文原文三态：hide（只中文）/ mix（半透明混排）/ show（整段对照）。
  // 设置页和这里共用 `ln-jp`，值必须是这三个之一。
  function saved(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  function setItem(k,v){try{localStorage.setItem(k,v);}catch(e){}}
  function jpMode(){var v=saved('ln-jp');return v==='show'||v==='mix'?v:'hide';}
  function applyJp(m){
    var b=document.body;
    b.classList.toggle('hidejp',m==='hide');
    b.classList.toggle('mixjp',m==='mix');
    var jp=document.getElementById('toggle-jp');
    if(jp){
      jp.setAttribute('aria-pressed',String(m!=='hide'));
      jp.textContent = m==='hide' ? '显示日文原文'
        : (m==='mix' ? '原文：混排（点击切对照）' : '原文：对照（点击隐藏）');
    }
  }
  let jpm=jpMode(); applyJp(jpm);
  const jp=document.getElementById('toggle-jp');
  if(jp){
    jp.onclick=()=>{
      jpm = jpm==='hide' ? 'mix' : (jpm==='mix' ? 'show' : 'hide');
      setItem('ln-jp',jpm); applyJp(jpm);
    };
  }
  const th=document.getElementById('theme');
  if(th) th.onclick=()=>{
    const r=document.documentElement,c=r.getAttribute('data-t');
    const t=c==='dark'?'light':'dark';
    r.setAttribute('data-t',t); r.style.colorScheme=t;
    try{localStorage.setItem('ln-theme',t);}catch(e){}
  };
  // 底栏「设置」：展开并滚到「阅读与翻译设置」（不跳页，读完原地回来）。
  const rb=document.getElementById('rb-settings');
  if(rb) rb.onclick=()=>{
    const d=document.getElementById('trans-settings');
    if(!d) return;
    d.open=true;
    d.scrollIntoView({behavior:'smooth',block:'start'});
  };
  // 「下章」还没译文时可点：催翻译。旧版只在注释里承诺"点了就催"，
  // 实际 span 没有任何 handler，读者只能干等（本次补上真正的入口）。
  document.addEventListener('click',e=>{
    const b=(e.target&&e.target.closest)?e.target.closest('[data-wait]'):null;
    if(!b) return;
    e.preventDefault();
    if(b.disabled) return;
    b.disabled=true;
    post('/api/translate',{slug:slug,resume:true,count:2,
      after:need||nextFrom||curCh,reason:'wait-next'})
      .catch(()=>{}).finally(()=>{b.disabled=false;});
    if(!polling) tick();
  });
  // 阅读排版：字号/行距只影响正文，存 localStorage，下次打开还是这套。
  const fs=document.getElementById('r-fs'), lh=document.getElementById('r-lh');
  const r=document.documentElement;
  function sync(){
    const f=(r.getAttribute('data-fs')==='s'||r.getAttribute('data-fs')==='l')
      ?r.getAttribute('data-fs'):'m';
    const h=(r.getAttribute('data-lh')==='tight'||r.getAttribute('data-lh')==='loose')
      ?r.getAttribute('data-lh'):'normal';
    if(fs) fs.value=f; if(lh) lh.value=h;
  }
  if(fs) fs.onchange=()=>{
    if(fs.value==='m') r.removeAttribute('data-fs'); else r.setAttribute('data-fs',fs.value);
    try{localStorage.setItem('ln-fs',fs.value);}catch(e){}
  };
  if(lh) lh.onchange=()=>{
    if(lh.value==='normal') r.removeAttribute('data-lh'); else r.setAttribute('data-lh',lh.value);
    try{localStorage.setItem('ln-lh',lh.value);}catch(e){}
  };
  sync();
})();

// —— 术语/人名：点一下看原文与人物简介 ——
// 手机上 hover 不存在（长按会被系统判成长按选字），所以用点击；再点一次收起。
// 气泡是 fixed 定位，跟着被点的词走，滚一下就消失（滚动时它留在原地会错位）。
(function(){
  var tip=null;
  function hide(){ if(tip){ tip.remove(); tip=null; } }
  document.addEventListener('click',function(e){
    var g=e.target&&e.target.closest?e.target.closest('.gloss'):null;
    if(!g){ hide(); return; }
    var same=(tip&&tip.__for===g);
    hide(); if(same) return;
    var t=document.createElement('div');
    t.id='gtip'; t.textContent=g.getAttribute('data-tip')||'';
    document.body.appendChild(t);
    var r=g.getBoundingClientRect();
    var top=r.bottom+8;
    if(top+t.offsetHeight>innerHeight-8) top=r.top-t.offsetHeight-8;
    var left=Math.min(Math.max(8,r.left),innerWidth-t.offsetWidth-8);
    t.style.top=Math.max(8,top)+'px'; t.style.left=left+'px';
    t.__for=g; tip=t;
  },{passive:true});
  addEventListener('scroll',hide,{passive:true});
  addEventListener('resize',hide);
})();

// —— 点击区域翻页（设置页可关闭；默认关，避免误触）——
// 只把「点正文空白/文字」当翻页；按钮、链接、术语气泡、输入框一律放行。
(function(){
  function saved(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  function mode(){var v=saved('ln-tap');return v==='lr'||v==='ud'?v:'off';}
  function go(ch){
    if(ch<1||ch>total) return;
    var a='c'+ch;
    if(ch===nextCh && !nextHave) a='need-'+ch;
    location.href='/read/'+encodeURIComponent(slug)+'?from='+ch+'#'+a;
  }
  document.addEventListener('click',function(e){
    var m=mode(); if(m==='off') return;
    if(e.defaultPrevented || e.button!==0) return;
    var t=e.target;
    if(t&&t.closest&&t.closest('a,button,input,select,textarea,summary,label,.gloss,.stale-note,#gtip,#fbpanel,#readerbar,#translatebar')) return;
    try{ if(String(window.getSelection&&getSelection()||'').length) return; }catch(err){}
    var x=e.clientX/innerWidth, y=e.clientY/innerHeight;
    var back = (m==='lr') ? x<0.4 : y<0.35;
    var fwd  = (m==='lr') ? x>0.6 : y>0.65;
    if(!back&&!fwd) return;
    go(curCh + (back?-1:1));
  },false);
})();

// —— 按新术语表重翻本章（术语表改过之后）——
(function(){
  function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,
    function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
  async function refreshStale(ch){
    for(var i=0;i<180;i++){
      await new Promise(function(r){setTimeout(r,2000);});
      try{
        var j=await fetch('/api/job?slug='+encodeURIComponent(slug))
          .then(function(r){return r.json();});
        if(j.status==='running'||j.status==='queued') continue;
        if(j.status!=='done'&&j.status!=='partial'){
          flashMsg('重翻未完成：'+esc(j.error||j.status||'未知状态'));
          return;
        }
        var req=j.requested||{};
        if(!req.force){
          flashMsg('另一个翻译任务先结束了，本次重翻没排上，请再点一次');
          return;
        }
        var d=await fetch('/api/chapter?slug='+encodeURIComponent(slug)+'&ch='+ch)
          .then(function(r){return r.json();});
        if(!d.html){ flashMsg('重翻完成，但没有读到新译文'); return; }
        var holder=document.createElement('div'); holder.innerHTML=d.html;
        var sec=holder.querySelector('section.ch');
        var old=document.querySelector('section.ch[data-ch="'+ch+'"]');
        if(sec&&old) old.replaceWith(sec);
        var note=document.querySelector('.stale-note'); if(note) note.remove();
        flashMsg('第 '+ch+' 章已按新术语表重翻');
        return;
      }catch(err){/* 服务抖一下继续等 */}
    }
    flashMsg('重翻还在后台进行，稍后刷新本页');
  }
  document.addEventListener('click',function(e){
    var b=e.target&&e.target.closest?e.target.closest('[data-stale-retranslate]'):null;
    if(!b) return;
    e.preventDefault();
    var ch=parseInt(b.getAttribute('data-stale-retranslate'),10)||curCh;
    b.disabled=true;
    post('/api/translate',{slug:slug,after:ch,count:1,ceiling:ch,force:true,
      reason:'glossary-stale',resume:true})
      .then(function(res){
        if(!res||!res.ok){
          b.disabled=false;
          flashMsg('重翻排队失败：'+esc((res&&res.error)||'稍后再试'));
          return;
        }
        flashMsg('已排队重翻第 '+ch+' 章…');
        refreshStale(ch);
      })
      .catch(function(){ b.disabled=false; flashMsg('重翻排队失败，稍后再试'); });
  });
})();

// —— 朗读本章（Web Speech；不花 token、不联网）——
(function(){
  var btn=document.getElementById('btn-speak');
  if(!btn) return;
  if(!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)){
    // 不支持也要**绑定 handler**：按钮点了必须有回应（"没反应"比"不支持"更糟），
    // 而且 test_click 会要求每个带 id 的按钮都有 handler。
    btn.onclick=function(){ flashMsg('这台设备的浏览器不支持语音朗读'); };
    return;
  }
  var speaking=false;
  function lang(){
    try{return localStorage.getItem('ln-speak')==='jp'?'jp':'zh';}catch(e){return 'zh';}
  }
  function chunk(t){
    var parts=String(t).match(/[^。！？!?…」』]+[。！？!?…」』]?/g)||[String(t)];
    var out=[],buf='';
    parts.forEach(function(s){
      if(buf && (buf+s).length>160){ out.push(buf); buf=s; }
      else buf+=s;
    });
    if(buf) out.push(buf);
    return out;
  }
  function texts(){
    var ch=curCh||window.__START__||1;
    var sec=document.querySelector('section.ch[data-ch="'+ch+'"]')
      || document.querySelector('section.ch:not(.pending)');
    if(!sec) return [];
    var sel=lang()==='jp'?'p.jp':'p:not(.jp):not(.blank)';
    var out=[];
    sec.querySelectorAll(sel).forEach(function(p){
      var s=(p.textContent||'').trim(); if(s) out=out.concat(chunk(s));
    });
    return out;
  }
  function stop(){
    try{speechSynthesis.cancel();}catch(e){}
    speaking=false; btn.textContent='朗读本章';
  }
  btn.onclick=function(){
    if(speaking){ stop(); return; }
    var arr=texts();
    if(!arr.length){ flashMsg('这一章还没有可朗读的'+(lang()==='jp'?'日文':'译文')); return; }
    speaking=true; btn.textContent='停止朗读';
    var i=0;
    function next(){
      if(i>=arr.length){ stop(); return; }
      var u=new SpeechSynthesisUtterance(arr[i++]);
      u.lang = lang()==='jp' ? 'ja-JP' : 'zh-CN';
      u.rate = 1.0;
      u.onend = next;
      u.onerror = stop;
      try{ speechSynthesis.speak(u); }catch(e){ stop(); }
    }
    next();
  };
  addEventListener('beforeunload',stop);
})();

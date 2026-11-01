
async function refresh(){
  try{
    const r=await fetch('/api/library');const d=await r.json();
    for(const it of d.items){
      const bar=document.querySelector(`[data-slug="${it.slug}"] .pbar>i`);
      if(bar) bar.style.width=(it.translated/it.total*100).toFixed(1)+'%';
      const p=document.querySelector(`[data-slug="${it.slug}"] .pill`);
      if(p){
        p.textContent = it.translated>=it.total ? '已全译'
          : (it.job && it.translated<it.total ? '翻译中' : `${it.translated}/${it.total} 章`);
        p.className='pill'+(it.translated>=it.total?' ok':'');
      }
    }
  }catch(e){}
}
setInterval(refresh,4000);

// —— 书架：搜索 + 按状态筛选 ——
// ⚠ 必须**只在书架面板里**过滤。
// 踩过：原来是 document.querySelectorAll('.card') 全局过滤 ——
// 在书架搜索框打个字，推荐卡和书库卡也被一起 display:none 了，
// 切到那两个页签就是一片空白（而且刷新才恢复）。
const qbox=document.getElementById('q');
let SHELF_F='all';
function shelfHit(c){
  const q=(qbox.value||'').trim().toLowerCase();
  if(q && !(c.dataset.hay||'').includes(q)) return false;
  if(SHELF_F==='all') return true;
  if(SHELF_F==='fav') return c.dataset.fav==='1';
  if(SHELF_F==='new')
    return c.dataset.status==='want' && (parseInt(c.dataset.read||'0',10)||0)<=0;
  return c.dataset.status===SHELF_F;
}
function applyShelfFilter(){
  const pane=document.getElementById('pane-shelf');
  if(!pane) return;
  let n=0;
  pane.querySelectorAll('.card').forEach(c=>{
    const hit=shelfHit(c);
    c.style.display=hit?'':'none'; if(hit)n++;
  });
  // 分组标题里的"N 本"说的是这一堆的**总数**，筛选后要让位给
  // 实际显示数，否则用户看到「在读 3 本」却只有 1 张卡（数字骗人）。
  pane.querySelectorAll('details[data-shelfkey]').forEach(s=>{
    const cards=[...s.querySelectorAll('.card')];
    const shown=cards.filter(c=>c.style.display!=='none').length;
    s.style.display=shown?'':'none';
    if(SHELF_F!=='all' || (qbox.value||'').trim()) s.open=!!shown;
    const slot=s.querySelector('summary .n');
    if(slot){
      if(!slot.dataset.orig) slot.dataset.orig=slot.textContent;
      // "N 本" 绝不能骗人：分组是分页渲染的，这里的 cards 只是**本页**的卡。
      // 筛选后要显示"本页命中 / 本页总数"，并注明只筛了本页，否则用户会以为
      // 收藏的书不见了（真实数据在下一页）。
      slot.textContent = shown===cards.length
        ? slot.dataset.orig
        : ('本页 '+shown+' / '+cards.length+' 本');
    }
  });
  const box=document.getElementById('empty');
  if(box) box.style.display=n?'none':'block';
  const sum=document.getElementById('fsum');
  if(sum){
    const off=SHELF_F!=='all'||(qbox.value||'').trim();
    sum.textContent = off
      ? ('本页匹配 '+n+' 部 · 搜索与筛选仅作用于当前页（翻页查看更多）')
      : '';
  }
}
if(qbox) qbox.oninput=applyShelfFilter;
document.querySelectorAll('#sfilter button').forEach(b=>{
  b.onclick=()=>{
    SHELF_F=b.dataset.f||'all';
    document.querySelectorAll('#sfilter button').forEach(x=>
      x.classList.toggle('on', x===b));
    applyShelfFilter();
  };
});

// 状态按钮 / 加入书架 / 翻页 / 看想看的处理器**全部**搬到 ACTION_JS：
// 事件委托，一次绑定覆盖全站。LIB_JS 里不再给按钮绑 onclick。

// —— 推荐位：换一批（本地翻页，秒回）/ 重新抓取（源站，慢，带进度） ——
// 踩过：两个语义塞进一个按钮 —— 点「换一批」其实去源站重抓同样的关键词，
// 同样的关键词抓回来还是同一批书、排序也一样，于是"等了三分半，页面没变"。
const rn=document.getElementById('recs-next');
if(rn) rn.onclick=async function(e){
  const b=e.target; b.disabled=true; const old=b.textContent; b.textContent='切换中…';
  try{
    const r=await fetch('/api/recs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({rotate:true})});
    const d=await r.json();
    if(d.ok){ reloadAt('recstop'); return; }
    b.textContent = d.reason==='empty' ? '暂无推荐' : '无法切换';
  }catch(err){ b.textContent='网络异常'; }
  setTimeout(()=>{ b.disabled=false; b.textContent=old; },1500);
};

const rt=document.getElementById('recs-topup');
if(rt) rt.onclick=async function(e){
  const b=e.target; b.disabled=true; const old=b.textContent; b.textContent='生成中…';
  try{
    const r=await fetch('/api/recs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({topup:true})});
    const d=await r.json();
    if(d.ok){ reloadAt('recstop'); return; }
    b.textContent = d.reason==='empty' ? '书库中暂无作品' : '请求失败';
  }catch(err){ b.textContent='网络异常'; }
  setTimeout(()=>{ b.disabled=false; b.textContent=old; },2000);
};
const rb=document.getElementById('recs-refresh');
if(rb) rb.onclick=async function(e){
  const b=e.target; b.disabled=true;
  try{
    const r=await fetch('/api/recs',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({refresh:true})});
    const d=await r.json();
    if(!d.ok){ b.textContent='失败：'+(d.error||'');
      setTimeout(()=>{b.disabled=false;},2000); return; }
  }catch(err){ b.textContent='网络异常';
    setTimeout(()=>{b.disabled=false;},2000); return; }
  // 后台在跑 → 轮询进度。必须显示 x/y，否则又是"点了没反应"。
  recsPoll(b);
};
// 进度轮询：按钮和页面上的进度行共用。
// 刷新页面也会接着显示 —— 抓取在服务端后台跑，不能因为刷新就"看不见了"。
async function recsPoll(el){
  if(!el) return;
  let tries=0;
  const tick=async ()=>{
    tries++;
    let s=null;
    try{ s=await (await fetch('/api/recsjob')).json(); }catch(err){}
    if(!s){ if(tries<400) setTimeout(tick,2000); return; }
    if(s.error){ el.textContent='抓取失败：'+s.error; return; }
    if(s.running){
      el.textContent='正在抓取 '+(s.done||0)+'/'+(s.total||0)+' 个关键词'
        +(s.found?('（已找到 '+s.found+' 部候选）'):'');
      if(tries<400) setTimeout(tick,1500);
      return;
    }
    el.textContent='抓取完成，共 '+(s.found||0)+' 部，正在刷新…';
    setTimeout(()=>reloadAt('recstop'),800);
  };
  tick();
}
// 刷新页面后如果后台还在抓，进度继续显示（否则用户以为它没在跑）
const rrun=document.getElementById('recs-run');
if(rrun) recsPoll(rrun);
// —— 分页切换（hash 路由，刷新后停在原页） ——
function showTab(name){
  document.querySelectorAll('.tabs a').forEach(a=>
    a.classList.toggle('on', a.dataset.tab===name));
  document.querySelectorAll('.pane').forEach(p=>
    p.classList.toggle('on', p.id==='pane-'+name));
  try{ history.replaceState(null,'','#'+name); }catch(e){}
}
document.querySelectorAll('.tabs a').forEach(a=>{
  a.onclick=()=>showTab(a.dataset.tab);
});
showTab((location.hash||'#recs').slice(1));

// —— 翻页/换页后回到「列表顶部」而非页面顶部/底部 ——
// 目标 id 由 action.js 的 reloadAt() 写进 sessionStorage，这里读出来滚过去。
// 必须先切好页签（上面 showTab 已完成），否则隐藏的 pane 量不出位置。
try{
  if(sessionStorage.getItem('ln-goto')) history.scrollRestoration='manual';
}catch(e){}
(function restoreGoto(){
  let sel=null;
  try{ sel=sessionStorage.getItem('ln-goto'); sessionStorage.removeItem('ln-goto'); }catch(e){}
  if(!sel) return;
  const go=function(){
    const el=document.getElementById(sel);
    if(!el) return;
    // 落在一个折叠的书架分组里时先展开，否则滚过去只是一条 summary。
    try{ const d=el.closest&&el.closest('details'); if(d) d.open=true; }catch(e){}
    try{ el.scrollIntoView({block:'start'}); }catch(e){ try{el.scrollIntoView();}catch(e2){} }
  };
  go();
  setTimeout(go,80);
})();

// —— 书库：想看 / 加入书架 / 搜索 ——
// 分页按钮与「标记想读」也在 ACTION_JS 的委托里，这里不再逐个绑。
// 注意：书库卡原来的「隐藏」按钮已并入「不感兴趣」——
// 只隐藏不学画像等于白点。data-dislike 的处理器见文件末尾的 DISLIKE_JS。
const lq=document.getElementById('libq');
const lw=document.getElementById('libwant');
if(lq) lq.onkeydown=e=>{ if(e.key==='Enter'){ applyLib(); } };
if(lq&&document.getElementById('libapply')){
  document.getElementById('libapply').onclick=applyLib;
}
if(lw) lw.onclick=async()=>{
  const on=lw.classList.contains('on');
  await fetch('/api/library?want='+(on?'0':'1'));
  reloadAt('libtop');
};
// 标签 facet 支持**多选**（语义 AND：同时满足）。点 chip 切换选中；全部取消=回到全量。
// chip 每次筛选后整体重渲染，这里在加载时逐个绑定即可（和 libwant 同理）。
function libSelTags(){
  return Array.prototype.slice.call(document.querySelectorAll('.libtag.on'))
    .map(function(b){return b.dataset.libtag;}).filter(Boolean);
}
function libTagsUrl(list){
  return '/api/library?'+
    (list.length ? list.map(function(t){return 'tag='+encodeURIComponent(t);}).join('&')
                 : 'tag=');
}
document.querySelectorAll('.libtag').forEach(b=>{
  if(b.id==='libtagclear') return;          // 清除按钮单独绑定
  b.onclick=async()=>{
    const t=b.dataset.libtag||'';
    if(!t) return;
    const cur=libSelTags();
    const next=cur.indexOf(t)>=0 ? cur.filter(x=>x!==t) : cur.concat([t]);
    await fetch(libTagsUrl(next));
    reloadAt('libtop');
  };
});
const _ltc=document.getElementById('libtagclear');
if(_ltc) _ltc.onclick=async()=>{ await fetch(libTagsUrl([])); reloadAt('libtop'); };
async function applyLib(){
  const q=encodeURIComponent(lq ? (lq.value||'') : '');
  await fetch('/api/library?q='+q);
  reloadAt('libtop');
}
// ⚠ 必须判空：以前这里直接 .onclick=，元素一缺就抛异常，
// 而异常会**掐掉同一段脚本里后面所有的绑定** —— 表现就是"一批按钮全没反应"。
const _ckAll=document.getElementById('check-all');
if(_ckAll) _ckAll.onclick=async e=>{
  e.target.textContent='检查中…';
  await fetch('/api/check',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({all:true})});
  reloadAt('shelf-top');
};

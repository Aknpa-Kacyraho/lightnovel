
// ============================================================================
// 全局动作分发：所有 data-* 按钮的**唯一**绑定点（事件委托）
//
// 为什么不是「加载时给每个按钮 .onclick=?」——这条路上踩过三次
// 「按钮按了没反应」，每次漏绑的方式都不一样：
//   1) 详情页 ★收藏 的 class 写死 on → 前端永远发 value:false → 收藏永远开不了；
//   2) 卡片上「更新了 +N 话 · 点我翻译」不在 .ctrls 里 → 从来没人给它绑过 handler；
//   3) 一条 getElementById(...).onclick 抛异常 → 它之后的所有绑定全部失效。
// 委托只有一次绑定：按钮放哪儿都行、动态插入的也行、以后新增的按钮自动可用。
// 所有反馈都取自**服务端返回的真实状态**，不在本地猜（见 STATE-MACHINE.md §3）。
//
// 这份脚本被 /、/book、/tags 三类页面共用，所以**不许依赖某个页面特有的元素**。
// ============================================================================
function $id(x){return document.getElementById(x);}
function clog(msg){
  try{fetch('/api/log',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({m:String(msg)})});}catch(e){}
}
function flash(card,msg){
  let t;
  if(card){ t=card.querySelector('.toast'); }
  if(!t){
    t=document.createElement('div');
    t.className = card ? 'toast' : 'toast page';
    (card||document.body).appendChild(t);
  }
  t.textContent=msg;
  t.style.opacity='1'; t.style.transform='translateY(0)';
  clearTimeout(t._hide);
  t._hide=setTimeout(function(){
    t.style.opacity='0'; t.style.transform='translateY(-4px)';
    if(!card) setTimeout(function(){ if(t.parentNode) t.parentNode.removeChild(t); },400);
  },2600);
}
// 按服务端返回的真实状态重绘按钮与徽标 —— UI 永远等于实际
function applyCardState(card,st){
  const tk=st.tracking||'want';
  // 卡片上的 data-* 是书架筛选（lib.js 的 shelfHit）的依据：只改按钮 class、
  // 不改 dataset，会让「刚收藏 → 点『已收藏』筛选 → 这本却被藏起来」。
  // 状态变化必须同时落到 UI 和数据属性上（同一个事实只有一份来源）。
  if(card){
    card.dataset.fav = st.favorite ? '1' : '0';
    card.dataset.status = tk;
  }
  const set=(act,on)=>{
    const el=card.querySelector('.ctrls button[data-act="'+act+'"]');
    if(el) el.classList.toggle('on',!!on);
  };
  set('favorite', st.favorite);
  set('reading',  tk==='reading');
  set('finished', tk==='finished');
  set('dropped',  tk==='dropped');
  const t=card.querySelector('.t');
  if(t){
    card.querySelectorAll('.badge.fav,.badge.fin,.badge.drop,.badge.tk').forEach(x=>x.remove());
    if(st.favorite){
      const s=document.createElement('span'); s.className='badge fav'; s.textContent='收藏'; t.appendChild(s);
    }
    const map={finished:['fin','看完'],dropped:['drop','弃文'],reading:['tk','在读']};
    if(map[tk]){
      const s=document.createElement('span'); s.className='badge '+map[tk][0];
      s.textContent=map[tk][1]; t.appendChild(s);
    }
  }
}
// 翻页/换页后回到「列表顶部」而不是页面顶部 —— 否则用户点完下一页，
// 新页停在底部、还得从下往上看（用户原话）。把目标元素的 id 存进 sessionStorage，
// 刷新后由 lib.js 读出来 scrollIntoView。
function gopageTarget(anchor){
  anchor = anchor || '';
  if(anchor.indexOf('shelf:')===0) return 'shelf-'+(anchor.slice(6)||'');
  return 'libtop';
}
function reloadAt(target){
  try{ if(target) sessionStorage.setItem('ln-goto',target); }catch(e){}
  location.reload();
}
async function postJSON(url,payload){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload||{})});
  return r.json();
}
// 服务端返回之后，这个按钮应该是什么状态
function stateOn(act,d){
  if(act==='favorite') return !!d.favorite;
  if(act==='off') return false;
  return (d.tracking||'')===act;
}
// 文案同步：只有「★/☆ 收藏」这类**用文案表示状态**的按钮需要改字。
// 书架卡的按钮是固定多词标签（"✕ 移出"），靠 .on 类表示状态，不该被改写。
function syncLabel(b,act,d){
  if(act!=='favorite') return;
  const t=(b.textContent||'').trim();
  if(t.indexOf('收藏')>=0 && (t.charAt(0)==='★'||t.charAt(0)==='☆')){
    b.textContent = d.favorite ? '★ 已收藏' : '☆ 收藏';
  }
}
async function runAction(b,ev){
  const card = b.closest ? b.closest('.card') : null;
  const slug = b.dataset.slug || b.dataset.dSlug || (card ? (card.dataset.slug||'') : '');
  const act  = b.dataset.act || b.dataset.dAct || '';
  clog('click act='+act+' slug='+slug);

  // ---------- ＋ 加入书架（推荐卡 / 书库卡 / 详情页共用） ----------
  if(b.dataset.add || b.dataset.dAdd){
    const url=b.dataset.add || b.dataset.dAdd;
    const old=b.textContent;
    b.disabled=true; b.textContent='加入中…';
    try{
      const d=await postJSON('/api/add',{url:url, id:b.dataset.dId||''});
      if(d&&d.ok){
        b.textContent = d.existed ? '已在书架' : '已加入';
        flash(card, d.existed ? '该作品已在书架中' : '已加入书架，可以开始阅读了');
        setTimeout(()=>location.reload(),700);
      }else{
        b.disabled=false; b.textContent='失败：'+((d&&d.error)||'未知错误');
      }
    }catch(e){
      b.disabled=false; b.textContent=old;
      flash(card,'加入失败：服务未响应');
    }
    return;
  }

  // ---------- 书库「☆ 想看」：只在书库清单里做标记，还不能读 ----------
  if(b.dataset.want){
    const on=b.classList.contains('on');
    b.disabled=true;
    try{
      await postJSON('/api/want',{id:b.dataset.want,value:!on});
      b.classList.toggle('on',!on);
      b.textContent = !on ? '已标记想读' : '标记想读';
    }catch(e){ flash(card,'保存失败'); }
    b.disabled=false;
    return;
  }

  // ---------- 翻页（书架/书库共用） ----------
  if(b.dataset.gopage){
    const p=parseInt(b.dataset.gopage,10), anchor=b.dataset.anchor||'';
    b.disabled=true;
    try{
      if(anchor.indexOf('shelf:')===0){
        await postJSON('/api/shelfpage',{key:anchor.slice(6),page:p});
      }else{
        await fetch('/api/library?page='+p);
      }
      reloadAt(gopageTarget(anchor));
    }catch(e){ b.disabled=false; flash(card,'翻页失败'); }
    return;
  }

  if(!slug){ clog('ABORT: no slug'); return; }

  // ---------- 慢操作：都要有可见进度，不许"点了没反应" ----------
  if(act==='check'){
    b.disabled=true; b.textContent='查询中…';
    try{ await postJSON('/api/check',{slug:slug}); }
    catch(e){ flash(card,'检查更新失败'); }
    location.reload(); return;
  }
  if(act==='autotrans'){
    b.disabled=true; b.textContent='启动中…';
    try{
      await postJSON('/api/transcfg',{slug:slug,enabled:true});
      await postJSON('/api/queue',{action:'add',slug:slug});
      const d=await postJSON('/api/translate',{slug:slug,count:3,reason:'shelf-start'});
      if(d&&d.ok===false){
        b.disabled=false; b.textContent='开启翻译';
        flash(card, d.error||'启动翻译失败'); return;
      }
    }catch(e){
      b.disabled=false; b.textContent='开启翻译';
      flash(card,'启动翻译失败：服务未响应'); return;
    }
    const poll=async()=>{
      let j={};
      try{ j=await (await fetch('/api/job?slug='+encodeURIComponent(slug))).json(); }catch(e){}
      if(j.status==='running'||j.status==='queued'){
        b.textContent='翻译中 '+(j.done||0)+' 章…'; setTimeout(poll,3000);
      }else if(j.status==='error'){
        b.disabled=false; b.textContent='翻译出错，点击重试';
      }else{ location.reload(); }
    };
    setTimeout(poll,1500); return;
  }
  if(act==='fill'){
    b.disabled=true; b.textContent='开始翻译…';
    // count 取自按钮上的 data-n（= 卡片显示的"新话数"）：
    // 按钮名字是承诺，不能一次点击就把整本欠账全翻掉（那会很贵）。
    const n=parseInt(b.dataset.n||'2',10)||2;
    try{ await postJSON('/api/translate',{slug:slug,count:n,fill:true,reason:'shelf-fill'}); }
    catch(e){ flash(card,'启动翻译失败'); }
    const poll=async()=>{
      let j={};
      try{ j=await (await fetch('/api/job?slug='+encodeURIComponent(slug))).json(); }catch(e){}
      if(j.status==='running'||j.status==='queued'){
        b.textContent='翻译中 '+(j.done||0)+' 章…'; setTimeout(poll,3000);
      }else if(j.status==='error'){
        b.disabled=false; b.textContent='翻译出错，点击重试';
      }else{ location.reload(); }
    };
    setTimeout(poll,1500); return;
  }
  if(act==='retry'){
    // 上次任务失败（卡片上有「翻译失败」徽标 + 这个按钮）。
    // 只补 2 章、不 fill：失败可能只是某一段，重试从"读到 + ahead"继续。
    b.disabled=true; b.textContent='重试中…';
    try{ await postJSON('/api/translate',{slug:slug,count:2,reason:'retry'}); }
    catch(e){ b.disabled=false; b.textContent='重试翻译'; flash(card,'启动失败'); return; }
    const poll=async()=>{
      let j={};
      try{ j=await (await fetch('/api/job?slug='+encodeURIComponent(slug))).json(); }catch(e){}
      if(j.status==='running'||j.status==='queued'){
        b.textContent='重试中 '+(j.done||0)+' 章…'; setTimeout(poll,3000);
      }else if(j.status==='error'){
        b.disabled=false; b.textContent='重试翻译';
        flash(card,'仍然失败：'+((j&&j.error)||'未知原因'));
      }else{ location.reload(); }
    };
    setTimeout(poll,1500); return;
  }
  if(act==='trname'){
    const wid=b.dataset.wid || (card ? (card.dataset.wid||'') : '');
    if(!wid){ flash(card,'无法获取作品 id，无法翻译书名'); return; }
    b.disabled=true; b.textContent='翻译中…';
    try{ await postJSON('/api/translate_meta',{id:wid}); }
    catch(e){ b.disabled=false; b.textContent='翻译书名'; flash(card,'请求失败'); return; }
    let tries=0;
    const tick=async()=>{
      tries++;
      let s={};
      try{ s=await (await fetch('/api/trstate?id='+encodeURIComponent(wid))).json(); }catch(e){}
      if(s.zh_title){ location.reload(); return; }
      if(tries>20){ b.disabled=false; b.textContent='尚未完成，点击重试'; return; }
      setTimeout(tick,1500);
    };
    setTimeout(tick,1500); return;
  }

  // ---------- 状态类：报文里的 value 只由「按钮当前 on 状态」决定 ----------
  const cur=b.classList.contains('on');
  const orig=b.textContent;
  b.disabled=true; b.textContent='…';
  let d;
  try{
    d=await postJSON('/api/status',{slug:slug,action:act,value:!cur});
  }catch(err){
    b.disabled=false; b.textContent=orig;
    flash(card,'请求失败：服务未响应'); clog('FETCH FAIL '+err.message);
    return;
  }
  b.disabled=false; b.textContent=orig;
  if(!d||!d.ok){
    flash(card,'保存失败：'+((d&&d.error)||'未知错误'));
    clog('BAD RESP '+JSON.stringify(d)); return;
  }
  if(card) applyCardState(card,d);
  b.classList.toggle('on', stateOn(act,d));
  syncLabel(b,act,d);
  if(d.removed){
    flash(card,'已移出书架（译文保留，随时能加回来）');
    setTimeout(()=>location.reload(),700); return;
  }
  if(d.cleared_favorite){
    flash(card,'已弃文 · 已自动取消收藏');
    setTimeout(()=>location.reload(),900); return;
  }
  const say={favorite:d.favorite?'已收藏（将用于口味学习）':'已取消收藏',
             reading:d.tracking==='reading'?'已标记在读':'已取消在读',
             finished:d.tracking==='finished'?'已标记为读完':'已取消看完',
             dropped:d.tracking==='dropped'?'已弃文':'已取消弃文'};
  flash(card, say[act] || '已更新');
}
// 唯一绑定：一次委托覆盖全部页面的全部动作按钮
document.addEventListener('click',function(ev){
  const el=ev.target;
  const b=(el&&el.closest)?el.closest('[data-act],[data-d-act],[data-add],[data-d-add],[data-want],[data-gopage]'):null;
  if(!b) return;
  runAction(b,ev);
});

// 「⋯」更多菜单：点卡片外面 / 点完菜单里的动作后自动收起。
// 原生 <details> 只有点 summary 才关，点外面会一直开着，看着像卡住。
document.addEventListener('click',function(ev){
  var t=ev.target;
  var inMenu=(t&&t.closest)?t.closest('.moremenu'):null;
  if(inMenu){
    if(t.closest('.morelist button')) inMenu.open=false;
    return;
  }
  document.querySelectorAll('.moremenu[open]').forEach(function(d){d.open=false;});
},true);

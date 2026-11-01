
// 详情页自己只需要管两件**本页特有**的事：
//   ① 翻译状态按钮（#d-tr）；② 重抓简介/目录（#d-refresh）。
// 状态按钮（收藏/在读/读完/弃文/移出）和「加入书架」**不在这里绑** ——
// 它们由 ACTION_JS 的全局委托处理，绑两遍会重复发请求。
// 踩过：这里曾经给每个按钮 .onclick=，而 ★收藏 的 class 被写死成 on，
// 于是前端永远发 value:false，收藏怎么点都开不了（用户连点四次）。
// 译成中文：标题 + 简介。翻完自动刷新
var dt = document.getElementById('d-tr');
if(dt){
  dt.onclick = async function(){
    dt.disabled = true; dt.textContent = '翻译中…';
    try{
      await fetch('/api/translate_meta', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id:dt.dataset.id})});
    }catch(e){ dt.disabled=false; dt.textContent='翻译标题与简介'; return; }
    var tries = 0;
    var poll = async function(){
      tries++;
      var j = {};
      try{ j = await (await fetch('/api/trstate?id=' + encodeURIComponent(dt.dataset.id))).json(); }catch(e){}
      if(j.zh_title || j.zh_synopsis){ location.reload(); return; }
      if(j.status === 'error'){ dt.disabled=false; dt.textContent='翻译失败，点击重试'; return; }
      if(tries > 40){ dt.disabled=false; dt.textContent='翻译中，点击刷新'; return; }
      setTimeout(poll, 1500);
    };
    setTimeout(poll, 1200);
  };
}
// 没中文简介时自动开翻（用户是中文读者，日文简介等于没给）
if(!window.__ZH_SYN__ && window.__WID__){ 
  fetch('/api/translate_meta', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id:window.__WID__})}).catch(function(){});
}

// 手动重抓简介 / 目录
var dr = document.getElementById('d-refresh');
if(dr){
  dr.onclick = async function(){
    dr.disabled = true; dr.textContent = '刷新中…';
    try{
      await fetch('/api/detail', {method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id:dr.dataset.id, force:true})});
    }catch(e){}
    location.reload();
  };
}

// 「加入翻译列表」：提前排队翻译（不打开这本书也会被翻）。
// 用 data-qadd 委托，避免详情页每次多绑一个 onclick（漏绑一次就整页失灵）。
document.addEventListener('click', async function (e) {
  var b = e.target && e.target.closest ? e.target.closest('[data-qadd]') : null;
  if (!b) return;
  e.preventDefault();
  var slug = b.getAttribute('data-qadd') || '';
  if (!slug) return;
  var old = b.textContent;
  b.disabled = true;
  b.textContent = '加入中…';
  try {
    var r = await fetch('/api/queue', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'add', slug: slug})
    });
    var d = await r.json();
    b.textContent = d && d.ok ? '已加入翻译列表' : '加入失败';
    if (!(d && d.ok)) b.disabled = false;
  } catch (err) {
    b.textContent = old;
    b.disabled = false;
  }
});

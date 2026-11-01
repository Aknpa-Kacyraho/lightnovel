// 自动把列表里缺的中文标题/简介补齐。
// 用户要求「进来了就好好翻译」：首页、书架、书库、翻译列表都要补，
// 不能因为地址栏没有 hash 就跳过（首次打开首页正是这种情况）。
(function(){
  if(window.__LN_META_AUTO__) return;
  window.__LN_META_AUTO__ = true;
  let started = false;

  async function tick(){
    let st = null;
    try{ st = await (await fetch('/api/batchstate')).json(); }catch(e){ return; }
    if(!st || !st.pending){ return; }
    if(!started){
      started = true;
      try{
        await fetch('/api/translate_batch', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({limit:40})});
      }catch(e){ started = false; return; }
    }
    let tries = 0, last = st.done;
    const poll = async function(){
      tries++;
      let s = {};
      try{ s = await (await fetch('/api/batchstate')).json(); }catch(e){}
      if(s.pending === 0){
        if(s.done > last){
          try{ sessionStorage.setItem('ln-meta-reloaded','1'); }catch(e){}
          location.reload();
        }
        return;
      }
      if(s.done > last){ last = s.done; tries = Math.max(0, tries - 6); }
      if(tries > 180){ return; }
      try{
        await fetch('/api/translate_batch', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({limit:40})});
      }catch(e){}
      setTimeout(poll, 2000);
    };
    setTimeout(poll, 2000);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', tick, {once:true});
  }else{
    tick();
  }
})();

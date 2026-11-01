function qApi(payload){
  return fetch('/api/queue',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)}).then(r=>r.json());
}
function qEsc(s){
  return String(s==null?'':s).replace(/[&<>"]/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
}
document.addEventListener('click',async ev=>{
  const b=ev.target.closest?ev.target.closest('button[data-q]'):null;
  if(!b) return;
  const row=b.closest('.qrow'); if(!row) return;
  await qApi({action:b.dataset.q,slug:row.dataset.slug});
  location.reload();
});
document.addEventListener('click',async ev=>{
  const b=ev.target.closest?ev.target.closest('button[data-qadd]'):null;
  if(!b) return;
  b.disabled=true;
  await qApi({action:'add',slug:b.dataset.qadd});
  location.reload();
});
const qToggle=document.getElementById('q-toggle');
if(qToggle){
  qToggle.onclick=async()=>{
    await qApi({action:'pause_all',paused:qToggle.dataset.paused!=='1'});
    location.reload();
  };
}
const qBudget=document.getElementById('q-budget');
function qBump(extra){
  const cur=parseInt((qBudget&&qBudget.value)||'0',10)||0;
  return qApi({action:'budget',tokens:cur+extra}).then(()=>location.reload());
}
['q-add5','q-add10'].forEach(id=>{
  const b=document.getElementById(id);
  if(b) b.onclick=()=>qBump(id==='q-add5'?50000:100000);
});
if(qBudget){
  qBudget.onchange=async e=>{
    await qApi({action:'budget',tokens:parseInt(e.target.value||'0',10)});
    location.reload();
  };
}
const qIdle=document.getElementById('q-idle');
if(qIdle){
  qIdle.onchange=async e=>{
    await qApi({action:'idle',minutes:parseInt(e.target.value||'30',10)});
    location.reload();
  };
}
let qCands=[];
function qRender(text){
  const box=document.getElementById('q-cands'); if(!box) return;
  const q=String(text||'').trim();
  const hits=qCands.filter(c=>!q||(c.title||'').includes(q)).slice(0,8);
  box.innerHTML=hits.map(c=>'<li class="qrow"><div class="qmain">'+qEsc(c.title)+
    '<span class="qwhy">已译 '+c.have+'/'+c.total+'</span></div>'+
    '<div class="qops"><button data-qadd="'+qEsc(c.slug)+'">加入列表</button></div></li>').join('');
}
function qAdd(slug){
  return qApi({action:'add',slug:slug||''}).then(()=>location.reload());
}
const qAddInput=document.getElementById('q-add');
if(qAddInput) qAddInput.oninput=e=>qRender(e.target.value);
const qAddBtn=document.getElementById('q-add-btn');
if(qAddBtn) qAddBtn.onclick=()=>{
  const q=String((qAddInput&&qAddInput.value)||'').trim();
  const hit=qCands.filter(c=>!q||(c.title||'').includes(q))[0];
  if(hit) qAdd(hit.slug); else qRender(q);
};
fetch('/api/library').then(r=>r.json()).then(d=>{
  qCands=(d.items||[]).map(x=>({slug:x.slug,title:x.title,
    have:x.translated,total:x.total}));
  qRender('');
}).catch(()=>{});

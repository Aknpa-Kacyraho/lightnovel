
document.querySelectorAll('button[data-dislike]').forEach(function(b){
  b.onclick = function(ev){
    ev.stopPropagation();
    var card = b.closest('.card');
    if(card && card.querySelector('.dlmenu')) return;
    var m = document.createElement('div');
    m.className = 'dlmenu';
    // 菜单自己吞掉点击，否则冒泡到卡片 onclick 会跳进阅读页
    m.onclick = function(e){ e.stopPropagation(); };
    m.innerHTML = '<span>请选择原因</span>'
      + '<button data-r="meh">不感兴趣</button>'
      + '<button data-r="theme">不喜欢该题材</button>'
      + '<button data-r="cliche">套路化严重</button>'
      + '<button data-cancel="1">取消</button>';
    b.parentNode.appendChild(m);
    m.querySelectorAll('button').forEach(function(x){
      x.onclick = async function(e2){
        e2.stopPropagation();
        if(x.dataset.cancel){ m.remove(); return; }
        m.innerHTML = '<span>已记录，正在更新偏好…</span>';
        var d = {};
        try{
          d = await (await fetch('/api/dislike', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({id:b.dataset.dislike, reason:x.dataset.r})}
          )).json();
        }catch(e){}
        if(card){
          card.style.transition = 'opacity .25s';
          card.style.opacity = '0';
          setTimeout(function(){ card.remove(); }, 250);
        }
      };
    });
  };
});

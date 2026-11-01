(function () {
  var stage = document.querySelector('[data-preview-stage]');
  if (!stage) return;

  function pick(attr, key) {
    var nodes = document.querySelectorAll('[' + attr + ']');
    for (var i = 0; i < nodes.length; i++) {
      (function (node) {
        node.addEventListener('click', function () {
          for (var j = 0; j < nodes.length; j++) nodes[j].classList.remove('on');
          node.classList.add('on');
          stage.setAttribute(key, node.getAttribute(attr));
        });
      })(nodes[i]);
    }
  }

  pick('data-ui-theme', 'data-theme');
  pick('data-reading-theme', 'data-reading-theme');
  pick('data-reading-size', 'data-reading-size');
  pick('data-viewport', 'data-viewport');
})();

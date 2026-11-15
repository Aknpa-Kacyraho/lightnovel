'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(
  path.join(__dirname, 'static', 'lnui-import.js'), 'utf8');

function element(id) {
  return {
    id,
    textContent: '',
    innerHTML: '',
    value: '',
    hidden: false,
    disabled: false,
    files: [],
    style: {},
    classList: { toggle() {} },
  };
}

const ids = [
  'imp-file', 'imp-title', 'imp-author', 'imp-go', 'imp-retry',
  'imp-status', 'imp-progress', 'imp-fill', 'imp-pct', 'imp-step',
];
const elements = Object.fromEntries(ids.map((id) => [id, element(id)]));
elements['imp-progress'].hidden = true;
elements['imp-file'].files = [{ name: 'empty.txt' }];

function FakeXhr() {
  this.upload = {};
  this.status = 0;
  this.responseText = '';
}
FakeXhr.prototype.open = function () {};
FakeXhr.prototype.setRequestHeader = function () {};
FakeXhr.prototype.send = function () {
  this.status = 400;
  this.responseText = JSON.stringify({
    ok: false,
    error: '没有收到文件',
  });
  this.onload();
};

vm.runInNewContext(source, {
  document: {
    querySelector(selector) {
      return selector === '[data-ui-import]' ? {} : null;
    },
    getElementById(id) {
      return elements[id] || null;
    },
  },
  localStorage: {
    getItem() { return ''; },
    setItem() {},
    removeItem() {},
  },
  XMLHttpRequest: FakeXhr,
  fetch() {
    throw new Error('HTTP rejection should not start polling');
  },
  setTimeout() { return 1; },
  clearTimeout() {},
  console,
}, { filename: 'lnui-import.js' });

elements['imp-go'].onclick();

const errors = [];
if (!elements['imp-status'].textContent.includes('导入失败')) {
  errors.push('failure status was not shown');
}
if (!elements['imp-progress'].hidden) {
  errors.push('progress UI remained visible after HTTP rejection');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }));
  process.exit(1);
}
console.log(JSON.stringify({ ok: true }));

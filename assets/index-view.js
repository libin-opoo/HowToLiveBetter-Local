/* ============================================================
   条目索引界面（index-view.js）
   ------------------------------------------------------------
   为什么需要它：
     正文里有 600 多处交叉引用（「见第 4 条」「见第 13 节第 1 条」），
     但主列表是按证据等级 A→C 排的，章节和编号被打散——
     第 7 节的 22 条能散落到列表第 107 位和第 620 位，隔着 510 条，
     用户看到「第 4 条」根本找不到。

   这个模块另起一个全屏界面，按「章节号 → 条目号」的书序浏览，
   编号醒目、可以直接输 7-4 定位。**完全不碰主列表和它的排序。**

   解耦做法：
     - 数据只用主逻辑已经暴露的公开接口 window.__htlb.exportText()
       （它返回「当前正在使用的数据」，导入过的数据也能反映出来），
       拿不到时退回读页面里的 #dataset 数据块；两个都拿不到就显示空状态。
     - 入口按钮由本模块自己创建、追加到页脚工具栏，不改模板 HTML。
     - 移除本文件（或从 assets/ 移走）后页面回到原样，无需改任何现有代码。
   ============================================================ */
(function () {
  'use strict';

  if (window.HTLBIndexView) { return; }

  var RENDER_DEBOUNCE = 100;

  var panel = null;
  var bodyEl = null;
  var inputEl = null;
  var hintCountEl = null;
  var sections = [];        /* 分组后的书序数据 */
  var opened = false;
  var renderTimer = null;

  /* ============================================================
     一、取数据
     ============================================================ */
  function loadRows() {
    /* 首选：主逻辑暴露的公开接口，返回当前正在使用的数据 */
    try {
      if (window.__htlb && typeof window.__htlb.exportText === 'function') {
        var t = window.__htlb.exportText();
        if (t) { return JSON.parse(t); }
      }
    } catch (e) { /* 落到下一档 */ }

    /* 退路：直接读页面内嵌的数据块（公开 DOM） */
    try {
      var el = document.getElementById('dataset');
      if (el && el.textContent) { return JSON.parse(el.textContent); }
    } catch (e2) { /* 落到空状态 */ }

    return [];
  }

  /* 把记录按章节分组，章节按节号升序、节内按条目号升序 —— 也就是原书的顺序 */
  function buildIndex(rows) {
    var map = {};
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i];
      var m = /^(\d+)-(\d+)$/.exec(String(r['条目编号'] || ''));
      var sno = m ? parseInt(m[1], 10) : 999999;
      var ino = m ? parseInt(m[2], 10) : i;
      if (!map[sno]) { map[sno] = { no: sno, title: r['所属主题'] || '', items: [] }; }
      if (!map[sno].title && r['所属主题']) { map[sno].title = r['所属主题']; }
      map[sno].items.push({ ino: ino, id: String(r['条目编号'] || ''), r: r });
    }
    var list = [];
    for (var k in map) {
      if (Object.prototype.hasOwnProperty.call(map, k)) { list.push(map[k]); }
    }
    list.sort(function (a, b) { return a.no - b.no; });
    for (var j = 0; j < list.length; j++) {
      list[j].items.sort(function (a, b) { return a.ino - b.ino; });
    }
    return list;
  }

  /* ============================================================
     二、筛选：支持输编号，也支持关键词
     ============================================================ */
  function filterSections(all, kw) {
    if (!kw) { return all; }

    /* 纯编号：7 → 整个第 7 节；7-4 / 7 4 / 7–4 → 精确定位一条 */
    var num = /^(\d+)(?:\s*[-–—.、\s]\s*(\d+))?$/.exec(kw);
    if (num) {
      var sno = parseInt(num[1], 10);
      var want = num[2] ? parseInt(num[2], 10) : null;
      var out = [];
      for (var i = 0; i < all.length; i++) {
        if (all[i].no !== sno) { continue; }
        if (want === null) {
          out.push(all[i]);
        } else {
          var items = all[i].items.filter(function (it) { return it.ino === want; });
          if (items.length) { out.push({ no: all[i].no, title: all[i].title, items: items }); }
        }
      }
      return out;
    }

    /* 关键词：标题 / 内容 / 备注 / 编号 */
    var q = kw.toLowerCase();
    var res = [];
    for (var s = 0; s < all.length; s++) {
      var keep = [];
      for (var t = 0; t < all[s].items.length; t++) {
        var r = all[s].items[t].r;
        var hay = [r['标题'], r['内容'], r['备注'], all[s].items[t].id]
          .join('\n').toLowerCase();
        if (hay.indexOf(q) !== -1) { keep.push(all[s].items[t]); }
      }
      if (keep.length) { res.push({ no: all[s].no, title: all[s].title, items: keep }); }
    }
    return res;
  }

  /* ============================================================
     三、渲染
     ============================================================ */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  /* 命中关键词高亮，只用 DOM 节点拼，不走 innerHTML */
  function fillHighlighted(node, text, kw) {
    text = text || '';
    if (!kw) { node.textContent = text; return; }
    var lower = text.toLowerCase(), q = kw.toLowerCase(), idx = lower.indexOf(q);
    if (idx === -1) { node.textContent = text; return; }
    if (idx > 0) { node.appendChild(document.createTextNode(text.slice(0, idx))); }
    var mk = el('span', 'iv-mark', text.slice(idx, idx + q.length));
    node.appendChild(mk);
    if (idx + q.length < text.length) {
      node.appendChild(document.createTextNode(text.slice(idx + q.length)));
    }
  }

  function buildDetail(item) {
    var r = item.r;
    var wrap = el('div', 'iv-detail');
    var dl = el('dl');
    var fields = [['内容', r['内容'], ''], ['成本', r['成本'], ''], ['收益', r['收益'], ''],
                  ['备注', r['备注'], ''], ['来源出处', r['来源出处'], 'iv-src']];
    for (var i = 0; i < fields.length; i++) {
      if (!fields[i][1]) { continue; }
      dl.appendChild(el('dt', '', fields[i][0]));
      dl.appendChild(el('dd', fields[i][2], fields[i][1]));
    }
    wrap.appendChild(dl);
    return wrap;
  }

  function buildItem(item, kw) {
    var row = el('div', 'iv-item');
    row.setAttribute('role', 'button');
    row.setAttribute('tabindex', '0');
    row.dataset.id = item.id;

    /* 编号是这一屏的主角 */
    row.appendChild(el('span', 'iv-no', item.id));

    var title = el('span', 'iv-t');
    fillHighlighted(title, item.r['标题'], /^\d/.test(kw || '') ? '' : kw);
    row.appendChild(title);

    var lv = String(item.r['证据等级'] || 'C');
    row.appendChild(el('span', 'iv-ev iv-ev-' + lv.charAt(0).toUpperCase(), lv));

    var detail = buildDetail(item);
    row.appendChild(detail);

    function toggle() {
      var open = row.classList.contains('iv-open');
      row.classList.toggle('iv-open', !open);
    }
    row.addEventListener('click', function (e) {
      if (e.target.closest('.iv-detail')) { return; }   /* 详情里允许选中文字 */
      toggle();
    });
    row.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        toggle();
      }
    });
    return row;
  }

  function render() {
    if (!bodyEl) { return; }
    var kw = (inputEl.value || '').trim();
    var shown = filterSections(sections, kw);

    var frag = document.createDocumentFragment();
    var total = 0;
    for (var i = 0; i < shown.length; i++) {
      var sec = shown[i];
      var box = el('section', 'iv-sec');
      var head = el('h2', 'iv-sec-head');
      head.appendChild(el('span', 'iv-sec-title', '第 ' + sec.no + ' 节 · ' + (sec.title || '')));
      head.appendChild(el('span', 'iv-sec-count', sec.items.length + ' 条'));
      box.appendChild(head);
      for (var j = 0; j < sec.items.length; j++) {
        box.appendChild(buildItem(sec.items[j], numSearch(kw) ? '' : kw));
        total++;
      }
      frag.appendChild(box);
    }

    bodyEl.textContent = '';

    /* 顶部提示：这一屏是干什么的、怎么用 */
    var hint = el('p', 'iv-hint');
    hint.appendChild(document.createTextNode('正文里的引用就长这样：'));
    hint.appendChild(el('code', '', '第 4 条'));
    hint.appendChild(document.createTextNode('　'));
    hint.appendChild(el('code', '', '第 13 节第 1 条'));
    hint.appendChild(document.createTextNode(
      '。这里按原书顺序（章节号 → 条目号）排列，编号在左边，' +
      '直接在上面输编号就能定位，比如 '));
    hint.appendChild(el('code', '', '7-4'));
    hint.appendChild(document.createTextNode(' 或 '));
    hint.appendChild(el('code', '', '13'));
    hint.appendChild(document.createTextNode('。点条目可以展开看全文。'));
    bodyEl.appendChild(hint);

    if (!total) {
      bodyEl.appendChild(el('p', 'iv-empty',
        '没有匹配的条目。输编号（如 7-4）试试，或者换个关键词。'));
    } else {
      bodyEl.appendChild(frag);
    }

    if (hintCountEl) {
      hintCountEl.textContent = kw
        ? ('筛选出 ' + total + ' 条 / 共 ' + countAll() + ' 条')
        : ('共 ' + total + ' 条，分 ' + shown.length + ' 节');
    }
  }

  function numSearch(kw) { return /^\d/.test(kw || ''); }

  function countAll() {
    var n = 0;
    for (var i = 0; i < sections.length; i++) { n += sections[i].items.length; }
    return n;
  }

  function scheduleRender() {
    clearTimeout(renderTimer);
    renderTimer = setTimeout(render, RENDER_DEBOUNCE);
  }

  /* ============================================================
     四、面板的建与开关
     ============================================================ */
  function ensurePanel() {
    if (panel && panel.isConnected) { return; }

    panel = el('div', 'iv-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', '条目索引');

    var head = el('div', 'iv-head');
    var row = el('div', 'iv-head-row');
    var txt = el('div', 'iv-head-text');
    txt.appendChild(el('h2', 'iv-title', '条目索引 · 按书序查条目'));
    hintCountEl = el('p', 'iv-sub', '');
    txt.appendChild(hintCountEl);
    row.appendChild(txt);

    var closeBtn = el('button', 'iv-close', '关闭');
    closeBtn.type = 'button';
    closeBtn.addEventListener('click', close);
    row.appendChild(closeBtn);
    head.appendChild(row);

    var tools = el('div', 'iv-tools');
    inputEl = el('input', 'iv-input');
    inputEl.type = 'search';
    inputEl.setAttribute('placeholder', '输编号（7-4）或关键词，比如 救助站');
    inputEl.setAttribute('aria-label', '按编号或关键词查找条目');
    inputEl.addEventListener('input', scheduleRender);
    tools.appendChild(inputEl);
    head.appendChild(tools);

    panel.appendChild(head);

    bodyEl = el('div', 'iv-body');
    panel.appendChild(bodyEl);

    document.body.appendChild(panel);
  }

  function open() {
    ensurePanel();
    sections = buildIndex(loadRows());
    opened = true;
    panel.classList.add('iv-show');
    document.body.classList.add('iv-locked');
    try { inputEl.value = ''; } catch (e) { /* 忽略 */ }
    render();
    try { inputEl.focus(); } catch (e) { /* 忽略 */ }
  }

  function close() {
    if (!panel) { return; }
    opened = false;
    panel.classList.remove('iv-show');
    document.body.classList.remove('iv-locked');
  }

  function isOpen() { return opened; }

  /* ============================================================
     五、入口按钮：追加到现有页脚工具栏，不改模板
     ============================================================ */
  function mountEntry() {
    var toolbar = document.querySelector('.io');
    if (!toolbar) { return; }
    if (document.getElementById('iv-open-btn')) { return; }

    var btn = el('button', 'btn iv-entry', '条目索引');
    btn.type = 'button';
    btn.id = 'iv-open-btn';
    btn.title = '按章节和条目编号浏览（正文里的「见第 N 条」在这里找）';
    btn.addEventListener('click', open);
    toolbar.appendChild(btn);
  }

  /* Esc 关闭：只在面板打开时拦截，不影响页面原有的 Esc 行为 */
  document.addEventListener('keydown', function (e) {
    if (!opened) { return; }
    if (e.key === 'Escape' || e.key === 'Esc') {
      e.preventDefault();
      e.stopPropagation();
      close();
    }
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountEntry);
  } else {
    mountEntry();
  }

  /* ============================================================
     六、对外只暴露调试/测试接口，不参与业务
     ============================================================ */
  window.HTLBIndexView = {
    version: '1.0.0',
    open: open,
    close: close,
    isOpen: isOpen,
    loadRows: loadRows,
    buildIndex: buildIndex,
    entryMounted: function () { return !!document.getElementById('iv-open-btn'); },
    /* 测试辅助 */
    _query: function (q) { inputEl.value = q; render(); },
    _sections: function () { return document.querySelectorAll('.iv-sec').length; },
    _items: function () { return document.querySelectorAll('.iv-item').length; },
    _ids: function () {
      return Array.prototype.map.call(document.querySelectorAll('.iv-item'), function (n) {
        return n.querySelector('.iv-no').textContent;
      });
    },
    _titleOf: function (id) {
      var rows = document.querySelectorAll('.iv-item');
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].dataset.id === id) { return rows[i].querySelector('.iv-t').textContent; }
      }
      return null;
    },
    _clickItem: function (id) {
      var rows = document.querySelectorAll('.iv-item');
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].dataset.id === id) {
          rows[i].click();
          return rows[i].classList.contains('iv-open');
        }
      }
      return null;
    },
    _detailOpen: function (id) {
      var rows = document.querySelectorAll('.iv-item');
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].dataset.id === id) {
          var d = rows[i].querySelector('.iv-detail');
          return d ? window.getComputedStyle(d).display !== 'none' : false;
        }
      }
      return null;
    }
  };
})();

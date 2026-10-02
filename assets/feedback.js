/* ============================================================
   操作反馈模块（feedback.js）
   ------------------------------------------------------------
   设计原则：与主逻辑完全解耦。
   - 不读取、不修改页面里的任何内部变量（DATA / state / setMsg 等）
   - 只通过公开的 DOM 接口工作：#io-msg、#file-input、按钮元素
   - 移除本文件后，页面立刻回到原来的行为，无需改回任何代码

   它做四件事：
   1. 监听 #io-msg 的变化 → 弹轻量提示（成功/失败），并把页脚文案换成人话
   2. 失败提示统一给出「错误原因 + 简易解决建议」，不裸露原始报错
   3. 导入这类耗时操作给出加载状态（顶部进度条 + 按钮转圈）
   4. 按钮点击给出轻量按压反馈
   ============================================================ */
(function () {
  'use strict';

  if (window.HTLBFeedback) { return; }   /* 防重复注入 */

  var TOAST_LIMIT = 3;       /* 同时最多留几条，超出就顶掉最旧的 */
  var BUSY_TIMEOUT = 30000;  /* 加载状态的兜底超时：30 秒还没结果就自动收起 */
  var AUTO_CLOSE = { success: 4500, info: 6000, error: 9000 };

  /* ============================================================
     一、把原始报错翻译成「人话 + 建议」
     规则按最具体到最宽泛排列；认不出来的一律走兜底分支，
     保证任何情况下都有原因和建议，不会只丢一句原始报错。
     ============================================================ */
  function stripPrefix(t) {
    return String(t || '').replace(/^导入失败[：:]/, '').trim();
  }

  function friendly(rawText) {
    var raw = String(rawText || '').trim();
    var t = stripPrefix(raw);
    var m;

    /* ---- 导入类报错 ---- */
    if (/^不是合法的 JSON/.test(t)) {
      return { kind: 'error', title: '这个文件不是合法的 JSON',
               reason: '文件内容不是有效的 JSON 格式，程序解析不了。',
               advice: '用记事本或 VS Code 打开它，重点看：有没有多余的逗号、少写引号或括号。也可以先点「导出数据」生成一份格式正确的文件，照着改。',
               raw: raw };
    }
    if (/^JSON 顶层必须是数组/.test(t)) {
      return { kind: 'error', title: '文件最外层必须是数组',
               reason: '整个文件要用一对方括号包起来，现在不是。',
               advice: '把内容改成 [ { … }, { … } ] 这种形式。直接点「导出数据」拿到的文件就是这个格式。',
               raw: raw };
    }
    if (/^数组是空的/.test(t)) {
      return { kind: 'error', title: '文件里一条数据都没有',
               reason: '数组是空的，没有可以导入的内容。',
               advice: '换一个含内容的文件；或者先确认一下原来导出的时候数据是否正常。',
               raw: raw };
    }
    if ((m = t.match(/^第 (\d+) 条不是对象/))) {
      return { kind: 'error', title: '第 ' + m[1] + ' 条格式不对',
               reason: '第 ' + m[1] + ' 条不是「对象」，程序读不出字段。',
               advice: '每一条都要用一对花括号包起来，写成 { "标题": "…", "内容": "…" } 这样。检查第 ' + m[1] + ' 条是不是写成了数字或纯文字。',
               raw: raw };
    }
    if ((m = t.match(/^第 (\d+) 条缺少字段「(.+?)」/))) {
      return { kind: 'error', title: '第 ' + m[1] + ' 条缺了一个字段',
               reason: '第 ' + m[1] + ' 条的「' + m[2] + '」是空的或者根本没写。',
               advice: '7 个字段一个都不能少、也不能是空字符串：标题、内容、所属主题、成本、收益、证据等级、来源出处。补上再导入。',
               raw: raw };
    }
    if ((m = t.match(/^第 (\d+) 条「证据等级」/))) {
      return { kind: 'error', title: '第 ' + m[1] + ' 条的证据等级不对',
               reason: '「证据等级」必须以 A、B 或 C 开头。',
               advice: '把它改成 A、B、C 三者之一，例如 "A"，或者像原数据那样写成 "B（指南强推荐）"。',
               raw: raw };
    }
    if (/^读不到文件内容/.test(t)) {
      return { kind: 'error', title: '读不到这个文件',
               reason: '文件可能正被别的程序占用，或者已经损坏。',
               advice: '先关掉可能占用它的程序（Excel、编辑器等）再试一次；还不行就换一个文件。',
               raw: raw };
    }

    /* ---- 成功 / 进行中提示 ---- */
    if (/^已导出 /.test(t)) {
      return { kind: 'success', title: '导出完成',
               reason: '', advice: t + '。文件在浏览器的「下载」目录里，可以直接用它覆盖项目里的 data.json。',
               raw: '' };
    }
    if (/^已导入 /.test(t)) {
      return { kind: 'success', title: '导入完成', reason: '', advice: t, raw: '' };
    }
    if (/^已恢复内置数据/.test(t)) {
      return { kind: 'success', title: '已恢复内置数据',
               reason: '', advice: '页面回到随项目一起发布的原始数据。本浏览器里保存的导入内容已清除。',
               raw: '' };
    }
    if (/^正在使用本机导入的数据/.test(t)) {
      return { kind: 'info', title: '正在使用本机导入的数据',
               reason: '', advice: t + '。想回到原始数据，点页面底部的「恢复内置数据」。',
               raw: '' };
    }

    /* ---- 兜底：不认识的提示，原样保留但补上建议 ---- */
    return { kind: 'info', title: '操作提示',
             reason: raw.slice(0, 120),
             advice: '如果不是你预期的结果，可以用页面底部的「导出数据」先备份当前数据，再点「恢复内置数据」回到原始状态。',
             raw: raw.length > 120 ? raw : '' };
  }

  /* ============================================================
     二、Toast 渲染
     ============================================================ */
  var host = null;

  function ensureHost() {
    if (host && host.isConnected) { return host; }
    host = document.createElement('div');
    host.className = 'fb-toasts';
    host.setAttribute('role', 'status');
    host.setAttribute('aria-live', 'polite');
    document.body.appendChild(host);
    return host;
  }

  function dismiss(el) {
    if (!el || el.dataset.fbLeaving === '1') { return; }
    el.dataset.fbLeaving = '1';
    el.classList.add('fb-leaving');
    setTimeout(function () { if (el.parentNode) { el.parentNode.removeChild(el); } }, 200);
  }

  function dismissAll() {
    var list = document.querySelectorAll('.fb-toast');
    for (var i = 0; i < list.length; i++) { dismiss(list[i]); }
  }

  function showToast(info) {
    var h = ensureHost();
    var kind = info.kind || 'info';

    /* 超出上限就顶掉最早的一条 */
    var existing = h.querySelectorAll('.fb-toast');
    while (existing.length >= TOAST_LIMIT) {
      h.removeChild(existing[0]);
      existing = h.querySelectorAll('.fb-toast');
    }

    var box = document.createElement('div');
    box.className = 'fb-toast fb-' + kind;

    /* 图标：用文字符号，不引入任何图片资源 */
    var icon = document.createElement('span');
    icon.className = 'fb-icon';
    icon.textContent = kind === 'error' ? '!' : (kind === 'success' ? '\u2713' : 'i');
    icon.setAttribute('aria-hidden', 'true');
    box.appendChild(icon);

    var body = document.createElement('div');
    body.className = 'fb-body';

    var title = document.createElement('div');
    title.className = 'fb-title';
    title.textContent = info.title || '';
    body.appendChild(title);

    if (info.reason) {
      var r = document.createElement('p');
      r.className = 'fb-line';
      var rb = document.createElement('b');
      rb.textContent = '原因：';
      r.appendChild(rb);
      r.appendChild(document.createTextNode(info.reason));
      body.appendChild(r);
    }
    if (info.advice) {
      var a = document.createElement('p');
      a.className = 'fb-line';
      var ab = document.createElement('b');
      ab.textContent = '建议：';
      a.appendChild(ab);
      a.appendChild(document.createTextNode(info.advice));
      body.appendChild(a);
    }

    /* 原始报错不裸露在正面，收进可展开的「技术细节」 */
    if (info.raw) {
      var pre = document.createElement('p');
      pre.className = 'fb-raw';
      pre.textContent = info.raw;
      body.appendChild(pre);

      var tg = document.createElement('button');
      tg.type = 'button';
      tg.className = 'fb-toggle';
      tg.textContent = '查看技术细节';
      tg.addEventListener('click', function () {
        var open = pre.classList.toggle('fb-open');
        tg.textContent = open ? '收起技术细节' : '查看技术细节';
      });
      body.appendChild(tg);
    }
    box.appendChild(body);

    var close = document.createElement('button');
    close.type = 'button';
    close.className = 'fb-close';
    close.setAttribute('aria-label', '关闭提示');
    close.textContent = '\u00d7';
    close.addEventListener('click', function () { dismiss(box); });
    box.appendChild(close);

    h.appendChild(box);

    var ms = AUTO_CLOSE[kind] || 6000;
    setTimeout(function () { dismiss(box); }, ms);
    return box;
  }

  /* ============================================================
     三、加载状态（耗时操作）
     ============================================================ */
  var busyTimer = null;

  function startBusy(btn) {
    document.body.classList.add('fb-busy');
    if (btn) {
      btn.classList.add('fb-pending');
      btn.setAttribute('aria-busy', 'true');
    }
    clearTimeout(busyTimer);
    /* 兜底：万一原流程没有回写提示，也不能让页面一直转圈 */
    busyTimer = setTimeout(endBusy, BUSY_TIMEOUT);
  }

  function endBusy() {
    document.body.classList.remove('fb-busy');
    var pend = document.querySelectorAll('.fb-pending');
    for (var i = 0; i < pend.length; i++) {
      pend[i].classList.remove('fb-pending');
      pend[i].removeAttribute('aria-busy');
    }
    clearTimeout(busyTimer);
  }

  /* ============================================================
     四、接线
     ============================================================ */
  var lastHandled = '';   /* 上一次处理过的页脚原文，避免重复弹同一条 */
  var selfWritten = '';   /* 自己写回页脚的文本，用于识别、防止死循环 */

  function onMsgChange() {
    var msgEl = document.getElementById('io-msg');
    if (!msgEl) { return; }
    var raw = (msgEl.textContent || '').trim();

    if (raw === selfWritten) { return; }     /* 是我自己写回去的，忽略 */
    if (raw === lastHandled) { return; }     /* 已经处理过 */
    if (!raw) { lastHandled = ''; return; }  /* 被清空，不是一次新的操作 */
    lastHandled = raw;

    var f = friendly(raw);
    showToast(f);
    endBusy();

    /* 方案 B：把页脚也换成人话；原来的报错降级到 toast 的「技术细节」。
       注意 setMsg 本身一行没动，这里只是改写它写下的文本。 */
    var summary = f.title + (f.advice ? '　' + f.advice : '');
    selfWritten = summary;
    msgEl.textContent = summary;
  }

  function wire() {
    /* 1) 监听页脚提示的变化（只读观察 + 改写文案，不碰原函数） */
    var msgEl = document.getElementById('io-msg');
    if (msgEl && window.MutationObserver) {
      new MutationObserver(onMsgChange).observe(msgEl, {
        childList: true, characterData: true, subtree: true
      });
    }

    /* 2) 导入：捕获阶段先挂上加载状态，保证在原逻辑跑之前就显示出来 */
    var fileEl = document.getElementById('file-input');
    if (fileEl) {
      fileEl.addEventListener('change', function () {
        if (fileEl.files && fileEl.files[0]) {
          lastHandled = '';   /* 新一轮操作，允许弹出与上次相同的提示 */
          startBusy(document.getElementById('import-btn'));
        }
      }, true);
    }

    /* 3) 所有按钮点击的轻量按压反馈（纯视觉，不影响任何行为） */
    document.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || !t.closest) { return; }
      var btn = t.closest('button, .btn, .chip');
      if (!btn) { return; }
      btn.classList.remove('fb-pulse');
      void btn.offsetWidth;              /* 强制重排，连续点击也能重播动画 */
      btn.classList.add('fb-pulse');
      setTimeout(function () { btn.classList.remove('fb-pulse'); }, 300);
    }, true);

    /* 4) 导出是同步操作，点下去先给个「进行中」，成功提示会立刻把它收掉 */
    var exportBtn = document.getElementById('export-btn');
    if (exportBtn) {
      exportBtn.addEventListener('click', function () {
        lastHandled = '';
      }, true);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }

  /* ============================================================
     五、对外只暴露一个只读的调试/测试接口，不参与业务
     ============================================================ */
  window.HTLBFeedback = {
    version: '1.0.0',
    friendly: friendly,
    toast: function (kind, title, reason, advice, raw) {
      return showToast({ kind: kind, title: title, reason: reason, advice: advice, raw: raw });
    },
    dismissAll: dismissAll,
    isBusy: function () { return document.body.classList.contains('fb-busy'); },
    count: function () { return document.querySelectorAll('.fb-toast').length; },
    texts: function () {
      return Array.prototype.map.call(document.querySelectorAll('.fb-toast'), function (n) {
        return n.textContent;
      });
    }
  };
})();

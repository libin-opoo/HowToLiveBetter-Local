#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 index.html 的本地数据导入 / 导出功能，确保数据不丢失。

在无头浏览器里加载 index.html，用真实事件驱动按钮和文件输入，逐项断言：
  - 导出内容必须与磁盘上的 data.json 逐字符一致
  - 导入合法文件后数据被替换，且能导出回来
  - 各类非法文件都会被拦下并报错，且不会破坏当前数据
  - 导入的数据在刷新后仍在（localStorage），「恢复内置数据」能还原

用法:
    python3 tools/check_io.py
    python3 tools/check_io.py --browser "/path/to/msedge"
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

PROBE = r"""
<script>
var out = [];
function check(name, cond, detail) {
  out.push({ name: name, pass: !!cond, detail: detail == null ? '' : String(detail) });
}
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function report(text) {
  var d = document.createElement('div');
  d.id = '__report';
  d.textContent = 'REPORT:' + btoa(unescape(encodeURIComponent(JSON.stringify(text || '')))) +
                  '|' + btoa(unescape(encodeURIComponent(JSON.stringify(out))));
  document.body.appendChild(d);
}
var f = document.getElementById('f');

function getDoc() { try { return f.contentDocument; } catch (e) { return null; } }
async function waitCards(doc, min) {
  for (var i = 0; i < 300; i++) {
    doc = getDoc();
    if (doc && doc.querySelectorAll('.card').length >= min) { return doc; }
    await sleep(50);
  }
  return getDoc();
}

/* 导出与真实点击走同一条代码路径。这里拦下 createObjectURL 取 Blob，
   同时把 anchor.click 换成记录，避免无头模式下真的触发下载而卡住浏览器。 */
function captureExport(win, doc) {
  return new Promise(function (resolve) {
    var origCreate = win.URL.createObjectURL;
    var origClick = win.HTMLAnchorElement.prototype.click;
    var captured = null, anchor = null;
    win.URL.createObjectURL = function (blob) { captured = blob; return origCreate.call(win.URL, blob); };
    win.HTMLAnchorElement.prototype.click = function () { anchor = this; };
    try { doc.getElementById('export-btn').click(); }
    finally {
      win.URL.createObjectURL = origCreate;
      win.HTMLAnchorElement.prototype.click = origClick;
    }
    if (!captured) { resolve({ text: null, anchor: null }); return; }
    captured.text().then(function (t) {
      resolve({
        text: t,
        download: anchor ? anchor.getAttribute('download') : null,
        href: anchor ? String(anchor.getAttribute('href') || '') : null,
        type: captured.type
      });
    }, function () { resolve({ text: null, anchor: null }); });
  });
}

function makeFile(win, text, name) {
  return new win.File([text], name || 'data.json', { type: 'application/json' });
}

async function waitUntil(fn, tries) {
  for (var i = 0; i < (tries || 200); i++) {
    if (fn()) { return true; }
    await sleep(50);
  }
  return false;
}

/* FileReader 是异步的，固定 sleep 会在虚拟时间下抢跑（实测会读到上一步的消息）。
   这里改成轮询等待状态栏消息真正发生变化。 */
async function feed(win, doc, text, name) {
  var msg = doc.getElementById('io-msg');
  var before = msg.textContent;
  var input = doc.getElementById('file-input');
  var dt = new win.DataTransfer();
  dt.items.add(makeFile(win, text, name));
  input.files = dt.files;
  input.dispatchEvent(new win.Event('change', { bubbles: true }));
  var changed = await waitUntil(function () { return msg.textContent !== before; });
  return changed ? msg.textContent : null;
}

(async function () {
 try {
  var doc = await waitCards(getDoc(), 650);   /* 分片渲染，要等到齐 */
  if (!doc) { check('页面可访问', false, 'iframe 读不到'); report(); return; }
  var win = f.contentWindow;
  var n0 = doc.querySelectorAll('.card').length;
  check('初始加载 650 条', n0 === 650, n0 + ' 条');

  /* ---- 1. 按钮存在 ---- */
  check('底部有「导出数据」按钮',
        doc.getElementById('export-btn').textContent.trim() === '导出数据', '');
  check('底部有「导入数据」按钮',
        doc.getElementById('import-btn').textContent.trim() === '导入数据', '');
  check('有隐藏的文件输入框',
        !!doc.getElementById('file-input') &&
        doc.getElementById('file-input').type === 'file', '');

  /* ---- 2. 导出内容与磁盘 data.json 逐字符一致 ---- */
  var expected = null;
  try { expected = await (await fetch('data.json')).text(); } catch (e) { expected = null; }
  var ex = await captureExport(win, doc);
  var exported = ex.text;
  check('导出触发并拿到数据', exported !== null, exported === null ? '未捕获到 Blob' : '');
  check('下载文件名为 data.json', ex.download === 'data.json', String(ex.download));
  check('下载内容是 Blob URL', ex.href.indexOf('blob:') === 0, ex.href.slice(0, 24));
  check('导出类型为 JSON', String(ex.type).indexOf('application/json') === 0, ex.type);
  if (expected === null) {
    check('能读到 data.json 作为基准', false, 'fetch 失败，跳过逐字符比对');
  } else if (exported !== null) {
    check('导出内容与 data.json 完全相同', exported === expected,
          exported === expected ? (exported.length + ' 字符完全一致')
                                : ('长度 ' + exported.length + ' vs ' + expected.length +
                                   '，首处差异 @' + (function () {
                                     for (var i = 0; i < Math.min(exported.length, expected.length); i++) {
                                       if (exported[i] !== expected[i]) { return i; }
                                     }
                                     return '长度不同';
                                   })()));
  }
  var exported650 = exported;

  /* ---- 3. 导入合法文件 ---- */
  var good = [
    { "标题": "测试条目一", "内容": "这是导入测试的内容。", "所属主题": "不要早死",
      "成本": "不花钱", "收益": "验证导入", "证据等级": "C", "来源出处": "本地测试" },
    { "标题": "测试条目二", "内容": "第二条测试内容。", "所属主题": "不要早死",
      "成本": "1 元", "收益": "验证排序", "证据等级": "A", "来源出处": "本地测试" }
  ];
  var goodText = JSON.stringify(good, null, 2) + '\n';
  await feed(win, doc, goodText);
  doc = getDoc();
  await waitUntil(function () { return doc.querySelectorAll('.card').length === 2; });
  var n1 = doc.querySelectorAll('.card').length;
  check('导入合法文件后数据被替换', n1 === 2, n1 + ' 条');
  check('导入后状态栏更新', doc.getElementById('status').textContent.indexOf('共 2 条') !== -1,
        doc.getElementById('status').textContent.trim());
  var ls = null;
  try { ls = win.localStorage.getItem('htlb.dataset.v1'); } catch (e) { ls = null; }
  check('导入的数据写入了 localStorage', !!ls && JSON.parse(ls).length === 2,
        ls ? '已写入 ' + ls.length + ' 字符' : '未写入');
  check('导入后出现「恢复内置数据」按钮',
        doc.getElementById('reset-btn').hidden === false, '');
  var titles2 = Array.prototype.map.call(doc.querySelectorAll('.card-title'),
                                          function (t) { return t.textContent; });
  /* 主列表默认排序已改为「书序」；这两条测试数据没有 条目编号，
     所以书序下保持原顺序。证据等级排序本身由 tools/check_search.py 覆盖。 */
  check('导入后按当前排序展示（默认书序，无编号则保持原顺序）',
        titles2[0] === '测试条目一' && titles2.length === 2, titles2.join(' / '));

  /* ---- 4. 导入后导出的是新数据 ---- */
  var exported2 = (await captureExport(win, doc)).text;
  check('导入后导出的是导入的数据', exported2 === goodText,
        exported2 === goodText ? '与导入文件一致'
                               : ('长度 ' + (exported2 ? exported2.length : 'null') + ' vs ' + goodText.length));

  /* ---- 5. 非法文件全部被拦下，且不破坏当前数据 ---- */
  var badCases = [
    ['非 JSON 文本', '这不是 JSON'],
    ['顶层不是数组', '{"标题":"x"}'],
    ['空数组', '[]'],
    ['数组元素不是对象', '[1,2,3]'],
    ['缺必填字段', JSON.stringify([{ "标题": "只有标题" }])],
    ['证据等级非法', JSON.stringify([{ "标题": "t", "内容": "c", "所属主题": "s",
                                      "成本": "0", "收益": "y", "证据等级": "Z", "来源出处": "x" }])]
  ];
  for (var i = 0; i < badCases.length; i++) {
    var name = badCases[i][0], text = badCases[i][1];
    var returned = await feed(win, doc, text, 'bad.json');
    doc = getDoc();
    var cnt = doc.querySelectorAll('.card').length;
    var msg = doc.getElementById('io-msg');
    /* 加了「操作反馈」模块后，页脚文案会从原始报错换成人话，
       所以这里判断「是否进入错误状态」，不再匹配原始报错前缀。
       提示内容是否友好由 tools/check_feedback.py 负责验证。 */
    check('拦截「' + name + '」并报错',
          returned !== null && msg.classList.contains('err') && msg.textContent.trim().length > 0,
          returned === null ? '等不到反馈（可能未触发导入）' : '"' + returned.slice(0, 60) + '"');
    check('「' + name + '」未破坏已有数据', cnt === 2, cnt + ' 条');
  }

  /* ---- 6. 重新打开页面（新开 iframe）后，导入的数据仍在 ---- */
  var f2 = document.createElement('iframe');
  f2.style.cssText = 'border:0;display:block;width:1100px;height:900px';
  f2.src = 'index.html';
  document.body.appendChild(f2);
  var doc2 = null;
  await waitUntil(function () {
    try { doc2 = f2.contentDocument; } catch (e3) { doc2 = null; }
    return doc2 && doc2.querySelectorAll('.card').length === 2;
  }, 300);
  var n2 = doc2 ? doc2.querySelectorAll('.card').length : -1;
  check('重新打开页面后仍是导入的数据', n2 === 2, n2 + ' 条');
  var modeTxt = doc2 ? doc2.getElementById('mode').textContent : '';
  check('重新打开后来源标注为本地导入', modeTxt.indexOf('导入') !== -1, modeTxt);
  f2.remove();

  /* ---- 7. 恢复内置数据 ---- */
  doc.getElementById('reset-btn').click();
  await waitUntil(function () {
    doc = getDoc();
    return doc && doc.querySelectorAll('.card').length === 650;
  }, 300);
  doc = getDoc();
  var n3 = doc.querySelectorAll('.card').length;
  check('「恢复内置数据」还原 650 条', n3 === 650, n3 + ' 条');
  var ls2 = null;
  try { ls2 = f.contentWindow.localStorage.getItem('htlb.dataset.v1'); } catch (e) { ls2 = null; }
  check('恢复后清空了 localStorage', !ls2, ls2 ? '仍有残留' : '已清空');
  var exported3 = (await captureExport(f.contentWindow, f.contentDocument)).text;
  check('恢复后导出回到原始 data.json', exported3 === exported650,
        exported3 === exported650 ? '与初始导出一致' : '不一致');

  report(expected ? String(expected.length) : '');
 } catch (err) {
  check('测试过程未抛异常', false, String(err && err.stack || err).slice(0, 200));
  report('');
 }
})();
</script>
"""

HARNESS = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>probe</title>
<style>html,body{margin:0}iframe{border:0;display:block;width:1100px;height:900px}</style>
</head><body><iframe id="f" src="index.html"></iframe>
__PROBE__
</body></html>"""

DEFAULT_BROWSERS = [
    "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Microsoft/Edge/Application/msedge.exe",
    "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def to_windows_path(p: Path) -> str:
    s = str(p)
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", s)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m else s


def find_browser(explicit):
    if explicit:
        return explicit
    for b in DEFAULT_BROWSERS:
        if Path(b).exists():
            return b
    sys.exit("找不到浏览器，请用 --browser 指定 Edge/Chrome 路径")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default=os.environ.get("LAYOUT_BROWSER"))
    ap.add_argument("--budget", type=int, default=180000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)
    is_wsl = "microsoft" in os.uname().release.lower()
    # 每次运行用独立 profile：复用同一个目录时，上一次没退干净的 Edge
    # 会锁住 profile，导致浏览器启动失败、探针偶发取不到结果。
    _tag = uuid.uuid4().hex[:8]
    _win = f"C:\\Temp\\htlb-io-{_tag}"
    _nix = f"/mnt/c/Temp/htlb-io-{_tag}"
    profile = _win if is_wsl else f"/tmp/htlb-io-{_tag}"
    profile_dir_to_clean = _nix if is_wsl else profile

    probe = root / ".io-probe.html"
    probe.write_text(HARNESS.replace("__PROBE__", PROBE), encoding="utf-8")
    url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()

    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--allow-file-access-from-files", f"--user-data-dir={profile}",
        "--window-size=1300,1000", f"--virtual-time-budget={args.budget}", "--dump-dom", url,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=200)
        dom = res.stdout.decode("utf-8", "replace")
        m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)\|([A-Za-z0-9+/=]+)<', dom)
        if not m:
            print("探针未返回结果。stderr 末尾：")
            print(res.stderr.decode("utf-8", "replace")[-1200:])
            sys.exit(1)
        results = json.loads(base64.b64decode(m.group(2)).decode("utf-8"))
    finally:
        probe.unlink(missing_ok=True)
        shutil.rmtree(profile_dir_to_clean, ignore_errors=True)

    width = max(len(r["name"]) for r in results)
    failed = 0
    print(f"{'检查项':<{width}}  结果   详情")
    print("-" * (width + 40))
    for r in results:
        if not r["pass"]:
            failed += 1
        print(f"{r['name']:<{width}}  {'✅' if r['pass'] else '❌'}    {r['detail']}")

    print()
    print(f"共 {len(results)} 项，通过 {len(results) - failed} 项，失败 {failed} 项。")
    if failed:
        sys.exit(1)
    print("导入、导出、校验、持久化、还原均正常，数据无丢失。")


if __name__ == "__main__":
    main()

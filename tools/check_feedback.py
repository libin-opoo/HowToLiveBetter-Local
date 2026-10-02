#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「操作反馈」模块的验收测试。

覆盖三类场景：
  正常：导出成功提示、导入成功提示、耗时操作的加载状态
  异常：非法输入的提示必须给出「原因 + 建议」，且不裸露原始报错
  边界：空提示不弹、同一条提示去重、提示数量上限、按压反馈

用法:
    python3 tools/check_feedback.py
    python3 tools/check_feedback.py --browser "/path/to/msedge"
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
function report() {
  var d = document.createElement('div');
  d.id = '__report';
  d.textContent = 'REPORT:' + btoa(unescape(encodeURIComponent(JSON.stringify(out))));
  document.body.appendChild(d);
}
async function waitUntil(fn, tries) {
  for (var i = 0; i < (tries || 120); i++) {
    if (fn()) { return true; }
    await sleep(40);
  }
  return false;
}
var f = document.getElementById('f');

(async function () {
 try {
  var doc, win;
  for (var i = 0; i < 300; i++) {
    try { doc = f.contentDocument; win = f.contentWindow; } catch (e) { doc = null; }
    if (doc && doc.querySelectorAll('.card').length >= 650) { break; }
    await sleep(40);
  }
  if (!doc) { check('页面可访问', false, '读不到 iframe'); report(); return; }
  check('iframe 已加载 index.html', doc.querySelectorAll('.card').length >= 650,
        'cards=' + doc.querySelectorAll('.card').length);

  /* 点「导出数据」会触发真实下载，无头浏览器会挂住不退出（上一轮就踩过）。
     这里把 anchor.click 拦成空操作：导出逻辑本身照跑，只是不真的落盘。
     真实落盘的正确性由 tools/check_io.py + CDP 单独验证。 */
  var origAnchorClick = win.HTMLAnchorElement.prototype.click;
  win.HTMLAnchorElement.prototype.click = function () { /* 拦下下载 */ };

  var FB = win.HTLBFeedback;
  var msg = doc.getElementById('io-msg');
  var toastCount = function () { return doc.querySelectorAll('.fb-toast').length; };
  var lastToast = function () {
    var all = doc.querySelectorAll('.fb-toast');
    return all.length ? all[all.length - 1] : null;
  };
  var toastText = function () {
    var t = lastToast();
    return t ? t.textContent : '';
  };
  /* toast 里图标是文本节点，所以用 .fb-title 取标题才准 */
  var toastTitle = function () {
    var t = lastToast();
    var el = t ? t.querySelector('.fb-title') : null;
    return el ? el.textContent : '';
  };
  /* 「用户看得见」的文本：要把折叠起来的技术细节排除掉 */
  var toastVisibleText = function () {
    var t = lastToast();
    if (!t) { return ''; }
    var clone = t.cloneNode(true);
    var raw = clone.querySelector('.fb-raw');
    if (raw) { raw.parentNode.removeChild(raw); }
    return clone.textContent;
  };

  /* ================= 正常场景 ================= */
  check('反馈模块已加载', !!FB && typeof FB.toast === 'function',
        FB ? ('v' + FB.version) : 'HTLBFeedback 不存在');

  FB.dismissAll();
  await sleep(250);
  doc.getElementById('export-btn').click();
  await waitUntil(function () { return toastCount() > 0; });
  var t1 = toastText();
  check('导出后弹出成功提示', toastCount() === 1 && toastTitle() === '导出完成', toastTitle());
  check('成功提示带「建议」说明', t1.indexOf('建议：') !== -1,
        t1.indexOf('建议：') !== -1 ? '已包含' : t1.slice(0, 60));
  check('导出提示不含原始报错', !/Unexpected|TypeError|undefined/.test(t1), '');

  /* 导入一个合法文件，验证成功提示 + 加载状态 */
  FB.dismissAll(); await sleep(250);
  var good = JSON.stringify([
    { "标题": "反馈测试 A", "内容": "c", "所属主题": "测试", "成本": "0",
      "收益": "y", "证据等级": "A", "来源出处": "local" }
  ], null, 2);
  var input = doc.getElementById('file-input');
  var dt = new win.DataTransfer();
  dt.items.add(new win.File([good], 'ok.json', { type: 'application/json' }));
  input.files = dt.files;
  input.dispatchEvent(new win.Event('change', { bubbles: true }));

  /* 同一轮事件里同步检查加载状态：捕获阶段要先于原逻辑挂上状态 */
  check('导入时出现加载状态', doc.body.classList.contains('fb-busy'),
        'body.fb-busy=' + doc.body.classList.contains('fb-busy'));
  check('导入按钮进入加载态', doc.getElementById('import-btn').classList.contains('fb-pending'), '');

  await waitUntil(function () { return toastCount() > 0 && !doc.body.classList.contains('fb-busy'); });
  check('导入成功弹出提示', toastTitle() === '导入完成', toastTitle());
  check('加载状态已自动收起', !doc.body.classList.contains('fb-busy'), '');
  check('导入按钮加载态已清除',
        !doc.getElementById('import-btn').classList.contains('fb-pending'), '');

  /* ================= 异常场景 ================= */
  /* 选一个格式错误的文件 */
  FB.dismissAll(); await sleep(250);
  var dt2 = new win.DataTransfer();
  dt2.items.add(new win.File(['这不是 JSON'], 'bad.json', { type: 'application/json' }));
  input.files = dt2.files;
  input.dispatchEvent(new win.Event('change', { bubbles: true }));
  await waitUntil(function () { return toastCount() > 0 && !doc.body.classList.contains('fb-busy'); });

  var bad = lastToast();
  var badText = bad ? bad.textContent : '';
  check('非法文件弹出错误提示', !!bad && bad.className.indexOf('fb-error') !== -1,
        bad ? bad.className : '没有提示');
  check('错误提示给出「原因」', badText.indexOf('原因：') !== -1, '');
  check('错误提示给出「建议」', badText.indexOf('建议：') !== -1, '');
  check('错误提示不裸露原始 JS 报错',
        !/Unexpected token|is not valid JSON|SyntaxError|TypeError/.test(toastVisibleText()),
        toastVisibleText().slice(0, 70));

  /* 原始报错要收进「技术细节」，默认不展开 */
  var rawEl = bad ? bad.querySelector('.fb-raw') : null;
  check('原始报错收进技术细节', !!rawEl && rawEl.textContent.length > 0,
        rawEl ? rawEl.textContent.slice(0, 40) : '没有 .fb-raw');
  check('技术细节默认收起', !!rawEl && !rawEl.classList.contains('fb-open'), '');
  if (bad) {
    var tg = bad.querySelector('.fb-toggle');
    check('技术细节可展开', !!tg, tg ? tg.textContent : '没有按钮');
    if (tg) {
      tg.click();
      await sleep(120);
      check('点击后技术细节展开', rawEl.classList.contains('fb-open'), '');
    }
  } else {
    check('技术细节可展开', false, '没有 toast');
    check('点击后技术细节展开', false, '没有 toast');
  }

  /* 页脚文案也要换成人话 */
  check('页脚文案已换成人话（不含原始报错）',
        msg.textContent.length > 0 &&
        !/Unexpected token|is not valid JSON|SyntaxError/.test(msg.textContent),
        msg.textContent.slice(0, 60));
  check('页脚仍然带错误样式（不影响原逻辑）', msg.classList.contains('err'), '');

  /* 缺字段的提示要能定位到第几条 */
  FB.dismissAll(); await sleep(250);
  var dt3 = new win.DataTransfer();
  dt3.items.add(new win.File([JSON.stringify([{ "标题": "只有标题" }])], 'miss.json',
                             { type: 'application/json' }));
  input.files = dt3.files;
  input.dispatchEvent(new win.Event('change', { bubbles: true }));
  await waitUntil(function () { return toastCount() > 0 && !doc.body.classList.contains('fb-busy'); });
  var missText = toastText();
  check('缺字段时能定位到第几条', /第\s*1\s*条/.test(missText), missText.slice(0, 50));
  check('缺字段时给出补全建议', missText.indexOf('建议：') !== -1 && /字段/.test(missText), '');

  /* ================= 边界场景 ================= */
  /* 页脚被清空时不应该弹提示 */
  FB.dismissAll(); await sleep(260);
  var n0 = toastCount();
  msg.textContent = '';
  await sleep(200);
  check('页脚清空时不弹提示', toastCount() === n0, n0 + ' → ' + toastCount());

  /* 同一条提示连续出现两次，只弹一次 */
  FB.dismissAll(); await sleep(260);
  msg.textContent = '导入失败：读不到文件内容';
  await waitUntil(function () { return toastCount() > 0; });
  var n1 = toastCount();
  msg.textContent = '导入失败：读不到文件内容';
  await sleep(300);
  check('同一提示重复出现只弹一次', toastCount() === n1, n1 + ' → ' + toastCount());

  /* 提示数量上限 */
  FB.dismissAll(); await sleep(260);
  for (var k = 1; k <= 5; k++) { FB.toast('info', '第 ' + k + ' 条提示', '', ''); }
  await sleep(150);
  check('提示数量上限为 3', toastCount() === 3, toastCount() + ' 条');

  /* 关闭按钮 */
  var top = lastToast();
  if (top) {
    var closeBtn = top.querySelector('.fb-close');
    var before = toastCount();
    if (closeBtn) { closeBtn.click(); }
    await sleep(400);
    check('提示可手动关闭', toastCount() < before, before + ' → ' + toastCount());
  } else {
    check('提示可手动关闭', false, '没有提示可关');
  }

  /* 按钮按压反馈 */
  FB.dismissAll();
  var chip = doc.querySelector('.chip');
  chip.dispatchEvent(new win.MouseEvent('click', { bubbles: true, cancelable: true }));
  await sleep(60);
  check('按钮点击有按压反馈', chip.classList.contains('fb-pulse'),
        chip.className.slice(0, 40));

  win.HTMLAnchorElement.prototype.click = origAnchorClick;
  report();
 } catch (err) {
  check('测试过程未抛异常', false, String(err && err.stack || err).slice(0, 200));
  report();
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
    ap.add_argument("--budget", type=int, default=120000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)
    is_wsl = "microsoft" in os.uname().release.lower()

    probe = root / ".feedback-probe.html"
    probe.write_text(HARNESS.replace("__PROBE__", PROBE), encoding="utf-8")
    tag = uuid.uuid4().hex[:8]
    win_profile = f"C:\\Temp\\htlb-fb-{tag}"
    nix_profile = f"/mnt/c/Temp/htlb-fb-{tag}"
    url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()

    cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--allow-file-access-from-files",
           f"--user-data-dir={win_profile if is_wsl else nix_profile}",
           "--window-size=1300,1000", f"--virtual-time-budget={args.budget}",
           "--dump-dom", url]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=260)
        dom = res.stdout.decode("utf-8", "replace")
        m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)<', dom)
        if not m:
            print("探针未返回结果。stderr 末尾：")
            print(res.stderr.decode("utf-8", "replace")[-800:])
            sys.exit(1)
        results = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    finally:
        probe.unlink(missing_ok=True)
        shutil.rmtree(nix_profile, ignore_errors=True)

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
    print("操作反馈模块：加载状态、成功/失败提示、原因+建议、去重与上限、按压反馈 —— 全部正常。")


if __name__ == "__main__":
    main()

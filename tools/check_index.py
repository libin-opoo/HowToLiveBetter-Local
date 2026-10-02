#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「条目索引界面」的验收测试。

核心要验的是用户报的那个问题：
  正文里写「见第 4 条」，而主列表按证据等级排过序，编号被打散，找不到。
  索引界面必须按书序（章节号 → 条目号）列出，并且能直接输编号定位。

用法:
    python3 tools/check_index.py
    python3 tools/check_index.py --browser "/path/to/msedge"
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

  var IV = win.HTLBIndexView;
  check('索引模块已加载', !!IV && typeof IV.open === 'function', IV ? ('v' + IV.version) : '不存在');
  if (!IV) { report(); return; }

  /* ---- 入口按钮由模块自己注入，不改模板 ---- */
  check('入口按钮已注入到页脚工具栏',
        IV.entryMounted() && !!doc.querySelector('.io #iv-open-btn'),
        doc.querySelector('#iv-open-btn') ? doc.querySelector('#iv-open-btn').textContent : '没有按钮');
  check('原有按钮一个没少',
        !!doc.querySelector('#export-btn') && !!doc.querySelector('#import-btn') &&
        !!doc.querySelector('#reset-btn'), '');

  /* ---- 打开面板 ---- */
  doc.querySelector('#iv-open-btn').click();
  await sleep(400);
  check('面板可以打开', IV.isOpen() && doc.querySelector('.iv-panel.iv-show') !== null, '');
  check('共 650 条分 34 节',
        IV._items() === 650 && IV._sections() === 34,
        IV._items() + ' 条 / ' + IV._sections() + ' 节');

  /* ---- 核心：书序正确，编号连续 ---- */
  var ids = IV._ids();
  var sec7 = [];
  ids.forEach(function (id, i) {
    if (/^7-/.test(id)) { sec7.push({ i: i, id: id, n: parseInt(id.split('-')[1], 10) }); }
  });
  var contiguous = sec7.every(function (x, k) { return k === 0 || x.i === sec7[k - 1].i + 1; });
  var ascending = sec7.every(function (x, k) { return k === 0 || x.n > sec7[k - 1].n; });
  check('同一节的条目连续排列（不打散）', contiguous,
        '第 7 节 ' + sec7.length + ' 条，位置 ' + sec7.slice(0, 5).map(function (x) { return x.i; }).join(',') + ' …');
  check('同一节内按条目号升序', ascending, '首个=' + (sec7[0] || {}).id + ' 末个=' + (sec7[sec7.length - 1] || {}).id);

  /* ---- 核心：能找到引用里说的「第 4 条」 ---- */
  var t74 = IV._titleOf('7-4');
  check('7-4 就是引用说的那条',
        t74 === '走投无路时去救助站，管吃住和返乡车票', String(t74));

  /* ---- 直接输编号定位 ---- */
  IV._query('7-4');
  await sleep(200);
  check('输 7-4 精确定位到 1 条',
        IV._items() === 1 && IV._sections() === 1 && IV._ids()[0] === '7-4',
        IV._items() + ' 条：' + IV._ids().join(','));
  check('定位到的就是救助站那条',
        IV._titleOf('7-4') === '走投无路时去救助站，管吃住和返乡车票', String(IV._titleOf('7-4')));

  IV._query('7 4');
  await sleep(200);
  check('空格分隔「7 4」也能定位', IV._items() === 1 && IV._ids()[0] === '7-4', IV._ids().join(','));

  IV._query('13');
  await sleep(200);
  check('只输 13 显示整个第 13 节',
        IV._sections() === 1 && IV._items() > 1 && /^13-/.test(IV._ids()[0]),
        IV._items() + ' 条');

  /* ---- 展开看全文 ---- */
  IV._query('7-4');
  await sleep(200);
  check('点条目能展开详情', IV._clickItem('7-4') === true && IV._detailOpen('7-4') === true, '');
  var dts = Array.prototype.map.call(
    doc.querySelectorAll('.iv-item[data-id="7-4"] .iv-detail dt'),
    function (n) { return n.textContent; });
  check('详情含全部字段',
        ['内容', '成本', '收益', '备注', '来源出处'].every(function (k) { return dts.indexOf(k) !== -1; }),
        dts.join('/'));

  /* ---- 关键词筛选 ---- */
  IV._query('');
  await sleep(200);
  IV._query('救助站');
  await sleep(250);
  check('关键词筛选可用', IV._items() > 0 && IV._items() < 650,
        IV._items() + ' 条命中「救助站」');
  check('关键词有高亮', doc.querySelectorAll('.iv-mark').length > 0,
        doc.querySelectorAll('.iv-mark').length + ' 处');

  /* ---- 异常：找不到 ---- */
  IV._query('99-99');
  await sleep(200);
  check('不存在的编号给出空状态提示（不白屏）',
        IV._items() === 0 && !!doc.querySelector('.iv-empty'),
        doc.querySelector('.iv-empty') ? doc.querySelector('.iv-empty').textContent.slice(0, 30) : '没有提示');

  IV._query('zzz不存在的词zzz');
  await sleep(200);
  check('不存在的关键词同样有提示', IV._items() === 0 && !!doc.querySelector('.iv-empty'), '');

  IV._query('');
  await sleep(250);
  check('清空输入后恢复全部', IV._items() === 650, IV._items() + ' 条');

  /* ---- Esc 关闭，且不影响主页面原有的搜索框 ---- */
  var mainQ = doc.getElementById('q');
  mainQ.value = '血压';
  mainQ.dispatchEvent(new win.Event('input', { bubbles: true }));
  await sleep(350);
  var beforeCards = doc.querySelectorAll('.card').length;

  doc.dispatchEvent(new win.KeyboardEvent('keydown',
    { key: 'Escape', bubbles: true, cancelable: true }));
  await sleep(250);
  check('Esc 关闭索引面板', !IV.isOpen(), '');
  check('关闭后背景恢复滚动', !doc.body.classList.contains('iv-locked'), '');
  check('Esc 只关了面板，没动主页面的搜索框',
        mainQ.value === '血压' && doc.querySelectorAll('.card').length === beforeCards,
        '输入框="' + mainQ.value + '"，卡片 ' + doc.querySelectorAll('.card').length);
  check('面板关闭后不可见',
        doc.querySelector('.iv-panel').classList.contains('iv-show') === false, '');

  /* ---- 关闭按钮 ---- */
  IV.open();
  await sleep(250);
  doc.querySelector('.iv-close').click();
  await sleep(250);
  check('「关闭」按钮可用', !IV.isOpen(), '');

  /* ---- 数据来源解耦 ---- */
  IV.open();
  await sleep(250);
  var rows = IV.loadRows();
  check('能从公开接口取到当前数据', rows.length === 650, rows.length + ' 条');
  check('取到的数据字段完整',
        rows.every(function (r) {
          return r['标题'] && r['内容'] && r['所属主题'] && r['成本'] &&
                 r['收益'] && r['证据等级'] && r['来源出处'];
        }), '');
  IV.close();

  /* ---- 窄屏下索引面板不能横向溢出 ---- */
  f.style.width = '360px';
  await sleep(300);
  IV.open();
  await sleep(400);
  var de = doc.documentElement;
  var worst = 0, worstEl = '';
  Array.prototype.forEach.call(doc.querySelectorAll('.iv-panel *'), function (n) {
    var b = n.getBoundingClientRect();
    if (b.width === 0) { return; }
    var over = b.right - de.clientWidth;
    if (over > worst) { worst = Math.round(over); worstEl = (n.className || n.tagName).toString(); }
  });
  check('窄屏(360px)下面板不横向溢出',
        de.scrollWidth - de.clientWidth <= 1 && worst <= 1,
        '页面溢出=' + (de.scrollWidth - de.clientWidth) + 'px，面板内最远越界 ' + worst + 'px @' + worstEl);
  check('窄屏下仍能输编号定位', (function () {
    IV._query('7-4');
    return IV._items() === 1 && IV._ids()[0] === '7-4';
  })(), IV._ids().join(','));
  IV._query('13');
  await sleep(250);
  check('窄屏下详情仍可展开', IV._clickItem('13-1') === true && IV._detailOpen('13-1') === true, '');
  IV.close();
  f.style.width = '1100px';
  await sleep(200);

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

    probe = root / ".index-probe.html"
    probe.write_text(HARNESS.replace("__PROBE__", PROBE), encoding="utf-8")
    tag = uuid.uuid4().hex[:8]
    win_profile = f"C:\\Temp\\htlb-ix-{tag}"
    nix_profile = f"/mnt/c/Temp/htlb-ix-{tag}"
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
    print("-" * (width + 42))
    for r in results:
        if not r["pass"]:
            failed += 1
        print(f"{r['name']:<{width}}  {'✅' if r['pass'] else '❌'}    {r['detail']}")

    print()
    print(f"共 {len(results)} 项，通过 {len(results) - failed} 项，失败 {failed} 项。")
    if failed:
        sys.exit(1)
    print("条目索引：书序排列、编号定位、详情展开、空状态、Esc 关闭 —— 全部正常。")


if __name__ == "__main__":
    main()

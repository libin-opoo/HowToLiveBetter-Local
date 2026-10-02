#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 index.html 的搜索与分类筛选功能（含证据等级排序），确保没有逻辑错误。

在无头浏览器里加载 index.html，用真实事件驱动搜索框和分类按钮，逐项断言并汇总。

用法:
    python3 tools/check_search.py
    python3 tools/check_search.py --browser "/path/to/msedge"
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
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
  var doc, win;
  try { doc = f.contentDocument; win = f.contentWindow; }
  catch (e) { check('iframe 可访问', false, e); report(); return; }

  for (var i = 0; i < 300 && doc.querySelectorAll('.card').length === 0; i++) {
    await sleep(50);
    doc = f.contentDocument; win = f.contentWindow;
  }

  var cards = function () { return Array.prototype.slice.call(doc.querySelectorAll('.card')); };
  var titles = function () {
    return cards().map(function (c) { return c.querySelector('.card-title').textContent; });
  };
  var levels = function () {
    return cards().map(function (c) { return c.querySelector('.ev').textContent; });
  };
  var texts = function () {
    return cards().map(function (c) {
      return c.querySelector('.card-title').textContent + '\n' +
             c.querySelector('.brief').textContent + '\n' +
             c.querySelector('.theme').textContent;
    });
  };
  function sortedOK(lv) {
    var rank = { A: 0, B: 1, C: 2 };
    for (var i = 1; i < lv.length; i++) {
      var a = rank[lv[i - 1].charAt(0)], b = rank[lv[i].charAt(0)];
      if (a > b) { return '第 ' + i + ' 项 ' + lv[i - 1] + ' 排在 ' + lv[i] + ' 前面'; }
    }
    return true;
  }
  function setSearch(v) {
    var q = doc.getElementById('q');
    q.value = v;
    q.dispatchEvent(new win.Event('input', { bubbles: true }));
  }
  function tap(cat) {
    doc.querySelector('.chip[data-cat="' + cat + '"]').click();
  }
  var q = doc.getElementById('q');

  /* ---- 1. 默认状态 ---- */
  check('默认展示全部 650 条', cards().length === 650, cards().length);
  check('默认按证据等级排序', sortedOK(levels()) === true, sortedOK(levels()));
  check('状态栏标注排序规则',
        doc.getElementById('status').textContent.indexOf('按证据等级') !== -1,
        doc.getElementById('status').textContent.trim());
  var firstLevels = levels().slice(0, 5).join(',');
  check('A 级排在最前', levels()[0].charAt(0) === 'A', firstLevels);

  /* ---- 2. 单关键词搜索 ---- */
  setSearch('血压');
  await sleep(320);
  var n = cards().length;
  var bpCount = n;                      /* 「血压」单关键词命中数，后面复用，避免写死 */
  check('搜索“血压”有结果', n > 0, n + ' 条');
  var miss = texts().filter(function (t) { return t.indexOf('血压') === -1; });
  check('命中项都包含关键词(标题/内容/主题)', miss.length === 0,
        miss.length ? '有 ' + miss.length + ' 条不含关键词：' + miss[0].split('\n')[0] : '全部命中');
  check('搜索结果按证据等级排序', sortedOK(levels()) === true, sortedOK(levels()));
  check('关键词被高亮(<mark>)', doc.querySelectorAll('.card mark').length > 0,
        doc.querySelectorAll('.card mark').length + ' 处');

  /* ---- 3. 搜索范围只限标题/内容/主题 ---- */
  setSearch('Cochrane');            /* 只出现在「来源出处」里 */
  await sleep(320);
  check('来源/备注里的词不再命中(范围收窄)', cards().length === 0, cards().length + ' 条');

  /* ---- 4. 多关键词 AND ---- */
  setSearch('血压 筛查');
  await sleep(320);
  n = cards().length;
  check('多关键词取交集', n > 0 && n < bpCount,
        n + ' 条（“血压”单搜为 ' + bpCount + ' 条）');
  var bad = texts().filter(function (t) {
    return t.indexOf('血压') === -1 || t.indexOf('筛查') === -1;
  });
  check('多关键词结果同时含两个词', bad.length === 0, bad.length + ' 条不满足');

  /* ---- 5. 清空搜索 ---- */
  setSearch('');
  await sleep(320);
  check('清空搜索恢复全部', cards().length === 650, cards().length);

  /* ---- 6. 分类筛选 ---- */
  tap('健康');
  await sleep(200);
  n = cards().length;
  check('点“健康”筛选生效', n === 327, n + ' 条');
  check('分类筛选结果按证据等级排序', sortedOK(levels()) === true, sortedOK(levels()));
  check('“健康”按钮呈选中态',
        doc.querySelector('.chip[data-cat="健康"]').getAttribute('aria-pressed') === 'true', '');
  check('分类状态栏显示命中数',
        doc.getElementById('status').textContent.indexOf('327') !== -1,
        doc.getElementById('status').textContent.trim());

  /* ---- 7. 再次点击取消 ---- */
  tap('健康');
  await sleep(200);
  check('再点一次取消筛选', cards().length === 650, cards().length);
  check('取消后按钮复原',
        doc.querySelector('.chip[data-cat="健康"]').getAttribute('aria-pressed') === 'false', '');

  /* ---- 8. 搜索 + 分类 组合 ---- */
  tap('健康');
  await sleep(150);
  setSearch('血压');
  await sleep(320);
  var combo = cards().length;
  check('搜索与分类可叠加', combo > 0 && combo <= bpCount, combo + ' 条');
  check('组合结果仍按证据等级排序', sortedOK(levels()) === true, sortedOK(levels()));

  /* ---- 9. 空结果 ---- */
  setSearch('zzzz不存在的词zzzz');
  await sleep(320);
  check('无结果时卡片清空', cards().length === 0, cards().length);
  check('无结果时给出提示', !!doc.querySelector('.empty'),
        doc.querySelector('.empty') ? doc.querySelector('.empty').textContent.trim() : '无提示');

  /* ---- 10. 全部复位 ---- */
  setSearch('');
  await sleep(320);
  tap('健康');
  await sleep(250);
  check('复位后回到 650 条', cards().length === 650, cards().length);

  report();
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
    ap.add_argument("--budget", type=int, default=40000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)

    is_wsl = "microsoft" in os.uname().release.lower()
    profile = "C:\\Temp\\htlb-search-profile" if is_wsl else "/tmp/htlb-search-profile"

    probe = root / ".search-probe.html"
    probe.write_text(HARNESS.replace("__PROBE__", PROBE), encoding="utf-8")
    url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()

    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--allow-file-access-from-files", f"--user-data-dir={profile}",
        "--window-size=1300,1000", f"--virtual-time-budget={args.budget}", "--dump-dom", url,
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, timeout=300)
        dom = res.stdout.decode("utf-8", "replace")
        m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)<', dom)
        if not m:
            print("探针未返回结果。stderr 末尾：")
            print(res.stderr.decode("utf-8", "replace")[-1000:])
            sys.exit(1)
        results = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    finally:
        probe.unlink(missing_ok=True)

    width = max(len(r["name"]) for r in results)
    failed = 0
    print(f"{'检查项':<{width}}  结果   详情")
    print("-" * (width + 34))
    for r in results:
        mark = "✅" if r["pass"] else "❌"
        if not r["pass"]:
            failed += 1
        print(f"{r['name']:<{width}}  {mark}    {r['detail']}")

    print()
    print(f"共 {len(results)} 项，通过 {len(results) - failed} 项，失败 {failed} 项。")
    if failed:
        sys.exit(1)
    print("搜索、分类筛选与证据等级排序均正常。")


if __name__ == "__main__":
    main()

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
  var doc, win;
  try { doc = f.contentDocument; win = f.contentWindow; }
  catch (e) { check('iframe 可访问', false, e); report(); return; }

  for (var i = 0; i < 400 && doc.querySelectorAll('.card').length < 650; i++) {
    await sleep(40);
    doc = f.contentDocument; win = f.contentWindow;
  }
  await stableCount();

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
  var cardNos = function () {
    return cards().map(function (c) {
      var n = c.querySelector('.card-no');
      return n ? n.textContent : '';
    });
  };
  /* 书序 = 条目编号的「章节号 → 条目号」单调不减 */
  function bookOrderOK(ids) {
    var prev = null;
    for (var i = 0; i < ids.length; i++) {
      var m = /^(\d+)-(\d+)$/.exec(ids[i]);
      if (!m) { return '第 ' + (i + 1) + ' 项没有编号：' + ids[i]; }
      var cur = [parseInt(m[1], 10), parseInt(m[2], 10)];
      if (prev && (cur[0] < prev[0] || (cur[0] === prev[0] && cur[1] < prev[1]))) {
        return '第 ' + (i + 1) + ' 项 ' + ids[i] + ' 排在 ' + ids[i - 1] + ' 后面';
      }
      prev = cur;
    }
    return true;
  }
  /* 当前排序模式：状态栏按钮上写着 */
  function sortMode() {
    var b = doc.querySelector('.status-sort');
    return b && b.textContent.indexOf('证据等级') !== -1 ? 'evidence' : 'book';
  }
  async function toggleSort() {
    var b = doc.querySelector('.status-sort');
    if (b) { b.click(); }
    return await stableCount();
  }

  function sortedOK(lv) {
    var rank = { A: 0, B: 1, C: 2 };
    for (var i = 1; i < lv.length; i++) {
      var a = rank[lv[i - 1].charAt(0)], b = rank[lv[i].charAt(0)];
      if (a > b) { return '第 ' + i + ' 项 ' + lv[i - 1] + ' 排在 ' + lv[i] + ' 前面'; }
    }
    return true;
  }
  /* 卡片是分片渲染的，固定 sleep 会读到中间态（实测读到过 164 = 24+140）。
     这里等数量连续两次不变再断言。 */
  async function stableCount() {
    var last = -1, stable = 0, n;
    for (var i = 0; i < 250; i++) {
      n = doc.querySelectorAll('.card').length;
      if (n === last) { stable++; if (stable >= 2) { return n; } } else { stable = 0; }
      last = n;
      await sleep(40);
    }
    return doc.querySelectorAll('.card').length;
  }

  /* 搜索有 120ms 防抖：必须越过防抖再等分片渲染，否则读到的是改动前的旧结果 */
  async function setSearch(v) {
    var q = doc.getElementById('q');
    q.value = v;
    q.dispatchEvent(new win.Event('input', { bubbles: true }));
    await sleep(260);
    return await stableCount();
  }
  async function tap(cat) {
    doc.querySelector('.chip[data-cat="' + cat + '"]').click();
    return await stableCount();
  }
  /* 把搜索和分类都恢复成「什么都没选」，避免用例之间互相污染 */
  async function resetFilters() {
    await setSearch('');
    var on = doc.querySelector('.chip[aria-pressed="true"]');
    if (on) { await tap(on.dataset.cat); }
    return await stableCount();
  }
  var q = doc.getElementById('q');

  /* ---- 1. 默认状态 ---- */
  check('默认展示全部 650 条', cards().length === 650, cards().length);
  check('默认按书序排列（章节号→条目号）', bookOrderOK(cardNos()) === true, bookOrderOK(cardNos()));
  check('卡片显示自己的条目编号', cardNos()[0] === '1-1', cardNos().slice(0, 3).join(', '));
  check('状态栏有排序切换按钮并显示当前排序',
        !!doc.querySelector('.status-sort') && /排序：/.test(doc.querySelector('.status-sort').textContent),
        doc.querySelector('.status-sort') ? doc.querySelector('.status-sort').textContent : '没有按钮');
  check('默认排序模式为书序', sortMode() === 'book', sortMode());

  /* ---- 2. 单关键词搜索 ---- */
  await setSearch('血压');
  var n = cards().length;
  var bpCount = n;                      /* 「血压」单关键词命中数，后面复用，避免写死 */
  check('搜索“血压”有结果', n > 0, n + ' 条');
  var miss = texts().filter(function (t) { return t.indexOf('血压') === -1; });
  check('命中项都包含关键词(标题/内容/主题)', miss.length === 0,
        miss.length ? '有 ' + miss.length + ' 条不含关键词：' + miss[0].split('\n')[0] : '全部命中');
  check('搜索结果跟随当前排序（书序）', bookOrderOK(cardNos()) === true, bookOrderOK(cardNos()));
  check('关键词被高亮(<mark>)', doc.querySelectorAll('.card mark').length > 0,
        doc.querySelectorAll('.card mark').length + ' 处');

  /* ---- 3. 搜索范围只限标题/内容/主题 ---- */
  await setSearch('Cochrane');      /* 只出现在「来源出处」里 */
  check('来源/备注里的词不再命中(范围收窄)', cards().length === 0, cards().length + ' 条');

  /* ---- 4. 多关键词 AND ---- */
  await setSearch('血压 筛查');
  n = cards().length;
  check('多关键词取交集', n > 0 && n < bpCount,
        n + ' 条（“血压”单搜为 ' + bpCount + ' 条）');
  var bad = texts().filter(function (t) {
    return t.indexOf('血压') === -1 || t.indexOf('筛查') === -1;
  });
  check('多关键词结果同时含两个词', bad.length === 0, bad.length + ' 条不满足');

  /* ---- 5. 清空搜索 ---- */
  await setSearch('');
  check('清空搜索恢复全部', cards().length === 650, cards().length);

  /* ---- 6. 分类筛选 ---- */
  await tap('健康');
  n = cards().length;
  check('点“健康”筛选生效', n === 327, n + ' 条');
  check('分类筛选结果跟随当前排序（书序）', bookOrderOK(cardNos()) === true, bookOrderOK(cardNos()));
  check('“健康”按钮呈选中态',
        doc.querySelector('.chip[data-cat="健康"]').getAttribute('aria-pressed') === 'true', '');
  check('分类状态栏显示命中数',
        doc.getElementById('status').textContent.indexOf('327') !== -1,
        doc.getElementById('status').textContent.trim());

  /* ---- 7. 再次点击取消 ---- */
  await tap('健康');
  check('再点一次取消筛选', cards().length === 650, cards().length);
  check('取消后按钮复原',
        doc.querySelector('.chip[data-cat="健康"]').getAttribute('aria-pressed') === 'false', '');

  /* ---- 8. 搜索 + 分类 组合 ---- */
  await tap('健康');
  await setSearch('血压');
  var combo = cards().length;
  check('搜索与分类可叠加', combo > 0 && combo <= bpCount, combo + ' 条');
  check('组合结果仍跟随当前排序（书序）', bookOrderOK(cardNos()) === true, bookOrderOK(cardNos()));

  /* ---- 9. 空结果 ---- */
  await setSearch('zzzz不存在的词zzzz');
  check('无结果时卡片清空', cards().length === 0, cards().length);
  check('无结果时给出提示', !!doc.querySelector('.empty'),
        doc.querySelector('.empty') ? doc.querySelector('.empty').textContent.trim() : '无提示');

  /* ---- 10. 快捷键 ---- */
  function press(key, opts) {
    var ev = new win.KeyboardEvent('keydown', Object.assign(
      { key: key, bubbles: true, cancelable: true }, opts || {}));
    doc.dispatchEvent(ev);
    return ev;
  }
  await resetFilters();
  if (doc.activeElement && doc.activeElement.blur) { doc.activeElement.blur(); }
  press('k', { ctrlKey: true });
  check('Ctrl+K 聚焦搜索框', doc.activeElement === q,
        doc.activeElement ? (doc.activeElement.id || doc.activeElement.tagName) : 'null');
  press('k', { metaKey: true });
  check('Cmd+K 也聚焦搜索框', doc.activeElement === q,
        doc.activeElement ? (doc.activeElement.id || doc.activeElement.tagName) : 'null');
  if (doc.activeElement && doc.activeElement.blur) { doc.activeElement.blur(); }
  var plainK = press('k', {});
  check('单按 K 不触发（不劫持普通输入）', doc.activeElement !== q && !plainK.defaultPrevented,
        'activeElement=' + (doc.activeElement ? (doc.activeElement.id || doc.activeElement.tagName) : 'null'));

  await resetFilters();
  await setSearch('血压');
  var beforeEsc = cards().length;
  press('Escape');
  await sleep(80);
  await stableCount();
  check('Esc 清空搜索内容', q.value === '' && cards().length === 650,
        '输入框="' + q.value + '"，卡片 ' + beforeEsc + ' → ' + cards().length);

  await tap('健康');
  press('Escape');
  await sleep(80);
  await stableCount();
  check('搜索为空时 Esc 取消分类筛选',
        cards().length === 650 &&
        doc.querySelector('.chip[data-cat="健康"]').getAttribute('aria-pressed') === 'false',
        '卡片 ' + cards().length);

  /* ---- 11. 排序切换 ---- */
  await resetFilters();
  await toggleSort();
  check('点按钮切到证据等级排序', sortMode() === 'evidence', sortMode());
  check('切到证据等级后 A 级排在最前', levels()[0].charAt(0) === 'A',
        levels().slice(0, 5).join(','));
  check('证据等级排序整体单调不减', sortedOK(levels()) === true, sortedOK(levels()));
  check('切换后选择写入了 localStorage', (function () {
    try { return localStorage.getItem('htlb.sort') === 'evidence'; }
    catch (e) { return false; }
  })(), (function () { try { return String(localStorage.getItem('htlb.sort')); } catch (e) { return '读不到'; } })());

  /* 证据等级模式下搜索，结果也要按证据等级排 */
  await setSearch('血压');
  check('证据等级模式下搜索结果仍按证据等级排', sortedOK(levels()) === true, sortedOK(levels()));
  await resetFilters();

  /* 再点一次切回书序 */
  await toggleSort();
  check('再点一次切回书序', sortMode() === 'book', sortMode());
  check('切回书序后编号重新有序', bookOrderOK(cardNos()) === true, bookOrderOK(cardNos()));
  check('切回书序后 A 级不再强制在最前（说明真的换了排序）',
        levels().slice(0, 40).indexOf('C') !== -1 || levels()[0].charAt(0) !== 'A',
        levels().slice(0, 8).join(','));

  /* ---- 12. 全部复位 ---- */
  await resetFilters();
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
    # 每次运行用独立 profile：复用同一个目录时，上一次没退干净的 Edge
    # 会锁住 profile，导致浏览器启动失败、探针偶发取不到结果。
    _tag = uuid.uuid4().hex[:8]
    _win = f"C:\\Temp\\htlb-search-{_tag}"
    _nix = f"/mnt/c/Temp/htlb-search-{_tag}"
    profile = _win if is_wsl else f"/tmp/htlb-search-{_tag}"
    profile_dir_to_clean = _nix if is_wsl else profile

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
        shutil.rmtree(profile_dir_to_clean, ignore_errors=True)

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

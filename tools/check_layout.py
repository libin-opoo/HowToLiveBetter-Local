#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在不同屏幕宽度下渲染 index.html，检查是否出现横向溢出 / 布局错乱。

为什么用 iframe：无头浏览器（Edge/Chrome）在 Windows 上有最小窗口宽度限制
（约 496px），--window-size=375 根本测不到真实手机宽度。改成在一个足够宽的
窗口里放一个可调宽度的 iframe，iframe 自身就是 index.html 的视口，媒体查询会
按 iframe 宽度生效，于是 320px 这类窄屏也能准确测到。

用法:
    python3 tools/check_layout.py
    python3 tools/check_layout.py --widths 320,375,768,1440
    python3 tools/check_layout.py --browser "/path/to/msedge"
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

HARNESS = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>layout probe</title>
<style>html,body{margin:0;padding:0}iframe{border:0;display:block;height:900px}</style>
</head><body>
<iframe id="f" src="index.html"></iframe>
<script>
var WIDTHS = __WIDTHS__;
function report(obj) {
  var d = document.createElement('div');
  d.id = '__report';
  d.textContent = 'REPORT:' + btoa(unescape(encodeURIComponent(JSON.stringify(obj))));
  document.body.appendChild(d);
}
var f = document.getElementById('f');
var tries = 0;
function waitCards(cb) {
  var doc;
  try { doc = f.contentDocument; }
  catch (e) { report({ error: '无法访问 iframe（需要 --allow-file-access-from-files）: ' + e }); return; }
  if ((doc && doc.querySelectorAll('.card').length > 0) || tries++ > 300) { cb(); return; }
  setTimeout(function () { waitCards(cb); }, 40);
}
waitCards(function () {
  var out = [];
  var i = 0;
  (function step() {
    if (i >= WIDTHS.length) { report({ results: out }); return; }
    var w = WIDTHS[i++];
    f.style.width = w + 'px';
    setTimeout(function () {
      try {
        var doc = f.contentDocument, win = f.contentWindow, de = doc.documentElement;
        var cardsEl = doc.getElementById('cards');
        var r = {
          requested: w,
          innerWidth: win.innerWidth,
          clientWidth: de.clientWidth,
          scrollWidth: de.scrollWidth,
          overflowX: de.scrollWidth - de.clientWidth,
          cards: doc.querySelectorAll('.card').length,
          columns: cardsEl ? getComputedStyle(cardsEl).gridTemplateColumns.split(' ').length : 0,
          searchWidth: doc.getElementById('q')
            ? Math.round(doc.getElementById('q').getBoundingClientRect().width) : null,
          catsInternalScroll: (function () {
            var c = doc.getElementById('cats');
            return c ? c.scrollWidth - c.clientWidth : null;
          })(),
          worstOverflow: 0,
          worstElement: ''
        };
        Array.prototype.forEach.call(doc.querySelectorAll('.wrap *'), function (el) {
          var b = el.getBoundingClientRect();
          var over = b.right - de.clientWidth;
          if (over > r.worstOverflow) {
            r.worstOverflow = Math.round(over * 10) / 10;
            r.worstElement = (el.className && el.className.toString()) || el.tagName;
          }
        });
        out.push(r);
      } catch (e) { out.push({ requested: w, error: String(e) }); }
      setTimeout(step, 30);
    }, 80);
  })();
});
</script>
</body></html>
"""

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
    ap.add_argument("--widths",
                    default="320,360,375,414,480,600,768,820,1024,1280,1440,1920")
    ap.add_argument("--browser", default=os.environ.get("LAYOUT_BROWSER"))
    ap.add_argument("--budget", type=int, default=30000)
    ap.add_argument("--window", default="1500,1200")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)
    widths = [int(w) for w in args.widths.split(",") if w.strip()]

    is_wsl = "microsoft" in os.uname().release.lower()
    # 每次运行用独立 profile：复用同一个目录时，上一次没退干净的 Edge
    # 会锁住 profile，导致浏览器启动失败、探针偶发取不到结果。
    _tag = uuid.uuid4().hex[:8]
    _win = f"C:\\Temp\\htlb-layout-{_tag}"
    _nix = f"/mnt/c/Temp/htlb-layout-{_tag}"
    profile = _win if is_wsl else f"/tmp/htlb-layout-{_tag}"
    profile_dir_to_clean = _nix if is_wsl else profile

    probe = root / ".layout-probe.html"
    probe.write_text(HARNESS.replace("__WIDTHS__", json.dumps(widths)), encoding="utf-8")
    url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()

    cmd = [
        browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile}", f"--window-size={args.window}",
        f"--virtual-time-budget={args.budget}", "--dump-dom", url,
    ]
    print(f"浏览器: {browser}")
    print(f"页面:   {url}\n")

    try:
        out = subprocess.run(cmd, capture_output=True, timeout=300)
        dom = out.stdout.decode("utf-8", "replace")
        m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)<', dom)
        if not m:
            print("探针未返回结果。stderr 末尾：")
            print(out.stderr.decode("utf-8", "replace")[-1000:])
            sys.exit(1)
        payload = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    finally:
        probe.unlink(missing_ok=True)
        shutil.rmtree(profile_dir_to_clean, ignore_errors=True)

    if "error" in payload:
        sys.exit(f"探针错误: {payload['error']}")

    header = f"{'请求宽度':>8} {'实际视口':>8} {'卡片':>5} {'列':>3} {'横向溢出':>8} {'分类栏内滚':>10}  结论"
    print(header)
    print("-" * 62)

    problems = []
    for r in payload["results"]:
        if "error" in r:
            print(f"{r['requested']:>8}  探针异常: {r['error']}")
            problems.append((r["requested"], r["error"]))
            continue
        ok = r["overflowX"] <= 1 and r["worstOverflow"] <= 1
        print(f"{r['requested']:>8} {r['innerWidth']:>8} {r['cards']:>5} {r['columns']:>3} "
              f"{r['overflowX']:>8} {r['catsInternalScroll']:>10}  {'✅ 正常' if ok else '❌ 溢出'}")
        if not ok:
            problems.append((r["requested"],
                             f"横向溢出 {r['overflowX']}px；最远越界元素 {r['worstElement']} "
                             f"({r['worstOverflow']}px)"))
        if abs(r["innerWidth"] - r["requested"]) > 20:
            problems.append((r["requested"],
                             f"视口未按预期生效：请求 {r['requested']}，实际 {r['innerWidth']}"))

    print()
    if problems:
        print("发现问题：")
        for w, msg in problems:
            print(f"  {w}px: {msg}")
        sys.exit(1)
    print("全部宽度通过：无横向溢出、无元素越界、视口均按预期生效。")


if __name__ == "__main__":
    main()

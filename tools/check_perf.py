#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查「打开页面就能看到内容」：内容是否在数据请求结束之前就已经渲染出来。

在 <head> 最前面装探针（必须早于页面脚本）：
  - 劫持 fetch，记录它 settle 的时刻；
  - 用 MutationObserver 监听 documentElement，记录首张卡片和全部卡片进入 DOM 的时刻。
然后分别在 file:// 和 http://（本地起服务）两种打开方式下测一遍。

判定：
  - 首张卡片必须在 fetch 结束之前就出现（说明没有等网络）——这是主判据，结构上是确定的；
  - 首张卡片也不能太晚（默认 800ms 以内）。

注意：绝对毫秒数在这类共享机器上波动很大（同一版本实测能在 198~294ms 之间跳），
所以不要拿单个数字做结论，看「首卡是否早于数据返回」这个次序关系。

用法:
    python3 tools/check_perf.py
"""
import argparse
import base64
import functools
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import uuid
from pathlib import Path

PRELUDE = """<script>
window.__perf = { firstCard: null, allCards: null, fetchSettled: null };
(function () {
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function () {
      var p = origFetch.apply(this, arguments);
      var mark = function () {
        if (window.__perf.fetchSettled === null) { window.__perf.fetchSettled = performance.now(); }
      };
      p.then(mark, mark);
      return p;
    };
  }
  var obs = new MutationObserver(function () {
    var n = document.querySelectorAll('.card').length;
    if (n > 0 && window.__perf.firstCard === null) { window.__perf.firstCard = performance.now(); }
    if (n >= __TOTAL__ && window.__perf.allCards === null) { window.__perf.allCards = performance.now(); }
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
})();
</script>
"""

PROBE = r"""
<script>
(function () {
  var t = 0;
  (function wait() {
    var ready = window.__perf.allCards !== null && window.__perf.fetchSettled !== null;
    if (ready || t++ > 600) { done(); return; }
    setTimeout(wait, 25);
  })();
  function done() {
    var nav = performance.getEntriesByType('navigation')[0] || {};
    var m = {
      dcl: Math.round(nav.domContentLoadedEventEnd || 0),
      load: Math.round(nav.loadEventEnd || 0),
      firstCard: window.__perf.firstCard === null ? null : Math.round(window.__perf.firstCard),
      allCards: window.__perf.allCards === null ? null : Math.round(window.__perf.allCards),
      fetchSettled: window.__perf.fetchSettled === null ? null : Math.round(window.__perf.fetchSettled),
      cards: document.querySelectorAll('.card').length
    };
    var d = document.createElement('div');
    d.id = '__report';
    d.textContent = 'REPORT:' + btoa(unescape(encodeURIComponent(JSON.stringify(m))));
    document.body.appendChild(d);
  }
})();
</script>
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


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def measure(browser, url, is_wsl, total):
    tag = uuid.uuid4().hex[:8]
    win_profile = f"C:\\Temp\\htlb-perf-{tag}"
    nix_profile = f"/mnt/c/Temp/htlb-perf-{tag}"
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
           "--hide-scrollbars", "--allow-file-access-from-files",
           f"--user-data-dir={win_profile if is_wsl else nix_profile}",
           "--window-size=1300,900", "--virtual-time-budget=40000",
           "--dump-dom", url]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=200)
        dom = res.stdout.decode("utf-8", "replace")
        m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)<', dom)
        return json.loads(base64.b64decode(m.group(1)).decode("utf-8")) if m else None
    finally:
        shutil.rmtree(nix_profile, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default=os.environ.get("LAYOUT_BROWSER"))
    ap.add_argument("--budget-ms", type=int, default=800)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)
    is_wsl = "microsoft" in os.uname().release.lower()

    total = len(json.loads((root / "data.json").read_text(encoding="utf-8")))
    src = (root / "index.html").read_text(encoding="utf-8")
    probe = root / ".perf-probe.html"
    probe.write_text(
        src.replace("<head>", "<head>" + PRELUDE.replace("__TOTAL__", str(total)), 1)
           .replace("</body>", PROBE + "</body>", 1),
        encoding="utf-8")

    port = free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    file_url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()
    http_url = f"http://127.0.0.1:{port}/{probe.name}"

    cases = [("直接双击 (file://)", file_url), ("本地服务 (http://)", http_url)]
    results = {}
    failed = 0
    try:
        for label, url in cases:
            print(f"===== {label} =====")
            m = measure(browser, url, is_wsl, total)
            if m is None:
                print("  探针未返回结果\n")
                failed += 1
                continue
            results[label] = m
            print(f"  DOMContentLoaded      {m['dcl']} ms")
            print(f"  首张卡片进入 DOM       {m['firstCard']} ms   ← 用户看到内容的时间")
            print(f"  全部 {total} 张渲染完     {m['allCards']} ms")
            print(f"  数据请求返回           {m['fetchSettled']} ms")
            print(f"  渲染卡片数             {m['cards']}")
            print()

            if m["firstCard"] is None:
                print("  ❌ 首张卡片始终没出现")
                failed += 1
            elif m["firstCard"] > args.budget_ms:
                print(f"  ❌ 首张卡片 {m['firstCard']}ms，超过 {args.budget_ms}ms")
                failed += 1
            else:
                print(f"  ✅ 首张卡片 {m['firstCard']}ms ≤ {args.budget_ms}ms")
            if m["fetchSettled"] is not None and m["firstCard"] is not None:
                if m["firstCard"] < m["fetchSettled"]:
                    print(f"  ✅ 内容先于数据请求出现（{m['firstCard']}ms < {m['fetchSettled']}ms）：没有等网络")
                else:
                    print(f"  ❌ 首张卡片 {m['firstCard']}ms 晚于数据请求 {m['fetchSettled']}ms：页面在等网络")
                    failed += 1
            if m["cards"] != total:
                print(f"  ❌ 只渲染了 {m['cards']} 张，应为 {total} 张")
                failed += 1
            print()
    finally:
        server.shutdown()
        probe.unlink(missing_ok=True)

    if failed:
        print(f"共 {failed} 项未通过。")
        sys.exit(1)
    print("两种打开方式都是「内容先出、数据后到」，没有加载等待。")


if __name__ == "__main__":
    main()

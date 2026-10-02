#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查深色/浅色两种配色下所有文字的对比度，确认没有看不清的地方。

做法：把 index.html 复制一份，在 <head> 最前面塞一小段「预置脚本」强制指定配色
（其中 auto 用例还会伪造系统偏好为深色），再在 </body> 前塞入测量脚本。
测量脚本按 WCAG 2.1 的相对亮度公式算出每处文字与其实际背景的对比度。

判定标准：正文 4.5:1，大号文字（≥24px，或 ≥18.66px 且加粗）3:1。

用法:
    python3 tools/check_theme.py
    python3 tools/check_theme.py --browser "/path/to/msedge"
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

# 放在 <head> 最前面：早于页面自己的主题脚本执行
PRELUDE = """<script>
(function () {
  var mode = '__MODE__';
  try { localStorage.setItem('htlb.theme', mode); } catch (e) { /* 忽略 */ }
  __FAKE_DARK__
})();
</script>
"""

FAKE_DARK = """// 伪造系统配色偏好为深色，用来验证 auto 模式真的跟随系统
  var origMM = window.matchMedia;
  window.matchMedia = function (q) {
    if (/prefers-color-scheme:\\s*dark/.test(q)) {
      return { matches: true, media: q, addEventListener: function () {}, addListener: function () {} };
    }
    if (/prefers-color-scheme:\\s*light/.test(q)) {
      return { matches: false, media: q, addEventListener: function () {}, addListener: function () {} };
    }
    return origMM.call(window, q);
  };"""

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

/* ---- WCAG 2.1 对比度 ---- */
function parseColor(c) {
  var m = String(c).match(/rgba?\(([^)]+)\)/);
  if (!m) { return null; }
  var p = m[1].split(',').map(function (x) { return parseFloat(x); });
  return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
}
function lum(c) {
  function f(v) { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
}
function ratio(a, b) {
  var l1 = lum(a), l2 = lum(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}
function blend(fg, bg) {
  if (fg.a >= 1) { return fg; }
  return { r: fg.r * fg.a + bg.r * (1 - fg.a),
           g: fg.g * fg.a + bg.g * (1 - fg.a),
           b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 };
}
function bgOf(el, win) {
  var node = el;
  while (node && node.nodeType === 1) {
    var c = parseColor(win.getComputedStyle(node).backgroundColor);
    if (c && c.a > 0.9) { return c; }
    node = node.parentElement;
  }
  return { r: 255, g: 255, b: 255, a: 1 };
}

function contrastScan() {
  var bad = [], seen = {}, checked = 0;
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  var n;
  while ((n = walker.nextNode())) {
    var text = (n.nodeValue || '').trim();
    if (!text) { continue; }
    var el = n.parentElement;
    if (!el) { continue; }
    var cs = window.getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) { continue; }
    var box = el.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) { continue; }
    var full = el.closest ? el.closest('.full') : null;
    if (full && window.getComputedStyle(full).display === 'none') { continue; }

    var bg = bgOf(el, window);
    var fg = blend(parseColor(cs.color), bg);
    var cr = ratio(fg, bg);
    var size = parseFloat(cs.fontSize);
    var weight = parseInt(cs.fontWeight, 10) || 400;
    var large = size >= 24 || (size >= 18.66 && weight >= 700);
    var need = large ? 3.0 : 4.5;
    checked++;

    if (cr < need) {
      var key = String(el.className || el.tagName) + '|' + cs.color + '|' + Math.round(bg.r) + ',' +
                Math.round(bg.g) + ',' + Math.round(bg.b) + '|' + size;
      if (!seen[key]) {
        seen[key] = 1;
        bad.push({ text: text.slice(0, 20), cls: String(el.className || el.tagName),
                   color: cs.color,
                   bg: 'rgb(' + Math.round(bg.r) + ',' + Math.round(bg.g) + ',' + Math.round(bg.b) + ')',
                   size: size + 'px',
                   ratio: Math.round(cr * 100) / 100, need: need });
      }
    }
  }

  /* ::before / ::after 生成的文字不在文本节点里，TreeWalker 扫不到（比如卡片上的
     「展开 ▾」），这里按伪元素再查一遍，免得留下盲区。 */
  var nodes = document.querySelectorAll('*');
  for (var i = 0; i < nodes.length; i++) {
    var host = nodes[i];
    ['::before', '::after'].forEach(function (pseudo) {
      var ps = window.getComputedStyle(host, pseudo);
      var content = ps.content;
      if (!content || content === 'none' || content === 'normal' ||
          content === '""' || content === "''") { return; }
      if (ps.display === 'none' || ps.visibility === 'hidden') { return; }
      var bg = bgOf(host, window);
      var fg = blend(parseColor(ps.color), bg);
      var cr = ratio(fg, bg);
      var size = parseFloat(ps.fontSize);
      var weight = parseInt(ps.fontWeight, 10) || 400;
      var need = (size >= 24 || (size >= 18.66 && weight >= 700)) ? 3.0 : 4.5;
      checked++;
      if (cr < need) {
        var cls = String(host.className || host.tagName) + pseudo;
        if (!seen[cls]) {
          seen[cls] = 1;
          bad.push({ text: String(content).slice(0, 20), cls: cls, color: ps.color,
                     bg: 'rgb(' + Math.round(bg.r) + ',' + Math.round(bg.g) + ',' + Math.round(bg.b) + ')',
                     size: size + 'px',
                     ratio: Math.round(cr * 100) / 100, need: need });
        }
      }
    });
  }
  return { bad: bad, checked: checked };
}

(async function () {
 try {
  for (var i = 0; i < 400 && document.querySelectorAll('.card').length < __EXPECT__; i++) { await sleep(25); }

  var theme = document.documentElement.getAttribute('data-theme');
  check('data-theme = __MODE__', theme === '__EXPECTTHEME__', 'data-theme=' + theme);
  check('卡片全部渲染', document.querySelectorAll('.card').length === __EXPECT__,
        document.querySelectorAll('.card').length + ' 张');
  check('配色按钮文字', !!document.getElementById('theme-btn'),
        document.getElementById('theme-btn').textContent);

  if ('__MODE__' === 'dark') {
    /* 深色下把第一张卡片展开，让 成本/收益/备注/来源 也参与对比度检查 */
    var c0 = document.querySelector('.card');
    c0.click();
    await sleep(300);
    check('深色下卡片可展开', c0.getAttribute('aria-expanded') === 'true', '');
    /* 触发一次搜索，让 <mark> 高亮也参与检查 */
    var q = document.getElementById('q');
    q.value = '血压';
    q.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(400);
    check('深色下搜索可用', document.querySelectorAll('.card').length > 0,
          document.querySelectorAll('.card mark').length + ' 处高亮');
    q.value = '';
    q.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(500);
    /* 恢复展开，便于稳定扫描 */
    var c1 = document.querySelector('.card');
    if (c1.getAttribute('aria-expanded') !== 'true') { c1.click(); }
    await sleep(300);

    /* 主题按钮循环：深色 -> 自动 -> 浅色 -> 深色 */
    var tb = document.getElementById('theme-btn');
    check('初始按钮显示「深色」', tb.textContent === '深色', tb.textContent);
    tb.click(); await sleep(150);
    check('点一次 → 自动', tb.textContent === '自动', tb.textContent);
    check('选择已写入 localStorage',
          (function () { try { return localStorage.getItem('htlb.theme') === 'auto'; }
                         catch (e) { return false; } })(),
          (function () { try { return String(localStorage.getItem('htlb.theme')); }
                         catch (e) { return '读取失败'; } })());
    tb.click(); await sleep(150);
    check('再点 → 浅色，页面变浅色',
          tb.textContent === '浅色' && document.documentElement.getAttribute('data-theme') === 'light',
          tb.textContent + ' / ' + document.documentElement.getAttribute('data-theme'));
    tb.click(); await sleep(150);
    check('再点 → 回到深色',
          tb.textContent === '深色' && document.documentElement.getAttribute('data-theme') === 'dark',
          tb.textContent + ' / ' + document.documentElement.getAttribute('data-theme'));
    check('快捷键提示按平台显示',
          /^(Ctrl K|\u2318 K)$/.test(document.getElementById('kbd-hint').textContent),
          document.getElementById('kbd-hint').textContent);
  }

  /* 装了「操作反馈」模块时，先弹一条错误提示，让 toast 里的文字也参与对比度检查。
     用特性检测包起来，模块没装时这一句不生效，不影响原有检查。 */
  if (window.HTLBFeedback && window.HTLBFeedback.toast) {
    window.HTLBFeedback.toast('error', '配色检查用提示', '这是一条用于检查配色的提示文字。',
                              '它应当和页面里其他文字一样清晰可读。', '技术细节示例文本');
    await sleep(250);
  }

  var scan = contrastScan();
  check('所有文字对比度达标', scan.bad.length === 0,
        scan.bad.length === 0
          ? ('扫描 ' + scan.checked + ' 处文字，全部 ≥ 标准')
          : scan.bad.map(function (b) {
              return b.cls + ' 文字"' + b.text + '" ' + b.color + ' on ' + b.bg +
                     ' = ' + b.ratio + ':1 (需要 ' + b.need + ')';
            }).join('  //  '));

  report();
 } catch (err) {
  check('检查过程未抛异常', false, String(err && err.stack || err).slice(0, 200));
  report();
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


def build_case(root: Path, tag: str, mode: str, expect_theme: str, fake_dark: bool, expect_count: int):
    html = (root / "index.html").read_text(encoding="utf-8")
    prelude = PRELUDE.replace("__MODE__", mode)
    prelude = prelude.replace("__FAKE_DARK__", FAKE_DARK if fake_dark else "")
    probe = (PROBE.replace("__MODE__", mode)
                  .replace("__EXPECTTHEME__", expect_theme)
                  .replace("__EXPECT__", str(expect_count)))
    html = html.replace("<head>", "<head>" + prelude, 1)
    html = html.replace("</body>", probe + "</body>", 1)
    out = root / f".theme-probe-{tag}.html"
    out.write_text(html, encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default=os.environ.get("LAYOUT_BROWSER"))
    ap.add_argument("--budget", type=int, default=120000)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    browser = find_browser(args.browser)
    is_wsl = "microsoft" in os.uname().release.lower()

    cases = [
        ("light", "light", "light", False, "浅色模式"),
        ("dark", "dark", "dark", False, "深色模式"),
        ("auto", "auto", "dark", True, "跟随系统（伪造系统为深色）"),
    ]

    failed = 0
    probes = []
    try:
        for tag, mode, expect_theme, fake_dark, label in cases:
            probe = build_case(root, tag, mode, expect_theme, fake_dark, 650)
            probes.append(probe)
            _tag = uuid.uuid4().hex[:8]
            win_profile = f"C:\\Temp\\htlb-theme-{_tag}"
            nix_profile = f"/mnt/c/Temp/htlb-theme-{_tag}"
            url = ("file:///" + to_windows_path(probe)) if is_wsl else probe.as_uri()

            cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
                   "--hide-scrollbars", "--allow-file-access-from-files",
                   f"--user-data-dir={win_profile if is_wsl else nix_profile}",
                   "--window-size=1300,1000", f"--virtual-time-budget={args.budget}",
                   "--dump-dom", url]
            print(f"===== {label} =====")
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=240)
                dom = res.stdout.decode("utf-8", "replace")
                m = re.search(r'id="__report">REPORT:([A-Za-z0-9+/=]+)<', dom)
                if not m:
                    print("  探针未返回结果")
                    failed += 1
                    continue
                results = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
            finally:
                shutil.rmtree(nix_profile, ignore_errors=True)

            width = max(len(r["name"]) for r in results)
            for r in results:
                if not r["pass"]:
                    failed += 1
                print(f"  {r['name']:<{width}}  {'✅' if r['pass'] else '❌'}  {r['detail']}")
            print()
    finally:
        for p in probes:
            p.unlink(missing_ok=True)

    if failed:
        print(f"共 {failed} 项未通过。")
        sys.exit(1)
    print("浅色 / 深色 / 跟随系统三种情况全部通过，文字对比度均达标。")


if __name__ == "__main__":
    main()

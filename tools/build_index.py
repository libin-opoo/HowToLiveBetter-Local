#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 data.json 生成 index.html —— 只做一件事：把前 10 条用列表展示出来。

index.html 优先 fetch('data.json')；当用 file:// 直接双击打开（浏览器会拦截
本地 fetch）时，回退到构建时内嵌的前 10 条快照，保证离线也能看到数据。
"""
import json
from pathlib import Path

TOP_N = 10

HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>高性价比人生指南 · 前 10 条</title>
<style>
  :root { color-scheme: light dark; }
  body { max-width: 52rem; margin: 0 auto; padding: 1.5rem 1rem 4rem;
         font: 16px/1.7 system-ui, "Segoe UI", "Microsoft YaHei", sans-serif; }
  h1 { font-size: 1.35rem; margin: 0 0 .25rem; }
  .meta { color: #6b7280; font-size: .85rem; margin: 0 0 1.25rem; }
  .mode { display: inline-block; padding: .1rem .5rem; border-radius: .5rem;
          font-size: .78rem; background: #eef2f7; color: #374151; }
  @media (prefers-color-scheme: dark) { .mode { background:#2a2f38; color:#cbd5e1; } }
  ol { padding-left: 1.4rem; }
  li { margin: 0 0 1.4rem; padding-left: .2rem; }
  .title { font-weight: 600; }
  .tag { font-size: .78rem; color: #6b7280; margin-left: .4rem; }
  .ev { font-weight: 600; }
  dl { margin: .45rem 0 0; display: grid; grid-template-columns: 5.5rem 1fr;
       gap: .2rem .6rem; font-size: .92rem; }
  dt { color: #6b7280; }
  dd { margin: 0; }
  .src { font-size: .82rem; color: #6b7280; word-break: break-all; }
</style>
</head>
<body>
<h1>高性价比人生指南 · 前 10 条</h1>
<p class="meta">
  数据来源 <code>data.json</code> · 共 <span id="total">-</span> 条，此处只显示前 __TOP_N__ 条 ·
  <span class="mode" id="mode">加载中</span>
</p>
<ol id="list"></ol>

<script id="fallback" type="application/json">__FALLBACK_JSON__</script>
<script>
(function () {
  var FALLBACK = JSON.parse(document.getElementById('fallback').textContent);
  var TOTAL = __TOTAL__;
  var FIELDS = [
    ['内容', '内容'],
    ['成本', '成本'],
    ['收益', '收益'],
    ['来源出处', '来源']
  ];

  function render(rows, total, mode) {
    var list = document.getElementById('list');
    list.textContent = '';
    rows.forEach(function (r) {
      var li = document.createElement('li');

      var h = document.createElement('div');
      var t = document.createElement('span');
      t.className = 'title';
      t.textContent = r['标题'];
      h.appendChild(t);
      var tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = '§' + r['所属主题'] + ' · 证据等级 ';
      h.appendChild(tag);
      var ev = document.createElement('span');
      ev.className = 'ev';
      ev.textContent = r['证据等级'];
      h.appendChild(ev);
      li.appendChild(h);

      var dl = document.createElement('dl');
      FIELDS.forEach(function (pair) {
        var dt = document.createElement('dt');
        dt.textContent = pair[1];
        var dd = document.createElement('dd');
        if (pair[0] === '来源出处') { dd.className = 'src'; }
        dd.textContent = r[pair[0]] || '';
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      li.appendChild(dl);
      list.appendChild(li);
    });
    document.getElementById('total').textContent = total;
    document.getElementById('mode').textContent = mode;
  }

  fetch('data.json', { cache: 'no-store' })
    .then(function (res) {
      if (!res.ok) { throw new Error('HTTP ' + res.status); }
      return res.json();
    })
    .then(function (all) {
      render(all.slice(0, __TOP_N__), all.length, '读取 data.json');
    })
    .catch(function () {
      render(FALLBACK, TOTAL, '内嵌快照 · file:// 无法读取 data.json');
    });
})();
</script>
</body>
</html>
"""


def main():
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "data.json").read_text(encoding="utf-8"))
    top = data[:TOP_N]

    # 防止 </script> 提前闭合脚本块
    fallback = json.dumps(top, ensure_ascii=False).replace("<", "\\u003c")

    html = (
        HTML.replace("__FALLBACK_JSON__", fallback)
        .replace("__TOP_N__", str(TOP_N))
        .replace("__TOTAL__", str(len(data)))
    )
    out = root / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}  内嵌前 {len(top)} 条 / data.json 共 {len(data)} 条")


if __name__ == "__main__":
    main()

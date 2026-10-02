#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
由 data.json 生成 index.html —— 极简检索页。

页面结构：顶部搜索框 + 横向滚动的主题分类导航 + 卡片列表（点击展开）。
配色为浅蓝 + 白色，纯 CSS，适配电脑与手机。

index.html 优先 fetch('data.json')；用 file:// 直接双击打开时浏览器会拦截本地
fetch，此时回退到构建时内嵌的全量数据，保证离线也能搜索和筛选。
"""
import json
from pathlib import Path

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>高性价比人生指南 · 本地检索</title>
<style>
  :root{
    color-scheme: light;
    --bg:#f2f8ff;
    --surface:#ffffff;
    --line:#dbeafe;
    --line-soft:#eaf3fe;
    --primary:#2f7fd8;
    --primary-dark:#1f66b4;
    --primary-soft:#e6f2ff;
    --ink:#16212e;
    --ink-2:#5a6b7d;
    --ink-3:#93a5b8;
    --radius:14px;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{
    margin:0;background:var(--bg);color:var(--ink);
    font:16px/1.7 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  }
  .wrap{max-width:920px;margin:0 auto;padding:0 16px 56px}

  /* ---------- 顶部 ---------- */
  .hero{padding:26px 0 14px}
  .hero h1{margin:0;font-size:1.5rem;line-height:1.4;letter-spacing:.01em}
  .hero p{margin:6px 0 0;color:var(--ink-2);font-size:.875rem}

  .bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:10px 0 12px}
  .search input{
    display:block;width:100%;padding:12px 14px;
    font:inherit;font-size:1rem;color:var(--ink);
    background:var(--surface);border:1px solid var(--line);
    border-radius:12px;outline:none;
    -webkit-appearance:none;appearance:none;
    transition:border-color .15s,box-shadow .15s;
  }
  .search input::placeholder{color:var(--ink-3)}
  .search input:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(47,127,216,.15)}

  /* 横向滚动的主题分类导航 */
  .cats{
    display:flex;gap:8px;margin-top:10px;
    overflow-x:auto;overflow-y:hidden;
    -webkit-overflow-scrolling:touch;
    scrollbar-width:none;
    padding-bottom:2px;
  }
  .cats::-webkit-scrollbar{display:none}
  .chip{
    flex:0 0 auto;padding:7px 16px;border-radius:999px;
    border:1px solid var(--line);background:var(--surface);color:var(--primary-dark);
    font:inherit;font-size:.9rem;line-height:1.3;white-space:nowrap;
    cursor:pointer;transition:background .15s,border-color .15s,color .15s;
  }
  .chip:hover{border-color:#bcd9f7;background:var(--primary-soft)}
  .chip:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .chip[aria-pressed="true"]{background:var(--primary);border-color:var(--primary);color:#fff;font-weight:600}

  .status{margin:14px 2px 10px;color:var(--ink-2);font-size:.875rem}
  .status b{color:var(--primary-dark)}

  /* ---------- 卡片列表 ---------- */
  .cards{display:grid;gap:12px;grid-template-columns:1fr;align-items:start}
  @media (min-width:780px){ .cards{grid-template-columns:repeat(2,minmax(0,1fr))} }

  .card{
    min-width:0;
    background:var(--surface);border:1px solid var(--line-soft);
    border-radius:var(--radius);padding:14px 16px;
    cursor:pointer;transition:border-color .15s,box-shadow .15s;
  }
  .card:hover{border-color:#c3ddf8;box-shadow:0 4px 16px rgba(47,127,216,.08)}
  .card:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .card[aria-expanded="true"]{border-color:#aed4f6;box-shadow:0 6px 20px rgba(47,127,216,.1)}

  .card-head{display:flex;gap:10px;align-items:flex-start}
  .card-title{margin:0;flex:1 1 auto;min-width:0;font-size:1rem;font-weight:600;line-height:1.5}
  .ev{
    flex:0 0 auto;display:inline-block;padding:1px 9px;border-radius:999px;
    font-size:.75rem;font-weight:700;line-height:1.7;white-space:nowrap;
  }
  .ev-A{background:var(--primary);color:#fff}
  .ev-B{background:var(--primary-soft);color:var(--primary-dark);border:1px solid #c7e2fb}
  .ev-C{background:#eef3f9;color:var(--ink-2);border:1px solid #e2e9f1}

  .card-meta{
    display:flex;gap:8px;align-items:center;justify-content:space-between;
    margin-top:8px;font-size:.78rem;color:var(--ink-2);
  }
  .theme{
    padding:1px 9px;border-radius:999px;background:var(--primary-soft);
    color:var(--primary-dark);
    max-width:72%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  }
  .hint{color:var(--ink-3);white-space:nowrap}
  .hint::after{content:"展开 ▾"}
  .card[aria-expanded="true"] .hint::after{content:"收起 ▴"}

  .brief{
    margin:10px 0 0;font-size:.9rem;color:#33414f;
    display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
    line-clamp:2;overflow:hidden;
  }
  .card[aria-expanded="true"] .brief{display:block;overflow:visible}

  .full{display:none;margin-top:12px;padding-top:12px;border-top:1px dashed var(--line)}
  .card[aria-expanded="true"] .full{display:block}
  .full dl{margin:0;display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 12px;font-size:.88rem}
  .full dt{color:var(--ink-2);white-space:nowrap}
  .full dd{margin:0;min-width:0}
  .full .src{color:#4a5b6d;word-break:break-all}

  .empty{padding:44px 8px;text-align:center;color:var(--ink-2);font-size:.9rem}

  .foot{
    margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
    color:var(--ink-2);font-size:.78rem;line-height:1.8;
  }
  .foot a{color:var(--primary-dark)}
  .mode{
    display:inline-block;padding:1px 8px;border-radius:999px;
    background:var(--primary-soft);color:var(--primary-dark);font-size:.75rem;
  }

  /* ---------- 窄屏微调 ---------- */
  @media (max-width:520px){
    .hero{padding:20px 0 12px}
    .hero h1{font-size:1.28rem}
    .card{padding:12px 13px}
    .card-title{font-size:.95rem}
    .theme{max-width:64%}
    .full dl{grid-template-columns:minmax(0,1fr);gap:2px}
    .full dt{margin-top:8px;font-weight:600;color:var(--primary-dark)}
  }
</style>
</head>
<body>
<div class="wrap">

  <header class="hero">
    <h1>高性价比人生指南</h1>
    <p>用最少的钱、时间和精力，换回最多的寿命、金钱和人身自由 ·
       共 <b>__TOTAL__</b> 条循证建议</p>
  </header>

  <div class="bar">
    <div class="search">
      <input id="q" type="search" placeholder="搜索生活循证建议"
             autocomplete="off" aria-label="搜索生活循证建议">
    </div>
    <nav class="cats" id="cats" aria-label="主题分类">
      <button class="chip" type="button" data-cat="健康" aria-pressed="false">健康</button>
      <button class="chip" type="button" data-cat="金钱" aria-pressed="false">金钱</button>
      <button class="chip" type="button" data-cat="职场" aria-pressed="false">职场</button>
    </nav>
  </div>

  <p class="status" id="status" role="status"></p>
  <main class="cards" id="cards"></main>

  <footer class="foot">
    <p>
      数据取自 <a href="https://github.com/eternity4719/HowToLiveBetter" target="_blank" rel="noopener">eternity4719/HowToLiveBetter</a>，
      正文按 <a href="https://creativecommons.org/licenses/by/4.0/deed.zh" target="_blank" rel="noopener">CC BY 4.0</a> 发布，版权归原作者所有。
      本页为本地镜像，内容未作改动。
    </p>
    <p>数据来源：<span class="mode" id="mode">加载中…</span></p>
  </footer>

</div>

<script id="dataset" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";

  var EMBEDDED = JSON.parse(document.getElementById('dataset').textContent);

  /* 主题分类映射：把 34 个章节主题归到这 3 个分类里。
     这是按主题名粗分的，改这一处即可调整；同一个主题可以出现在多个分类。 */
  var CATEGORIES = {
    "健康": ["不要早死","不要慢慢死","不要浪费精力","紧急情况：先做什么","得了慢性病之后怎么活",
             "家里有老人","刚出生的孩子怎么带","怎么放松：娱乐场所和减压","看病：怎么少花钱少走弯路",
             "怀孕和生产：从发现怀孕到出院办证","别为了外形把身体搞坏","遭遇重大打击之后",
             "残疾之后怎么活","家里的常备药别吃出事","上学以后的孩子","反面清单","出国、旅行与境外安全"],
    "金钱": ["不要浪费钱","别把自己搭进去：法律与财产安全","没钱的时候怎么活","租房与买房",
             "养孩子划不划算","创业与做生意：别把家底赔进去","人走了以后要办什么",
             "普通人容易踩的法律红线","账号与信息安全","恋爱和结婚划不划算"],
    "职场": ["不要浪费时间","程序员和技术人容易踩的红线","在职、离职和工伤","学什么技能划算",
             "做一个网站或平台：资质、备案和服务器","十八岁之后有哪几条路",
             "出国留学：身份、打工、保险和回国认证"]
  };

  var cardsEl = document.getElementById('cards');
  var statusEl = document.getElementById('status');
  var inputEl = document.getElementById('q');
  var catsEl = document.getElementById('cats');
  var modeEl = document.getElementById('mode');

  var DATA = EMBEDDED;
  var state = { q: '', cat: '' };
  var debounceTimer = null;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  function haystack(r) {
    return [r['标题'], r['内容'], r['所属主题'], r['成本'], r['收益'], r['证据等级'],
            r['来源出处'], r['备注']].join('\n').toLowerCase();
  }

  function filterData() {
    var q = state.q.trim().toLowerCase();
    var themes = state.cat ? CATEGORIES[state.cat] : null;
    return DATA.filter(function (r) {
      if (themes && themes.indexOf(r['所属主题']) === -1) { return false; }
      if (!q) { return true; }
      return haystack(r).indexOf(q) !== -1;
    });
  }

  /* 展开内容按需构建，首屏只渲染标题和摘要，保证 650 条也不卡 */
  function buildFull(card, r) {
    if (card.dataset.full === '1') { return; }
    var full = el('div', 'full');
    var dl = el('dl');
    [['成本', r['成本'], ''], ['收益', r['收益'], ''],
     ['备注', r['备注'], ''], ['来源出处', r['来源出处'], 'src']].forEach(function (f) {
      if (!f[1]) { return; }
      dl.appendChild(el('dt', '', f[0]));
      dl.appendChild(el('dd', f[2], f[1]));
    });
    full.appendChild(dl);
    card.appendChild(full);
    card.dataset.full = '1';
  }

  function makeCard(r) {
    var card = el('article', 'card');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-expanded', 'false');

    var head = el('div', 'card-head');
    head.appendChild(el('h2', 'card-title', r['标题']));
    head.appendChild(el('span', 'ev ev-' + ((r['证据等级'] || 'C').charAt(0)), r['证据等级']));
    card.appendChild(head);

    var meta = el('div', 'card-meta');
    meta.appendChild(el('span', 'theme', r['所属主题']));
    meta.appendChild(el('span', 'hint', ''));
    card.appendChild(meta);

    card.appendChild(el('p', 'brief', r['内容']));

    function toggle() {
      var open = card.getAttribute('aria-expanded') === 'true';
      if (!open) { buildFull(card, r); }
      card.setAttribute('aria-expanded', open ? 'false' : 'true');
    }
    card.addEventListener('click', function (e) {
      if (e.target.closest('.full')) { return; }   /* 展开区域内允许选中文字 */
      toggle();
    });
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        toggle();
      }
    });
    return card;
  }

  function render() {
    var rows = filterData();
    var frag = document.createDocumentFragment();
    for (var i = 0; i < rows.length; i++) { frag.appendChild(makeCard(rows[i])); }
    cardsEl.textContent = '';
    cardsEl.appendChild(frag);

    if (!rows.length) {
      cardsEl.appendChild(el('p', 'empty', '没有匹配的条目，换个关键词或点掉分类试试。'));
    }

    var desc = [];
    if (state.cat) { desc.push('<b>' + state.cat + '</b>'); }
    if (state.q.trim()) { desc.push('“' + escapeHtml(state.q.trim()) + '”'); }
    statusEl.innerHTML = desc.length
      ? desc.join(' · ') + ' 命中 ' + rows.length + ' 条 / 共 ' + DATA.length + ' 条'
      : '共 ' + rows.length + ' 条';
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function setCat(cat) {
    state.cat = (state.cat === cat) ? '' : cat;
    var chips = catsEl.querySelectorAll('.chip');
    for (var i = 0; i < chips.length; i++) {
      chips[i].setAttribute('aria-pressed', String(chips[i].dataset.cat === state.cat));
    }
    render();
  }

  catsEl.addEventListener('click', function (e) {
    var chip = e.target.closest('.chip');
    if (chip) { setCat(chip.dataset.cat); }
  });

  inputEl.addEventListener('input', function () {
    state.q = inputEl.value;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(render, 120);
  });

  function start(rows, mode) {
    DATA = rows;
    modeEl.textContent = mode;
    render();
  }

  fetch('data.json', { cache: 'no-store' })
    .then(function (res) {
      if (!res.ok) { throw new Error('HTTP ' + res.status); }
      return res.json();
    })
    .then(function (all) { start(all, 'data.json'); })
    .catch(function () { start(EMBEDDED, '内嵌快照（file:// 无法读取 data.json）'); });
})();
</script>
</body>
</html>
"""


def main():
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "data.json").read_text(encoding="utf-8"))

    # 把全量数据内嵌进页面，保证 file:// 双击打开时搜索和筛选依然可用
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    html = HTML.replace("__DATA__", payload).replace("__TOTAL__", str(len(data)))

    out = root / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}  内嵌 {len(data)} 条  大小 {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

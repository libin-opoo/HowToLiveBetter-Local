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
<script>
/* 在样式生效前定好主题，避免深色模式打开时先闪一下白底。
   模式存 localStorage：auto（跟随系统）/ light / dark。 */
(function () {
  var mode = 'auto';
  try { mode = localStorage.getItem('htlb.theme') || 'auto'; } catch (e) { /* 忽略 */ }
  if (mode !== 'light' && mode !== 'dark') {
    mode = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? 'dark' : 'light';
  }
  document.documentElement.setAttribute('data-theme', mode);
})();
</script>
<style>
  /* 浅色（默认）。文字色都按 WCAG AA 4.5:1 选过，由 tools/check_theme.py 验证 */
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
    --ink-2:#4a5b6d;
    --ink-3:#5c6e84;
    --border-hover:#bcd9f7;
    --border-open:#aed4f6;
    --shadow:0 4px 16px rgba(47,127,216,.08);
    --shadow-open:0 6px 20px rgba(47,127,216,.10);
    --focus-ring:rgba(47,127,216,.15);
    --brief:#33414f;
    --src:#4a5b6d;
    --mark-bg:#b6dcff;
    --mark-ink:#0f2a45;
    --err:#b3271e;
    --ev-a-bg:#1f66b4;
    --ev-a-ink:#ffffff;
    --ev-b-bg:#e6f2ff;
    --ev-b-ink:#1f66b4;
    --ev-b-border:#c7e2fb;
    --ev-c-bg:#eef3f9;
    --ev-c-ink:#4a5b6d;
    --ev-c-border:#e2e9f1;
    --chip-on-bg:#1f66b4;
    --chip-on-ink:#ffffff;
    --radius:14px;
  }

  /* 深色 */
  :root[data-theme="dark"]{
    color-scheme: dark;
    --bg:#0f151d;
    --surface:#182029;
    --line:#2b3644;
    --line-soft:#232c37;
    --primary:#5aa9f0;
    --primary-dark:#9ecbf5;
    --primary-soft:#1b2836;
    --ink:#e8eef5;
    --ink-2:#aebccb;
    --ink-3:#93a3b4;
    --border-hover:#3b4a5c;
    --border-open:#4d6785;
    --shadow:0 4px 18px rgba(0,0,0,.40);
    --shadow-open:0 8px 26px rgba(0,0,0,.50);
    --focus-ring:rgba(90,169,240,.28);
    --brief:#cbd6e2;
    --src:#9fb0c2;
    --mark-bg:#3a6ea8;
    --mark-ink:#f2f8ff;
    --err:#ff9a90;
    --ev-a-bg:#9ecbf5;
    --ev-a-ink:#0f2438;
    --ev-b-bg:#1b2836;
    --ev-b-ink:#9ecbf5;
    --ev-b-border:#2f4a66;
    --ev-c-bg:#222c38;
    --ev-c-ink:#aebccb;
    --ev-c-border:#2b3644;
    --chip-on-bg:#9ecbf5;
    --chip-on-ink:#0f2438;
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
  .bar-row{display:flex;gap:8px;align-items:stretch}
  .search{position:relative;flex:1 1 auto;min-width:0}
  .search input{
    display:block;width:100%;padding:12px 76px 12px 14px;
    font:inherit;font-size:1rem;color:var(--ink);
    background:var(--surface);border:1px solid var(--line);
    border-radius:12px;outline:none;
    -webkit-appearance:none;appearance:none;
    transition:border-color .15s,box-shadow .15s;
  }
  .kbd{
    position:absolute;right:10px;top:50%;transform:translateY(-50%);
    font:inherit;font-size:.7rem;line-height:1.5;
    color:var(--ink-2);background:var(--primary-soft);
    border:1px solid var(--line);border-radius:6px;padding:1px 6px;
    pointer-events:none;white-space:nowrap;
  }
  .theme-btn{
    flex:0 0 auto;padding:0 14px;border-radius:12px;
    border:1px solid var(--line);background:var(--surface);color:var(--primary-dark);
    font:inherit;font-size:.875rem;cursor:pointer;white-space:nowrap;
    transition:background .15s,border-color .15s;
  }
  .theme-btn:hover{background:var(--primary-soft);border-color:var(--border-hover)}
  .theme-btn:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .search input::placeholder{color:var(--ink-3)}
  .search input:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--focus-ring)}

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
  .chip:hover{border-color:var(--border-hover);background:var(--primary-soft)}
  .chip:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .chip[aria-pressed="true"]{background:var(--chip-on-bg);border-color:var(--chip-on-bg);color:var(--chip-on-ink);font-weight:600}

  .status{
    margin:14px 2px 10px;color:var(--ink-2);font-size:.875rem;
    display:flex;gap:8px 14px;flex-wrap:wrap;justify-content:space-between;
  }
  .status b{color:var(--primary-dark)}
  .status-sort{white-space:nowrap;color:var(--ink-3)}

  /* ---------- 卡片列表 ---------- */
  .cards{display:grid;gap:12px;grid-template-columns:1fr;align-items:start}
  @media (min-width:780px){ .cards{grid-template-columns:repeat(2,minmax(0,1fr))} }

  .card{
    min-width:0;
    background:var(--surface);border:1px solid var(--line-soft);
    border-radius:var(--radius);padding:14px 16px;
    cursor:pointer;transition:border-color .15s,box-shadow .15s;
  }
  .card:hover{border-color:var(--border-hover);box-shadow:var(--shadow)}
  .card:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .card[aria-expanded="true"]{border-color:var(--border-open);box-shadow:var(--shadow-open)}

  .card-head{display:flex;gap:10px;align-items:flex-start}
  .card-title{margin:0;flex:1 1 auto;min-width:0;font-size:1rem;font-weight:600;line-height:1.5}
  .ev{
    flex:0 0 auto;display:inline-block;padding:1px 9px;border-radius:999px;
    font-size:.75rem;font-weight:700;line-height:1.7;white-space:nowrap;
  }
  .ev-A{background:var(--ev-a-bg);color:var(--ev-a-ink)}
  .ev-B{background:var(--ev-b-bg);color:var(--ev-b-ink);border:1px solid var(--ev-b-border)}
  .ev-C{background:var(--ev-c-bg);color:var(--ev-c-ink);border:1px solid var(--ev-c-border)}

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
    margin:10px 0 0;font-size:.9rem;color:var(--brief);
    display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
    line-clamp:2;overflow:hidden;
  }
  /* 搜索时放宽摘要行数，让命中的关键词更容易露出来 */
  .cards.searching .brief{-webkit-line-clamp:4;line-clamp:4}
  mark{background:var(--mark-bg);color:var(--mark-ink);border-radius:3px;padding:0 1px}
  .card[aria-expanded="true"] .brief{display:block;overflow:visible}

  .full{display:none;margin-top:12px;padding-top:12px;border-top:1px dashed var(--line)}
  .card[aria-expanded="true"] .full{display:block}
  .full dl{margin:0;display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 12px;font-size:.88rem}
  .full dt{color:var(--ink-2);white-space:nowrap}
  .full dd{margin:0;min-width:0}
  .full .src{color:var(--src);word-break:break-all}

  .empty{padding:44px 8px;text-align:center;color:var(--ink-2);font-size:.9rem}

  .foot{
    margin-top:36px;padding-top:16px;border-top:1px solid var(--line);
    color:var(--ink-2);font-size:.78rem;line-height:1.8;
  }
  .foot a{color:var(--primary-dark)}
  .foot code{
    background:var(--primary-soft);color:var(--primary-dark);
    padding:1px 5px;border-radius:5px;font-size:.76rem;
  }
  [hidden]{display:none !important}

  /* 底部：数据导入导出 */
  .io{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 10px}
  .btn{
    padding:8px 16px;border-radius:10px;border:1px solid var(--line);
    background:var(--surface);color:var(--primary-dark);
    font:inherit;font-size:.875rem;line-height:1.3;cursor:pointer;
    transition:background .15s,border-color .15s;
  }
  .btn:hover{background:var(--primary-soft);border-color:var(--border-hover)}
  .btn:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
  .btn-ghost{background:transparent;color:var(--ink-2)}
  .io-msg{margin:0 0 10px;font-size:.8rem;line-height:1.6;color:var(--primary-dark)}
  .io-msg:empty{display:none}
  .io-msg.err{color:var(--err)}
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
    <div class="bar-row">
      <div class="search">
        <input id="q" type="search" placeholder="搜索生活循证建议"
               autocomplete="off" aria-label="搜索生活循证建议">
        <kbd class="kbd" id="kbd-hint" aria-hidden="true">Ctrl K</kbd>
      </div>
      <button class="theme-btn" id="theme-btn" type="button"
              title="配色模式" aria-label="配色模式">自动</button>
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
    <div class="io">
      <button class="btn" id="export-btn" type="button">导出数据</button>
      <button class="btn" id="import-btn" type="button">导入数据</button>
      <button class="btn btn-ghost" id="reset-btn" type="button" hidden>恢复内置数据</button>
      <input id="file-input" type="file" accept="application/json,.json" hidden>
    </div>
    <p class="io-msg" id="io-msg" role="status"></p>
    <p>
      导入导出全部在你自己浏览器里完成，数据不会上传到任何服务器。
      浏览器无法直接改写磁盘上的 <code>data.json</code>：导入会替换本页正在使用的数据并保存在本机浏览器；
      要让磁盘文件也跟着更新，导入后点「导出数据」，用它覆盖项目里的 <code>data.json</code>。
    </p>
    <p>
      数据取自 <a href="https://github.com/eternity4719/HowToLiveBetter" target="_blank" rel="noopener">eternity4719/HowToLiveBetter</a>，
      正文按 <a href="https://creativecommons.org/licenses/by/4.0/deed.zh" target="_blank" rel="noopener">CC BY 4.0</a> 发布，版权归原作者所有。
      本页为本地镜像，内容未作改动。
    </p>
    <p>当前数据来源：<span class="mode" id="mode">加载中…</span></p>
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

  /* 搜索范围：只匹配 data.json 的标题、内容、所属主题三个字段 */
  var SEARCH_FIELDS = ['标题', '内容', '所属主题'];

  /* 模糊匹配：按空白拆成多个关键词，全部命中才算匹配（AND） */
  function terms() {
    var q = state.q.trim().toLowerCase();
    return q ? q.split(/\s+/).filter(Boolean) : [];
  }

  function matchTerms(r, ts) {
    if (!ts.length) { return true; }
    var hay = SEARCH_FIELDS.map(function (f) { return r[f] || ''; })
                           .join('\n').toLowerCase();
    for (var i = 0; i < ts.length; i++) {
      if (hay.indexOf(ts[i]) === -1) { return false; }
    }
    return true;
  }

  function filterData(ts) {
    var themes = state.cat ? CATEGORIES[state.cat] : null;
    return DATA.filter(function (r) {
      if (themes && themes.indexOf(r['所属主题']) === -1) { return false; }
      return matchTerms(r, ts);
    });
  }

  /* 证据等级排序：A -> B -> C，同级保持 data.json 里的原始顺序 */
  var EV_RANK = { A: 0, B: 1, C: 2 };
  function evRank(level) {
    var k = (level || 'C').trim().charAt(0).toUpperCase();
    return EV_RANK[k] == null ? 3 : EV_RANK[k];
  }
  function sortByEvidence(rows) {
    return rows
      .map(function (r, i) { return { r: r, i: i }; })
      .sort(function (a, b) {
        var d = evRank(a.r['证据等级']) - evRank(b.r['证据等级']);
        return d !== 0 ? d : a.i - b.i;
      })
      .map(function (x) { return x.r; });
  }

  /* 把命中的关键词包成 <mark>，只用 DOM 节点拼，不碰 innerHTML */
  function setText(el, text, ts) {
    text = text || '';
    if (!ts || !ts.length) { el.textContent = text; return; }
    var lower = text.toLowerCase();
    var ranges = [];
    for (var i = 0; i < ts.length; i++) {
      var t = ts[i], from = 0, idx;
      if (!t) { continue; }
      while ((idx = lower.indexOf(t, from)) !== -1) {
        ranges.push([idx, idx + t.length]);
        from = idx + t.length;
      }
    }
    if (!ranges.length) { el.textContent = text; return; }
    ranges.sort(function (a, b) { return a[0] - b[0]; });
    var merged = [ranges[0]];
    for (var j = 1; j < ranges.length; j++) {
      var last = merged[merged.length - 1];
      if (ranges[j][0] <= last[1]) { last[1] = Math.max(last[1], ranges[j][1]); }
      else { merged.push(ranges[j]); }
    }
    var pos = 0;
    for (var k = 0; k < merged.length; k++) {
      var rg = merged[k];
      if (rg[0] > pos) { el.appendChild(document.createTextNode(text.slice(pos, rg[0]))); }
      var mk = document.createElement('mark');
      mk.textContent = text.slice(rg[0], rg[1]);
      el.appendChild(mk);
      pos = rg[1];
    }
    if (pos < text.length) { el.appendChild(document.createTextNode(text.slice(pos))); }
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

  function makeCard(r, ts) {
    var card = el('article', 'card');
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-expanded', 'false');

    var head = el('div', 'card-head');
    var h2 = el('h2', 'card-title');
    setText(h2, r['标题'], ts);
    head.appendChild(h2);
    head.appendChild(el('span', 'ev ev-' + ((r['证据等级'] || 'C').charAt(0)), r['证据等级']));
    card.appendChild(head);

    var meta = el('div', 'card-meta');
    var theme = el('span', 'theme');
    setText(theme, r['所属主题'], ts);
    meta.appendChild(theme);
    meta.appendChild(el('span', 'hint', ''));
    card.appendChild(meta);

    var brief = el('p', 'brief');
    setText(brief, r['内容'], ts);
    card.appendChild(brief);

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

  /* ---------------- 配色模式 ---------------- */
  var THEME_KEY = 'htlb.theme';
  var THEME_MODES = ['auto', 'light', 'dark'];
  var THEME_LABELS = { auto: '自动', light: '浅色', dark: '深色' };
  var themeBtn = document.getElementById('theme-btn');
  var darkMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function readThemeMode() {
    try {
      var t = localStorage.getItem(THEME_KEY);
      return THEME_MODES.indexOf(t) >= 0 ? t : 'auto';
    } catch (e) { return 'auto'; }
  }

  /* auto 时看系统；其余用固定值 */
  function resolveTheme(mode) {
    if (mode === 'auto') { return (darkMedia && darkMedia.matches) ? 'dark' : 'light'; }
    return mode;
  }

  /* persist 只在用户主动切换时才为真：每次加载都写一遍 localStorage 在 file:// 下
     会产生同步磁盘写，实测让首屏多花几十毫秒。 */
  function applyTheme(mode, persist) {
    document.documentElement.setAttribute('data-theme', resolveTheme(mode));
    themeBtn.textContent = THEME_LABELS[mode];
    themeBtn.title = '配色模式：' + THEME_LABELS[mode] + '（点击切换）';
    themeBtn.setAttribute('aria-label', themeBtn.title);
    if (persist) {
      try { localStorage.setItem(THEME_KEY, mode); } catch (e) { /* 忽略 */ }
    }
  }

  themeBtn.addEventListener('click', function () {
    var m = readThemeMode();
    applyTheme(THEME_MODES[(THEME_MODES.indexOf(m) + 1) % THEME_MODES.length], true);
  });

  /* 系统配色变了，跟随模式下要立刻跟上 */
  if (darkMedia) {
    var onSchemeChange = function () {
      if (readThemeMode() === 'auto') { applyTheme('auto'); }
    };
    if (darkMedia.addEventListener) { darkMedia.addEventListener('change', onSchemeChange); }
    else if (darkMedia.addListener) { darkMedia.addListener(onSchemeChange); }
  }

  /* ---------------- 快捷键 ---------------- */
  /* Mac 显示 ⌘K，其它平台显示 Ctrl K */
  var kbdHint = document.getElementById('kbd-hint');
  var isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '');
  kbdHint.textContent = isMac ? '\u2318 K' : 'Ctrl K';

  document.addEventListener('keydown', function (e) {
    /* Ctrl+K / Cmd+K：聚焦搜索框（拦掉浏览器自带的搜索栏） */
    if ((e.ctrlKey || e.metaKey) && !e.altKey && String(e.key).toLowerCase() === 'k') {
      e.preventDefault();
      inputEl.focus();
      inputEl.select();
      return;
    }
    /* Esc：清空搜索；搜索本来就空时，顺手取消分类筛选 */
    if (e.key === 'Escape' || e.key === 'Esc') {
      if (state.q) {
        state.q = '';
        inputEl.value = '';
        clearTimeout(debounceTimer);
        render();
      } else if (state.cat) {
        setCat(state.cat);
      }
    }
  });

  /* 一次性同步渲染整份结果。
     曾经试过「先渲染 24 张、剩下的分片补齐」，用 tools/check_perf.py 实测后回退了：
     分片之间浏览器会对整个网格重新布局，650 张的整体渲染从 ~220ms 涨到 ~478ms（2 倍多），
     而首屏并没有真的提前（244ms vs 253ms）。一次布局比多次便宜得多。 */
  function render() {
    var ts = terms();
    var rows = sortByEvidence(filterData(ts));

    var frag = document.createDocumentFragment();
    for (var i = 0; i < rows.length; i++) { frag.appendChild(makeCard(rows[i], ts)); }
    cardsEl.textContent = '';
    cardsEl.classList.toggle('searching', ts.length > 0);
    cardsEl.appendChild(frag);

    if (!rows.length) {
      cardsEl.appendChild(el('p', 'empty', '没有匹配的条目，换个关键词或点掉分类试试。'));
    }

    var desc = [];
    if (state.cat) { desc.push('<b>' + state.cat + '</b>'); }
    if (state.q.trim()) { desc.push('“' + escapeHtml(state.q.trim()) + '”'); }
    var main = desc.length
      ? desc.join(' · ') + ' 命中 ' + rows.length + ' 条 / 共 ' + DATA.length + ' 条'
      : '共 ' + rows.length + ' 条';
    statusEl.innerHTML = '<span class="status-main">' + main + '</span>' +
      '<span class="status-sort">按证据等级 A→C 排序</span>';
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

  /* ---------------- 本地数据导入 / 导出 ----------------
     全程在浏览器内完成：导出用 Blob 下载，导入用 FileReader 读取并校验，
     都不经过网络。浏览器无法直接改写磁盘上的 data.json，所以导入后的数据
     存在 localStorage 里，并靠「导出数据」把文件同步回项目目录。 */

  var LS_KEY = 'htlb.dataset.v1';
  var REQUIRED_FIELDS = ['标题', '内容', '所属主题', '成本', '收益', '证据等级', '来源出处'];
  var exportBtn = document.getElementById('export-btn');
  var importBtn = document.getElementById('import-btn');
  var resetBtn = document.getElementById('reset-btn');
  var fileEl = document.getElementById('file-input');
  var msgEl = document.getElementById('io-msg');

  function setMsg(text, isErr) {
    msgEl.textContent = text || '';
    msgEl.classList.toggle('err', !!isErr);
  }

  /* 导出：把当前正在使用的数据存成 data.json 下载下来 */
  function exportData() {
    var text = JSON.stringify(DATA, null, 2) + '\n';
    var blob = new Blob([text], { type: 'application/json;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'data.json';
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    setMsg('已导出 ' + DATA.length + ' 条到 data.json');
  }

  /* 校验导入的数据：顶层是数组，每条都有 7 个必填字符串字段，证据等级以 A/B/C 开头 */
  function validateRecords(obj) {
    if (!Array.isArray(obj)) { return ['JSON 顶层必须是数组']; }
    if (!obj.length) { return ['数组是空的，没有可导入的数据']; }
    var errs = [];
    for (var i = 0; i < obj.length && errs.length < 5; i++) {
      var r = obj[i];
      if (!r || typeof r !== 'object' || Array.isArray(r)) {
        errs.push('第 ' + (i + 1) + ' 条不是对象');
        continue;
      }
      for (var j = 0; j < REQUIRED_FIELDS.length; j++) {
        var f = REQUIRED_FIELDS[j];
        if (typeof r[f] !== 'string' || !r[f].trim()) {
          errs.push('第 ' + (i + 1) + ' 条缺少字段「' + f + '」');
          break;
        }
      }
      var ev = r['证据等级'];
      if (typeof ev === 'string' && 'ABC'.indexOf(ev.trim().charAt(0).toUpperCase()) === -1) {
        errs.push('第 ' + (i + 1) + ' 条「证据等级」应以 A/B/C 开头');
      }
    }
    return errs;
  }

  function saveOverride(rows) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(rows)); return true; }
    catch (e) { return false; }
  }
  function loadOverride() {
    try {
      var s = localStorage.getItem(LS_KEY);
      if (!s) { return null; }
      var o = JSON.parse(s);
      return (Array.isArray(o) && o.length) ? o : null;
    } catch (e) { return null; }
  }
  function clearOverride() {
    try { localStorage.removeItem(LS_KEY); } catch (e) { /* 忽略 */ }
  }

  /* 换数据集：清掉当前的搜索和分类，避免旧筛选条件套在新数据上 */
  function applyDataset(rows, mode, imported) {
    DATA = rows;
    modeEl.textContent = mode;
    resetBtn.hidden = !imported;
    state.q = '';
    state.cat = '';
    inputEl.value = '';
    var chips = catsEl.querySelectorAll('.chip');
    for (var i = 0; i < chips.length; i++) { chips[i].setAttribute('aria-pressed', 'false'); }
    render();
  }

  function importFile(file) {
    var reader = new FileReader();
    reader.onload = function () {
      var obj;
      try { obj = JSON.parse(String(reader.result)); }
      catch (e) {
        setMsg('导入失败：不是合法的 JSON（' + e.message + '）', true);
        return;
      }
      var errs = validateRecords(obj);
      if (errs.length) {
        setMsg('导入失败：' + errs.join('；'), true);
        return;
      }
      var saved = saveOverride(obj);
      applyDataset(obj, '本地导入的数据' + (saved ? '（已存本机浏览器）' : '（仅本次会话）'), true);
      setMsg('已导入 ' + obj.length + ' 条，原数据未丢失，可用「导出数据」备份或用「恢复内置数据」还原' +
             (saved ? '' : '。注意：本浏览器存储空间不足，刷新后会回到原数据'));
    };
    reader.onerror = function () { setMsg('导入失败：读不到文件内容', true); };
    reader.readAsText(file, 'utf-8');
  }

  exportBtn.addEventListener('click', exportData);
  importBtn.addEventListener('click', function () { fileEl.click(); });
  fileEl.addEventListener('change', function () {
    var f = fileEl.files && fileEl.files[0];
    if (f) { importFile(f); }
    fileEl.value = '';   /* 允许重复导入同一个文件 */
  });
  resetBtn.addEventListener('click', function () {
    clearOverride();
    setMsg('已恢复内置数据');
    loadDefault();
  });

  /* 首屏不等待网络：先用内嵌数据同步渲染出来，再去看外部 data.json 有没有更新。
     两边内容一致就完全不重渲染（省下重建 650 张卡片的开销）。 */
  function fingerprint(rows) {
    if (!rows || !rows.length) { return '0'; }
    return rows.length + '|' + (rows[0]['标题'] || '') + '|' +
           (rows[rows.length - 1]['标题'] || '');
  }

  function loadDefault() {
    applyDataset(EMBEDDED, '内嵌快照', false);
    fetch('data.json', { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) { throw new Error('HTTP ' + res.status); }
        return res.json();
      })
      .then(function (all) {
        if (fingerprint(all) === fingerprint(EMBEDDED)) {
          modeEl.textContent = 'data.json（与内嵌副本一致）';
          return;
        }
        applyDataset(all, 'data.json', false);
      })
      .catch(function () {
        modeEl.textContent = '内嵌快照（file:// 无法读取 data.json）';
      });
  }

  /* 按钮上显示当前配色模式；<head> 里的早期脚本已经设过 data-theme，这里只是同步 UI */
  applyTheme(readThemeMode());

  /* 启动优先级：本机导入的数据 > data.json > 内嵌快照 */
  var override = loadOverride();
  if (override) {
    applyDataset(override, '本地导入的数据（已存本机浏览器）', true);
    setMsg('正在使用本机导入的数据，共 ' + override.length + ' 条');
  } else {
    loadDefault();
  }

  /* 供自动化测试调用，不参与页面交互 */
  window.__htlb = {
    exportText: function () { return JSON.stringify(DATA, null, 2) + '\n'; },
    count: function () { return DATA.length; }
  };
})();
</script>
</body>
</html>
"""


def _inject_assets(html, root):
    """把 assets/ 下的增量模块（*.css / *.js）内联进页面。

    这是增量模块与生成器的**唯一接触点**：只在 </head> 前和 </body> 前各插一段，
    模板 HTML 里的任何现有内容都不动。

    新增一个模块只要把文件丢进 assets/，不用再改这个生成器；想停用某个模块，
    把对应文件移出 assets/ 再重新生成即可。文件名决定注入顺序。
    """
    assets = root / "assets"
    if not assets.is_dir():
        return html

    css_parts, js_parts = [], []
    for f in sorted(assets.glob("*.css")):
        css_parts.append("/* ===== " + f.name + " ===== */\n" + f.read_text(encoding="utf-8"))
    for f in sorted(assets.glob("*.js")):
        code = f.read_text(encoding="utf-8")
        if "</script" in code:
            raise SystemExit(f"{f.name} 里出现了 </script，无法安全内联到页面")
        js_parts.append("/* ===== " + f.name + " ===== */\n" + code)

    if css_parts:
        html = html.replace("</head>", "<style>\n" + "\n".join(css_parts) + "\n</style>\n</head>", 1)
    if js_parts:
        html = html.replace("</body>", "<script>\n" + "\n".join(js_parts) + "\n</script>\n</body>", 1)
    return html


def main():
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "data.json").read_text(encoding="utf-8"))

    # 把全量数据内嵌进页面，保证 file:// 双击打开时搜索和筛选依然可用
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    html = HTML.replace("__DATA__", payload).replace("__TOTAL__", str(len(data)))

    # 增量模块：assets/ 下所有独立模块（解耦，移走文件即可回退）
    html = _inject_assets(html, root)

    out = root / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"已生成 {out}  内嵌 {len(data)} 条  大小 {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

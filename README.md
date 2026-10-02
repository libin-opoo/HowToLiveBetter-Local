# HowToLiveBetter-Local

《[高性价比人生指南](https://github.com/eternity4719/HowToLiveBetter)》的本地镜像 + 结构化数据抽取 + 本地检索页。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `upstream/` | 上游仓库的完整快照（正文、文档、工具、技能），不含 `.git` |
| `data.json` | 从正文抽取的结构化循证建议，**650 条** |
| `index.html` | 本地检索页：搜索框 + 主题分类导航 + 卡片列表（点击展开） |
| `tools/extract_data.py` | 抽取脚本：`upstream/book/*.md` → `data.json` |
| `tools/build_index.py` | 生成脚本：`data.json` → `index.html` |
| `tools/check_layout.py` | 布局测试：在 12 档屏幕宽度下检查横向溢出 |

## 数据来源

- 上游仓库：<https://github.com/eternity4719/HowToLiveBetter>
- 快照提交：`fcc93eb9a4bdc26e8a4e4c94bdaae0a89265927b`（2026-10-02）
- 数据源文件：`upstream/book/01-*.md` ~ `upstream/book/34-*.md`

## data.json 字段

共 650 条，按正文顺序排列。每条包含：

| 字段 | 含义 | 对应正文 |
| --- | --- | --- |
| `标题` | 条目标题 | `### N. 标题` |
| `内容` | 说人话，条目的通俗说明 | `- 说人话：` |
| `所属主题` | 所属章节主题，如「不要早死」 | 章节一级标题 |
| `成本` | 花掉什么 | `- 成本：` |
| `收益` | 换回什么 | `- 收益：` |
| `证据等级` | `A` / `B` / `C`（少数带括号说明） | `- 证据等级：` |
| `来源出处` | 期刊论文与官方文件 | `- 来源：` |
| `备注` | 附加说明（附加字段） | `- 备注：` |
| `源文件` | 来源文件路径（附加字段） | — |
| `条目编号` | `章节序号-条目序号`，如 `1-3`（附加字段） | — |

证据等级分布：A 425 · B 170 · C 50，另有 5 条带括号补充说明（如 `A（争议）`）。

## index.html 页面说明

- **搜索框**：跨 `标题 / 内容 / 所属主题 / 成本 / 收益 / 证据等级 / 来源出处 / 备注` 全文匹配，输入有 120ms 防抖。
- **主题分类导航**：横向滚动，目前放了「健康 / 金钱 / 职场」3 个分类，点一下筛选、再点一下取消。
  分类到章节主题的映射写在 `index.html` 里的 `CATEGORIES` 常量中（`tools/build_index.py` 内同名处），
  34 个章节主题当前已全部归入这 3 类，改这一处即可调整。
- **卡片列表**：默认展示全部 650 条；每条是卡片，点击（或聚焦后按 Enter/空格）展开
  `成本 / 收益 / 备注 / 来源出处`。展开内容做了按需渲染，首屏只渲染标题与摘要。
- **配色与适配**：浅蓝 + 白色，纯 CSS，无外部依赖；≥780px 两列、以下单列；已测 320–1920px 无横向溢出。

### 打开方式

- **直接双击**：`file://` 下浏览器会拦截 `fetch`，页面自动回退到构建时内嵌的**全量** 650 条数据，
  搜索和筛选照常可用（页脚会标注「内嵌快照」）。
- **本地起服务**（读取外部 `data.json`）：

  ```bash
  python3 -m http.server 8000
  # 打开 http://127.0.0.1:8000/index.html
  ```

## 重新生成

```bash
python3 tools/extract_data.py    # upstream/book/*.md -> data.json
python3 tools/build_index.py     # data.json          -> index.html
```

`extract_data.py` 会自检：7 个必填字段全非空，否则以非零码退出。

## 布局测试

```bash
python3 tools/check_layout.py                      # 默认 320 / 360 / 375 / ... / 1920 共 12 档
python3 tools/check_layout.py --widths 320,768,1440
python3 tools/check_layout.py --browser /path/to/msedge
```

脚本把 index.html 放进一个可调宽度的 iframe 里逐档测量（无头浏览器在 Windows 上有约 496px 的
最小窗口宽度，直接用 `--window-size` 测不到 320/375 这类手机宽度）。检查项：页面横向溢出、
元素越界、视口是否按预期生效。需要本机装有 Edge/Chrome。

## 许可与署名

内容与代码版权归原作者 **eternity4719** 所有：

- 正文内容：**[CC BY 4.0](upstream/LICENSE)** —— 转载、改编须署名并附原文链接。
- 工具代码：**[MIT](upstream/LICENSE-CODE)**。

本仓库仅为本地镜像与数据抽取，未改动上游正文；`upstream/LICENSE` 与 `upstream/LICENSE-CODE` 已随快照保留。

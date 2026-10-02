# HowToLiveBetter-Local

《[高性价比人生指南](https://github.com/eternity4719/HowToLiveBetter)》的本地镜像 + 结构化数据抽取。

## 目录结构

| 路径 | 说明 |
| --- | --- |
| `upstream/` | 上游仓库的完整快照（正文、文档、工具、技能），不含 `.git` |
| `data.json` | 从正文抽取的结构化循证建议，**650 条** |
| `index.html` | 最简展示页：把 `data.json` 的前 10 条用列表列出 |
| `tools/extract_data.py` | 抽取脚本：`upstream/book/*.md` → `data.json` |
| `tools/build_index.py` | 生成脚本：`data.json` → `index.html` |

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

## 重新生成

```bash
python3 tools/extract_data.py    # upstream/book/*.md -> data.json
python3 tools/build_index.py     # data.json          -> index.html
```

抽取脚本会自检：7 个必填字段全非空，否则以非零码退出。

## 查看 index.html

- **直接双击打开**：浏览器会拦截 `file://` 下的 `fetch`，页面自动回退到构建时内嵌的前 10 条快照，并给出提示。
- **本地起服务**（读取真实的 `data.json`）：

  ```bash
  python3 -m http.server 8000
  # 打开 http://127.0.0.1:8000/index.html
  ```

## 许可与署名

内容与代码版权归原作者 **eternity4719** 所有：

- 正文内容：**[CC BY 4.0](upstream/LICENSE)** —— 转载、改编须署名并附原文链接。
- 工具代码：**[MIT](upstream/LICENSE-CODE)**。

本仓库仅为本地镜像与数据抽取，未改动上游正文；`upstream/LICENSE` 与 `upstream/LICENSE-CODE` 已随快照保留。

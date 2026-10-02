#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 HowToLiveBetter 正文（book/*.md）提取循证建议，输出结构化 data.json。

数据来源: https://github.com/eternity4719/HowToLiveBetter
内容许可: CC BY 4.0 (Attribution 4.0 International), 作者 eternity4719

用法:
    python3 tools/extract_data.py
    python3 tools/extract_data.py --src upstream --out data.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

# 正文里的字段标签 -> data.json 的输出字段名
FIELD_MAP = {
    "成本": "成本",
    "说人话": "内容",
    "收益": "收益",
    "证据等级": "证据等级",
    "来源": "来源出处",
    "备注": "备注",
}

FIELD_RE = re.compile(r"^- (" + "|".join(FIELD_MAP) + r")：(.*)$")
H1_RE = re.compile(r"^# (?!#)(.*)$")
H3_RE = re.compile(r"^### (.+?)\s*$")
# "1. 不要早死" / "13. 紧急情况：先做什么"
TOPIC_NUM_RE = re.compile(r"^(\d+)\.\s*(.*)$")
# "### 3. 系安全带，前排后排都系"
ENTRY_NUM_RE = re.compile(r"^(\d+)\.\s*(.*)$")
COST_TAG_RE = re.compile(r"^<!--\s*成本标签:\s*(.*?)\s*-->\s*$")


def parse_chapter(path: Path):
    """解析一个章节文件，返回 (主题, 章节序号, [条目...])。"""
    lines = path.read_text(encoding="utf-8").splitlines()

    topic = ""
    chapter_no = None
    entries = []

    cur = None  # 当前条目

    def start_entry(raw_title):
        nonlocal cur
        cur = {"raw_title": raw_title, "fields": {}, "order": [], "cost_tag": None}

    def finish_entry():
        nonlocal cur
        if cur is not None:
            entries.append(cur)
            cur = None

    for line in lines:
        m1 = H1_RE.match(line)
        if m1 and not line.startswith("## "):
            # 新章节标题
            finish_entry()
            raw = m1.group(1).strip()
            mn = TOPIC_NUM_RE.match(raw)
            if mn and chapter_no is None:
                chapter_no = int(mn.group(1))
                topic = mn.group(2).strip()
            else:
                topic = raw
            continue

        if line.startswith("## "):
            # 其他级别的标题（例如文件末尾的「## 许可」）是段落边界：
            # 结束当前条目，避免尾部的版权说明被并进上一条的字段里
            finish_entry()
            continue

        m3 = H3_RE.match(line)
        if m3:
            finish_entry()
            start_entry(m3.group(1))
            continue

        if cur is None:
            continue

        mt = COST_TAG_RE.match(line.strip())
        if mt:
            if cur["cost_tag"] is None:
                cur["cost_tag"] = mt.group(1)
            continue

        mf = FIELD_RE.match(line)
        if mf:
            label = mf.group(1)
            cur["fields"][label] = mf.group(2).strip()
            if label not in cur["order"]:
                cur["order"].append(label)
            continue

        # 续行：接到上一个字段后面（跳过引用、表格、分隔线等块级标记）
        if line.strip() and cur["order"]:
            if re.match(r"^(#|\||>|```|---|\*\*\*)", line.strip()):
                continue
            last = cur["order"][-1]
            cur["fields"][last] = (cur["fields"][last] + "\n" + line.strip()).strip()

    finish_entry()
    return topic, chapter_no, entries


def build_records(src: Path):
    book = src / "book"
    files = sorted(book.glob("*.md"))
    if not files:
        sys.exit(f"找不到正文文件: {book}")

    records = []
    for path in files:
        topic, chapter_no, entries = parse_chapter(path)
        rel = path.relative_to(src).as_posix()
        for idx, e in enumerate(entries, start=1):
            mn = ENTRY_NUM_RE.match(e["raw_title"])
            if mn:
                entry_no = int(mn.group(1))
                title = mn.group(2).strip()
            else:
                entry_no = idx
                title = e["raw_title"].strip()

            rec = {"标题": title}
            for label, out_key in FIELD_MAP.items():
                val = e["fields"].get(label, "").strip()
                if out_key == "内容":
                    # 内容字段插到标题之后
                    rec["内容"] = val
                else:
                    rec[out_key] = val
            # 按要求的字段顺序重排
            ordered = {}
            ordered["标题"] = rec.pop("标题")
            ordered["内容"] = rec.pop("内容", "")
            ordered["所属主题"] = topic
            ordered["成本"] = rec.pop("成本", "")
            ordered["收益"] = rec.pop("收益", "")
            ordered["证据等级"] = rec.pop("证据等级", "")
            ordered["来源出处"] = rec.pop("来源出处", "")
            # 附加的可追溯字段
            ordered["备注"] = rec.pop("备注", "")
            ordered["源文件"] = rel
            ordered["条目编号"] = f"{chapter_no}-{entry_no}" if chapter_no else str(entry_no)
            records.append(ordered)

    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="upstream", help="上游仓库根目录")
    ap.add_argument("--out", default="data.json", help="输出文件")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    records = build_records(src)

    out = Path(args.out)
    out.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 自检
    missing = [
        (r["条目编号"], k)
        for r in records
        for k in ("标题", "内容", "所属主题", "成本", "收益", "证据等级", "来源出处")
        if not r.get(k)
    ]
    levels = {}
    for r in records:
        levels[r["证据等级"]] = levels.get(r["证据等级"], 0) + 1

    print(f"已写入 {out}  共 {len(records)} 条")
    print(f"主题数: {len({r['所属主题'] for r in records})}")
    print(f"证据等级分布: {dict(sorted(levels.items()))}")
    if missing:
        print(f"!! 缺失必填字段 {len(missing)} 处，前 10:")
        for m in missing[:10]:
            print("   ", m)
        sys.exit(1)
    print("自检通过: 所有条目的 7 个必填字段均非空")


if __name__ == "__main__":
    main()

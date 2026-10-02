#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端测试自动同步：造一个「有新提交」的假上游，跑完整同步流程，逐项校验。

全程在一个临时沙箱里做（把整个仓库复制过去），不会碰真实仓库，也不会推送。

用法:
    python3 tools/check_sync.py
    python3 tools/check_sync.py --keep    # 保留沙箱目录，便于人工查看
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 注意：正文里的标题是「### 42. 把灭火器放在顺手的地方」，解析后编号会被剥掉
NEW_TITLE = "把灭火器放在顺手的地方"
OLD_TITLE = "系安全带，前排后排都系"

results = []


def check(name, ok, detail=""):
    results.append({"name": name, "pass": bool(ok), "detail": str(detail)})


def run(cmd, cwd=None, check_ok=True):
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if check_ok and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))} 失败：\n{r.stdout}\n{r.stderr}")
    return r


def make_fake_upstream(dst: Path, base: Path):
    """基于真实上游内容造一个带新提交的假上游。"""
    shutil.copytree(base, dst, ignore=shutil.ignore_patterns(".git"))
    run(["git", "init", "-q"], dst)
    run(["git", "config", "user.name", "test"], dst)
    run(["git", "config", "user.email", "test@example.com"], dst)
    run(["git", "add", "-A"], dst)
    run(["git", "commit", "-q", "-m", "base"], dst)

    book = dst / "book" / "01-不要早死.md"
    text = book.read_text(encoding="utf-8")
    # 1) 改一条已有条目的收益栏
    assert "美国交通安全主管部门（NHTSA）估计，系安全带" in text
    text = text.replace("美国交通安全主管部门（NHTSA）估计，系安全带能让轿车前排乘员受致命伤的风险下降 45%",
                        "美国交通安全主管部门（NHTSA）估计，系安全带能让轿车前排乘员受致命伤的风险下降 46%（测试改动）")
    # 2) 末尾追加一条新条目
    text += """
### 42. 把灭火器放在顺手的地方
<!-- 成本标签: 钱=少 时间=少 毅力=否 收益=中 口径=死亡率 -->
- 成本：一只家用干粉灭火器几十到一百多元。
- 说人话：这是测试用的新增条目，用来验证自动同步能把新条目录进来。
- 收益：测试用收益说明，确认字段能被正确解析并写入 data.json。
- 证据等级：B
- 来源：本地测试，无文献。
- 备注：本条由 tools/check_sync.py 生成，仅用于测试。
"""
    book.write_text(text, encoding="utf-8")
    run(["git", "add", "-A"], dst)
    run(["git", "commit", "-q", "-m", "上游更新：新增 1 条，修改 1 条"], dst)
    return run(["git", "log", "-1", "--format=%H"], dst).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留沙箱")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="htlb-sync-test-"))
    sandbox = tmp / "repo"
    fake = tmp / "fake-upstream"
    try:
        # ---------- 准备沙箱 ----------
        shutil.copytree(ROOT, sandbox,
                        ignore=shutil.ignore_patterns(".git", "backups", ".sync.lock",
                                                      ".*-probe.html", "__pycache__"))
        run(["git", "init", "-q"], sandbox)
        run(["git", "config", "user.name", "libin-opoo"], sandbox)
        run(["git", "config", "user.email", "test@example.com"], sandbox)
        run(["git", "add", "-A"], sandbox)
        run(["git", "commit", "-q", "-m", "baseline"], sandbox)

        before = json.loads((sandbox / "data.json").read_text(encoding="utf-8"))
        before_text = (sandbox / "data.json").read_text(encoding="utf-8")
        check("沙箱初始 650 条", len(before) == 650, f"{len(before)} 条")

        fake_commit = make_fake_upstream(fake, ROOT / "upstream")
        check("假上游已就绪（有新提交）", bool(fake_commit), fake_commit[:8])

        sync = sandbox / "tools" / "sync_upstream.py"

        # ---------- 1. --check 应报出有更新 ----------
        r = run([sys.executable, str(sync), "--check", "--upstream-url", str(fake)], sandbox)
        check("--check 报出上游有更新", "上游有更新" in r.stdout, r.stdout.strip().replace("\n", " | ")[:90])

        # ---------- 2. 正式同步（不推送）----------
        r = run([sys.executable, str(sync), "--no-push", "--upstream-url", str(fake)], sandbox)
        check("同步命令成功退出", r.returncode == 0, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")

        after = json.loads((sandbox / "data.json").read_text(encoding="utf-8"))
        check("data.json 条数 650 → 651", len(after) == 651, f"{len(before)} → {len(after)}")

        titles = {r["标题"] for r in after}
        check("新增条已进入 data.json", NEW_TITLE in titles, NEW_TITLE)

        new_rec = next((r for r in after if r["标题"] == NEW_TITLE), None)
        if new_rec:
            fields_ok = all(new_rec.get(k) for k in
                            ["标题", "内容", "所属主题", "成本", "收益", "证据等级", "来源出处"])
            check("新增条目 7 个必填字段齐全", fields_ok,
                  f"证据等级={new_rec.get('证据等级')} 主题={new_rec.get('所属主题')}")
        else:
            check("新增条目 7 个必填字段齐全", False, "没找到新条目")

        old_rec = next((r for r in after if r["标题"] == OLD_TITLE), None)
        check("已有条目被修改并同步", old_rec and "46%" in old_rec["收益"],
              (old_rec["收益"][:60] if old_rec else "没找到"))

        # ---------- 3. 数据不丢失 ----------
        before_titles = {r["标题"] for r in before}
        after_titles = {r["标题"] for r in after}
        lost = before_titles - after_titles
        check("原有 650 条一条都没丢", not lost, f"丢失 {len(lost)} 条" if lost else "0 条丢失")
        same = sum(1 for r in before
                   if any(a["标题"] == r["标题"] and a == r for a in after))
        check("未被改动的条目内容逐字未变", same == 649, f"{same}/649 条完全一致")

        # ---------- 4. 版本备份 ----------
        backups = sorted((sandbox / "backups").glob("data-v1.0.0-*.json"))
        check("生成了旧版本备份", len(backups) == 1, backups[0].name if backups else "无")
        if backups:
            check("备份内容 == 同步前的 data.json",
                  backups[0].read_text(encoding="utf-8") == before_text,
                  "逐字符一致" if backups[0].read_text(encoding="utf-8") == before_text else "不一致")

        # ---------- 5. 版本号与状态 ----------
        st = json.loads((sandbox / "sync-state.json").read_text(encoding="utf-8"))
        check("版本号 1.0.0 → 1.1.0（有增删升 minor）", st["version"] == "1.1.0", st["version"])
        check("状态里条目数已更新", st["recordCount"] == 651, st["recordCount"])
        check("状态里记录了新上游 commit",
              st["upstream"]["commit"] == fake_commit, st["upstream"]["commit"][:8])
        check("版本历史追加了一条", len(st["history"]) == 2, f"{len(st['history'])} 条")
        if len(st["history"]) == 2:
            h = st["history"][-1]
            check("历史里的增删改统计正确",
                  (h["added"], h["removed"], h["changed"]) == (1, 0, 1),
                  f"added={h['added']} removed={h['removed']} changed={h['changed']}")

        # ---------- 6. index.html 重建 ----------
        html = (sandbox / "index.html").read_text(encoding="utf-8")
        check("index.html 已重建并含新条目", NEW_TITLE in html, "")
        check("index.html 内嵌数据同步到 651 条",
              json.loads(html.split('id="dataset" type="application/json">')[1].split("</script>")[0]).__len__() == 651, "")

        # ---------- 7. 上游快照已替换 ----------
        check("upstream/ 已换成新内容",
              "42. 把灭火器放在顺手的地方" in
              (sandbox / "upstream" / "book" / "01-不要早死.md").read_text(encoding="utf-8"), "")
        check("upstream/ 没有混进 .git",
              not (sandbox / "upstream" / ".git").exists(), "")

        # ---------- 8. git 提交 ----------
        r = run(["git", "log", "-1", "--format=%s%n%b"], sandbox)
        msg = r.stdout
        check("产生了提交且备注含版本号", "v1.1.0" in msg, msg.strip().splitlines()[0][:60])
        check("提交备注写明变更内容",
              "新增 1" in msg and "修改 1" in msg and NEW_TITLE[:10] in msg,
              " | ".join(msg.strip().splitlines()[1:4])[:110])
        r = run(["git", "status", "--porcelain"], sandbox)
        check("提交后工作区干净", r.stdout.strip() == "", r.stdout.strip()[:80])
        r = run(["git", "log", "--oneline"], sandbox)
        check("只新增了 1 个提交", len(r.stdout.strip().splitlines()) == 2,
              f"{len(r.stdout.strip().splitlines())} 个提交")

        # ---------- 9. 幂等 ----------
        r = run([sys.executable, str(sync), "--no-push", "--upstream-url", str(fake)], sandbox)
        check("再同步一次是空操作（幂等）", "没有更新" in r.stdout, r.stdout.strip()[:70])
        r = run(["git", "log", "--oneline"], sandbox)
        check("空操作没有产生多余提交", len(r.stdout.strip().splitlines()) == 2, "")

        # ---------- 10. 回滚 ----------
        r = run([sys.executable, str(sync), "--rollback", "1.0.0"], sandbox)
        rolled = json.loads((sandbox / "data.json").read_text(encoding="utf-8"))
        check("回滚到 v1.0.0 恢复 650 条", len(rolled) == 650, f"{len(rolled)} 条")
        check("回滚后新条目已移除", NEW_TITLE not in {r["标题"] for r in rolled}, "")
        check("回滚后是回滚前那份数据", rolled == before, "与同步前逐条一致" if rolled == before else "不一致")

        # ---------- 11. 失败不留烂摊子 ----------
        commit_before = run(["git", "log", "-1", "--format=%H"], sandbox).stdout.strip()
        r = run([sys.executable, str(sync), "--no-push",
                 "--upstream-url", str(tmp / "不存在的仓库")], sandbox, check_ok=False)
        check("上游不可用时明确失败", r.returncode != 0 and "失败" in (r.stderr + r.stdout),
              (r.stderr or r.stdout).strip().splitlines()[-1][:80] if (r.stderr or r.stdout).strip() else "")
        commit_after = run(["git", "log", "-1", "--format=%H"], sandbox).stdout.strip()
        check("失败后没有产生提交", commit_before == commit_after, "")
        check("失败后没有残留锁文件", not (sandbox / ".sync.lock").exists(), "")

    finally:
        if args.keep:
            print(f"\n沙箱保留在：{tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    width = max(len(r["name"]) for r in results)
    failed = 0
    print(f"\n{'检查项':<{width}}  结果   详情")
    print("-" * (width + 40))
    for r in results:
        if not r["pass"]:
            failed += 1
        print(f"{r['name']:<{width}}  {'✅' if r['pass'] else '❌'}    {r['detail']}")

    print(f"\n共 {len(results)} 项，通过 {len(results) - failed} 项，失败 {failed} 项。")
    if failed:
        sys.exit(1)
    print("自动同步、版本备份、提交备注、幂等、回滚、失败保护 —— 全部正常。")


if __name__ == "__main__":
    main()

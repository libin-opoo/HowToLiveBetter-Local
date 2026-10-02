#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步 GitHub 上游 HowToLiveBetter 的最新内容到本地，并打好版本。

一次同步按这个顺序做：

  1. 浅克隆上游仓库到临时目录，取最新 commit
  2. 和 sync-state.json 里记录的 commit 比对；没变就直接退出（幂等，可以随便重跑）
  3. 有更新时：
       a. 用最新内容整体替换 upstream/（不带 .git）
       b. 重跑 extract_data.py 生成新的 data.json
       c. 和上一版逐条比对，算出新增 / 删除 / 修改
       d. 版本号自增：有条目增减升 minor，只是内容修订升 patch
       e. 把旧版 data.json 备份进 backups/（只保留最近若干份）
       f. 重建 index.html
       g. 更新 sync-state.json（含完整版本历史）
       h. git add 受管路径后提交，备注写明版本号和本次变更
       i. 按需要推送
  4. 任何一步失败都不会提交，仓库保持原样

用法:
    python3 tools/sync_upstream.py                # 同步 + 提交 + 推送
    python3 tools/sync_upstream.py --no-push      # 只提交不推送
    python3 tools/sync_upstream.py --check        # 只看上游有没有更新，不改任何东西
    python3 tools/sync_upstream.py --init         # 首次建立 sync-state.json（以当前状态为基线）
    python3 tools/sync_upstream.py --rollback 1.0.0   # 回滚到某个版本的本地备份
    python3 tools/sync_upstream.py --upstream-url <url或本地路径>   # 换上游（测试用）
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "sync-state.json"
BACKUP_DIR = ROOT / "backups"
LOCK_FILE = ROOT / ".sync.lock"
KEEP_BACKUPS = 20

# 上游地址。这个环境里 github.com 的 HTTPS 被阻断，SSH 可用，所以默认走 SSH；
# 可以通过 --upstream-url 或 sync-state.json 里的 upstream.url 覆盖。
DEFAULT_UPSTREAM = "git@github.com:eternity4719/HowToLiveBetter.git"
# 只有这些路径由同步脚本负责，避免把无关的本地改动也提交进去
MANAGED_PATHS = ["upstream", "data.json", "index.html", "sync-state.json"]


def log(msg):
    print(msg, flush=True)


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd or ROOT),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败：\n{r.stdout}\n{r.stderr}")
    return r


def run_tool(script_name):
    """跑 extract_data.py / build_index.py，失败就抛出来，不吞掉。"""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / script_name)],
                       cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{script_name} 失败：\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


def clone_upstream(url, dest):
    """浅克隆上游，返回 (commit, 日期, 说明, 主题)。"""
    r = subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"拉取上游失败：{url}\n{r.stderr.strip()}")
    fmt = "%H%x00%ad%x00%s"
    out = subprocess.run(["git", "log", "-1", f"--format={fmt}", "--date=iso"],
                         cwd=str(dest), capture_output=True, text=True).stdout
    parts = out.strip().split("\x00")
    commit, date = parts[0], parts[1]
    subject = parts[2] if len(parts) > 2 else ""
    return commit, date, subject


def replace_upstream(src, dst):
    """用新拉下来的内容整体替换 upstream/（去掉 .git）。"""
    staging = dst.parent / ".upstream.new"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(src, staging, ignore=shutil.ignore_patterns(".git"))
    if dst.exists():
        shutil.rmtree(dst)
    staging.rename(dst)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def diff_records(old, new):
    """按标题比对（标题在本数据集里唯一）。返回 (新增, 删除, 修改标题列表)。"""
    o = {r["标题"]: r for r in old}
    n = {r["标题"]: r for r in new}
    if len(o) != len(old) or len(n) != len(new):
        raise RuntimeError("数据里出现重复标题，无法可靠比对，请先人工检查")
    added = [t for t in n if t not in o]
    removed = [t for t in o if t not in n]
    changed = [t for t in n if t in o and o[t] != n[t]]
    return added, removed, changed


def bump_version(version, added, removed):
    major, minor, patch = (int(x) for x in version.split("."))
    if added or removed:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def make_backup(version, data_text):
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = BACKUP_DIR / f"data-v{version}-{stamp}.json"
    path.write_text(data_text, encoding="utf-8")
    old = sorted(BACKUP_DIR.glob("data-v*.json"))
    for f in old[:-KEEP_BACKUPS]:
        f.unlink()
    return path


def build_commit_message(version, st, added, removed, changed, record_count, old_count):
    lines = [f"自动同步上游更新 v{version}", ""]
    lines.append(f"上游 {st['upstream']['repo']} @ {st['upstream']['commit'][:7]}")
    if st["upstream"].get("subject"):
        lines.append(f"来源 {st['upstream']['subject'][:110]}")
    lines.append(f"条目 {old_count} → {record_count}"
                 f"（新增 {len(added)}，删除 {len(removed)}，修改 {len(changed)}）")
    detail = []
    for t in added[:5]:
        detail.append(f"  + {t[:60]}")
    for t in changed[:5]:
        detail.append(f"  ~ {t[:60]}")
    for t in removed[:5]:
        detail.append(f"  - {t[:60]}")
    more = (len(added) + len(changed) + len(removed)) - len(detail)
    if detail:
        lines.append("变更：")
        lines.extend(detail)
        if more > 0:
            lines.append(f"  …另有 {more} 条")
    return "\n".join(lines)


def load_state():
    if not STATE_FILE.exists():
        raise SystemExit("找不到 sync-state.json。首次使用请先跑：\n"
                         "    python3 tools/sync_upstream.py --init")
    return read_json(STATE_FILE)


def save_state(st):
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")


def upstream_repo_label(url):
    s = url.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if "github.com" in s:
        s = s.split("github.com")[-1].lstrip(":/")
    return s


def do_init(url):
    """以当前仓库状态为基线建立 sync-state.json。"""
    if STATE_FILE.exists():
        raise SystemExit("sync-state.json 已存在，不用重复初始化。")
    with tempfile.TemporaryDirectory() as tmp:
        commit, date, subject = clone_upstream(url, Path(tmp) / "up")
    data = read_json(ROOT / "data.json")
    st = {
        "version": "1.0.0",
        "recordCount": len(data),
        "upstream": {"repo": upstream_repo_label(url), "url": url,
                     "commit": commit, "commitDate": date, "subject": subject},
        "syncCount": 0,
        "lastSyncAt": None,
        "history": [{"version": "1.0.0", "at": datetime.now().isoformat(timespec="seconds"),
                     "upstreamCommit": commit, "records": len(data),
                     "added": 0, "removed": 0, "changed": 0, "note": "初始基线"}],
    }
    save_state(st)
    log(f"已建立基线：v1.0.0，上游 {commit[:7]}，{len(data)} 条")


def do_check(url):
    st = load_state()
    url = url or st["upstream"].get("url") or DEFAULT_UPSTREAM
    with tempfile.TemporaryDirectory() as tmp:
        commit, date, subject = clone_upstream(url, Path(tmp) / "up")
    known = st["upstream"]["commit"]
    if commit == known:
        log(f"上游没有更新（仍是 {commit[:7]}，本地版本 v{st['version']}）")
        return 0
    log(f"上游有更新！")
    log(f"  本地: {known[:7]}")
    log(f"  上游: {commit[:7]}  {date}")
    log(f"  说明: {subject[:100]}")
    log("跑一次同步：python3 tools/sync_upstream.py")
    return 0


def do_rollback(version):
    cands = sorted(BACKUP_DIR.glob(f"data-v{version}-*.json"))
    if not cands:
        avail = sorted({f.name.split("-")[1] for f in BACKUP_DIR.glob("data-v*.json")})
        raise SystemExit(f"找不到 v{version} 的备份。现有备份版本：{avail or '（无）'}")
    src = cands[-1]
    data = read_json(src)
    (ROOT / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_tool("build_index.py")
    st = load_state()
    st["version"] = version
    st["recordCount"] = len(data)
    st["history"].append({"version": version, "at": datetime.now().isoformat(timespec="seconds"),
                          "upstreamCommit": st["upstream"]["commit"], "records": len(data),
                          "added": 0, "removed": 0, "changed": 0,
                          "note": f"从本地备份 {src.name} 回滚"})
    save_state(st)
    git("add", "-A", "--", *MANAGED_PATHS)
    git("commit", "-m", f"回滚到 v{version}（来自本地备份 {src.name}）")
    log(f"已回滚到 v{version}（{len(data)} 条），备份来源 {src.name}")
    return 0


def do_sync(url, push, dry_run):
    st = load_state()
    url = url or st["upstream"].get("url") or DEFAULT_UPSTREAM

    with tempfile.TemporaryDirectory() as tmp:
        commit, date, subject = clone_upstream(url, Path(tmp) / "up")
        upstream_tmp = Path(tmp) / "up"

        known = st["upstream"]["commit"]
        if commit == known:
            log(f"上游没有更新（仍是 {commit[:7]}），本地 v{st['version']}，什么都没做。")
            return 0

        log(f"上游有更新：{known[:7]} → {commit[:7]}")
        log(f"  {date}")
        log(f"  {subject[:110]}")

        old_data = read_json(ROOT / "data.json")

        if dry_run:
            log("（--dry-run，只报告不落地）")
            return 0

        # 先替换上游快照，再重新抽取
        replace_upstream(upstream_tmp, ROOT / "upstream")
        log("  upstream/ 已更新")
        log("  " + run_tool("extract_data.py").replace("\n", "\n  "))

        new_data = read_json(ROOT / "data.json")
        added, removed, changed = diff_records(old_data, new_data)
        record_count = len(new_data)
        version = bump_version(st["version"], added, removed)

        # 备份旧数据（此时 data.json 已是新版，所以用内存里的旧数据写备份）
        backup = make_backup(st["version"], json.dumps(old_data, ensure_ascii=False, indent=2) + "\n")
        log(f"  旧数据已备份：backups/{backup.name}")

        run_tool("build_index.py")

        st["version"] = version
        st["recordCount"] = record_count
        st["syncCount"] = st.get("syncCount", 0) + 1
        st["lastSyncAt"] = datetime.now().isoformat(timespec="seconds")
        st["upstream"] = {"repo": upstream_repo_label(url), "url": url,
                          "commit": commit, "commitDate": date, "subject": subject}
        st.setdefault("history", []).append({
            "version": version, "at": st["lastSyncAt"], "upstreamCommit": commit,
            "records": record_count, "added": len(added), "removed": len(removed),
            "changed": len(changed),
            "note": subject[:120]})
        save_state(st)

    msg = build_commit_message(version, st, added, removed, changed,
                               record_count, len(old_data))
    git("add", "-A", "--", *MANAGED_PATHS)
    r = git("diff", "--cached", "--quiet", check=False)
    if r.returncode == 0:
        log("没有需要提交的改动。")
        return 0
    git("commit", "-m", msg)
    log(f"已提交 v{version}（{record_count} 条，新增 {len(added)}，删除 {len(removed)}，修改 {len(changed)}）")

    if push:
        git("push", "origin", "HEAD")
        log("已推送到 GitHub")
    else:
        log("（--no-push，未推送）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="同步上游 HowToLiveBetter 并管理本地版本")
    ap.add_argument("--upstream-url", default=None, help="上游地址或本地路径")
    ap.add_argument("--no-push", action="store_true", help="只提交不推送")
    ap.add_argument("--check", action="store_true", help="只检查上游有没有更新")
    ap.add_argument("--init", action="store_true", help="首次建立 sync-state.json")
    ap.add_argument("--dry-run", action="store_true", help="只报告不落地")
    ap.add_argument("--rollback", metavar="VERSION", help="回滚到某个版本的本地备份")
    args = ap.parse_args()

    try:
        if args.check:
            return do_check(args.upstream_url)
        if args.init:
            return do_init(args.upstream_url or DEFAULT_UPSTREAM)
        if args.rollback:
            return do_rollback(args.rollback)

        # 简单互斥锁：定时任务和手动执行撞在一起时会互相踩，这里挡一下
        if LOCK_FILE.exists():
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age < 1800:
                raise SystemExit(f"检测到上一次同步还没结束（锁文件 {LOCK_FILE.name}，"
                                 f"{int(age)} 秒前）。确认是残留就删掉它再跑。")
            LOCK_FILE.unlink()
        LOCK_FILE.write_text(str(time.time()), encoding="utf-8")
        try:
            return do_sync(args.upstream_url, not args.no_push, args.dry_run)
        finally:
            LOCK_FILE.unlink(missing_ok=True)
    except RuntimeError as e:
        print(f"同步失败：{e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
daily_run.py — EcohTangoFoxtra v3.6 每日自动化管线

执行：模拟盘 + 静态报告 + 决策卡 + 基金日报 + 飞书（如已配置）
成功时写入 docs/.daily_run_status.json

用法:
  python3 scripts/daily_run.py              # 正常运行
  python3 scripts/daily_run.py --check-only # 仅检查今日是否已成功
  python3 scripts/daily_run.py --force      # 忽略今日已成功标记，强制重跑
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "docs" / ".daily_run_status.json"
PYTHON = sys.executable

REQUIRED_OUTPUTS = [
    ROOT / "docs" / "lite_card.md",
    ROOT / "docs" / "fund_report.md",
    ROOT / "docs" / "index.html",
]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def already_succeeded_today() -> bool:
    status = load_status()
    return status.get("date") == today_str() and status.get("success") is True


def write_status(success: bool, detail: dict | None = None) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": today_str(),
        "success": success,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        **(detail or {}),
    }
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_cmd(args: list[str], label: str) -> bool:
    log(f"▶ {label}")
    result = subprocess.run(
        args,
        cwd=ROOT,
        env={**os.environ, "LITE_VERBOSE": os.environ.get("LITE_VERBOSE", "1")},
    )
    if result.returncode != 0:
        log(f"❌ {label} 失败 (exit {result.returncode})")
        return False
    log(f"✅ {label} 完成")
    return True


def verify_outputs() -> tuple[bool, list[str]]:
    errors = []
    today = today_str()

    for path in REQUIRED_OUTPUTS:
        if not path.exists():
            errors.append(f"缺少输出: {path.relative_to(ROOT)}")
            continue
        if path.stat().st_size < 50:
            errors.append(f"输出过小: {path.relative_to(ROOT)}")

    for path in (ROOT / "docs" / "lite_card.md", ROOT / "docs" / "fund_report.md"):
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            # 允许 MM/DD 或 YYYY-MM-DD 格式
            mmdd = datetime.now().strftime("%m/%d")
            if today not in text and mmdd not in text:
                errors.append(f"{path.name} 未包含今日日期标记")

    return len(errors) == 0, errors


def run_daily(force: bool = False) -> int:
    if not force and already_succeeded_today():
        log(f"ℹ️ 今日 ({today_str()}) 已成功运行，跳过")
        return 0

    log("=" * 50)
    log(f"EcohTangoFoxtra 每日管线 {today_str()}")
    log("=" * 50)

    main = str(ROOT / "main_lite.py")

    steps = [
        ([PYTHON, main, "--paper", "--report", "--feishu"], "主管线 (paper + report + feishu)"),
        ([PYTHON, main, "--fund", "--feishu"], "基金日报 (fund + feishu)"),
    ]

    for cmd, label in steps:
        if not run_cmd(cmd, label):
            write_status(False, {"failed_step": label})
            return 1

    ok, errors = verify_outputs()
    if not ok:
        for e in errors:
            log(f"❌ 验证失败: {e}")
        write_status(False, {"validation_errors": errors})
        return 1

    write_status(True, {"outputs": [str(p.relative_to(ROOT)) for p in REQUIRED_OUTPUTS]})
    log("✅ 每日管线全部成功")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="EcohTangoFoxtra 每日自动化管线")
    parser.add_argument("--check-only", action="store_true", help="仅检查今日是否已成功")
    parser.add_argument("--force", action="store_true", help="强制重跑（忽略今日成功标记）")
    args = parser.parse_args()

    if args.check_only:
        if already_succeeded_today():
            log(f"✅ 今日 ({today_str()}) 已成功")
            sys.exit(0)
        log(f"⏳ 今日 ({today_str()}) 尚未成功")
        sys.exit(1)

    sys.exit(run_daily(force=args.force))


if __name__ == "__main__":
    main()

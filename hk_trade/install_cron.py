from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

MARKER_START = "# HK_TRADE_REPORTER_START"
MARKER_END = "# HK_TRADE_REPORTER_END"


def build_block(repo_root: Path, py_exec: str) -> str:
    log_file = repo_root / "logs" / "cron.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def line(expr: str, mode: str) -> str:
        cmd = (
            f"cd {shlex.quote(str(repo_root))} && "
            f"{shlex.quote(py_exec)} -m hk_trade.run_report --mode {mode} --send "
            f">> {shlex.quote(str(log_file))} 2>&1"
        )
        return f"{expr} {cmd}"

    rows = [
        MARKER_START,
        "CRON_TZ=Asia/Hong_Kong",
        line("30 9 * * 1-5", "intraday"),
        line("0,30 10-11 * * 1-5", "intraday"),
        line("0,30 13-15 * * 1-5", "intraday"),
        line("10 16 * * 1-5", "close"),
        line("0 22 * * *", "daily"),
        MARKER_END,
    ]
    return "\n".join(rows)


def read_crontab() -> str:
    try:
        proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except (PermissionError, FileNotFoundError):
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout


def replace_block(existing: str, new_block: str) -> str:
    pattern = re.compile(rf"{re.escape(MARKER_START)}[\s\S]*?{re.escape(MARKER_END)}\n?", re.MULTILINE)
    cleaned = re.sub(pattern, "", existing).strip()
    if cleaned:
        return f"{cleaned}\n\n{new_block}\n"
    return f"{new_block}\n"


def remove_block(existing: str) -> str:
    pattern = re.compile(rf"{re.escape(MARKER_START)}[\s\S]*?{re.escape(MARKER_END)}\n?", re.MULTILINE)
    return re.sub(pattern, "", existing).strip() + "\n"


def install(content: str) -> int:
    proc = subprocess.run(["crontab", "-"], input=content, text=True)
    return proc.returncode


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install cron jobs for hk_trade reporter")
    parser.add_argument("--print", action="store_true", dest="do_print", help="print resulting crontab")
    parser.add_argument("--install", action="store_true", help="install/update crontab")
    parser.add_argument("--remove", action="store_true", help="remove cron block")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd().resolve()
    block = build_block(repo_root=repo_root, py_exec=sys.executable)

    existing = read_crontab()
    target = replace_block(existing, block)

    if args.remove:
        target = remove_block(existing)

    if args.do_print or (not args.install and not args.remove):
        print(target, end="")

    if args.install or args.remove:
        rc = install(target)
        if rc != 0:
            print("failed to update crontab", file=sys.stderr)
            return rc
        action = "removed" if args.remove else "installed"
        print(f"cron block {action} successfully")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

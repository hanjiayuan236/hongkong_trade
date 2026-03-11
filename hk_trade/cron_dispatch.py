from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set
from zoneinfo import ZoneInfo

STATE_FILE = Path("/tmp/hk_trade_dispatch_state.json")
MAX_KEYS = 500

HK_TZ = ZoneInfo("Asia/Hong_Kong")
US_TZ = ZoneInfo("America/New_York")

HK_INTRADAY = {
    "09:30",
    "10:00",
    "10:30",
    "11:00",
    "11:30",
    "13:00",
    "13:30",
    "14:00",
    "14:30",
    "15:00",
    "15:30",
}
US_INTRADAY = {
    "09:30",
    "10:00",
    "10:30",
    "11:00",
    "11:30",
    "12:00",
    "12:30",
    "13:00",
    "13:30",
    "14:00",
    "14:30",
    "15:00",
    "15:30",
}


@dataclass(frozen=True)
class Task:
    key: str
    mode: str


def _fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def due_tasks(now_utc: datetime | None = None) -> List[Task]:
    now = now_utc.astimezone(timezone.utc) if now_utc else datetime.now(timezone.utc)
    hk = now.astimezone(HK_TZ)
    us = now.astimezone(US_TZ)

    tasks: List[Task] = []
    hk_key_date = hk.strftime("%Y-%m-%d")
    us_key_date = us.strftime("%Y-%m-%d")

    hk_hhmm = _fmt_hhmm(hk)
    us_hhmm = _fmt_hhmm(us)

    if _weekday(hk) and hk_hhmm in HK_INTRADAY:
        tasks.append(Task(key=f"hk:intraday:{hk_key_date}:{hk_hhmm}", mode="intraday"))
    if _weekday(hk) and hk_hhmm == "16:10":
        tasks.append(Task(key=f"hk:close:{hk_key_date}:{hk_hhmm}", mode="close"))
    if hk_hhmm == "22:00":
        tasks.append(Task(key=f"hk:daily:{hk_key_date}:{hk_hhmm}", mode="daily"))

    if _weekday(us) and us_hhmm in US_INTRADAY:
        tasks.append(Task(key=f"us:intraday:{us_key_date}:{us_hhmm}", mode="intraday"))
    if _weekday(us) and us_hhmm == "16:10":
        tasks.append(Task(key=f"us:close:{us_key_date}:{us_hhmm}", mode="close"))

    return tasks


def _load_state() -> Dict[str, float]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k): float(v) for k, v in payload.items()}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _save_state(state: Dict[str, float]) -> None:
    if len(state) > MAX_KEYS:
        sorted_items = sorted(state.items(), key=lambda x: x[1], reverse=True)[:MAX_KEYS]
        state = dict(sorted_items)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _run_report(mode: str) -> int:
    cmd = [sys.executable, "-m", "hk_trade.run_report", "--mode", mode, "--send"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode


def main() -> int:
    now_utc = datetime.now(timezone.utc)
    now_ts = now_utc.timestamp()
    hk_now = now_utc.astimezone(HK_TZ)
    us_now = now_utc.astimezone(US_TZ)
    tasks = due_tasks(now_utc)
    if not tasks:
        print(
            "[dispatch] tick no-task "
            f"utc={now_utc:%Y-%m-%d %H:%M} "
            f"hkt={hk_now:%Y-%m-%d %H:%M} "
            f"et={us_now:%Y-%m-%d %H:%M}"
        )
        return 0

    state = _load_state()
    code = 0

    for task in tasks:
        if task.key in state:
            print(f"[dispatch] skip duplicate key={task.key}")
            continue
        print(f"[dispatch] run key={task.key} mode={task.mode}")
        rc = _run_report(task.mode)
        if rc == 0:
            state[task.key] = now_ts
        else:
            code = rc

    _save_state(state)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


HKT = ZoneInfo("Asia/Hong_Kong")
TICK_RE = re.compile(r"\[dispatch\]\s+tick no-task\s+utc=[^\s]+\s+[^\s]+\s+hkt=(?P<hkt>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="8h cron/send verifier")
    parser.add_argument("--hours", type=float, default=8)
    parser.add_argument("--interval", type=int, default=300, help="seconds")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args()


def latest_tick_hkt(log_path: Path) -> Optional[datetime]:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    latest = None
    for m in TICK_RE.finditer(text):
        latest = m.group("hkt")
    if not latest:
        return None
    return datetime.strptime(latest, "%Y-%m-%d %H:%M").replace(tzinfo=HKT)


def latest_report_row(db_path: Path) -> dict:
    if not db_path.exists():
        return {"run_id": None, "mode": None, "created_at": None, "send_status": None}
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select run_id, mode, created_at, send_status from reports order by created_at desc limit 1"
        ).fetchone()
    if not row:
        return {"run_id": None, "mode": None, "created_at": None, "send_status": None}
    return {"run_id": row[0], "mode": row[1], "created_at": row[2], "send_status": row[3]}


def run_monitor(root: Path, hours: float, interval: int) -> int:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    cron_log = log_dir / "cron.log"
    db_path = root / "data" / "hk_reports.db"
    out_file = log_dir / "verify_8h.log"

    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=hours)

    with out_file.open("a", encoding="utf-8") as out:
        out.write(
            json.dumps(
                {
                    "event": "start",
                    "utc": start.isoformat(),
                    "hkt": start.astimezone(HKT).isoformat(),
                    "hours": hours,
                    "interval": interval,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

        while True:
            now = datetime.now(timezone.utc)
            if now >= end:
                break

            tick_hkt = latest_tick_hkt(cron_log)
            minutes_since_tick = None
            alert = None
            if tick_hkt is not None:
                minutes_since_tick = int((now.astimezone(HKT) - tick_hkt).total_seconds() // 60)
                if minutes_since_tick > 20:
                    alert = f"tick_gap_{minutes_since_tick}m"

            latest = latest_report_row(db_path)
            rec = {
                "event": "check",
                "utc": now.isoformat(),
                "hkt": now.astimezone(HKT).isoformat(),
                "cron_log_exists": cron_log.exists(),
                "cron_log_size": cron_log.stat().st_size if cron_log.exists() else 0,
                "last_tick_hkt": tick_hkt.isoformat() if tick_hkt else None,
                "minutes_since_last_tick": minutes_since_tick,
                "latest_report": latest,
            }
            if alert:
                rec["alert"] = alert

            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            time.sleep(interval)

        finish = datetime.now(timezone.utc)
        out.write(
            json.dumps(
                {
                    "event": "end",
                    "utc": finish.isoformat(),
                    "hkt": finish.astimezone(HKT).isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    return 0


def main() -> int:
    args = parse_args()
    return run_monitor(args.root.resolve(), args.hours, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())

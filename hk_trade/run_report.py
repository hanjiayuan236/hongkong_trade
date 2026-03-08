from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from hk_trade.collectors.etf import collect_etf_bundle
from hk_trade.collectors.options import collect_options_bundle
from hk_trade.config import LEVERAGE_MAP, load_config
from hk_trade.models import ReportContext
from hk_trade.report import render_report
from hk_trade.sender import gateway_healthy, send_report
from hk_trade.storage import (
    init_db,
    insert_error,
    insert_push_log,
    insert_report_run,
    next_issue_no,
    save_etf_snapshots,
    save_option_snapshots,
    save_report_path,
    save_strategies,
    update_send_status,
)
from hk_trade.strategy import build_risk_advice, generate_strategy_rows
from hk_trade.utils import now_in_tz, split_markdown_chunks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate HK ETF + options report")
    parser.add_argument("--mode", choices=["intraday", "close", "daily"], default="daily")
    parser.add_argument("--send", action="store_true", help="send to Telegram via OpenClaw")
    parser.add_argument("--dry-run", action="store_true", help="do not deliver external message")
    return parser.parse_args(argv)


def _archive_report(report_dir: Path, run_time, mode: str, run_id: str, content: str) -> Path:
    day_dir = report_dir / run_time.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{run_time.strftime('%H%M%S')}_{mode}_{run_id}.md"
    path.write_text(content, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config(Path.cwd())

    cfg.report_archive_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    init_db(cfg.db_path)

    now = now_in_tz(cfg.timezone)
    run_id = f"{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    issue_no = next_issue_no(cfg.db_path)
    created_at = now.isoformat()

    insert_report_run(cfg.db_path, run_id, args.mode, issue_no, created_at)

    quotes, news, quote_warnings = collect_etf_bundle(cfg.etf_watchlist, cfg.timezone)
    options_data, option_warnings = collect_options_bundle(cfg.options_symbols, cfg.timezone, LEVERAGE_MAP)
    all_warnings = quote_warnings + option_warnings

    strategy_rows = generate_strategy_rows(options_data)
    risk_advice = build_risk_advice(strategy_rows)

    ctx = ReportContext(
        run_id=run_id,
        run_time=now,
        mode=args.mode,
        issue_no=issue_no,
        quotes=quotes,
        news=news,
        options_data=options_data,
        strategy_rows=strategy_rows,
        risk_advice=risk_advice,
        data_sources=["新浪财经", "雪球", "Yahoo Finance"],
        warnings=all_warnings,
    )

    report_text = render_report(ctx)
    report_path = _archive_report(cfg.report_archive_dir, now, args.mode, run_id, report_text)

    save_report_path(cfg.db_path, run_id, str(report_path))
    save_etf_snapshots(cfg.db_path, run_id, created_at, quotes)
    save_option_snapshots(cfg.db_path, run_id, created_at, options_data)
    save_strategies(cfg.db_path, run_id, created_at, strategy_rows)

    for warning in all_warnings:
        insert_error(cfg.db_path, run_id, "collect", warning, None, created_at)

    if args.dry_run and not args.send:
        chunk_count = len(split_markdown_chunks(report_text, max_len=3400))
        update_send_status(cfg.db_path, run_id, "dry-run", None)
        print(f"[dry-run] report generated: {report_path}")
        print(f"[dry-run] chunks={chunk_count}, target={cfg.telegram_target}")
        return 0

    if not args.send:
        update_send_status(cfg.db_path, run_id, "skipped", None)
        print(f"report generated: {report_path}")
        print("send skipped (use --send)")
        return 0

    if not args.dry_run and not gateway_healthy(cfg.openclaw_bin):
        msg = "OpenClaw gateway unreachable; report archived without delivery"
        insert_error(cfg.db_path, run_id, "send", msg, None, created_at)
        update_send_status(cfg.db_path, run_id, "failed", msg)
        print(msg)
        print(f"report generated: {report_path}")
        return 1

    send_results = send_report(report_text, cfg, dry_run=args.dry_run)
    has_error = False
    for result in send_results:
        insert_push_log(
            cfg.db_path,
            run_id,
            created_at,
            result.chunk_index,
            result.status,
            result.response,
            result.error,
        )
        if result.status != "ok":
            has_error = True

    if has_error:
        update_send_status(cfg.db_path, run_id, "failed", "chunk delivery failed")
        print(f"delivery failed for some chunks. report: {report_path}")
        return 1

    status = "dry-run" if args.dry_run else "sent"
    update_send_status(cfg.db_path, run_id, status, None)
    print(f"delivery {status}. report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

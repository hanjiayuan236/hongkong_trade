from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from hk_trade.models import ETFQuote, OptionSymbolData, StrategyRow


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    issue_no INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    report_path TEXT,
    send_status TEXT DEFAULT 'pending',
    send_error TEXT
);

CREATE TABLE IF NOT EXISTS etf_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    price REAL,
    change_pct REAL,
    volume REAL,
    status TEXT,
    source TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS option_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    leverage TEXT,
    expiry_label TEXT,
    expiry_date TEXT,
    expiry_ts INTEGER,
    underlying_price REAL,
    calls_count INTEGER,
    puts_count INTEGER,
    has_data INTEGER,
    fetch_error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    leverage TEXT,
    expiry_label TEXT,
    expiry_date TEXT,
    strategy TEXT,
    sell_desc TEXT,
    strike_desc TEXT,
    call_price REAL,
    put_price REAL,
    premium REAL,
    yield_pct REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS push_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    chunk_index INTEGER,
    status TEXT,
    response TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def init_db(db_path: Path) -> None:
    ensure_parent(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def next_issue_no(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(issue_no), 0) + 1 FROM reports").fetchone()
    return int(row[0]) if row else 1


def insert_report_run(db_path: Path, run_id: str, mode: str, issue_no: int, created_at: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO reports(run_id, mode, issue_no, created_at) VALUES (?, ?, ?, ?)",
            (run_id, mode, issue_no, created_at),
        )
        conn.commit()


def save_report_path(db_path: Path, run_id: str, report_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE reports SET report_path = ? WHERE run_id = ?", (report_path, run_id))
        conn.commit()


def save_etf_snapshots(db_path: Path, run_id: str, created_at: str, quotes: List[ETFQuote]) -> None:
    rows = [
        (
            run_id,
            q.code,
            q.name,
            q.price,
            q.change_pct,
            q.volume,
            q.status,
            q.source,
            created_at,
        )
        for q in quotes
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO etf_snapshots(
                run_id, code, name, price, change_pct, volume, status, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def save_option_snapshots(db_path: Path, run_id: str, created_at: str, option_data: Dict[str, OptionSymbolData]) -> None:
    rows = []
    for symbol, data in option_data.items():
        if not data.chains:
            rows.append(
                (
                    run_id,
                    symbol,
                    data.leverage,
                    None,
                    None,
                    None,
                    data.spot_price,
                    0,
                    0,
                    0,
                    "; ".join(data.fetch_errors),
                    created_at,
                )
            )
        for label, chain in data.chains.items():
            rows.append(
                (
                    run_id,
                    symbol,
                    data.leverage,
                    label,
                    chain.expiry_date.isoformat(),
                    chain.expiry_ts,
                    chain.underlying_price,
                    len(chain.calls),
                    len(chain.puts),
                    1 if chain.has_data else 0,
                    chain.fetch_error,
                    created_at,
                )
            )

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO option_snapshots(
                run_id, symbol, leverage, expiry_label, expiry_date, expiry_ts,
                underlying_price, calls_count, puts_count, has_data, fetch_error, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def save_strategies(db_path: Path, run_id: str, created_at: str, rows: List[StrategyRow]) -> None:
    values = [
        (
            run_id,
            r.symbol,
            r.leverage,
            r.expiry_label,
            r.expiry_date.isoformat(),
            r.strategy,
            r.sell_desc,
            r.strike_desc,
            r.call_price,
            r.put_price,
            r.premium,
            r.yield_pct,
            created_at,
        )
        for r in rows
    ]

    if not values:
        return

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO strategies(
                run_id, symbol, leverage, expiry_label, expiry_date, strategy,
                sell_desc, strike_desc, call_price, put_price, premium, yield_pct, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.commit()


def update_send_status(db_path: Path, run_id: str, status: str, error: Optional[str] = None) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE reports SET send_status = ?, send_error = ? WHERE run_id = ?",
            (status, error, run_id),
        )
        conn.commit()


def insert_push_log(
    db_path: Path,
    run_id: str,
    created_at: str,
    chunk_index: int,
    status: str,
    response: Optional[Dict],
    error: Optional[str],
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO push_logs(run_id, chunk_index, status, response, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                chunk_index,
                status,
                json.dumps(response, ensure_ascii=False) if response else None,
                error,
                created_at,
            ),
        )
        conn.commit()


def insert_error(db_path: Path, run_id: str, stage: str, message: str, detail: Optional[str], created_at: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO errors(run_id, stage, message, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (run_id, stage, message, detail, created_at),
        )
        conn.commit()

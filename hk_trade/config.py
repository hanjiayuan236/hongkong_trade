from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


DEFAULT_ETF_WATCHLIST: Dict[str, str] = {
    "513130": "恒生科技ETF",
    "520880": "港股通创新药ETF",
    "159712": "港股通50ETF",
    "159331": "红利港股ETF",
    "513010": "港股通互联网ETF",
    "FXI": "富时25中国ETF",
}

OPTIONS_SYMBOLS = ["FXI", "YINN", "KWEB", "CWEB"]
LEVERAGE_MAP = {
    "FXI": "1x",
    "YINN": "3x",
    "KWEB": "1x",
    "CWEB": "2x",
}


@dataclass
class AppConfig:
    repo_root: Path
    timezone: str = "Asia/Hong_Kong"
    source_mode: str = "strict"
    openclaw_bin: str = "openclaw"
    openclaw_channel: str = "telegram"
    telegram_target: str = "@hk_etf_reports"
    db_path: Path = Path("./data/hk_reports.db")
    report_archive_dir: Path = Path("./reports")
    log_dir: Path = Path("./logs")
    etf_watchlist: Dict[str, str] = field(default_factory=lambda: DEFAULT_ETF_WATCHLIST.copy())
    options_symbols: List[str] = field(default_factory=lambda: list(OPTIONS_SYMBOLS))

    @property
    def cron_timezone(self) -> str:
        return self.timezone


def _parse_env_file(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def load_config(repo_root: Path | None = None) -> AppConfig:
    root = repo_root or Path.cwd()
    env_file = root / ".env"
    env_data = _parse_env_file(env_file)
    merged = {**env_data, **os.environ}

    cfg = AppConfig(
        repo_root=root,
        timezone=merged.get("TZ", "Asia/Hong_Kong"),
        source_mode=merged.get("SOURCE_MODE", "strict"),
        openclaw_bin=merged.get("OPENCLAW_BIN", "openclaw"),
        openclaw_channel=merged.get("OPENCLAW_CHANNEL", "telegram"),
        telegram_target=merged.get("TELEGRAM_TARGET", "@hk_etf_reports"),
        db_path=(root / merged.get("DB_PATH", "./data/hk_reports.db")).resolve(),
        report_archive_dir=(root / merged.get("REPORT_ARCHIVE_DIR", "./reports")).resolve(),
        log_dir=(root / merged.get("LOG_DIR", "./logs")).resolve(),
    )
    return cfg

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def http_get(url: str, timeout: int = 15, headers: Optional[Dict[str, str]] = None) -> str:
    req_headers = dict(DEFAULT_HEADERS)
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")


def http_get_json(url: str, timeout: int = 15, headers: Optional[Dict[str, str]] = None) -> Dict:
    text = http_get(url, timeout=timeout, headers=headers)
    return json.loads(text)


def safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def now_in_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5


def is_hk_trading_time(dt: datetime) -> bool:
    if is_weekend(dt):
        return False
    local_t = dt.time()
    morning = time(9, 30) <= local_t <= time(12, 0)
    afternoon = time(13, 0) <= local_t <= time(16, 0)
    return morning or afternoon


def next_half_hour(dt: datetime) -> datetime:
    base = dt.replace(second=0, microsecond=0)
    minute = base.minute
    if minute < 30:
        return base.replace(minute=30)
    return (base + timedelta(hours=1)).replace(minute=0)


def next_mode_update(dt: datetime, mode: str) -> datetime:
    if mode == "intraday":
        return next_half_hour(dt)
    if mode == "close":
        nxt = dt
        if dt.time() < time(22, 0):
            return dt.replace(hour=22, minute=0, second=0, microsecond=0)
        nxt = dt + timedelta(days=1)
        return nxt.replace(hour=22, minute=0, second=0, microsecond=0)
    nxt = dt + timedelta(days=1)
    return nxt.replace(hour=22, minute=0, second=0, microsecond=0)


def third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d + timedelta(days=14)


def add_months(year: int, month: int, count: int = 1) -> Tuple[int, int]:
    total = year * 12 + (month - 1) + count
    ny = total // 12
    nm = total % 12 + 1
    return ny, nm


def split_markdown_chunks(text: str, max_len: int = 3500) -> List[str]:
    if len(text) <= max_len:
        return [text]

    blocks = re.split(r"\n\n", text)
    chunks: List[str] = []
    current = ""

    for block in blocks:
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(block) <= max_len:
            current = block
        else:
            start = 0
            while start < len(block):
                end = start + max_len
                chunks.append(block[start:end])
                start = end

    if current:
        chunks.append(current)

    return chunks


def dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def parse_json_maybe(text: str) -> Optional[Dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def short_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"URL error: {exc.reason}"
    return str(exc)

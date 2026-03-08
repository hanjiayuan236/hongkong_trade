from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

from hk_trade.models import ETFQuote, NewsDigest
from hk_trade.utils import (
    dedupe_keep_order,
    http_get,
    is_hk_trading_time,
    now_in_tz,
    safe_float,
    short_error,
)


def _sina_symbol(code: str) -> str:
    if code.isdigit() and len(code) == 6:
        return ("sz" if code.startswith(("15", "16")) else "sh") + code
    if "." in code:
        base, suffix = code.split(".", 1)
        if suffix.upper() == "HK":
            return f"rt_hk{base}"
    return f"us{code.upper()}"


def _decode_best_effort(raw: bytes) -> str:
    for enc in ("gbk", "gb2312", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _fetch_sina_quote_lines(symbols: List[str]) -> str:
    joined = ",".join(symbols)
    url = f"https://hq.sinajs.cn/list={urllib.parse.quote(joined, safe=',')}"
    req = urllib.request.Request(
        url,
        headers={
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return _decode_best_effort(resp.read())


def _parse_sina_quote(code: str, name: str, payload: str, trading: bool) -> ETFQuote:
    price = None
    change_pct = None
    volume = None

    fields = payload.split(",") if payload else []

    if code.isdigit():
        prev = safe_float(fields[2] if len(fields) > 2 else None)
        price = safe_float(fields[3] if len(fields) > 3 else None)
        volume = safe_float(fields[8] if len(fields) > 8 else None)
        if price is not None and prev not in (None, 0):
            change_pct = round((price - prev) / prev * 100, 2)
    else:
        price = safe_float(fields[1] if len(fields) > 1 else None)
        pct = safe_float(fields[3] if len(fields) > 3 else None)
        if pct is not None:
            change_pct = pct
        volume = safe_float(fields[10] if len(fields) > 10 else None)

    status = "交易中" if trading else "休市"
    if price is None:
        status = "缺失"

    parsed_name = fields[0].strip() if fields and fields[0].strip() else name

    return ETFQuote(
        code=code,
        name=parsed_name,
        price=price,
        change_pct=change_pct,
        volume=volume,
        status=status,
        source="新浪财经",
    )


def fetch_etf_quotes(watchlist: Dict[str, str], tz_name: str) -> Tuple[List[ETFQuote], List[str]]:
    now = now_in_tz(tz_name)
    trading = is_hk_trading_time(now)
    warnings: List[str] = []

    symbol_map = {code: _sina_symbol(code) for code in watchlist}
    quote_by_code: Dict[str, ETFQuote] = {}

    try:
        text = _fetch_sina_quote_lines(list(symbol_map.values()))
        pattern = re.compile(r'var hq_str_(?P<sym>[^"]+)="(?P<body>.*)";')
        by_symbol: Dict[str, str] = {m.group("sym"): m.group("body") for m in pattern.finditer(text)}

        for code, cname in watchlist.items():
            sym = symbol_map[code]
            body = by_symbol.get(sym)
            quote_by_code[code] = _parse_sina_quote(code, cname, body or "", trading)
            if not body:
                warnings.append(f"新浪缺少 {code} 行情，已填充缺失值")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"新浪行情抓取失败: {short_error(exc)}")
        for code, cname in watchlist.items():
            quote_by_code[code] = ETFQuote(
                code=code,
                name=cname,
                price=None,
                change_pct=None,
                volume=None,
                status="缺失",
                source="新浪财经",
            )

    ordered = [quote_by_code[c] for c in watchlist]
    return ordered, warnings


def _fetch_sina_headlines(limit: int = 20) -> List[str]:
    url = (
        "https://feed.mix.sina.com.cn/api/roll/get"
        "?pageid=153&lid=2510&num=20&page=1"
    )
    payload = http_get(url)
    data = json.loads(payload)
    rows = data.get("result", {}).get("data", [])
    titles: List[str] = []
    for row in rows:
        title = str(row.get("title", "")).strip()
        if title:
            titles.append(title)
    return titles[:limit]


def _fetch_xueqiu_discussions(limit: int = 5) -> Tuple[List[str], List[str]]:
    notes: List[str] = []
    topics: List[str] = []
    query = urllib.parse.quote("港股ETF")

    api_url = (
        "https://xueqiu.com/query/v1/search/status.json"
        f"?sortId=1&q={query}&count={limit}&page=1"
    )
    try:
        payload = http_get(
            api_url,
            headers={
                "Referer": "https://xueqiu.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        data = json.loads(payload)
        items = data.get("list", [])
        for item in items:
            text = re.sub(r"<[^>]+>", "", str(item.get("text", ""))).strip()
            if text:
                topics.append(text)
        if topics:
            return topics[:limit], notes
    except Exception as exc:  # noqa: BLE001
        notes.append(f"雪球接口失败: {short_error(exc)}")

    try:
        html = http_get(
            f"https://xueqiu.com/search?type=all&keyword={query}",
            headers={"Referer": "https://xueqiu.com"},
        )
        matches = re.findall(r"\$[A-Za-z0-9\.]{2,8}\$", html)
        topics.extend([f"热门标的提及 {token}" for token in matches[:limit]])
    except Exception as exc:  # noqa: BLE001
        notes.append(f"雪球页面抓取失败: {short_error(exc)}")

    if not topics:
        topics = ["雪球讨论暂不可得，已降级输出"]

    return dedupe_keep_order(topics)[:limit], notes


def fetch_news_digest() -> NewsDigest:
    digest = NewsDigest()

    try:
        headlines = _fetch_sina_headlines(limit=20)
        institutional = [
            h for h in headlines if any(k in h for k in ("机构", "券商", "评级", "研报", "基金"))
        ]
        if len(institutional) < 2:
            institutional = headlines[:2]
        digest.institution_views = institutional[:2] if institutional else ["机构观点暂不可得"]

        flow = [h for h in headlines if any(k in h for k in ("资金", "流入", "流出", "北向"))]
        digest.fund_flow_summary = flow[0] if flow else "资金流向暂不可得（来源降级）"
    except Exception as exc:  # noqa: BLE001
        digest.institution_views = ["机构观点暂不可得", "建议关注官方公告与基金披露"]
        digest.fund_flow_summary = "资金流向暂不可得（来源抓取失败）"
        digest.source_notes.append(f"新浪消息抓取失败: {short_error(exc)}")

    topics, notes = _fetch_xueqiu_discussions(limit=5)
    digest.xueqiu_hot_discussions = topics
    digest.source_notes.extend(notes)

    return digest


def collect_etf_bundle(watchlist: Dict[str, str], tz_name: str) -> Tuple[List[ETFQuote], NewsDigest, List[str]]:
    quotes, warnings = fetch_etf_quotes(watchlist, tz_name)
    digest = fetch_news_digest()
    warnings.extend(digest.source_notes)

    # Ensure at least 5 symbols in output, fill placeholders if source returned less.
    if len(quotes) < 5:
        existing = {q.code for q in quotes}
        for code, name in watchlist.items():
            if code in existing:
                continue
            quotes.append(
                ETFQuote(
                    code=code,
                    name=name,
                    price=None,
                    change_pct=None,
                    volume=None,
                    status="缺失",
                    source="降级填充",
                )
            )
            if len(quotes) >= 5:
                break

    return quotes, digest, warnings

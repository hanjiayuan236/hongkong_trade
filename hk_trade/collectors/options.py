from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from hk_trade.models import OptionChain, OptionContract, OptionSymbolData
from hk_trade.utils import add_months, http_get_json, now_in_tz, safe_float, safe_int, short_error, third_friday

YAHOO_URL = "https://query2.finance.yahoo.com/v7/finance/options/{symbol}"


@dataclass
class ExpiryTargets:
    weekly: Optional[int]
    monthly: Optional[int]
    next_month: Optional[int]


def _next_friday(d: date) -> date:
    delta = (4 - d.weekday()) % 7
    return d + timedelta(days=delta)


def _expected_expiries(today: date) -> Tuple[date, date, date]:
    weekly = _next_friday(today)

    monthly = third_friday(today.year, today.month)
    if monthly < today:
        y, m = add_months(today.year, today.month, 1)
        monthly = third_friday(y, m)

    y2, m2 = add_months(monthly.year, monthly.month, 1)
    next_month = third_friday(y2, m2)
    return weekly, monthly, next_month


def _ts_to_date(ts: int) -> date:
    return datetime.utcfromtimestamp(ts).date()


def _date_to_ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def _is_nan(value: float | None) -> bool:
    return value is None or value != value


def map_expiry_targets(available_ts: Iterable[int], today: date) -> ExpiryTargets:
    available_sorted = sorted(set(int(x) for x in available_ts if int(x) > 0))
    if not available_sorted:
        return ExpiryTargets(None, None, None)

    weekly_exp, monthly_exp, next_month_exp = _expected_expiries(today)
    ts_to_day = {ts: _ts_to_date(ts) for ts in available_sorted}

    def pick_weekly() -> Optional[int]:
        candidates = []
        for ts, d in ts_to_day.items():
            if d < today:
                continue
            if d.isocalendar()[:2] == weekly_exp.isocalendar()[:2]:
                candidates.append((abs((d - weekly_exp).days), ts))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    def pick_monthly(target: date) -> Optional[int]:
        candidates = []
        for ts, d in ts_to_day.items():
            if d < today:
                continue
            if d.year == target.year and d.month == target.month:
                candidates.append((abs((d - target).days), ts))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    return ExpiryTargets(
        weekly=pick_weekly(),
        monthly=pick_monthly(monthly_exp),
        next_month=pick_monthly(next_month_exp),
    )


def _fetch_option_json(symbol: str, expiry_ts: Optional[int] = None) -> Dict:
    url = YAHOO_URL.format(symbol=symbol)
    if expiry_ts is not None:
        url = f"{url}?date={expiry_ts}"
    return http_get_json(url)


def _parse_contracts(rows: List[Dict]) -> List[OptionContract]:
    out: List[OptionContract] = []
    for row in rows:
        strike = safe_float(row.get("strike"))
        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        if _is_nan(strike) or _is_nan(bid) or _is_nan(ask):
            continue
        iv_val = safe_float(row.get("impliedVolatility"))
        if iv_val is not None and iv_val > 1:
            iv_val = iv_val / 100
        if iv_val is not None and iv_val != iv_val:
            iv_val = None
        out.append(
            OptionContract(
                strike=float(strike),
                bid=max(0.0, float(bid)),
                ask=max(0.0, float(ask)),
                iv=iv_val,
                volume=safe_int(row.get("volume")),
                open_interest=safe_int(row.get("openInterest")),
            )
        )
    out.sort(key=lambda x: x.strike)
    return out


def _parse_chain(symbol: str, label: str, payload: Dict, expiry_ts: int, fallback_price: Optional[float]) -> OptionChain:
    result = (payload.get("optionChain", {}).get("result") or [{}])[0]
    quote = result.get("quote", {})
    options = result.get("options") or [{}]
    opt = options[0] if options else {}

    underlying = safe_float(quote.get("regularMarketPrice")) or fallback_price
    calls = _parse_contracts(opt.get("calls") or [])
    puts = _parse_contracts(opt.get("puts") or [])

    return OptionChain(
        symbol=symbol,
        expiry_label=label,
        expiry_date=_ts_to_date(expiry_ts),
        expiry_ts=expiry_ts,
        underlying_price=underlying,
        calls=calls,
        puts=puts,
        source="Yahoo Finance",
        fetch_error=None,
    )


def _collect_from_api(symbol: str, option_data: OptionSymbolData, today: date) -> Tuple[bool, List[str]]:
    local_warnings: List[str] = []
    try:
        base = _fetch_option_json(symbol)
        result = (base.get("optionChain", {}).get("result") or [{}])[0]
        quote = result.get("quote", {})
        option_data.spot_price = safe_float(quote.get("regularMarketPrice"))
        expiry_ts_list = result.get("expirationDates") or []
        targets = map_expiry_targets(expiry_ts_list, today)
    except Exception as exc:  # noqa: BLE001
        err = f"{symbol} 期权主请求失败: {short_error(exc)}"
        option_data.fetch_errors.append(err)
        local_warnings.append(err)
        return False, local_warnings

    label_map = {
        "本周": targets.weekly,
        "本月": targets.monthly,
        "下月": targets.next_month,
    }

    for label, expiry_ts in label_map.items():
        if not expiry_ts:
            msg = f"{symbol} {label} 无可用到期日"
            option_data.fetch_errors.append(msg)
            local_warnings.append(msg)
            continue

        try:
            payload = _fetch_option_json(symbol, expiry_ts=expiry_ts)
            chain = _parse_chain(
                symbol=symbol,
                label=label,
                payload=payload,
                expiry_ts=expiry_ts,
                fallback_price=option_data.spot_price,
            )
            if not chain.has_data:
                msg = f"{symbol} {label} 无 calls/puts 数据"
                chain.fetch_error = msg
                local_warnings.append(msg)
            option_data.chains[label] = chain
        except Exception as exc:  # noqa: BLE001
            msg = f"{symbol} {label} 抓取失败: {short_error(exc)}"
            option_data.fetch_errors.append(msg)
            local_warnings.append(msg)

    return bool(option_data.chains), local_warnings


def _collect_from_yfinance(symbol: str, option_data: OptionSymbolData, today: date) -> Tuple[bool, List[str]]:
    local_warnings: List[str] = []

    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # noqa: BLE001
        msg = f"{symbol} yfinance 不可用: {short_error(exc)}"
        option_data.fetch_errors.append(msg)
        local_warnings.append(msg)
        return False, local_warnings

    try:
        ticker = yf.Ticker(symbol)
        expiry_strings = list(ticker.options or [])
    except Exception as exc:  # noqa: BLE001
        msg = f"{symbol} yfinance 到期日抓取失败: {short_error(exc)}"
        option_data.fetch_errors.append(msg)
        local_warnings.append(msg)
        return False, local_warnings

    if not expiry_strings:
        msg = f"{symbol} yfinance 无到期日"
        option_data.fetch_errors.append(msg)
        local_warnings.append(msg)
        return False, local_warnings

    ts_to_date_str: Dict[int, str] = {}
    expiry_ts_list: List[int] = []
    for ds in expiry_strings:
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        ts = _date_to_ts(d)
        ts_to_date_str[ts] = ds
        expiry_ts_list.append(ts)

    targets = map_expiry_targets(expiry_ts_list, today)

    if option_data.spot_price is None:
        try:
            fi = ticker.fast_info
            option_data.spot_price = safe_float(fi.get("lastPrice") or fi.get("last_price"))
        except Exception:  # noqa: BLE001
            pass

    label_map = {
        "本周": targets.weekly,
        "本月": targets.monthly,
        "下月": targets.next_month,
    }

    for label, expiry_ts in label_map.items():
        if not expiry_ts:
            msg = f"{symbol} {label} 无可用到期日"
            option_data.fetch_errors.append(msg)
            local_warnings.append(msg)
            continue

        expiry_str = ts_to_date_str.get(expiry_ts) or _ts_to_date(expiry_ts).isoformat()
        try:
            oc = ticker.option_chain(expiry_str)
            calls_df = oc.calls
            puts_df = oc.puts
            calls = _parse_contracts(calls_df.to_dict("records")) if calls_df is not None else []
            puts = _parse_contracts(puts_df.to_dict("records")) if puts_df is not None else []

            chain = OptionChain(
                symbol=symbol,
                expiry_label=label,
                expiry_date=_ts_to_date(expiry_ts),
                expiry_ts=expiry_ts,
                underlying_price=option_data.spot_price,
                calls=calls,
                puts=puts,
                source="Yahoo Finance (yfinance)",
                fetch_error=None,
            )
            if not chain.has_data:
                msg = f"{symbol} {label} 无 calls/puts 数据"
                chain.fetch_error = msg
                local_warnings.append(msg)
            option_data.chains[label] = chain
        except Exception as exc:  # noqa: BLE001
            msg = f"{symbol} {label} yfinance 抓取失败: {short_error(exc)}"
            option_data.fetch_errors.append(msg)
            local_warnings.append(msg)

    return bool(option_data.chains), local_warnings


def collect_options_bundle(symbols: List[str], tz_name: str, leverage_map: Dict[str, str]) -> Tuple[Dict[str, OptionSymbolData], List[str]]:
    warnings: List[str] = []
    today = now_in_tz(tz_name).date()
    output: Dict[str, OptionSymbolData] = {}

    for symbol in symbols:
        option_data = OptionSymbolData(
            symbol=symbol,
            leverage=leverage_map.get(symbol, "1x"),
            spot_price=None,
            chains={},
            fetch_errors=[],
        )

        api_success, api_warnings = _collect_from_api(symbol, option_data, today)
        if api_success:
            warnings.extend(api_warnings)
            output[symbol] = option_data
            continue

        # API often returns 401. Fallback to yfinance for free Yahoo-compatible access.
        option_data.chains = {}
        option_data.fetch_errors = []

        yf_success, yf_warnings = _collect_from_yfinance(symbol, option_data, today)
        if yf_success:
            warnings.append(f"{symbol} 已回退到 yfinance 成功获取期权数据")
            warnings.extend(yf_warnings)
            output[symbol] = option_data
            continue

        warnings.extend(api_warnings)
        warnings.extend(yf_warnings)
        output[symbol] = option_data

    return output, warnings

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hk_trade.models import OptionChain, OptionContract, OptionSymbolData, RiskAdvice, StrategyRow


def _first_otm_call(calls: List[OptionContract], spot: float) -> Optional[OptionContract]:
    for c in calls:
        if c.strike > spot:
            return c
    return None


def _next_higher_call(calls: List[OptionContract], strike: float) -> Optional[OptionContract]:
    for c in calls:
        if c.strike > strike:
            return c
    return None


def _first_otm_put(puts: List[OptionContract], spot: float) -> Optional[OptionContract]:
    for p in reversed(puts):
        if p.strike < spot:
            return p
    return None


def _next_lower_put(puts: List[OptionContract], strike: float) -> Optional[OptionContract]:
    lower = [p for p in puts if p.strike < strike]
    if not lower:
        return None
    return max(lower, key=lambda x: x.strike)


def _build_strangle(symbol_data: OptionSymbolData, chain: OptionChain) -> Optional[StrategyRow]:
    spot = chain.underlying_price or symbol_data.spot_price
    if not spot or not chain.calls or not chain.puts:
        return None

    call_sell = _first_otm_call(chain.calls, spot)
    put_sell = _first_otm_put(chain.puts, spot)
    if not call_sell or not put_sell:
        return None

    premium = round(call_sell.mid + put_sell.mid, 4)
    return StrategyRow(
        symbol=symbol_data.symbol,
        leverage=symbol_data.leverage,
        expiry_label=chain.expiry_label,
        expiry_date=chain.expiry_date,
        strategy="Strangle",
        sell_desc="Call+Put",
        strike_desc=f"{call_sell.strike:g}/{put_sell.strike:g}",
        call_price=call_sell.mid,
        put_price=put_sell.mid,
        premium=premium,
        underlying_price=spot,
    )


def _build_iron_condor(symbol_data: OptionSymbolData, chain: OptionChain) -> Optional[StrategyRow]:
    spot = chain.underlying_price or symbol_data.spot_price
    if not spot or not chain.calls or not chain.puts:
        return None

    call_sell = _first_otm_call(chain.calls, spot)
    put_sell = _first_otm_put(chain.puts, spot)
    if not call_sell or not put_sell:
        return None

    call_buy = _next_higher_call(chain.calls, call_sell.strike)
    put_buy = _next_lower_put(chain.puts, put_sell.strike)
    if not call_buy or not put_buy:
        return None

    premium = round(call_sell.mid + put_sell.mid - call_buy.mid - put_buy.mid, 4)
    return StrategyRow(
        symbol=symbol_data.symbol,
        leverage=symbol_data.leverage,
        expiry_label=chain.expiry_label,
        expiry_date=chain.expiry_date,
        strategy="Iron Condor",
        sell_desc="Call+Put(价差)",
        strike_desc=(
            f"SellC{call_sell.strike:g}/BuyC{call_buy.strike:g} + "
            f"SellP{put_sell.strike:g}/BuyP{put_buy.strike:g}"
        ),
        call_price=call_sell.mid,
        put_price=put_sell.mid,
        premium=premium,
        underlying_price=spot,
    )


def _build_put_spread(symbol_data: OptionSymbolData, chain: OptionChain) -> Optional[StrategyRow]:
    spot = chain.underlying_price or symbol_data.spot_price
    if not spot or not chain.puts:
        return None

    put_sell = _first_otm_put(chain.puts, spot)
    if not put_sell:
        return None

    put_buy = _next_lower_put(chain.puts, put_sell.strike)
    if not put_buy:
        return None

    premium = round(put_sell.mid - put_buy.mid, 4)
    return StrategyRow(
        symbol=symbol_data.symbol,
        leverage=symbol_data.leverage,
        expiry_label=chain.expiry_label,
        expiry_date=chain.expiry_date,
        strategy="Put Spread",
        sell_desc="Put(价差)",
        strike_desc=f"SellP{put_sell.strike:g}/BuyP{put_buy.strike:g}",
        call_price=None,
        put_price=put_sell.mid,
        premium=premium,
        underlying_price=spot,
    )


def generate_strategy_rows(options_data: Dict[str, OptionSymbolData]) -> List[StrategyRow]:
    rows: List[StrategyRow] = []

    for symbol in options_data:
        symbol_data = options_data[symbol]
        for label in ("本周", "本月", "下月"):
            chain = symbol_data.chains.get(label)
            if not chain:
                continue

            for builder in (_build_strangle, _build_iron_condor, _build_put_spread):
                row = builder(symbol_data, chain)
                if row is None:
                    continue
                rows.append(row)

    rows.sort(key=lambda x: ((x.yield_pct is None), -(x.yield_pct or -9999)))
    return rows


def build_risk_advice(rows: List[StrategyRow]) -> List[RiskAdvice]:
    if not rows:
        return [
            RiskAdvice("稳健", "0-20%", "本期策略数据缺失，建议观望", "来源不完整"),
            RiskAdvice("平衡", "20-50%", "等待下一次完整链路后再配置", "数据延迟"),
            RiskAdvice("进取", "50-80%", "暂停杠杆ETF双卖，避免盲目开仓", "高Gamma风险"),
        ]

    top_sorted = [r for r in rows if r.yield_pct is not None]
    top_sorted.sort(key=lambda x: x.yield_pct or 0, reverse=True)

    conservative = next((r for r in top_sorted if r.symbol in ("FXI", "KWEB")), top_sorted[0])
    balanced = top_sorted[min(1, len(top_sorted) - 1)]
    aggressive = top_sorted[0]

    return [
        RiskAdvice(
            risk_level="稳健",
            allocation="20%",
            suggestion=(
                f"优先 {conservative.symbol} {conservative.strategy} "
                f"{conservative.expiry_label} ({conservative.strike_desc})"
            ),
            key_risk="控制仓位，遇到权利金亏损50%止损",
        ),
        RiskAdvice(
            risk_level="平衡",
            allocation="40%",
            suggestion=(
                f"组合 {balanced.symbol} {balanced.strategy} "
                f"{balanced.expiry_label} ({balanced.strike_desc})"
            ),
            key_risk="避免同一到期日过度集中",
        ),
        RiskAdvice(
            risk_level="进取",
            allocation="40%",
            suggestion=(
                f"仅小仓位尝试 {aggressive.symbol} {aggressive.strategy} "
                f"{aggressive.expiry_label} ({aggressive.strike_desc})"
            ),
            key_risk="杠杆ETF Gamma 风险高，到期前3天必须了结",
        ),
    ]


def top_strategy_rows(rows: List[StrategyRow], limit: int = 10) -> List[StrategyRow]:
    valid = [r for r in rows if r.yield_pct is not None]
    valid.sort(key=lambda x: x.yield_pct or 0, reverse=True)
    return valid[:limit]

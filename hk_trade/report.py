from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from hk_trade.models import ETFQuote, OptionSymbolData, ReportContext, StrategyRow
from hk_trade.strategy import top_strategy_rows
from hk_trade.utils import is_weekend, next_mode_update


LABEL_ORDER = {"本周": 0, "本月": 1, "下月": 2}
STRATEGY_ORDER = {"Strangle": 0, "Iron Condor": 1, "Put Spread": 2}


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.2f}"


def _fmt_change(v: float | None) -> str:
    if v is None:
        return "N/A"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def _fmt_num(v: float | None) -> str:
    if v is None:
        return "N/A"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:.2f}K"
    return f"{v:.2f}"


def _render_etf_table(quotes: List[ETFQuote]) -> str:
    lines = [
        "| ETF名称 | 代码 | 最新价 | 涨跌幅 | 状态 |",
        "|---|---|---:|---:|---|",
    ]
    for q in quotes:
        lines.append(
            f"| {q.name} | {q.code} | {_fmt_price(q.price)} | {_fmt_change(q.change_pct)} | {q.status} |"
        )
    return "\n".join(lines)


def _render_completeness(options_data: Dict[str, OptionSymbolData]) -> str:
    lines = [
        "### 完整性检查 ✅",
        "",
        "| Ticker | 本周 | 本月 | 下月 |",
        "|---|---|---|---|",
    ]
    for symbol in ("FXI", "YINN", "KWEB", "CWEB"):
        data = options_data.get(symbol)
        if not data:
            lines.append(f"| {symbol} | - | - | - |")
            continue
        marks = []
        for label in ("本周", "本月", "下月"):
            chain = data.chains.get(label)
            marks.append("✅" if chain and chain.has_data else "-")
        lines.append(f"| {symbol} | {marks[0]} | {marks[1]} | {marks[2]} |")
    return "\n".join(lines)


def _render_baseline_table(options_data: Dict[str, OptionSymbolData]) -> str:
    lines = [
        "### 一、标的基本面对比",
        "",
        "| 标的 | 价格 | 杠杆 | 本周 | 本月 | 下月 |",
        "|---|---:|---|---|---|---|",
    ]
    for symbol in ("FXI", "YINN", "KWEB", "CWEB"):
        data = options_data.get(symbol)
        if not data:
            lines.append(f"| {symbol} | N/A | N/A | 无 | 无 | 无 |")
            continue
        spot = _fmt_price(data.spot_price)
        present = [
            "有" if data.chains.get("本周") and data.chains["本周"].has_data else "无",
            "有" if data.chains.get("本月") and data.chains["本月"].has_data else "无",
            "有" if data.chains.get("下月") and data.chains["下月"].has_data else "无",
        ]
        lines.append(f"| {symbol} | {spot} | {data.leverage} | {present[0]} | {present[1]} | {present[2]} |")
    return "\n".join(lines)


def _strategy_row_display(row: StrategyRow) -> str:
    call_price = f"{row.call_price:.3f}" if row.call_price is not None else "-"
    put_price = f"{row.put_price:.3f}" if row.put_price is not None else "-"
    if row.underlying_price and row.yield_pct is not None:
        calc = f"**{row.premium:.3f}÷{row.underlying_price:.2f}={row.yield_pct:.2f}%**"
    else:
        calc = "-"
    return (
        f"| {row.expiry_label}({row.expiry_date:%m/%d}) | {row.strategy} | {row.sell_desc} | "
        f"{row.strike_desc} | {call_price} | {put_price} | {row.premium:.3f} | {calc} |"
    )


def _render_symbol_strategy(symbol: str, symbol_rows: List[StrategyRow], spot: float | None) -> str:
    lines = [
        f"#### {symbol} (${_fmt_price(spot)})",
        "",
        "| 到期日 | 策略 | 卖什么 | 行权价 | Call价 | Put价 | 权利金 | **收益率=权利金÷股价** |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    if not symbol_rows:
        lines.append("| - | - | - | - | - | - | - | - |")
        return "\n".join(lines)

    symbol_rows.sort(
        key=lambda r: (LABEL_ORDER.get(r.expiry_label, 9), STRATEGY_ORDER.get(r.strategy, 9), r.expiry_date)
    )
    for row in symbol_rows:
        lines.append(_strategy_row_display(row))
    return "\n".join(lines)


def _render_rank_table(rows: List[StrategyRow]) -> str:
    top = top_strategy_rows(rows, limit=10)
    lines = [
        "### 三、收益排名",
        "",
        "| 排名 | 标的 | 到期日 | 策略 | 权利金 | 收益率 |",
        "|---:|---|---|---|---:|---:|",
    ]
    if not top:
        lines.append("| 1 | N/A | N/A | N/A | N/A | N/A |")
        return "\n".join(lines)

    for idx, row in enumerate(top, start=1):
        lines.append(
            f"| {idx} | {row.symbol} | {row.expiry_label}({row.expiry_date:%m/%d}) | "
            f"{row.strategy} {row.strike_desc} | {row.premium:.3f} | **{(row.yield_pct or 0):.2f}%** |"
        )
    return "\n".join(lines)


def _render_realized_table(rows: List[StrategyRow]) -> str:
    top = top_strategy_rows(rows, limit=8)
    lines = [
        "### 四、实际收益（1手=100股）",
        "",
        "| 策略 | 权利金 | 1手 | 10手 |",
        "|---|---:|---:|---:|",
    ]
    if not top:
        lines.append("| N/A | N/A | N/A | N/A |")
        return "\n".join(lines)

    for row in top:
        one = row.premium * 100
        ten = one * 10
        lines.append(
            f"| {row.symbol} {row.expiry_label} {row.strategy} | {row.premium:.3f} | "
            f"${one:,.2f} | ${ten:,.2f} |"
        )
    return "\n".join(lines)


def render_report(ctx: ReportContext) -> str:
    now = ctx.run_time
    weekend_note = "\n> 周末休市：当前为休市时段，以下为最新可得快照。\n" if is_weekend(now) else ""

    lines: List[str] = []
    lines.append(f"## 📊 港股ETF研究报告 (第{ctx.issue_no}期)")
    lines.append(f"更新时间：{now:%Y-%m-%d %H:%M:%S %Z}")
    lines.append(weekend_note)

    lines.append("### 📈 行情汇总")
    lines.append(_render_etf_table(ctx.quotes))
    lines.append("")

    lines.append("### 📰 消息分析")
    lines.append(f"- 机构观点1：{ctx.news.institution_views[0] if ctx.news.institution_views else '暂不可得'}")
    lines.append(
        f"- 机构观点2：{ctx.news.institution_views[1] if len(ctx.news.institution_views) > 1 else '关注下次更新'}"
    )
    lines.append(f"- 资金流向：{ctx.news.fund_flow_summary or '暂不可得'}")
    lines.append("")

    lines.append("### 💬 用户讨论")
    for item in (ctx.news.xueqiu_hot_discussions or ["雪球讨论暂不可得"]):
        lines.append(f"- {item}")
    lines.append("")

    lines.append("### 🎯 投资建议")
    lines.append("| 风险偏好 | 建议仓位 | 建议动作 | 核心风险 |")
    lines.append("|---|---:|---|---|")
    for advice in ctx.risk_advice:
        lines.append(
            f"| {advice.risk_level} | {advice.allocation} | {advice.suggestion} | {advice.key_risk} |"
        )
    lines.append("")

    lines.append("## 📊 港股ETF期权双卖策略报告")
    lines.append(_render_completeness(ctx.options_data))
    lines.append("")
    lines.append(_render_baseline_table(ctx.options_data))
    lines.append("")

    lines.append("### 二、各ETF策略详情（包含所有策略收益率计算）")
    grouped: Dict[str, List[StrategyRow]] = defaultdict(list)
    for row in ctx.strategy_rows:
        grouped[row.symbol].append(row)

    for symbol in ("FXI", "YINN", "KWEB", "CWEB"):
        spot = ctx.options_data.get(symbol).spot_price if ctx.options_data.get(symbol) else None
        lines.append("")
        lines.append(_render_symbol_strategy(symbol, grouped.get(symbol, []), spot))

    lines.append("")
    lines.append(_render_rank_table(ctx.strategy_rows))
    lines.append("")
    lines.append(_render_realized_table(ctx.strategy_rows))
    lines.append("")

    lines.append("### 五、风控要点")
    lines.append("1. 杠杆ETF（YINN/CWEB）Gamma风险高，避免重仓隔夜。")
    lines.append("2. 止损规则：权利金亏损达到50%时平仓。")
    lines.append("3. 到期前3天优先减仓，避免临近到期跳空风险。")
    lines.append("")

    lines.append("### ⚠️ 风险警告")
    lines.append("卖出期权盈利有限但尾部风险高，请务必控制仓位并设置止损。")
    lines.append("")

    if ctx.warnings:
        lines.append("### 数据质量提示")
        for warning in ctx.warnings[:10]:
            lines.append(f"- {warning}")
        lines.append("")

    nxt = next_mode_update(now, ctx.mode)
    sources = "、".join(ctx.data_sources)
    lines.append("---")
    lines.append(f"**数据来源**：{sources}")
    lines.append(f"**下次更新时间**：约 {nxt:%Y-%m-%d %H:%M:%S %Z}")
    lines.append("**免责声明**：仅供研究学习，不构成投资建议。")

    return "\n".join(lines).replace("\n\n\n", "\n\n")

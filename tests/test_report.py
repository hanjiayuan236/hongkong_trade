from __future__ import annotations

import unittest
from datetime import date, datetime

from hk_trade.models import (
    ETFQuote,
    NewsDigest,
    OptionChain,
    OptionContract,
    OptionSymbolData,
    ReportContext,
    RiskAdvice,
    StrategyRow,
)
from hk_trade.report import render_report


class ReportRenderTests(unittest.TestCase):
    def _sample_context(self) -> ReportContext:
        quotes = [
            ETFQuote("513130", "恒生科技ETF", 1.0, 0.1, 1000, "交易中", "新浪财经"),
            ETFQuote("520880", "港股通创新药ETF", 1.0, 0.1, 1000, "交易中", "新浪财经"),
            ETFQuote("159712", "港股通50ETF", 1.0, 0.1, 1000, "交易中", "新浪财经"),
            ETFQuote("159331", "红利港股ETF", 1.0, 0.1, 1000, "交易中", "新浪财经"),
            ETFQuote("513010", "港股通互联网ETF", 1.0, 0.1, 1000, "交易中", "新浪财经"),
        ]
        news = NewsDigest(
            institution_views=["机构A看多", "机构B中性"],
            fund_flow_summary="资金净流入",
            xueqiu_hot_discussions=["讨论1", "讨论2"],
        )

        contract = OptionContract(36, 0.2, 0.3, 0.2, 100, 200)
        put = OptionContract(35, 0.2, 0.3, 0.2, 100, 200)
        chain = OptionChain(
            symbol="FXI",
            expiry_label="本周",
            expiry_date=date(2026, 3, 13),
            expiry_ts=1773360000,
            underlying_price=35.5,
            calls=[contract],
            puts=[put],
        )

        options_data = {
            "FXI": OptionSymbolData("FXI", "1x", 35.5, chains={"本周": chain}),
            "YINN": OptionSymbolData("YINN", "3x", 33.0, chains={}),
            "KWEB": OptionSymbolData("KWEB", "1x", 29.0, chains={}),
            "CWEB": OptionSymbolData("CWEB", "2x", 28.0, chains={}),
        }

        strategy_rows = [
            StrategyRow(
                symbol="FXI",
                leverage="1x",
                expiry_label="本周",
                expiry_date=date(2026, 3, 13),
                strategy="Strangle",
                sell_desc="Call+Put",
                strike_desc="36/35",
                call_price=0.25,
                put_price=0.25,
                premium=0.5,
                underlying_price=35.5,
            )
        ]
        advice = [
            RiskAdvice("稳健", "20%", "建议1", "风险1"),
            RiskAdvice("平衡", "40%", "建议2", "风险2"),
            RiskAdvice("进取", "40%", "建议3", "风险3"),
        ]

        return ReportContext(
            run_id="r1",
            run_time=datetime(2026, 3, 8, 10, 0),
            mode="daily",
            issue_no=1,
            quotes=quotes,
            news=news,
            options_data=options_data,
            strategy_rows=strategy_rows,
            risk_advice=advice,
            data_sources=["新浪财经", "雪球", "Yahoo Finance"],
            warnings=[],
        )

    def test_report_contains_required_sections(self) -> None:
        text = render_report(self._sample_context())
        required = [
            "## 📊 港股ETF研究报告 (第1期)",
            "### 📈 行情汇总",
            "### 📰 消息分析",
            "### 🎯 投资建议",
            "## 📊 港股ETF期权双卖策略报告",
            "### 完整性检查 ✅",
            "### 一、标的基本面对比",
            "### 二、各ETF策略详情（包含所有策略收益率计算）",
            "### 三、收益排名",
            "### 四、实际收益（1手=100股）",
            "### 五、风控要点",
            "### ⚠️ 风险警告",
            "**数据来源**：新浪财经、雪球、Yahoo Finance",
        ]
        for item in required:
            self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from hk_trade.models import ETFQuote, NewsDigest, OptionChain, OptionContract, OptionSymbolData
from hk_trade.run_report import main


class RunReportTests(unittest.TestCase):
    def _mock_collect_etf(self, watchlist, tz):
        quotes = [
            ETFQuote("513130", "恒生科技ETF", 1.0, 0.1, 1000, "交易中", "新浪"),
            ETFQuote("520880", "港股通创新药ETF", 1.0, 0.1, 1000, "交易中", "新浪"),
            ETFQuote("159712", "港股通50ETF", 1.0, 0.1, 1000, "交易中", "新浪"),
            ETFQuote("159331", "红利港股ETF", 1.0, 0.1, 1000, "交易中", "新浪"),
            ETFQuote("513010", "港股通互联网ETF", 1.0, 0.1, 1000, "交易中", "新浪"),
        ]
        news = NewsDigest(
            institution_views=["机构观点A", "机构观点B"],
            fund_flow_summary="资金净流入",
            xueqiu_hot_discussions=["热帖1", "热帖2"],
        )
        return quotes, news, ["雪球降级"]

    def _mock_collect_options(self, symbols, tz, leverage):
        calls = [
            OptionContract(36, 0.2, 0.3, 0.2, 100, 100),
            OptionContract(37, 0.1, 0.2, 0.2, 100, 100),
        ]
        puts = [
            OptionContract(34, 0.1, 0.2, 0.2, 100, 100),
            OptionContract(35, 0.2, 0.3, 0.2, 100, 100),
        ]
        chain = OptionChain(
            symbol="FXI",
            expiry_label="本周",
            expiry_date=date(2026, 3, 13),
            expiry_ts=1773360000,
            underlying_price=35.5,
            calls=calls,
            puts=puts,
        )
        data = {
            "FXI": OptionSymbolData("FXI", "1x", 35.5, chains={"本周": chain}),
            "YINN": OptionSymbolData("YINN", "3x", 30.0, chains={}),
            "KWEB": OptionSymbolData("KWEB", "1x", 30.0, chains={}),
            "CWEB": OptionSymbolData("CWEB", "2x", 30.0, chains={}),
        }
        return data, ["某到期日无数据"]

    def test_run_report_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                "DB_PATH=./data/test.db\nREPORT_ARCHIVE_DIR=./reports\nLOG_DIR=./logs\n",
                encoding="utf-8",
            )

            with patch("hk_trade.run_report.collect_etf_bundle", side_effect=self._mock_collect_etf), patch(
                "hk_trade.run_report.collect_options_bundle", side_effect=self._mock_collect_options
            ):
                old_cwd = Path.cwd()
                try:
                    import os

                    os.chdir(root)
                    code = main(["--mode", "daily", "--dry-run"])
                finally:
                    os.chdir(old_cwd)

            self.assertEqual(code, 0)
            reports = list((root / "reports").rglob("*.md"))
            self.assertTrue(reports)


if __name__ == "__main__":
    unittest.main()

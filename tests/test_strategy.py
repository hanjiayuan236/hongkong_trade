from __future__ import annotations

import unittest
from datetime import date

from hk_trade.models import OptionChain, OptionContract, OptionSymbolData
from hk_trade.strategy import build_risk_advice, generate_strategy_rows


class StrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        calls = [
            OptionContract(strike=36, bid=0.2, ask=0.3, iv=0.2, volume=100, open_interest=200),
            OptionContract(strike=37, bid=0.1, ask=0.2, iv=0.2, volume=80, open_interest=150),
        ]
        puts = [
            OptionContract(strike=34, bid=0.1, ask=0.2, iv=0.2, volume=100, open_interest=200),
            OptionContract(strike=35, bid=0.2, ask=0.3, iv=0.2, volume=90, open_interest=180),
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
        self.options_data = {
            "FXI": OptionSymbolData(symbol="FXI", leverage="1x", spot_price=35.5, chains={"本周": chain})
        }

    def test_generate_strategy_rows(self) -> None:
        rows = generate_strategy_rows(self.options_data)
        names = {r.strategy for r in rows}
        self.assertIn("Strangle", names)
        self.assertIn("Iron Condor", names)
        self.assertIn("Put Spread", names)

        strangle = next(r for r in rows if r.strategy == "Strangle")
        self.assertAlmostEqual(strangle.premium, 0.5, places=4)
        self.assertAlmostEqual(strangle.yield_pct or 0, round(0.5 / 35.5 * 100, 2), places=2)

    def test_build_risk_advice(self) -> None:
        rows = generate_strategy_rows(self.options_data)
        advice = build_risk_advice(rows)
        self.assertEqual(len(advice), 3)
        self.assertEqual(advice[0].risk_level, "稳健")


if __name__ == "__main__":
    unittest.main()

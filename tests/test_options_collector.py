from __future__ import annotations

import unittest
from datetime import date, datetime

from hk_trade.collectors.options import map_expiry_targets


class OptionExpiryTests(unittest.TestCase):
    def test_map_expiry_targets(self) -> None:
        # 2026-03 Fridays: 6, 13, 20, 27
        available_dates = [
            int(datetime(2026, 3, 13).timestamp()),
            int(datetime(2026, 3, 20).timestamp()),
            int(datetime(2026, 4, 17).timestamp()),
        ]
        targets = map_expiry_targets(available_dates, today=date(2026, 3, 8))

        self.assertIsNotNone(targets.weekly)
        self.assertIsNotNone(targets.monthly)
        self.assertIsNotNone(targets.next_month)
        self.assertNotEqual(targets.weekly, targets.monthly)
        self.assertNotEqual(targets.monthly, targets.next_month)


if __name__ == "__main__":
    unittest.main()

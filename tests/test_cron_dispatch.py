from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from hk_trade.cron_dispatch import due_tasks


class CronDispatchTests(unittest.TestCase):
    def test_hk_intraday_slot(self) -> None:
        hk_dt = datetime(2026, 3, 9, 9, 30, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        tasks = due_tasks(hk_dt)
        keys = {t.key for t in tasks}
        self.assertTrue(any(k.startswith("hk:intraday:2026-03-09:09:30") for k in keys))

    def test_hk_close_slot(self) -> None:
        hk_dt = datetime(2026, 3, 9, 16, 10, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        tasks = due_tasks(hk_dt)
        keys = {t.key for t in tasks}
        self.assertTrue(any(k.startswith("hk:close:2026-03-09:16:10") for k in keys))

    def test_us_intraday_slot(self) -> None:
        us_dt = datetime(2026, 3, 9, 9, 30, tzinfo=ZoneInfo("America/New_York"))
        tasks = due_tasks(us_dt)
        keys = {t.key for t in tasks}
        self.assertTrue(any(k.startswith("us:intraday:2026-03-09:09:30") for k in keys))

    def test_no_slot(self) -> None:
        hk_dt = datetime(2026, 3, 9, 9, 37, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        tasks = due_tasks(hk_dt)
        self.assertEqual(tasks, [])


if __name__ == "__main__":
    unittest.main()

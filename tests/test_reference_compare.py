from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.reference_compare import compare_rebalance  # noqa: E402

FIXTURES = ROOT / "src" / "common" / "fixtures"


class ReferenceCompareTests(unittest.TestCase):
    def test_quarterly_snapshot_skips_the_second_month(self) -> None:
        comparison = compare_rebalance(FIXTURES, rebalance_months=3)

        self.assertEqual(comparison["compare_rebalance_months"], 3)
        for market in ("US", "KR"):
            monthly = comparison["markets"][market]["snapshot_monthly"]
            quarterly = comparison["markets"][market]["snapshot_compare"]
            self.assertEqual(len(monthly["rebalance_months"]), 2)
            self.assertEqual(len(quarterly["rebalance_months"]), 1)
            self.assertEqual(quarterly["held_months"], ["2025-02"])
            self.assertLessEqual(quarterly["buy_turnover"], monthly["buy_turnover"])
            later = comparison["markets"][market]["frozen_monthly"]["later"]
            self.assertEqual(later["start"], "2021-01")
            self.assertEqual(later["end"], "2025-12")

    def test_compare_cli_stays_offline_and_does_not_order(self) -> None:
        result = subprocess.run(
            [sys.executable, "routines/참조전략-실험.py", "--compare", "--no-send"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3개월", result.stdout)
        self.assertIn("청산 시점", result.stdout)
        self.assertNotIn("주문 전송", result.stdout)


if __name__ == "__main__":
    unittest.main()

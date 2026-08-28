from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.reference_data import adjusted_monthly_returns  # noqa: E402


class ReferenceDataTests(unittest.TestCase):
    def test_adjusted_monthly_returns_uses_adjclose_and_month_labels(self):
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [
                        _timestamp("2023-12-01"),
                        _timestamp("2024-01-02"),
                        _timestamp("2024-02-01"),
                    ],
                    "indicators": {
                        "quote": [{"close": [100.0, 120.0, 90.0]}],
                        "adjclose": [{"adjclose": [100.0, 110.0, 121.0]}],
                    },
                }],
                "error": None,
            }
        }

        self.assertEqual(
            adjusted_monthly_returns(payload),
            {"2024-01": 0.10, "2024-02": 0.10},
        )

    def test_missing_adjusted_close_is_not_forward_filled(self):
        payload = {
            "chart": {
                "result": [{
                    "timestamp": [
                        _timestamp("2023-12-01"),
                        _timestamp("2024-01-02"),
                        _timestamp("2024-02-01"),
                    ],
                    "indicators": {
                        "adjclose": [{"adjclose": [100.0, None, 121.0]}],
                    },
                }],
                "error": None,
            }
        }

        self.assertEqual(adjusted_monthly_returns(payload), {})


def _timestamp(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp())


if __name__ == "__main__":
    unittest.main()

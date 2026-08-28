from __future__ import annotations

import sys

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReferenceRoutineTests(unittest.TestCase):
    def test_offline_routine_shows_both_markets_and_locked_reference(self):
        result = subprocess.run(
            [sys.executable, "routines/참조전략-실험.py", "--no-send"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("미국 고정 바스켓", result.stdout)
        self.assertIn("한국 고정 바스켓", result.stdout)
        self.assertIn("참조 시장: US", result.stdout)
        self.assertIn("자동 손절이 아닙니다", result.stdout)
        self.assertNotIn("가격 역할", result.stdout)


if __name__ == "__main__":
    unittest.main()

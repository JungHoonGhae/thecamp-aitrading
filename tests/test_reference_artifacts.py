from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.reference_momentum import (  # noqa: E402
    content_hash,
    materialize_market_manifest,
    run_reference_backtest,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


class ReferenceArtifactTests(unittest.TestCase):
    def setUp(self):
        self.manifest = _load("reference_manifest.json")
        self.selection = _load("reference_selection.json")

    def test_result_bundles_are_bound_to_manifest_and_self_hash(self):
        manifest_hash = content_hash(self.manifest)
        for market in ("US", "KR"):
            result = _load(f"{market.lower()}_momentum_result.json")
            stored_hash = result.pop("result_hash")

            self.assertEqual(result["manifest_hash"], manifest_hash)
            self.assertEqual(content_hash(result), stored_hash)
            self.assertEqual(result["periods"]["earlier"]["months"], 60)
            self.assertEqual(result["periods"]["later"]["months"], 60)

    def test_small_snapshots_recompute_offline(self):
        for market in ("US", "KR"):
            snapshot = _load(f"{market.lower()}_momentum_snapshot.json")
            stored_input_hash = snapshot.pop("input_hash")
            contract = materialize_market_manifest(self.manifest, market)

            self.assertEqual(content_hash(snapshot), stored_input_hash)
            result = run_reference_backtest(contract, snapshot)
            self.assertEqual(len(result["months"]), 2)
            self.assertEqual(result["manifest_hash"], content_hash(self.manifest))

    def test_reference_market_follows_locked_later_period_rule(self):
        us = _load("us_momentum_result.json")
        kr = _load("kr_momentum_result.json")
        expected = (
            "US"
            if us["periods"]["later"]["net_excess_return"]
            > kr["periods"]["later"]["net_excess_return"]
            else "KR"
        )

        self.assertEqual(self.selection["reference_market"], expected)
        self.assertEqual(self.selection["manifest_hash"], content_hash(self.manifest))
        self.assertEqual(
            self.selection["result_hashes"],
            {"US": us["result_hash"], "KR": kr["result_hash"]},
        )


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

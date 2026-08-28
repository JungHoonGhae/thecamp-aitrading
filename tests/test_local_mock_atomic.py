from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.us_mock import LocalMockBroker  # noqa: E402
from common.us_reference import (  # noqa: E402
    AdvisoryProposal,
    ExitPolicy,
    Guardrails,
    ReferenceReview,
    adopt_proposal,
    build_order_plan,
    proposal_digest,
)


class LocalMockAtomicTests(unittest.TestCase):
    def test_validated_batch_is_recorded_once_with_one_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            broker = _broker(Path(tmp) / "ledger.json")
            plan = _plan()

            fills = broker.execute_batch(plan)
            after = broker.get_balance()

            self.assertEqual(len(fills), 3)
            self.assertEqual(after["revision"], 1)
            self.assertEqual(set(after["holdings"]), {"AAA", "BBB", "CCC"})
            with self.assertRaisesRegex(ValueError, "이미 처리"):
                broker.execute_batch(plan)
            self.assertEqual(broker.get_balance()["revision"], 1)

    def test_failure_before_atomic_replace_writes_no_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            broker = _broker(Path(tmp) / "ledger.json")
            plan = _plan()

            def fail_before_replace(ledger: dict) -> None:
                raise OSError("simulated crash")

            broker._save_atomic = fail_before_replace  # type: ignore[method-assign]
            with self.assertRaisesRegex(OSError, "simulated crash"):
                broker.execute_batch(plan)

            self.assertEqual(broker.get_balance()["holdings"], {})
            self.assertEqual(broker.get_balance()["revision"], 0)


def _broker(path: Path) -> LocalMockBroker:
    return LocalMockBroker(
        market="US",
        currency="USD",
        prices={"AAA": 10_000, "BBB": 20_000, "CCC": 25_000},
        initial_cash=1_000_000,
        ledger_path=path,
    )


def _plan():
    proposal = AdvisoryProposal(
        schema_version=1,
        proposal_id="",
        manifest_hash="b" * 64,
        input_hash="c" * 64,
        result_hash="d" * 64,
        market="US",
        currency="USD",
        scope="local_mock",
        selected=("AAA", "BBB", "CCC"),
        suggested_weights={"AAA": 30.0, "BBB": 30.0, "CCC": 30.0},
        cash_weight=10.0,
        exchanges={"AAA": "NASD", "BBB": "NYSE", "CCC": "NASD"},
        review=ReferenceReview("약점", "반대", "질문", ("b" * 64, "d" * 64)),
        exit_policy=ExitPolicy(1, True, 10.0, False),
    )
    proposal = replace(proposal, proposal_id=proposal_digest(proposal))
    spec = adopt_proposal(proposal, proposal.proposal_id, max_position_weight=40)
    return build_order_plan(
        spec,
        account_id="course-local-us",
        cash=1_000_000,
        holdings={},
        ledger_revision=0,
        prices={"AAA": 10_000, "BBB": 20_000, "CCC": 25_000},
        quote_timestamp="2026-08-28T00:00:00Z",
        guardrails=Guardrails(40, 10),
        created_at="2026-08-28T00:00:00Z",
        expires_at="2026-08-28T00:10:00Z",
    )


if __name__ == "__main__":
    unittest.main()

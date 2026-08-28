from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.us_reference import (  # noqa: E402
    AdvisoryProposal,
    ExitPolicy,
    Guardrails,
    ReferenceReview,
    adopt_proposal,
    build_order_plan,
    plan_digest,
    proposal_digest,
    load_adopted_spec,
    save_adopted_spec,
)


class ReferenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.proposal = AdvisoryProposal(
            schema_version=1,
            proposal_id="a" * 64,
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
            review=ReferenceReview(
                weakness="고정 바스켓에는 생존편향이 있습니다.",
                contrary_evidence="한국 시장 연구 결과는 일관되지 않습니다.",
                next_question="3개월 주기로 바꾸면 비용 후 결과가 어떻게 달라지는가?",
                evidence_ids=("b" * 64, "d" * 64),
            ),
            exit_policy=ExitPolicy(
                rebalance_months=1,
                sell_when_outside_target=True,
                stop_loss_review_pct=10.0,
                automatic_stop_loss=False,
            ),
        )
        self.proposal = replace(
            self.proposal,
            proposal_id=proposal_digest(self.proposal),
        )

    def test_adoption_is_mock_only_and_bound_to_full_hash_chain(self):
        spec = adopt_proposal(
            self.proposal,
            self.proposal.proposal_id,
            max_position_weight=40,
            spec_version=2,
        )

        self.assertEqual(len(spec.spec_hash), 64)
        self.assertEqual(spec.scope, "local_mock")
        self.assertEqual(spec.spec_version, 2)
        self.assertEqual(spec.manifest_hash, "b" * 64)
        self.assertEqual(spec.result_hash, "d" * 64)
        self.assertEqual(spec.max_position_weight, 40)

    def test_order_plan_binds_quotes_holdings_and_provenance(self):
        spec = adopt_proposal(
            self.proposal,
            self.proposal.proposal_id,
            max_position_weight=40,
        )

        plan = build_order_plan(
            spec,
            account_id="course-local-us",
            cash=1_000_000,
            holdings={},
            ledger_revision=0,
            prices={"AAA": 10_000, "BBB": 20_000, "CCC": 25_000},
            quote_timestamp="2026-08-28T00:00:00Z",
            guardrails=Guardrails(max_weight=40, min_cash=10),
            created_at="2026-08-28T00:00:00Z",
            expires_at="2026-08-28T00:10:00Z",
        )

        self.assertEqual(len(plan.plan_id), 64)
        self.assertEqual(plan.environment, "local_mock")
        self.assertEqual(plan.account_id, "course-local-us")
        self.assertEqual(plan.ledger_revision, 0)
        self.assertEqual(len(plan.holdings_hash), 64)
        self.assertEqual(plan.spec_hash, spec.spec_hash)
        self.assertEqual(plan.result_hash, spec.result_hash)
        self.assertEqual(plan.plan_id, plan_digest(plan))
        self.assertTrue(
            all(
                order.order_key == f"{plan.plan_id}:{index}"
                for index, order in enumerate(plan.orders)
            )
        )

    def test_tampered_order_plan_digest_is_detected(self):
        spec = adopt_proposal(
            self.proposal,
            self.proposal.proposal_id,
            max_position_weight=40,
        )
        plan = build_order_plan(
            spec,
            account_id="course-local-us",
            cash=1_000_000,
            holdings={},
            ledger_revision=0,
            prices={"AAA": 10_000, "BBB": 20_000, "CCC": 25_000},
            quote_timestamp="2026-08-28T00:00:00Z",
            guardrails=Guardrails(max_weight=40, min_cash=10),
            created_at="2026-08-28T00:00:00Z",
            expires_at="2026-08-28T00:10:00Z",
        )
        changed_order = replace(plan.orders[0], qty=plan.orders[0].qty + 1)
        tampered = replace(plan, orders=(changed_order, *plan.orders[1:]))

        self.assertNotEqual(plan_digest(tampered), tampered.plan_id)

    def test_adopted_spec_roundtrips_and_rejects_tampering(self):
        spec = adopt_proposal(
            self.proposal,
            self.proposal.proposal_id,
            max_position_weight=40,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.json"
            save_adopted_spec(spec, path)
            self.assertEqual(load_adopted_spec(path), spec)

            raw = path.read_text(encoding="utf-8").replace('"cash_weight": 10.0', '"cash_weight": 99.0')
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "스펙이 변경"):
                load_adopted_spec(path)


if __name__ == "__main__":
    unittest.main()

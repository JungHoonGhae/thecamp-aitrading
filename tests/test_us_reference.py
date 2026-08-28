from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.us_committee import (  # noqa: E402
    build_reference_advisory,
    load_advisory,
    load_reference_packet,
    save_advisory,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


class ReferenceProposalTests(unittest.TestCase):
    def test_reference_result_gets_one_read_only_ai_review(self):
        packet = load_reference_packet(FIXTURES, "US")
        calls: list[str] = []

        def fake_ask(*, 재료: str, 질문: str) -> str:
            calls.append(질문)
            return (
                "약점: 고정 바스켓에는 생존편향이 있습니다.\n"
                "반대 근거: 시장과 기간에 따라 모멘텀 결과가 약해질 수 있습니다.\n"
                "다음 질문: 3개월 주기로 바꾸면 비용 후 결과가 어떻게 달라지는가?"
            )

        proposal = build_reference_advisory(packet, ask_fn=fake_ask)

        self.assertEqual(len(calls), 1)
        self.assertEqual(proposal.review.weakness, "고정 바스켓에는 생존편향이 있습니다.")
        self.assertEqual(len(proposal.selected), 3)
        self.assertEqual(sum(proposal.suggested_weights.values()), 90)
        self.assertEqual(proposal.cash_weight, 10)
        self.assertEqual(proposal.exit_policy.rebalance_months, 1)
        self.assertFalse(proposal.exit_policy.automatic_stop_loss)
        self.assertEqual(proposal.scope, "local_mock")
        self.assertEqual(len(proposal.proposal_id), 64)

    def test_saved_proposal_roundtrips_without_reasking_ai(self):
        proposal = build_reference_advisory(load_reference_packet(FIXTURES, "US"))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            save_advisory(proposal, path)
            restored = load_advisory(path)

        self.assertEqual(restored, proposal)

    def test_tampered_saved_proposal_is_rejected(self):
        proposal = build_reference_advisory(load_reference_packet(FIXTURES, "US"))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            save_advisory(proposal, path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            first = next(iter(raw["suggested_weights"]))
            raw["suggested_weights"][first] = 99
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "변경되었거나 손상"):
                load_advisory(path)

    def test_korean_result_uses_same_proposal_boundary(self):
        proposal = build_reference_advisory(load_reference_packet(FIXTURES, "KR"))

        self.assertEqual(proposal.market, "KR")
        self.assertEqual(proposal.currency, "KRW")
        self.assertTrue(all(ticker.endswith(".KS") for ticker in proposal.selected))
        self.assertTrue(all(proposal.exchanges[ticker] == "KRX" for ticker in proposal.selected))


if __name__ == "__main__":
    unittest.main()

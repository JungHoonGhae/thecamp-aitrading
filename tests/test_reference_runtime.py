from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.plan_store import load_plan_record, save_pending_plan  # noqa: E402
from common.reference_runtime import (  # noqa: E402
    approve_reference_plan,
    create_reference_plan,
)
from common.us_committee import build_reference_advisory, load_reference_packet  # noqa: E402
from common.us_reference import adopt_proposal, save_adopted_spec  # noqa: E402

FIXTURES = ROOT / "src" / "common" / "fixtures"


class ReferenceRuntimeTests(unittest.TestCase):
    def test_stored_plan_executes_without_recalculation_and_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            packet = load_reference_packet(FIXTURES, "US")
            proposal = build_reference_advisory(packet)
            spec = adopt_proposal(
                proposal,
                proposal.proposal_id,
                max_position_weight=40,
            )
            save_adopted_spec(spec, state / "us-active-spec.json")
            plan = create_reference_plan(
                FIXTURES,
                state,
                market="US",
                now="2026-08-28T00:00:00Z",
            )
            pending = state / "telegram-plan.json"
            save_pending_plan(
                pending,
                plan,
                channel_id=10,
                sender_id=20,
                message_id=30,
            )

            fills = approve_reference_plan(
                FIXTURES,
                state,
                pending,
                plan_id=plan.plan_id,
                channel_id=10,
                sender_id=20,
                message_id=30,
                now="2026-08-28T00:05:00Z",
            )

            self.assertEqual(len(fills), 3)
            self.assertEqual(load_plan_record(pending)["status"], "executed")
            with self.assertRaisesRegex(RuntimeError, "executed"):
                approve_reference_plan(
                    FIXTURES,
                    state,
                    pending,
                    plan_id=plan.plan_id,
                    channel_id=10,
                    sender_id=20,
                    message_id=30,
                    now="2026-08-28T00:06:00Z",
                )


if __name__ == "__main__":
    unittest.main()

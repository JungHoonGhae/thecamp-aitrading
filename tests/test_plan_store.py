from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.plan_store import (  # noqa: E402
    PlanClaimError,
    cancel_plan,
    claim_pending_plan,
    finish_plan,
    load_plan_record,
    save_pending_plan,
)
from tests.test_local_mock_atomic import _plan  # noqa: E402


class PlanStoreTests(unittest.TestCase):
    def test_valid_plan_is_claimed_once_then_finished(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pending.json"
            plan = _plan()
            save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)

            claimed = _claim(path, plan)
            self.assertEqual(claimed, plan)
            self.assertEqual(load_plan_record(path)["status"], "executing")

            finish_plan(path, plan.plan_id, status="executed")
            with self.assertRaisesRegex(PlanClaimError, "executed"):
                _claim(path, plan)

    def test_expired_plan_is_persisted_as_expired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pending.json"
            plan = _plan()
            save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)

            with self.assertRaisesRegex(PlanClaimError, "expired"):
                _claim(path, plan, now="2026-08-28T00:11:00Z")

            self.assertEqual(load_plan_record(path)["status"], "expired")

    def test_tampered_plan_is_terminally_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pending.json"
            plan = _plan()
            save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["plan"]["prices"]["AAA"] += 1
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaisesRegex(PlanClaimError, "tampered"):
                _claim(path, plan)

            record = load_plan_record(path)
            self.assertEqual(record["status"], "failed")
            self.assertIn("tampered", record["failure_reason"])

    def test_wrong_owner_or_message_does_not_consume_plan(self):
        wrong_values = (
            {"channel_id": 99},
            {"sender_id": 99},
            {"message_id": 99},
            {"plan_id": "f" * 64},
        )
        for overrides in wrong_values:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pending.json"
                plan = _plan()
                save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)

                with self.assertRaises(PlanClaimError):
                    _claim(path, plan, **overrides)

                self.assertEqual(load_plan_record(path)["status"], "pending")

    def test_changed_spec_or_ledger_is_terminally_failed(self):
        wrong_values = (
            {"active_spec_version": 2},
            {"ledger_revision": 1},
            {"holdings_hash": "e" * 64},
        )
        for overrides in wrong_values:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pending.json"
                plan = _plan()
                save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)

                with self.assertRaises(PlanClaimError):
                    _claim(path, plan, **overrides)

                self.assertEqual(load_plan_record(path)["status"], "failed")

    def test_concurrent_callbacks_claim_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pending.json"
            plan = _plan()
            save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def attempt() -> None:
                barrier.wait()
                try:
                    _claim(path, plan)
                    outcomes.append("claimed")
                except PlanClaimError:
                    outcomes.append("rejected")

            threads = [threading.Thread(target=attempt) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(sorted(outcomes), ["claimed", "rejected"])
            self.assertEqual(load_plan_record(path)["status"], "executing")

    def test_cancelled_plan_cannot_be_claimed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pending.json"
            plan = _plan()
            save_pending_plan(path, plan, channel_id=10, sender_id=20, message_id=30)

            cancel_plan(
                path,
                plan_id=plan.plan_id,
                channel_id=10,
                sender_id=20,
                message_id=30,
            )

            self.assertEqual(load_plan_record(path)["status"], "cancelled")
            with self.assertRaisesRegex(PlanClaimError, "cancelled"):
                _claim(path, plan)


def _claim(path: Path, plan, **overrides):
    values = {
        "plan_id": plan.plan_id,
        "channel_id": 10,
        "sender_id": 20,
        "message_id": 30,
        "active_spec_version": 1,
        "ledger_revision": 0,
        "holdings_hash": plan.holdings_hash,
        "now": "2026-08-28T00:05:00Z",
    }
    values.update(overrides)
    return claim_pending_plan(path, **values)


if __name__ == "__main__":
    unittest.main()

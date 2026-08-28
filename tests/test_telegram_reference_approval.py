from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent.telegram_bot import Bot  # noqa: E402
from common.plan_store import load_plan_record  # noqa: E402
from common.us_committee import build_reference_advisory, load_reference_packet  # noqa: E402
from common.us_reference import adopt_proposal, save_adopted_spec  # noqa: E402

FIXTURES = ROOT / "src" / "common" / "fixtures"


class TelegramReferenceApprovalTests(unittest.TestCase):
    def test_rebalance_button_executes_the_stored_plan_once(self):
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
            bot = FakeBot(state)

            bot.cmd_rebalance(confirmed=False, sender_id=20)

            pending = state / "telegram-plan.json"
            record = load_plan_record(pending)
            self.assertEqual(record["status"], "pending")
            self.assertEqual(record["message_id"], 30)
            self.assertEqual(len(record["plan_id"]), 64)

            callback = {
                "id": "callback-1",
                "data": record["plan_id"],
                "from": {"id": 20},
                "message": {"message_id": 30, "chat": {"id": 10}},
            }
            bot.on_button(callback)
            first_ledger = json.loads(
                (state / "us-ledger.json").read_text(encoding="utf-8")
            )
            bot.on_button(callback)
            second_ledger = json.loads(
                (state / "us-ledger.json").read_text(encoding="utf-8")
            )

            self.assertEqual(load_plan_record(pending)["status"], "executed")
            self.assertEqual(first_ledger["revision"], 1)
            self.assertEqual(second_ledger["revision"], 1)


class FakeBot(Bot):
    def __init__(self, state: Path):
        super().__init__(
            "token",
            "10",
            state_dir=state,
            fixtures_dir=FIXTURES,
            clock=lambda: "2026-08-28T00:00:00Z",
        )
        self.calls: list[tuple[str, dict]] = []

    def call(self, method: str, payload: dict) -> dict:
        self.calls.append((method, payload))
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 30}}
        return {"ok": True, "result": {}}


class TelegramUpdateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = FakeBot(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_update_config_empty_does_not_call_judge(self) -> None:
        with mock.patch("src.common.judge.ask") as ask:
            self.bot.cmd_update_config("")
        ask.assert_not_called()
        self.assertTrue(
            any("바꿀 칸" in t[1]["text"] for t in self.bot.calls if t[0] == "sendMessage")
        )

    def test_dispatch_update_config_passes_trailing_text(self) -> None:
        with mock.patch.object(self.bot, "cmd_update_config") as handler:
            self.bot.dispatch("/update_config 허용 오차를 7%p 로")
        handler.assert_called_once_with("허용 오차를 7%p 로")

    def test_help_leads_with_scenes_not_init(self) -> None:
        self.bot.cmd_help()
        text = next(t[1]["text"] for t in self.bot.calls if t[0] == "sendMessage")
        self.assertIn("/config", text)
        self.assertIn("/update_config", text)
        self.assertLess(text.find("/config"), text.find("/init"))
        self.assertTrue(text.startswith("가져가는 것부터입니다"))

    def test_update_config_without_judge_explains(self) -> None:
        with mock.patch("agent.telegram_bot.judge.available", return_value=""):
            self.bot.cmd_update_config("허용 오차를 7%p 로")
        text = next(t[1]["text"] for t in self.bot.calls if t[0] == "sendMessage")
        self.assertIn("코딩 앱", text)


class TelegramAliasAndRoutineTests(unittest.TestCase):
    def test_점검_goes_to_check_not_doctor(self) -> None:
        from agent.telegram_bot import ALIASES

        self.assertEqual(ALIASES["점검"], "check")
        self.assertEqual(ALIASES["진단"], "doctor")
        self.assertEqual(len(ALIASES), len(set(ALIASES)))

    def test_dispatch_점검_calls_check(self) -> None:
        bot = FakeBot(Path(tempfile.mkdtemp()))
        with mock.patch.object(bot, "cmd_check") as check:
            with mock.patch.object(bot, "cmd_doctor") as doctor:
                bot.dispatch("점검")
        check.assert_called_once_with()
        doctor.assert_not_called()

    def test_routines_offers_on_demand_buttons(self) -> None:
        bot = FakeBot(Path(tempfile.mkdtemp()))
        with mock.patch("subprocess.run") as run:
            run.side_effect = OSError("no hermes")
            bot.cmd_routines()
        send = next(t for t in bot.calls if t[0] == "sendMessage")
        keyboard = send[1]["reply_markup"]["inline_keyboard"]
        data = {btn["callback_data"] for row in keyboard for btn in row}
        self.assertEqual(data, {"go:backtest", "go:levels"})
        self.assertIn("가격도달-감시", send[1]["text"])


class TelegramRejectAndExpireTests(unittest.TestCase):
    def _pending_bot(self, tmp: str) -> FakeBot:
        state = Path(tmp)
        packet = load_reference_packet(FIXTURES, "US")
        proposal = build_reference_advisory(packet)
        spec = adopt_proposal(
            proposal,
            proposal.proposal_id,
            max_position_weight=40,
        )
        save_adopted_spec(spec, state / "us-active-spec.json")
        bot = FakeBot(state)
        bot.cmd_rebalance(confirmed=False, sender_id=20)
        return bot

    def test_reject_button_cancels_without_fills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bot = self._pending_bot(tmp)
            record = load_plan_record(Path(tmp) / "telegram-plan.json")
            bot.on_button({
                "id": "callback-no",
                "data": "rb:no",
                "from": {"id": 20},
                "message": {"message_id": 30, "chat": {"id": 10}},
            })
            after = load_plan_record(Path(tmp) / "telegram-plan.json")
            self.assertEqual(after["status"], "cancelled")
            self.assertEqual(after["plan_id"], record["plan_id"])
            self.assertFalse((Path(tmp) / "us-ledger.json").exists())

    def test_expired_approval_does_not_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bot = self._pending_bot(tmp)
            record = load_plan_record(Path(tmp) / "telegram-plan.json")
            bot.clock = lambda: "2026-08-28T00:20:00Z"
            bot.on_button({
                "id": "callback-late",
                "data": record["plan_id"],
                "from": {"id": 20},
                "message": {"message_id": 30, "chat": {"id": 10}},
            })
            after = load_plan_record(Path(tmp) / "telegram-plan.json")
            self.assertEqual(after["status"], "expired")
            self.assertFalse((Path(tmp) / "us-ledger.json").exists())


if __name__ == "__main__":
    unittest.main()

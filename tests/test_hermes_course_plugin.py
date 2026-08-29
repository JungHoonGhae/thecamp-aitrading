from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "hermes" / "plugins" / "thecamp-invest" / "__init__.py"


class FakeContext:
    def __init__(self) -> None:
        self.commands: dict[str, dict] = {}
        self.hooks: dict[str, object] = {}

    def register_command(self, name, handler, description="", args_hint="") -> None:
        self.commands[name] = {
            "handler": handler,
            "description": description,
            "args_hint": args_hint,
        }

    def register_hook(self, name, callback) -> None:
        self.hooks[name] = callback


def load_plugin():
    spec = importlib.util.spec_from_file_location("thecamp_invest_plugin", PLUGIN)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HermesCoursePluginTests(unittest.TestCase):
    def test_helper_does_not_confuse_hermes_internal_agent_package(self) -> None:
        plugin = load_plugin()
        fake_agent = types.ModuleType("agent")
        previous = sys.modules.get("agent")
        sys.modules["agent"] = fake_agent
        try:
            helper = plugin._helper()
        finally:
            if previous is None:
                sys.modules.pop("agent", None)
            else:
                sys.modules["agent"] = previous

        self.assertEqual(ROOT / "agent" / "hermes_invest.py", Path(helper.__file__))
        self.assertTrue(callable(helper.pending_orders))

    def test_public_commands_have_ts_prefix_and_clear_names(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        expected = {
            "ts-help", "ts-update", "ts-doctor", "ts-auth", "ts-status",
            "ts-tools", "ts-config", "ts-analyze", "ts-rule", "ts-order-plan", "ts-memory",
        }
        self.assertEqual(expected, set(context.commands))
        self.assertTrue(all(name.startswith("ts-") for name in context.commands))

    def test_plan_command_rewrites_to_button_skill(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        event = type("Event", (), {"text": "/ts_order_plan"})()
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual("rewrite", result["action"])
        self.assertEqual("/thecamp-plan", result["text"])

    def test_review_command_uses_deterministic_native_choice(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        event = type("Event", (), {"text": "/ts_rule"})()
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual({"action": "rewrite", "text": "/ts-rule"}, result)

        menu = __import__("asyncio").run(context.commands["ts-rule"]["handler"](""))
        self.assertTrue(menu["__hermes_choice__"])
        self.assertEqual(
            ["📌 현재 규칙", "🔎 기본 분석 규칙의 근거와 한계"],
            menu["choices"],
        )
        self.assertIn("실행되지 않았습니다", menu["timeout_message"])

    def test_telegram_underscore_direct_commands_rewrite_to_registered_names(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        help_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_help"})()
        )
        memory_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_log 오늘은 보류"})()
        )
        status_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_status"})()
        )
        update_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_update"})()
        )
        doctor_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_doctor"})()
        )
        auth_result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_auth"})()
        )

        self.assertEqual({"action": "rewrite", "text": "/ts-help"}, help_result)
        self.assertEqual({"action": "rewrite", "text": "/ts-status"}, status_result)
        self.assertEqual({"action": "rewrite", "text": "/ts-update"}, update_result)
        self.assertEqual({"action": "rewrite", "text": "/ts-doctor"}, doctor_result)
        self.assertEqual({"action": "rewrite", "text": "/ts-auth"}, auth_result)
        self.assertEqual(
            {"action": "rewrite", "text": "/thecamp-memory 오늘은 보류"}, memory_result
        )

    def test_old_fundamental_command_rewrites_to_grouped_analyze_skill(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        event = type("Event", (), {"text": "/ts_fundamental AAPL"})()
        result = context.hooks["pre_gateway_dispatch"](event=event)
        self.assertEqual("/thecamp-analyze AAPL", result["text"])
        self.assertIn("기술적·펀더멘탈·둘 다", context.commands["ts-analyze"]["description"])

    def test_help_says_plan_uses_buttons(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        text = context.commands["ts-help"]["handler"]("")
        self.assertIn("승인·보류 버튼", text)
        self.assertIn("/ts_status", text)
        self.assertIn("/ts_update", text)
        self.assertIn("/ts_doctor", text)
        self.assertIn("/ts_auth", text)
        self.assertIn("/ts_config", text)
        self.assertIn("/ts_analyze [종목명·티커·시장]", text)
        self.assertIn("/ts_rule", text)
        self.assertIn("/ts_order_plan", text)
        self.assertIn("/ts_tools [찾을 말]", text)
        self.assertIn("/ts_memory [선택: 기억할 말]", text)
        self.assertIn("자동 기록 조회·필요한 원칙만 기억", text)
        self.assertNotIn("계획번호", text)
        self.assertIn("/stop", text)

        self.assertTrue(
            context.commands["ts-analyze"]["description"].startswith("[종목명·티커·시장]")
        )
        self.assertTrue(
            context.commands["ts-rule"]["description"].startswith("현재 규칙")
        )

    def test_status_is_direct_while_config_rewrites_to_button_skill(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        status = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_status"})()
        )
        config = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "/ts_config"})()
        )
        self.assertEqual("/ts-status", status["text"])
        self.assertEqual("/thecamp-settings", config["text"])
        self.assertNotIn("ts-status", load_plugin().ROUTED)
        self.assertIn("한 번에 확인", context.commands["ts-status"]["description"])

    def test_plain_account_questions_skip_the_model_and_open_status(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        for text in ("내 계좌상태 어때?", "+인가 -인가?", "평가손익 알려줘"):
            result = context.hooks["pre_gateway_dispatch"](
                event=type("Event", (), {"text": text})()
            )
            self.assertEqual({"action": "rewrite", "text": "/ts-status"}, result)

    def test_plain_tool_question_opens_the_166_catalog(self) -> None:
        context = FakeContext()
        load_plugin().register(context)
        result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": "MCP 166개에는 어떤 도구가 있어?"})()
        )
        self.assertEqual("rewrite", result["action"])
        self.assertTrue(result["text"].startswith("/ts-tools "))

    def test_explicit_plain_memory_request_uses_memory_skill(self) -> None:
        context = FakeContext()
        load_plugin().register(context)

        text = "앞으로도 기술주 합계 40%를 넘지 않게 기억해 줘"
        result = context.hooks["pre_gateway_dispatch"](
            event=type("Event", (), {"text": text})()
        )

        self.assertEqual(
            {"action": "rewrite", "text": f"/thecamp-memory {text}"},
            result,
        )


if __name__ == "__main__":
    unittest.main()

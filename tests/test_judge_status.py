from __future__ import annotations

import subprocess
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.common import judge


class JudgeStatusTests(unittest.TestCase):
    def test_worker_chain_has_a_classroom_time_limit(self) -> None:
        self.assertLessEqual(judge.TIMEOUT, 180)
        self.assertLessEqual(judge.TOTAL_TIMEOUT, 420)
        self.assertLess(judge.acp_worker.IDLE_TIMEOUT_SECONDS, judge.TOTAL_TIMEOUT)

    def test_reads_configured_model_and_effort_for_each_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_settings = root / "claude.json"
            claude_settings.write_text(
                json.dumps({"model": "opus[1m]", "effortLevel": "medium"}),
                encoding="utf-8",
            )
            codex_config = root / "config.toml"
            codex_config.write_text(
                'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "xhigh"\n',
                encoding="utf-8",
            )

            self.assertEqual(
                ("opus[1m]", "medium"),
                judge.configured_profile("claude", claude_settings=claude_settings),
            )
            self.assertEqual(
                ("gpt-5.6-sol", "xhigh"),
                judge.configured_profile("codex", codex_config=codex_config),
            )

        self.assertEqual(
            "Claude · 응답 · 모델 opus[1m] · effort medium",
            judge.route_attempt_line(
                judge.RouteAttempt("claude", "ok", "opus[1m]", "medium")
            ),
        )
        claude_command = judge._command(
            "claude", "질문", research=False, model="opus[1m]", effort="medium"
        )
        codex_command = judge._command(
            "codex", "질문", research=False, model="gpt-5.6-sol", effort="xhigh"
        )
        self.assertIn("--model", claude_command)
        self.assertIn("opus[1m]", claude_command)
        self.assertIn("--effort", claude_command)
        self.assertIn("medium", claude_command)
        self.assertIn("-m", codex_command)
        self.assertIn("gpt-5.6-sol", codex_command)
        self.assertIn('model_reasoning_effort="xhigh"', codex_command)

    def test_reports_when_no_cli_is_installed(self) -> None:
        with mock.patch("src.common.judge.shutil.which", return_value=None):
            result = judge.ask_with_status(재료="재료", 질문="질문", prefer_acp=False)

        self.assertFalse(result.ok)
        self.assertEqual("not_installed", result.status)
        self.assertIn("실행 파일", result.notice)
        self.assertIn("규칙 계산", result.notice)

    def test_reports_usage_limit_without_exposing_raw_error(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["claude"], returncode=1, stdout="", stderr="rate limit: secret-account"
        )
        with mock.patch("src.common.judge.shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("src.common.judge.subprocess.run", return_value=completed):
                result = judge.ask_with_status(
                    재료="재료", 질문="질문", prefer_acp=False
                )

        self.assertFalse(result.ok)
        self.assertEqual("usage_limit", result.status)
        self.assertIn("사용 한도", result.notice)
        self.assertNotIn("secret-account", result.notice)

    def test_falls_through_to_codex_when_earlier_routes_are_limited(self) -> None:
        limited = subprocess.CompletedProcess(
            args=["claude"], returncode=1, stdout="", stderr="rate limit"
        )
        success = subprocess.CompletedProcess(
            args=["codex"], returncode=0, stdout="검토 결과", stderr=""
        )
        with mock.patch("src.common.judge.shutil.which", return_value="/usr/bin/tool"):
            with mock.patch(
                "src.common.judge.subprocess.run",
                side_effect=[limited, success],
            ):
                result = judge.ask_with_status(
                    재료="재료", 질문="질문", prefer_acp=False
                )

        self.assertTrue(result.ok)
        self.assertEqual("codex", result.engine)
        self.assertEqual("검토 결과", result.text)
        self.assertIn("Claude · CLI · 사용 한도", judge.route_report(result))
        self.assertIn("Codex · CLI · 응답", judge.route_report(result))

    def test_uses_a_free_model_only_after_claude_and_codex_fail(self) -> None:
        failed = subprocess.CompletedProcess(
            args=["tool"], returncode=1, stdout="", stderr="not available"
        )
        success = subprocess.CompletedProcess(
            args=["hermes"], returncode=0, stdout="무료 폴백", stderr=""
        )
        with mock.patch("src.common.judge.shutil.which", return_value="/usr/bin/tool"):
            with mock.patch(
                "src.common.judge.subprocess.run",
                side_effect=[failed, failed, success],
            ) as run:
                result = judge.ask_with_status(
                    재료="재료", 질문="질문", prefer_acp=False
                )

        self.assertTrue(result.ok)
        self.assertEqual("free", result.engine)
        self.assertEqual(judge.PRIMARY_FREE_MODEL, result.model)
        self.assertEqual(3, run.call_count)
        command = run.call_args_list[-1].args[0]
        self.assertIn(judge.PRIMARY_FREE_MODEL, command)
        self.assertIn("무료 폴백 · solar-pro4 · Nous · 응답", judge.route_report(result))

    def test_prefers_claude_acp_and_displays_transport(self) -> None:
        acp_result = judge.acp_worker.ACPResult("ACP 검토 결과")
        with (
            mock.patch("src.common.judge.acp_worker.available", return_value=True),
            mock.patch(
                "src.common.judge.acp_worker.run_claude", return_value=acp_result
            ) as run,
        ):
            result = judge.ask_with_status(재료="재료", 질문="질문")

        self.assertTrue(result.ok)
        self.assertEqual("claude", result.engine)
        self.assertEqual("ACP", result.transport)
        self.assertIn("Claude · ACP · 응답", judge.route_report(result))
        run.assert_called_once()

    def test_current_nous_free_catalog_is_appended_without_paid_models(self) -> None:
        cache = {
            "portal": {"data": {"freeRecommendedModels": [
                {"modelName": "new/model:free"},
                {"modelName": "paid/model"},
            ]}}
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "models.json"
            path.write_text(json.dumps(cache), encoding="utf-8")
            models = judge.free_models(path)

        self.assertEqual(judge.PRIMARY_FREE_MODEL, models[0])
        self.assertIn("new/model:free", models)
        self.assertNotIn("paid/model", models)


if __name__ == "__main__":
    unittest.main()

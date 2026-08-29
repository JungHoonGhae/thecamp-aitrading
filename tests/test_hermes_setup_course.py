from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes import setup_course


def subprocess_result(output: str, *, returncode: int = 0) -> object:
    return mock.Mock(returncode=returncode, stdout=output, stderr="")


class HermesSetupCourseTests(unittest.TestCase):
    def test_public_commands_keep_update_near_the_top(self) -> None:
        self.assertEqual("ts_help", setup_course.PUBLIC_COMMANDS[0])
        self.assertEqual("ts_update", setup_course.PUBLIC_COMMANDS[1])
        self.assertEqual("ts_doctor", setup_course.PUBLIC_COMMANDS[2])
        self.assertEqual("ts_auth", setup_course.PUBLIC_COMMANDS[3])
        self.assertEqual(11, len(setup_course.PUBLIC_COMMANDS))

    def test_find_executable_supports_windows_gui_install_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            command = home / "AppData" / "Roaming" / "npm" / "hermes.cmd"
            command.parent.mkdir(parents=True)
            command.touch()
            with (
                mock.patch.object(setup_course.shutil, "which", return_value=None),
                mock.patch.object(setup_course.Path, "home", return_value=home),
            ):
                self.assertEqual(str(command), setup_course._find_executable("hermes"))

    def test_find_executable_supports_official_windows_hermes_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local_app_data = Path(tmp) / "AppData" / "Local"
            command = local_app_data / "hermes" / "bin" / "hermes.exe"
            command.parent.mkdir(parents=True)
            command.touch()
            with (
                mock.patch.object(setup_course.shutil, "which", return_value=None),
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                self.assertEqual(str(command), setup_course._find_executable("hermes"))

    def test_hermes_python_supports_windows_venv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            python = home / "hermes-agent" / "venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.touch()
            self.assertEqual(python, setup_course._hermes_python(home))

    def test_telegram_reactions_use_check_and_cross_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            adapter = (
                home
                / "hermes-agent"
                / "plugins"
                / "platforms"
                / "telegram"
                / "adapter.py"
            )
            adapter.parent.mkdir(parents=True)
            adapter.write_text(
                "from enum import Enum\n"
                "class ProcessingOutcome(Enum):\n"
                "    SUCCESS = 'success'\n"
                "reaction = "
                + setup_course.TELEGRAM_REACTION_SOURCE
                + "\n",
                encoding="utf-8",
            )

            self.assertTrue(setup_course._ensure_telegram_reaction_symbols(home))
            first = adapter.read_text(encoding="utf-8")
            self.assertIn(setup_course.TELEGRAM_REACTION_TARGET, first)
            self.assertNotIn(setup_course.TELEGRAM_REACTION_SOURCE, first)

            self.assertTrue(setup_course._ensure_telegram_reaction_symbols(home))
            self.assertEqual(first, adapter.read_text(encoding="utf-8"))

    def test_telegram_reaction_patch_leaves_unknown_versions_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            adapter = (
                home
                / "hermes-agent"
                / "plugins"
                / "platforms"
                / "telegram"
                / "adapter.py"
            )
            adapter.parent.mkdir(parents=True)
            adapter.write_text("REACTION = 'future-config'\n", encoding="utf-8")

            self.assertFalse(setup_course._ensure_telegram_reaction_symbols(home))
            self.assertEqual(
                "REACTION = 'future-config'\n",
                adapter.read_text(encoding="utf-8"),
            )

    def test_plugin_choice_bridge_is_installed_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            gateway = home / "hermes-agent" / "gateway" / "run.py"
            gateway.parent.mkdir(parents=True)
            gateway.write_text(
                "import asyncio\n"
                "async def dispatch(plugin_handler, user_args):\n"
                + setup_course.PLUGIN_CHOICE_SOURCE,
                encoding="utf-8",
            )

            self.assertTrue(setup_course._ensure_plugin_choice_bridge(home))
            first = gateway.read_text(encoding="utf-8")
            self.assertIn("__hermes_choice__", first)
            self.assertIn("send_clarify", first)
            self.assertIn("asyncio.to_thread", first)

            self.assertTrue(setup_course._ensure_plugin_choice_bridge(home))
            self.assertEqual(first, gateway.read_text(encoding="utf-8"))

    def test_plugin_choice_bridge_leaves_unknown_versions_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            gateway = home / "hermes-agent" / "gateway" / "run.py"
            gateway.parent.mkdir(parents=True)
            gateway.write_text("async def future_dispatch():\n    return None\n", encoding="utf-8")

            self.assertFalse(setup_course._ensure_plugin_choice_bridge(home))
            self.assertEqual(
                "async def future_dispatch():\n    return None\n",
                gateway.read_text(encoding="utf-8"),
            )

    def test_managed_telegram_keeps_token_out_of_process_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            python = home / "hermes-agent" / "venv" / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.touch()

            def fake_run(command: list[str], **_: object) -> None:
                compile(command[2], "<managed-telegram-helper>", "exec")
                result_path = Path(command[-2])
                fd = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "token": "123456:abcdefghijklmnopqrstuvwxyzABCDEFGHIJ",
                            "owner_user_id": "424242",
                            "bot_username": "hermes_course_bot",
                        },
                        stream,
                    )

            with mock.patch.object(setup_course.subprocess, "run", side_effect=fake_run) as run:
                token, chat_id, username = setup_course._managed_telegram_result(home)

        self.assertEqual("123456:abcdefghijklmnopqrstuvwxyzABCDEFGHIJ", token)
        self.assertEqual("424242", chat_id)
        self.assertEqual("hermes_course_bot", username)
        command = run.call_args.args[0]
        self.assertNotIn(token, command)
        self.assertIn("sys.stdout.flush()", command[2])
        self.assertIn("temporary", setup_course._managed_telegram_result.__doc__ or "")

    def test_gateway_restarts_when_it_is_already_running(self) -> None:
        status_running = subprocess_result("Gateway supervised (PID 4242)")
        restarted = subprocess_result("restarted")
        verified = subprocess_result("Gateway supervised (PID 4343)")
        with mock.patch.object(
            setup_course,
            "_gateway_call",
            side_effect=[status_running, restarted, verified],
        ) as call:
            action = setup_course._activate_gateway()

        self.assertEqual("다시 연결", action)
        self.assertEqual(
            [mock.call("status"), mock.call("restart"), mock.call("status")],
            call.call_args_list,
        )

    def test_gateway_is_installed_after_first_start_fails(self) -> None:
        stopped = subprocess_result("Gateway service is not loaded")
        failed_start = subprocess_result("service missing", returncode=1)
        installed = subprocess_result("installed")
        started = subprocess_result("started")
        verified = subprocess_result("Gateway supervised (PID 5151)")
        with mock.patch.object(
            setup_course,
            "_gateway_call",
            side_effect=[stopped, failed_start, installed, started, verified],
        ) as call:
            action = setup_course._activate_gateway()

        self.assertEqual("시작", action)
        self.assertEqual(mock.call("install"), call.call_args_list[2])
        self.assertEqual(mock.call("start"), call.call_args_list[3])

    def test_external_skill_dirs_are_written_as_a_real_config_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            hermes_python = home / "hermes-agent" / "venv" / "bin" / "python"
            hermes_python.parent.mkdir(parents=True)
            hermes_python.touch()
            hermes_calls = []

            def fake_hermes(*args: str, capture: bool = False) -> str:
                hermes_calls.append(args)
                if args == ("config", "get", "skills.external_dirs"):
                    return json.dumps(["/existing/skills"])
                if args == ("config", "path"):
                    return str(home / "config.yaml")
                return ""

            with (
                mock.patch.object(setup_course, "_hermes", side_effect=fake_hermes),
                mock.patch.object(setup_course.subprocess, "run") as run,
            ):
                setup_course._configure_commands()

        self.assertNotIn(
            ("config", "set", "skills.external_dirs", mock.ANY), hermes_calls
        )
        self.assertIn(
            (
                "config", "set", "agent.clarify_timeout",
                str(setup_course.COURSE_CLARIFY_TIMEOUT_SECONDS),
            ),
            hermes_calls,
        )
        self.assertIn(
            ("config", "set", "telegram.reactions", "true"),
            hermes_calls,
        )
        command = run.call_args.args[0]
        external_dirs = json.loads(command[-2])
        priority = json.loads(command[-1])
        self.assertEqual(
            ["/existing/skills", str(setup_course.SKILLS)], external_dirs
        )
        self.assertEqual(setup_course.PUBLIC_COMMANDS, priority)
        self.assertIn("['external_dirs']", command[2])

    def test_course_skills_use_hermes_absolute_path_template(self) -> None:
        skill_names = (
            "my-analyze", "my-status", "my-settings", "my-review", "my-plan",
            "my-tech", "my-fund", "my-hypothesis", "my-rule", "my-log",
        )
        for name in skill_names:
            skill_dir = setup_course.SKILLS / name
            body = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("python REPO/", body, name)
            self.assertIn("${HERMES_SKILL_DIR}", body, name)
            self.assertTrue((skill_dir / "../../../agent").resolve().is_dir(), name)

    def test_analysis_skill_preserves_native_telegram_attachments(self) -> None:
        body = (setup_course.SKILLS / "my-analyze" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("MEDIA:/절대경로.png", body)
        self.assertIn("MEDIA:/절대경로.html", body)
        self.assertIn("한 글자도 바꾸지 말고", body)
        self.assertIn("HTML은 Telegram 문서 파일로 직접 첨부", body)

    def test_review_skill_does_not_ask_students_to_adopt_the_fixed_example_again(self) -> None:
        body = (setup_course.SKILLS / "my-review" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("hypothesis-review", body)
        self.assertIn("두 번째 채택 질문을 띄우지", body)
        self.assertNotIn("adopt-latest", body)


if __name__ == "__main__":
    unittest.main()

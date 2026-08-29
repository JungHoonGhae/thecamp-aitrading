from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from agent import hermes_invest  # noqa: E402
from common.plan_store import load_plan_record  # noqa: E402
from common.us_committee import (  # noqa: E402
    build_reference_advisory,
    load_reference_packet,
    save_advisory,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


class HermesInvestTests(unittest.TestCase):
    class FakePaperKIS:
        account = "12345678"
        mode = "live"
        env = "paper"

        def __init__(self) -> None:
            self.orders: list[dict] = []
            self.balance = {"cash": 10_000_000, "holdings": []}

        def get_balance(self) -> dict:
            return {
                "cash": self.balance["cash"],
                "holdings": [dict(item) for item in self.balance["holdings"]],
            }

        def get_price(self, code: str) -> dict:
            return {"code": code, "price": 100_000}

        def get_pending_orders(self) -> list[dict]:
            return []

        def place_order(self, code: str, side: str, qty: int, name: str = "") -> dict:
            result = {
                "ok": True,
                "code": code,
                "side": side,
                "qty": qty,
                "msg": "모의 주문 접수",
                "order_no": f"P{len(self.orders) + 1}",
            }
            self.orders.append(result)
            return result

    def test_private_telegram_session_uses_chat_id_when_adapter_omits_user_id(self) -> None:
        env = {
            "HERMES_SESSION_PLATFORM": "telegram",
            "HERMES_SESSION_CHAT_ID": "10010",
            "HERMES_SESSION_CHAT_TYPE": "private",
            "HERMES_SESSION_USER_ID": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(("telegram", 10010, 10010), hermes_invest._session_ids())

    def test_group_telegram_session_still_requires_sender_id(self) -> None:
        env = {
            "HERMES_SESSION_PLATFORM": "telegram",
            "HERMES_SESSION_CHAT_ID": "-10010",
            "HERMES_SESSION_CHAT_TYPE": "group",
            "HERMES_SESSION_USER_ID": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with self.assertRaisesRegex(ValueError, "사용자를 확인하지 못했습니다"):
                hermes_invest._session_ids()

    def test_direct_plugin_command_recovers_single_user_ids_from_saved_setup(self) -> None:
        def env_for(path: Path) -> dict[str, str]:
            if path == hermes_invest.ROOT / ".env":
                return {"TELEGRAM_CHANNEL_ID": "10010"}
            return {
                "TELEGRAM_HOME_CHANNEL": "10010",
                "TELEGRAM_ALLOWED_USERS": "10010",
            }

        empty_context = {
            "HERMES_SESSION_PLATFORM": "",
            "HERMES_SESSION_CHAT_ID": "",
            "HERMES_SESSION_CHAT_TYPE": "",
            "HERMES_SESSION_USER_ID": "",
        }
        with (
            mock.patch.dict(os.environ, empty_context, clear=False),
            mock.patch.object(hermes_invest, "_read_env_file", side_effect=env_for),
        ):
            self.assertEqual(("telegram", 10010, 10010), hermes_invest._session_ids())

    def test_read_only_account_commands_use_the_same_course_mock_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "10010",
                "HERMES_SESSION_USER_ID": "20",
            }
            with mock.patch.object(hermes_invest, "STATE", Path(tmp)):
                with mock.patch.dict(os.environ, env, clear=False):
                    account = hermes_invest.account()
                    holdings = hermes_invest.holdings()
                    pending = hermes_invest.pending_orders()
                    status = hermes_invest.status()

        self.assertIn("수업용 모의계좌", account)
        self.assertIn("$10,000.00", account)
        self.assertIn("보유 종목이 없습니다", holdings)
        self.assertIn("승인 대기 계획 없음", pending)
        self.assertIn("미체결 주문 없음", pending)
        self.assertIn("[계좌 · 수업용 모의계좌]", status)
        self.assertIn("[보유 주식 · 수업용 모의계좌]", status)
        self.assertIn("[대기 주문 · 수업용 계좌]", status)
        self.assertNotIn("아래 버튼", status)

    def test_account_config_defaults_to_course_and_switches_only_after_paper_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "10010",
                "HERMES_SESSION_USER_ID": "20",
            }
            fake = self.FakePaperKIS()
            with mock.patch.object(hermes_invest, "STATE", Path(tmp)):
                with mock.patch.dict(os.environ, env, clear=False):
                    before = hermes_invest.settings()
                    with mock.patch.object(
                        hermes_invest, "_kis_paper_client", return_value=fake
                    ):
                        changed = hermes_invest.set_account_type("kis-paper")
                        after = hermes_invest.settings()
                        account = hermes_invest.account()

        self.assertIn("현재 선택: 수업용 계좌", before)
        self.assertIn("KIS 모의투자 계좌", changed)
        self.assertIn("현재 선택: KIS 모의투자 계좌", after)
        self.assertIn("계좌 ****5678", account)
        self.assertIn("수업용 계좌와 별도", account)

    def test_failed_paper_check_keeps_the_course_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "10010",
                "HERMES_SESSION_USER_ID": "20",
            }
            with mock.patch.object(hermes_invest, "STATE", Path(tmp)):
                with mock.patch.dict(os.environ, env, clear=False):
                    with mock.patch.object(
                        hermes_invest,
                        "_kis_paper_client",
                        side_effect=RuntimeError("연결 실패"),
                    ):
                        with self.assertRaisesRegex(ValueError, "전환하지 않았습니다"):
                            hermes_invest.set_account_type("kis-paper")
                    current = hermes_invest.settings()

        self.assertIn("현재 선택: 수업용 계좌", current)

    def test_rule_uses_the_selected_kis_paper_portfolio_instead_of_us_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "10010",
                "HERMES_SESSION_USER_ID": "20",
            }
            fake = self.FakePaperKIS()
            with (
                mock.patch.object(hermes_invest, "STATE", Path(tmp)),
                mock.patch.dict(os.environ, env, clear=False),
                mock.patch.object(hermes_invest, "_kis_paper_client", return_value=fake),
            ):
                hermes_invest.set_account_type("kis-paper")
                output = hermes_invest.rule()

        self.assertIn("현재 규칙 · KIS 모의투자 계좌", output)
        self.assertIn("삼성전자 (005930) 목표 20%", output)
        self.assertIn("한 종목 최대 40%", output)
        self.assertNotIn("최근 한 달을 빼고", output)

    def test_hypothesis_review_keeps_candidates_separate_from_orders(self) -> None:
        result = hermes_invest.judge.AskResult(
            text="관찰: 설명 가능한 후보 선별\n장점: 같은 기준\n약점: 시장 국면\n다음 질문: 비용 후에도 남는가?",
            engine="claude",
            status="ok",
            notice="",
            attempts=(
                hermes_invest.judge.RouteAttempt(
                    "claude", "ok", "sonnet", "low", "ACP"
                ),
            ),
            model="sonnet",
            effort="low",
            transport="ACP",
        )
        with mock.patch.object(
            hermes_invest.judge, "ask_with_status", return_value=result
        ) as ask:
            output = hermes_invest.hypothesis_review()

        self.assertIn("KIS 국내주식 시가총액 상위 결과에서 앞 30개", output)
        self.assertIn("현재가가 20일 이동평균 위", output)
        self.assertIn("후보는 주문이 아닙니다", output)
        self.assertIn("Claude · ACP · 모델 sonnet · effort low", output)
        self.assertNotIn("수업 규칙으로 채택", output)
        self.assertIn("후보 세 개를 주문", ask.call_args.kwargs["규칙"])

    def test_paper_client_recovers_from_official_settings_when_project_has_placeholders(self) -> None:
        recovered_client = self.FakePaperKIS()
        failed = RuntimeError("live 모드인데 KIS_APP_KEY 가 비어 있습니다")
        done = mock.Mock(returncode=0, stdout="복구 완료", stderr="")
        with (
            mock.patch.object(
                hermes_invest, "KISClient", side_effect=[failed, recovered_client]
            ) as client,
            mock.patch.object(
                hermes_invest,
                "_read_env_file",
                return_value={
                    "KIS_APP_KEY": "여기에_앱키",
                    "KIS_APP_SECRET": "여기에_시크릿",
                    "KIS_ACCOUNT": "모의계좌_앞8자리",
                },
            ),
            mock.patch.object(
                hermes_invest, "_official_kis_settings_ready", return_value=True
            ),
            mock.patch.object(hermes_invest.subprocess, "run", return_value=done) as run,
        ):
            result = hermes_invest._kis_paper_client()

        self.assertIs(recovered_client, result)
        self.assertEqual(2, client.call_count)
        run.assert_called_once()

    def test_auth_status_is_read_only_and_names_cli_style_probes(self) -> None:
        env = {
            "HERMES_SESSION_PLATFORM": "telegram",
            "HERMES_SESSION_CHAT_ID": "10010",
            "HERMES_SESSION_USER_ID": "20",
        }
        credentials = {
            "KIS_APP_KEY": "a" * 36,
            "KIS_APP_SECRET": "b" * 180,
            "KIS_ACCOUNT": "12345678",
            "TELEGRAM_BOT_TOKEN": "saved",
        }
        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(hermes_invest.shutil, "which", return_value="/tool"),
            mock.patch.object(hermes_invest, "_probe_command", return_value=True),
            mock.patch.object(hermes_invest, "_read_env_file", return_value=credentials),
        ):
            output = hermes_invest.auth_status()

        self.assertIn("Claude Code · auth status", output)
        self.assertIn("Codex CLI · login status", output)
        self.assertIn("Nous :free 로그인", output)
        self.assertIn("AI 호출·잔고 조회·주문을 하지 않습니다", output)

    def test_gateway_status_requires_a_running_pid(self) -> None:
        stopped = subprocess.CompletedProcess(
            ["hermes", "gateway", "status"],
            0,
            stdout="Gateway service is not loaded\n",
            stderr="",
        )
        running = subprocess.CompletedProcess(
            ["hermes", "gateway", "status"],
            0,
            stdout="Gateway is supervised by launchd (PID 2265)\n",
            stderr="",
        )
        with mock.patch.object(hermes_invest.subprocess, "run", return_value=stopped):
            self.assertFalse(
                hermes_invest._probe_command(
                    ["hermes", "gateway", "status"], success_text="pid"
                )
            )
        with mock.patch.object(hermes_invest.subprocess, "run", return_value=running):
            self.assertTrue(
                hermes_invest._probe_command(
                    ["hermes", "gateway", "status"], success_text="pid"
                )
            )

    def test_windows_hermes_install_and_runtime_paths_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local_app_data = Path(tmp) / "AppData" / "Local"
            binary = local_app_data / "hermes" / "bin" / "hermes.exe"
            binary.parent.mkdir(parents=True)
            binary.touch()
            runtime = local_app_data / "hermes"
            config = runtime / "config.yaml"
            secret_env = runtime / ".env"
            responses = [
                subprocess.CompletedProcess([str(binary)], 0, stdout=str(config) + "\n", stderr=""),
                subprocess.CompletedProcess([str(binary)], 0, stdout=str(secret_env) + "\n", stderr=""),
            ]
            with (
                mock.patch.object(hermes_invest.shutil, "which", return_value=None),
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                found = hermes_invest._find_executable("hermes")
                with mock.patch.object(
                    hermes_invest.subprocess, "run", side_effect=responses
                ):
                    home, env_path = hermes_invest._hermes_runtime_paths(found)

        self.assertEqual(str(binary), found)
        self.assertEqual(runtime, home)
        self.assertEqual(secret_env, env_path)

    def test_auth_status_does_not_claim_free_router_login_when_portal_is_logged_out(self) -> None:
        env = {
            "HERMES_SESSION_PLATFORM": "telegram",
            "HERMES_SESSION_CHAT_ID": "10010",
            "HERMES_SESSION_USER_ID": "20",
        }
        credentials = {
            "KIS_APP_KEY": "a" * 36,
            "KIS_APP_SECRET": "b" * 180,
            "KIS_ACCOUNT": "12345678",
            "TELEGRAM_BOT_TOKEN": "saved",
        }

        def probe(command: list[str], **_: object) -> bool:
            return command[1:3] != ["portal", "info"]

        with (
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(hermes_invest, "_find_executable", return_value="/tool"),
            mock.patch.object(hermes_invest, "_probe_command", side_effect=probe),
            mock.patch.object(hermes_invest, "_read_env_file", return_value=credentials),
        ):
            output = hermes_invest.auth_status()

        self.assertIn("Nous Portal 로그인 필요", output)
        self.assertNotIn("Nous :free 로그인", output)

    def test_analysis_indicator_can_show_ma5_without_changing_account(self) -> None:
        prices = [100.0 + i for i in range(120)]
        benchmark = [100.0 + i * 0.25 for i in range(120)]
        env = {
            "HERMES_SESSION_PLATFORM": "telegram",
            "HERMES_SESSION_CHAT_ID": "10010",
            "HERMES_SESSION_USER_ID": "20",
        }
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(hermes_invest, "STATE", Path(tmp)):
                with mock.patch.dict(os.environ, env, clear=False):
                    changed = hermes_invest.set_analysis_indicator("ma5")
                    with mock.patch("agent.hermes_invest.market.to_symbol", return_value="AAPL"):
                        with mock.patch(
                            "agent.hermes_invest.market.history",
                            side_effect=[prices, benchmark],
                        ):
                            with mock.patch(
                                "agent.hermes_invest.market.profile",
                                return_value={"name": "Apple"},
                            ):
                                output = hermes_invest.technical("AAPL")
                    current = hermes_invest.settings()

        self.assertIn("5일선 추가", changed)
        self.assertIn("5일 평균보다", output)
        self.assertIn("현재 선택: 수업용 계좌", current)
        self.assertIn("확장 · 5일선 추가", current)

    def test_course_update_delegates_then_verifies_and_refreshes(self) -> None:
        agent_done = mock.Mock(returncode=0, stdout="🔄 실습 환경 · 업데이트\n✅ 맞춤 완료", stderr="")
        verify_done = mock.Mock(returncode=0, stdout="5/5", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(hermes_invest, "STATE", Path(tmp)),
                mock.patch.object(
                    hermes_invest,
                    "_course_update_agents",
                    return_value=[("Claude Code · Sonnet · effort low", ["claude"])],
                ),
                mock.patch.object(
                    hermes_invest.subprocess,
                    "run",
                    side_effect=[agent_done, verify_done],
                ) as run,
                mock.patch.object(hermes_invest, "_refresh_course_connection") as refresh,
            ):
                output = hermes_invest.update_course()

        self.assertEqual(2, run.call_count)
        refresh.assert_called_once_with()
        self.assertIn("Claude Code · Sonnet · effort low", output)
        self.assertIn("python verify.py 5/5", output)

    def test_course_update_gives_claude_scoped_edit_permission(self) -> None:
        def executable(name: str) -> str | None:
            return "/usr/local/bin/claude" if name == "claude" else None

        with mock.patch.object(
            hermes_invest.shutil, "which", side_effect=executable
        ):
            label, command = hermes_invest._course_update_agents()[0]

        self.assertIn("실습 폴더 수정", label)
        self.assertIn("acceptEdits", command)
        self.assertNotIn("bypassPermissions", command)
        allowed = command[command.index("--allowedTools") + 1]
        self.assertIn("Edit", allowed)
        self.assertIn("Bash(python verify.py)", allowed)

    def test_course_update_restores_student_settings_after_agent_changes_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            protected = Path(tmp) / ".env"
            protected.write_text("KIS_APP_KEY=student-secret\n", encoding="utf-8")
            with mock.patch.object(
                hermes_invest, "_student_settings_paths", return_value=[protected]
            ):
                with hermes_invest._preserve_student_settings():
                    protected.write_text("KIS_APP_KEY=example\n", encoding="utf-8")

            restored = protected.read_text(encoding="utf-8")

        self.assertEqual("KIS_APP_KEY=student-secret\n", restored)

    def test_course_update_falls_back_from_claude_to_codex(self) -> None:
        failed = mock.Mock(returncode=1, stdout="", stderr="rate limit")
        succeeded = mock.Mock(returncode=0, stdout="🔄 업데이트", stderr="")
        verified = mock.Mock(returncode=0, stdout="5/5", stderr="")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(hermes_invest, "STATE", Path(tmp)),
                mock.patch.object(
                    hermes_invest,
                    "_course_update_agents",
                    return_value=[
                        ("Claude Code", ["claude"]),
                        ("Codex CLI", ["codex"]),
                    ],
                ),
                mock.patch.object(
                    hermes_invest.subprocess,
                    "run",
                    side_effect=[failed, succeeded, verified],
                ),
                mock.patch.object(hermes_invest, "_refresh_course_connection"),
            ):
                output = hermes_invest.update_course()

        self.assertIn("Codex CLI", output)
        self.assertNotIn("rate limit", output)

    def test_paper_plan_uses_exact_approved_orders_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HERMES_SESSION_PLATFORM": "telegram",
                "HERMES_SESSION_CHAT_ID": "10010",
                "HERMES_SESSION_USER_ID": "20",
            }
            fake = self.FakePaperKIS()
            with mock.patch.object(hermes_invest, "STATE", Path(tmp)):
                with mock.patch.dict(os.environ, env, clear=False):
                    with mock.patch.object(
                        hermes_invest, "_kis_paper_client", return_value=fake
                    ):
                        hermes_invest.set_account_type("kis-paper")
                        preview = hermes_invest.plan()
                        filled = hermes_invest.plan(approve_latest=True)
                        with self.assertRaisesRegex(RuntimeError, "already executed"):
                            hermes_invest.plan(approve_latest=True)

        self.assertIn("KIS 모의투자 계좌 · 아직 주문 아님", preview)
        self.assertIn("Telegram 버튼", preview)
        self.assertIn("KIS 모의투자 계좌", filled)
        self.assertGreater(len(fake.orders), 0)

    def test_technical_is_deterministic_and_compares_index(self) -> None:
        prices = [100.0 + i for i in range(120)]
        benchmark = [100.0 + i * 0.25 for i in range(120)]
        with mock.patch("agent.hermes_invest.market.to_symbol", return_value="AAPL"):
            with mock.patch(
                "agent.hermes_invest.market.history", side_effect=[prices, benchmark]
            ):
                with mock.patch(
                    "agent.hermes_invest.market.profile",
                    return_value={"name": "Apple", "sector": "기술", "industry": ""},
                ):
                    text = hermes_invest.technical("AAPL")

        self.assertIn("S&P500", text)
        self.assertIn("주문과 연결되지 않습니다", text)
        self.assertIn("Yahoo Finance 시세", text)
        self.assertIn("주문 계산에는 사용하지 않음", text)

    def test_technical_review_keeps_base_numbers_and_names_the_ai_worker(self) -> None:
        prices = [100.0 + i for i in range(120)]
        benchmark = [100.0 + i * 0.25 for i in range(120)]
        result = hermes_invest.judge.AskResult(
            "관찰 의견: 강한 흐름\n지수보다 강하지만 변동을 확인하세요.",
            "claude",
            "ok",
            "",
            (hermes_invest.judge.RouteAttempt("claude", "ok"),),
        )
        with mock.patch("agent.hermes_invest.market.to_symbol", return_value="AAPL"):
            with mock.patch(
                "agent.hermes_invest.market.history", side_effect=[prices, benchmark]
            ):
                with mock.patch(
                    "agent.hermes_invest.market.profile", return_value={"name": "Apple"}
                ):
                    with mock.patch.object(
                        hermes_invest.judge, "ask_with_status", return_value=result
                    ):
                        text = hermes_invest.technical_review("AAPL")

        self.assertIn("[기본 분석 · 규칙 코드]", text)
        self.assertIn("[AI 최종 의견 · Claude", text)
        self.assertIn("1년 가격 변화", text)
        self.assertIn("주문값을 만들거나 바꾸지 않습니다", text)

    def test_market_review_supports_korea_group_and_names_codex(self) -> None:
        kospi = [100.0 + i * 0.5 for i in range(120)]
        kosdaq = [100.0 - i * 0.1 for i in range(120)]
        result = hermes_invest.judge.AskResult(
            "시장 의견: 엇갈림\n코스피와 코스닥의 방향이 다릅니다.",
            "codex",
            "ok",
            "",
            (hermes_invest.judge.RouteAttempt("codex", "ok"),),
        )
        with mock.patch.object(
            hermes_invest.market, "history", side_effect=[kospi, kosdaq]
        ):
            with mock.patch.object(
                hermes_invest.judge, "ask_with_status", return_value=result
            ):
                text = hermes_invest.market_review("한국")

        self.assertIn("[시장 분석] 한국 증시", text)
        self.assertIn("코스피", text)
        self.assertIn("코스닥", text)
        self.assertIn("[AI 최종 의견 · Codex", text)

    def test_fundamental_discloses_the_selected_worker(self) -> None:
        result = hermes_invest.judge.AskResult(
            "사업과 재무 요약 [공식 자료 · 2026-08-01]",
            "claude",
            "ok",
            "",
            (hermes_invest.judge.RouteAttempt("claude", "ok"),),
        )
        with mock.patch.object(
            hermes_invest.judge, "ask_with_status", return_value=result
        ) as ask:
            text = hermes_invest.fundamental("AAPL")

        self.assertTrue(ask.call_args.kwargs["research"])
        self.assertIn("Claude · 응답", text)
        self.assertIn("주문 권한 없음", text)
        self.assertIn("주문값을 바꾸지 않습니다", text)

    def test_combined_analysis_uses_one_research_worker_for_both_parts(self) -> None:
        result = hermes_invest.judge.AskResult(
            "펀더멘탈 확인: 공식 자료\n종합 의견: 엇갈림",
            "claude",
            "ok",
            "",
            (hermes_invest.judge.RouteAttempt(
                "claude", "ok", transport="ACP"
            ),),
            transport="ACP",
        )
        packet = {"display": "Apple Inc.", "symbol": "AAPL"}
        with (
            mock.patch.object(
                hermes_invest, "_technical_packet", return_value=packet
            ),
            mock.patch.object(
                hermes_invest, "_technical_text", return_value="[기술적 분석] AAPL"
            ),
            mock.patch.object(
                hermes_invest.judge, "ask_with_status", return_value=result
            ) as ask,
        ):
            output = hermes_invest.combined_analysis("AAPL")

        self.assertEqual(1, ask.call_count)
        self.assertTrue(ask.call_args.kwargs["research"])
        self.assertIn("펀더멘탈 확인", output)
        self.assertIn("Claude · ACP", output)

    def test_plan_is_bound_to_telegram_user_and_executes_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            packet = load_reference_packet(FIXTURES, "US")
            proposal = build_reference_advisory(packet)
            save_advisory(proposal, state / "us-proposal.json")
            with mock.patch.object(hermes_invest, "STATE", state):
                hermes_invest.adopt(proposal.proposal_id)
                env = {
                    "HERMES_SESSION_PLATFORM": "telegram",
                    "HERMES_SESSION_CHAT_ID": "-10010",
                    "HERMES_SESSION_USER_ID": "20",
                }
                with mock.patch.dict(os.environ, env, clear=False):
                    preview = hermes_invest.plan()
                    pending = hermes_invest._pending_path(-10010)
                    plan_id = load_plan_record(pending)["plan_id"]
                    ai_result = hermes_invest.judge.AskResult(
                        "사람이 비중을 확인하세요.", "codex", "ok", "",
                        (hermes_invest.judge.RouteAttempt("codex", "ok"),),
                    )
                    with mock.patch.object(
                        hermes_invest.judge, "ask_with_status", return_value=ai_result
                    ):
                        reviewed = hermes_invest.review_pending_plan()
                    filled = hermes_invest.plan(approve_latest=True)
                    with self.assertRaisesRegex(RuntimeError, "already executed"):
                        hermes_invest.plan(approve_latest=True)

        self.assertIn("아직 주문 아님", preview)
        self.assertNotRegex(preview, r"[0-9a-f]{64}")
        self.assertIn("Telegram 버튼", preview)
        self.assertIn("Codex · 응답", reviewed)
        self.assertIn("승인도 대신하지 않습니다", reviewed)
        self.assertIn("실제 돈은 움직이지 않았습니다", filled)

    def test_plan_rejects_a_different_telegram_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            packet = load_reference_packet(FIXTURES, "US")
            proposal = build_reference_advisory(packet)
            save_advisory(proposal, state / "us-proposal.json")
            with mock.patch.object(hermes_invest, "STATE", state):
                hermes_invest.adopt(proposal.proposal_id)
                owner = {
                    "HERMES_SESSION_PLATFORM": "telegram",
                    "HERMES_SESSION_CHAT_ID": "-10010",
                    "HERMES_SESSION_USER_ID": "20",
                }
                with mock.patch.dict(os.environ, owner, clear=False):
                    preview = hermes_invest.plan()
                stranger = {**owner, "HERMES_SESSION_USER_ID": "21"}
                with mock.patch.dict(os.environ, stranger, clear=False):
                    with self.assertRaisesRegex(RuntimeError, "wrong sender"):
                        hermes_invest.plan(approve_latest=True)

    def test_plan_can_be_cancelled_with_button_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            packet = load_reference_packet(FIXTURES, "US")
            proposal = build_reference_advisory(packet)
            save_advisory(proposal, state / "us-proposal.json")
            with mock.patch.object(hermes_invest, "STATE", state):
                hermes_invest.adopt(proposal.proposal_id)
                env = {
                    "HERMES_SESSION_PLATFORM": "telegram",
                    "HERMES_SESSION_CHAT_ID": "10010",
                    "HERMES_SESSION_USER_ID": "20",
                }
                with mock.patch.dict(os.environ, env, clear=False):
                    hermes_invest.plan()
                    cancelled = hermes_invest.plan(cancel_latest=True)
                    with self.assertRaisesRegex(RuntimeError, "already cancelled"):
                        hermes_invest.plan(approve_latest=True)

        self.assertIn("실행하지 않았습니다", cancelled)


if __name__ == "__main__":
    unittest.main()

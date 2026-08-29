from __future__ import annotations

import subprocess
import unittest
from unittest import mock

import verify


class VerifyDeliveryTests(unittest.TestCase):
    def test_checks_never_send_reports_to_telegram(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["python", "agent/agent.py"],
            returncode=0,
            stdout="주문 전송",
            stderr="",
        )

        with mock.patch.dict(
            verify.os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "live-token",
                "TELEGRAM_CHANNEL_ID": "1234",
            },
            clear=False,
        ):
            with mock.patch.object(verify.subprocess, "run", return_value=completed) as run:
                self.assertTrue(
                    verify.run(
                        "연습 계좌에 주문이 들어갑니다",
                        ["agent/agent.py", "--execute"],
                        "주문 전송",
                    )
                )

        child_env = run.call_args.kwargs["env"]
        self.assertEqual(child_env["TELEGRAM_BOT_TOKEN"], "")
        self.assertEqual(child_env["TELEGRAM_CHANNEL_ID"], "")


if __name__ == "__main__":
    unittest.main()

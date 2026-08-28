from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class USReferenceCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_committee_stops_at_a_saved_advisory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "proposal.json"
            result = self.run_cli("agent/committee.py", "--output", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("아직 주문이 아닙니다", result.stdout)
            self.assertIn("제안 번호", result.stdout)
            self.assertIn("1개월마다", result.stdout)
            self.assertIn("-10%", result.stdout)
            self.assertTrue(output.is_file())

    def test_demo_requires_both_proposal_adoption_and_exact_order_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal_path = Path(tmp) / "proposal.json"
            ledger_path = Path(tmp) / "ledger.json"
            committee = self.run_cli(
                "agent/committee.py", "--output", str(proposal_path)
            )
            self.assertEqual(committee.returncode, 0, committee.stderr)
            proposal_id = json.loads(proposal_path.read_text(encoding="utf-8"))[
                "proposal_id"
            ]

            preview = self.run_cli(
                "agent/us_agent.py",
                "--proposal",
                str(proposal_path),
                "--ledger",
                str(ledger_path),
                "--adopt",
                proposal_id,
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("주문 계획 번호", preview.stdout)
            plan_id = next(
                line.split(": ", 1)[1]
                for line in preview.stdout.splitlines()
                if line.startswith("주문 계획 번호:")
            )

            blocked = self.run_cli(
                "agent/us_agent.py",
                "--proposal",
                str(proposal_path),
                "--ledger",
                str(ledger_path),
                "--adopt",
                proposal_id,
                "--max-weight",
                "15",
            )
            self.assertEqual(blocked.returncode, 0, blocked.stderr)
            self.assertIn("최대 비중", blocked.stdout)

            missing = self.run_cli(
                "agent/us_agent.py",
                "--proposal",
                str(proposal_path),
                "--ledger",
                str(ledger_path),
                "--adopt",
                proposal_id,
                "--execute",
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(ledger_path.exists())

            executed = self.run_cli(
                "agent/us_agent.py",
                "--proposal",
                str(proposal_path),
                "--ledger",
                str(ledger_path),
                "--adopt",
                proposal_id,
                "--approve",
                plan_id,
                "--execute",
            )
            self.assertEqual(executed.returncode, 0, executed.stderr)
            self.assertIn("로컬 모의계좌 체결", executed.stdout)
            self.assertTrue(ledger_path.is_file())

    def test_same_cli_flow_supports_korean_stocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proposal_path = Path(tmp) / "kr-proposal.json"
            ledger_path = Path(tmp) / "kr-ledger.json"
            committee = self.run_cli(
                "agent/committee.py",
                "--market",
                "KR",
                "--output",
                str(proposal_path),
            )
            self.assertEqual(committee.returncode, 0, committee.stderr)
            saved = json.loads(proposal_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["market"], "KR")

            preview = self.run_cli(
                "agent/us_agent.py",
                "--market",
                "KR",
                "--proposal",
                str(proposal_path),
                "--ledger",
                str(ledger_path),
                "--adopt",
                saved["proposal_id"],
            )
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertIn("한국 주식", preview.stdout)
            self.assertIn("원", preview.stdout)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsStudentFlowTests(unittest.TestCase):
    def test_utf8_mcp_order_works_from_a_korean_path_with_cp949_parent(self) -> None:
        """Reproduce the Windows failure mode without needing a Windows host.

        The parent advertises cp949, while MCP JSON and the Korean order words
        remain UTF-8.  The copied repository path also contains spaces and
        Korean characters, matching the most failure-prone student layout.
        """
        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / "학생 실습 폴더"
            (course / "agent").mkdir(parents=True)
            shutil.copy2(ROOT / "agent" / "mcp_server.py", course / "agent" / "mcp_server.py")
            shutil.copytree(ROOT / "src", course / "src")
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "call_api",
                        "arguments": {
                            "api": "order_cash",
                            "params": {
                                "code": "005930",
                                "side": "매수",
                                "qty": 1,
                                "confirm": "모의주문",
                            },
                        },
                    },
                },
            ]
            payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
            env = {**os.environ, "PYTHONIOENCODING": "cp949", "KIS_MODE": "mock"}
            done = subprocess.run(
                [sys.executable, str(course / "agent" / "mcp_server.py")],
                cwd=course,
                input=payload,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=30,
                env=env,
            )

        self.assertEqual(0, done.returncode, done.stderr)
        responses = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
        order = next(item for item in responses if item.get("id") == 2)
        body = json.loads(order["result"]["content"][0]["text"])
        self.assertTrue(body["실행"])
        self.assertEqual("mock", body["mode"])
        self.assertIn("주문 전송 완료", body["msg1"])


if __name__ == "__main__":
    unittest.main()

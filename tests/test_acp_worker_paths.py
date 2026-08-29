from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.common import acp_worker


class AcpWorkerPathTests(unittest.TestCase):
    def test_gui_path_fallback_finds_windows_npm_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            command = home / "AppData" / "Roaming" / "npm" / "claude.cmd"
            command.parent.mkdir(parents=True)
            command.touch()
            with (
                mock.patch.object(acp_worker.shutil, "which", return_value=None),
                mock.patch.object(acp_worker.Path, "home", return_value=home),
            ):
                self.assertEqual(str(command), acp_worker.find_executable("claude"))

    def test_child_path_includes_cli_directories_without_duplicates(self) -> None:
        env = acp_worker._cli_env("/opt/course/bin/claude", "/opt/course/bin/npx")
        parts = env["PATH"].split(acp_worker.os.pathsep)
        self.assertEqual("/opt/course/bin", parts[0])
        self.assertEqual(1, parts.count("/opt/course/bin"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hermes import setup_kis_mcp


class SetupKisMcpTests(unittest.TestCase):
    def test_runtime_file_defaults_every_api_to_paper_and_preserves_token(self) -> None:
        values = {
            "KIS_APP_KEY": "paper-key",
            "KIS_APP_SECRET": "paper-secret",
            "KIS_ACCOUNT": "12345678-01",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kis.env"
            path.write_text("MCP_ACCESS_TOKEN=existing-token\n", encoding="utf-8")
            setup_kis_mcp._write_runtime_env(path, values)
            result = setup_kis_mcp._read_env(path)
            mode = stat_mode(path)

        self.assertEqual("sse", result["MCP_TYPE"])
        self.assertEqual("existing-token", result["MCP_ACCESS_TOKEN"])
        self.assertEqual("paper-key", result["KIS_PAPER_APP_KEY"])
        self.assertEqual("12345678", result["KIS_PAPER_STOCK"])
        self.assertEqual(0o600, mode)

    def test_user_docker_path_is_found_when_shell_path_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / ".docker" / "bin" / ("docker.exe" if os.name == "nt" else "docker")
            binary.parent.mkdir(parents=True)
            binary.touch()
            with (
                mock.patch.object(setup_kis_mcp.shutil, "which", return_value=None),
                mock.patch.object(setup_kis_mcp.Path, "home", return_value=Path(tmp)),
            ):
                found = setup_kis_mcp._find_executable("docker")

        self.assertEqual(str(binary), found)

    def test_official_windows_hermes_path_is_found_when_shell_path_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local_app_data = Path(tmp) / "AppData" / "Local"
            binary = local_app_data / "hermes" / "bin" / "hermes.exe"
            binary.parent.mkdir(parents=True)
            binary.touch()
            with (
                mock.patch.object(setup_kis_mcp.shutil, "which", return_value=None),
                mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
            ):
                found = setup_kis_mcp._find_executable("hermes")

        self.assertEqual(str(binary), found)

    def test_windows_docker_candidates_include_system_and_user_installs(self) -> None:
        candidates = setup_kis_mcp._windows_docker_candidates(
            {
                "ProgramFiles": r"C:\Program Files",
                "LOCALAPPDATA": r"C:\Users\Student\AppData\Local",
            }
        )

        rendered = [str(path).replace("\\", "/") for path in candidates]
        self.assertTrue(any("Program Files/Docker/Docker/resources/bin/docker.exe" in path for path in rendered))
        self.assertTrue(any("AppData/Local/Docker/resources/bin/docker.exe" in path for path in rendered))

    def test_gateway_restart_preserves_an_intentional_stop(self) -> None:
        self.assertFalse(setup_kis_mcp._gateway_is_running("Gateway service is not loaded"))
        self.assertFalse(setup_kis_mcp._gateway_is_running("service stopped"))
        self.assertTrue(
            setup_kis_mcp._gateway_is_running("Gateway is supervised by launchd (PID 2265)")
        )
        self.assertTrue(setup_kis_mcp._gateway_is_running("Active: active (running)"))


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()

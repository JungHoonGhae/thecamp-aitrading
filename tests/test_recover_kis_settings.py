from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import recover_kis_settings


class RecoverKisSettingsTests(unittest.TestCase):
    def test_valid_maps_official_paper_fields_without_showing_values(self) -> None:
        source = {
            "paper_app": "a" * 36,
            "paper_sec": "b" * 180,
            "my_paper_stock": "12345678",
        }

        result = recover_kis_settings._valid(source)

        self.assertEqual(36, len(result["KIS_APP_KEY"]))
        self.assertEqual(180, len(result["KIS_APP_SECRET"]))
        self.assertEqual("12345678", result["KIS_ACCOUNT"])

    def test_update_env_preserves_unrelated_student_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "KIS_APP_KEY=example\nTELEGRAM_BOT_TOKEN=keep-me\nKIS_MODE=mock\n",
                encoding="utf-8",
            )
            recover_kis_settings._update_env(path, {
                "KIS_APP_KEY": "a" * 36,
                "KIS_APP_SECRET": "b" * 180,
                "KIS_ACCOUNT": "12345678",
            })
            body = path.read_text(encoding="utf-8")

        self.assertIn("TELEGRAM_BOT_TOKEN=keep-me", body)
        self.assertIn("KIS_MODE=mock", body)
        self.assertIn("KIS_APP_KEY=" + "a" * 36, body)
        self.assertIn("KIS_APP_SECRET=" + "b" * 180, body)
        self.assertIn("KIS_ACCOUNT=12345678", body)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.kis_catalog import ingredient_counts, load_catalog, render_catalog, search_catalog  # noqa: E402


class KISTradingCatalogTests(unittest.TestCase):
    def test_catalog_keeps_the_official_166_count_and_eight_domains(self) -> None:
        catalog = load_catalog()
        self.assertEqual(166, catalog["total"])
        self.assertEqual(166, len(catalog["apis"]))
        self.assertEqual(8, len(catalog["domains"]))

    def test_students_can_search_by_plain_korean_ingredient(self) -> None:
        flow = search_catalog("수급")
        order = search_catalog("주문")
        self.assertTrue(any("외국인" in row["name"] or "투자자" in row["name"] for row in flow))
        self.assertTrue(any("주문" in row["name"] for row in order))

    def test_summary_explains_eight_entries_and_166_apis(self) -> None:
        text = render_catalog()
        self.assertIn("166개", text)
        self.assertIn("8개 분야", text)
        self.assertIn("한 번에 부르지 않습니다", text)
        self.assertTrue(ingredient_counts())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import analysis_report  # noqa: E402


class AnalysisReportTests(unittest.TestCase):
    def test_mobile_html_survives_when_preview_browser_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(analysis_report, "_browser", return_value=None):
                artifacts = analysis_report.build_analysis_artifacts(
                    Path(tmp),
                    title="기술적 분석",
                    subject="삼성전자 (005930.KS)",
                    basic_analysis=(
                        "1년 가격 변화 +10.0%\n"
                        "20일 평균보다 +1.1%\n"
                        "60일 평균보다 -3.2%\n"
                        "1년 고점보다 -8.0% · 저점~고점 구간의 64% 지점\n"
                        "하루 등락폭 평균 2.10%\n"
                        "같은 기간 코스피 +4.0% · 지수보다 +6.0%p"
                    ),
                    ai_label="Claude · 모델 opus[1m] · effort medium",
                    ai_engine="claude",
                    ai_opinion=(
                        "종합 의견: 엇갈림\n"
                        "- 장점: 지수보다 강합니다. [공식 자료](https://example.com/ir)\n"
                        "- 위험: 장기 평균 아래입니다."
                    ),
                    source="Yahoo Finance 시세",
                    visual_data={
                        "kind": "technical",
                        "series": [100, 104, 103, 109, 112],
                        "asset_return": 10.0,
                        "benchmark_name": "코스피",
                        "benchmark_return": 4.0,
                        "range_position": 64.0,
                    },
                )

            body = artifacts.html_path.read_text(encoding="utf-8")

        self.assertIsNone(artifacts.preview_path)
        self.assertIn("HTML 보고서는 정상", artifacts.preview_notice)
        self.assertIn('name="viewport"', body)
        self.assertIn('"Pretendard Variable","Pretendard","Malgun Gothic"', body)
        self.assertIn("AI 최종 의견", body)
        self.assertIn("Claude", body)
        self.assertIn("모델 opus[1m]", body)
        self.assertIn("effort medium", body)
        self.assertIn('class="engine-mark claude"', body)
        self.assertIn('class="price-chart"', body)
        self.assertIn('class="metric-grid"', body)
        self.assertIn('class="range-track"', body)
        self.assertIn('href="https://example.com/ir"', body)
        self.assertNotIn("[공식 자료](https://example.com/ir)", body)
        self.assertIn(f"MEDIA:{artifacts.html_path}", artifacts.media_directives())

    def test_market_report_uses_visual_period_rows(self) -> None:
        body = analysis_report._report_html(
            title="시장 분석",
            subject="한국 증시",
            basic_analysis="[시장 분석] 한국 증시",
            ai_label="Codex",
            ai_opinion="시장 의견: 엇갈림\n코스피와 코스닥의 방향이 다릅니다.",
            source="Yahoo Finance 시세",
            visual_data={
                "kind": "market",
                "rows": [
                    {
                        "name": "코스피",
                        "one_month": 3.2,
                        "three_month": 8.1,
                        "one_year": 21.4,
                        "ma20_gap": 1.8,
                    },
                    {
                        "name": "코스닥",
                        "one_month": -2.4,
                        "three_month": 1.1,
                        "one_year": -5.0,
                        "ma20_gap": -3.2,
                    },
                ],
            },
        )

        self.assertIn('class="market-card"', body)
        self.assertIn("코스피", body)
        self.assertIn("1개월", body)
        self.assertIn("-5.0%", body)

    @unittest.skipIf(sys.platform == "win32", "POSIX pipe inheritance repro")
    def test_preview_returns_when_browser_child_keeps_output_pipe_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser = root / "fake-browser"
            browser.write_text(
                "#!/bin/sh\n"
                "for arg in \"$@\"; do\n"
                "  case \"$arg\" in --screenshot=*) printf png > \"${arg#--screenshot=}\" ;; esac\n"
                "done\n"
                "(sleep 3) &\n",
                encoding="utf-8",
            )
            browser.chmod(0o755)
            html_path = root / "report.html"
            preview_path = root / "report.png"
            html_path.write_text("<html></html>", encoding="utf-8")

            started = time.monotonic()
            with mock.patch.object(analysis_report, "_browser", return_value=str(browser)):
                notice = analysis_report._render_preview(html_path, preview_path)
            elapsed = time.monotonic() - started

        self.assertEqual("", notice)
        self.assertLess(elapsed, 1.0)

    def test_preview_requests_two_x_device_scale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            html_path = root / "report.html"
            preview_path = root / "report.png"
            html_path.write_text("<html></html>", encoding="utf-8")
            seen: list[list[str]] = []

            def capture(command: list[str], _preview: Path) -> str:
                seen.append(command)
                return ""

            with mock.patch.object(analysis_report, "_browser", return_value="browser"):
                with mock.patch.object(analysis_report, "_run_browser", side_effect=capture):
                    notice = analysis_report._render_preview(html_path, preview_path)

        self.assertEqual("", notice)
        self.assertIn("--force-device-scale-factor=2", seen[0])

    def test_technical_preview_height_removes_fixed_bottom_gap(self) -> None:
        visual = {"kind": "technical"}
        self.assertEqual(1360, analysis_report._preview_height("20일 평균보다 +1%", "짧은 의견", visual))
        self.assertEqual(1530, analysis_report._preview_height("5일 평균보다 +1%", "짧은 의견", visual))


if __name__ == "__main__":
    unittest.main()

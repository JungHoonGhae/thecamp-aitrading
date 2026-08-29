"""모바일용 단일 HTML 분석 보고서와 Telegram PNG 미리보기."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import signal
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class AnalysisArtifacts:
    html_path: Path
    preview_path: Path | None
    preview_notice: str = ""

    def media_directives(self) -> str:
        lines = []
        if self.preview_path is not None:
            lines.append(f"MEDIA:{self.preview_path}")
        lines.append(f"MEDIA:{self.html_path}")
        return "\n".join(lines)


def _browser() -> str | None:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", "")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)", "")
    candidates = [
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe") if program_files_x86 else None,
        str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe") if program_files else None,
        str(Path(local_app_data) / "Microsoft/Edge/Application/msedge.exe") if local_app_data else None,
        str(Path(program_files) / "Google/Chrome/Application/chrome.exe") if program_files else None,
        str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe") if program_files_x86 else None,
        str(Path(local_app_data) / "Google/Chrome/Application/chrome.exe") if local_app_data else None,
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _safe_text(value: str) -> str:
    return html.escape(value, quote=True).replace("\n", "<br>")


_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def _inline_html(value: str) -> str:
    """AI 답변의 출처 링크만 안전하게 살린다."""
    parts: list[str] = []
    cursor = 0
    for match in _MARKDOWN_LINK.finditer(value):
        parts.append(html.escape(value[cursor:match.start()], quote=True))
        label = html.escape(match.group(1), quote=True)
        href = html.escape(match.group(2), quote=True)
        parts.append(f'<a href="{href}" target="_blank" rel="noreferrer">{label}</a>')
        cursor = match.end()
    parts.append(html.escape(value[cursor:], quote=True))
    return "".join(parts)


def _rich_text(value: str) -> str:
    """긴 AI 평문을 모바일에서 훑을 수 있는 문단·목록으로 바꾼다."""
    rendered: list[str] = []
    bullets: list[str] = []

    def flush_bullets() -> None:
        if bullets:
            rendered.append("<ul>" + "".join(f"<li>{item}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    for raw in value.splitlines():
        line = raw.strip()
        if not line:
            flush_bullets()
            continue
        if line.startswith("- "):
            bullets.append(_inline_html(line[2:].strip()))
            continue
        flush_bullets()
        heading = re.fullmatch(r"\[([^\]]+)\]", line)
        if heading:
            rendered.append(f"<h3>{html.escape(heading.group(1), quote=True)}</h3>")
            continue
        key_value = re.match(r"^([^:：]{1,18})[:：]\s*(.+)$", line)
        if key_value:
            rendered.append(
                f'<p><strong>{html.escape(key_value.group(1), quote=True)}</strong>'
                f'<span>{_inline_html(key_value.group(2))}</span></p>'
            )
        else:
            rendered.append(f"<p>{_inline_html(line)}</p>")
    flush_bullets()
    return "".join(rendered)


def _number(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text)
    return float(match.group(1)) if match else None


def _technical_metrics(text: str) -> list[tuple[str, str, str, str]]:
    values = [
        ("1년 변화", _number(text, r"1년 가격 변화\s*([+-]?\d+(?:\.\d+)?)%"), "지난 1년", "return"),
        ("5일선", _number(text, r"5일 평균보다\s*([+-]?\d+(?:\.\d+)?)%"), "아주 짧은 흐름", "very-short"),
        ("20일선", _number(text, r"20일 평균보다\s*([+-]?\d+(?:\.\d+)?)%"), "단기 흐름", "short"),
        ("60일선", _number(text, r"60일 평균보다\s*([+-]?\d+(?:\.\d+)?)%"), "중기 흐름", "mid"),
        ("하루 변동", _number(text, r"하루 등락폭 평균\s*([+-]?\d+(?:\.\d+)?)%"), "평균 등락폭", "volatility"),
    ]
    metrics = []
    for label, value, note, kind in values:
        if value is None:
            continue
        signed = kind != "volatility"
        display = f"{value:+.1f}%" if signed else f"{value:.2f}%"
        tone = "positive" if value >= 0 else "negative"
        if kind == "volatility":
            tone = "neutral"
        metrics.append((label, display, note, tone))
    return metrics


def _supporting_text(value: str) -> str:
    skip_starts = (
        "[기본 분석", "[기술적 분석]", "1년 가격 변화", "5일 평균", "20일 평균", "60일 평균",
        "1년 고점보다", "하루 등락폭 평균", "같은 기간 ", "가격 움직임과 추세",
        "매수·매도 신호", "출처:",
    )
    lines = [line for line in value.splitlines() if not line.strip().startswith(skip_starts)]
    return "\n".join(lines).strip()


def _verdict(value: str) -> tuple[str, str]:
    lines = value.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(?:종합 의견|관찰 의견|시장 의견)\s*[:：]\s*(.+)$", line.strip())
        if match:
            remainder = "\n".join(lines[:index] + lines[index + 1:]).strip()
            return match.group(1).strip(), remainder
    return "검토 완료", value.strip()


def _engine_mark(ai_engine: str, ai_label: str) -> str:
    """외부 이미지 없이 보고서에 작업자별 시각 표식을 넣는다."""
    engine = ai_engine.strip().lower()
    label = ai_label.lower()
    if not engine:
        engine = "claude" if "claude" in label else "codex" if "codex" in label else "free"
    if engine == "claude":
        icon = (
            '<svg viewBox="0 0 32 32" aria-hidden="true">'
            '<path d="M16 3v26M3 16h26M6.8 6.8l18.4 18.4M25.2 6.8L6.8 25.2"/>'
            "</svg>"
        )
        name = "Claude"
    elif engine == "codex":
        icon = (
            '<svg viewBox="0 0 32 32" aria-hidden="true">'
            '<path d="M16 5.2 25.4 10.6v10.8L16 26.8 6.6 21.4V10.6z"/>'
            '<path d="m13.4 11.5-4 4.5 4 4.5M18.6 11.5l4 4.5-4 4.5"/>'
            "</svg>"
        )
        name = "Codex"
    else:
        icon = '<strong aria-hidden="true">H</strong>'
        name = "Hermes 무료 폴백"
        engine = "free"
    return (
        f'<span class="engine-mark {engine}" title="{html.escape(name, quote=True)}">'
        f"{icon}</span>"
    )


def _sparkline(visual_data: dict | None) -> str:
    if not visual_data or visual_data.get("kind") != "technical":
        return ""
    series = [float(value) for value in visual_data.get("series", [])]
    if len(series) < 2:
        return ""
    width, height, pad = 600.0, 176.0, 8.0
    low, high = min(series), max(series)
    spread = high - low or 1.0
    points = []
    for index, value in enumerate(series):
        x = pad + index / (len(series) - 1) * (width - pad * 2)
        y = pad + (high - value) / spread * (height - pad * 2)
        points.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{pad:.1f},{height:.1f} {line} {width-pad:.1f},{height:.1f}"
    return f"""
    <figure class="chart-card">
      <figcaption><span>1년 가격 흐름</span><small>방향을 보는 보조 자료</small></figcaption>
      <svg class="price-chart" viewBox="0 0 600 176" role="img" aria-label="1년 가격 흐름 선 차트">
        <line x1="8" y1="44" x2="592" y2="44"/><line x1="8" y1="88" x2="592" y2="88"/><line x1="8" y1="132" x2="592" y2="132"/>
        <polygon points="{area}"/><polyline points="{line}"/>
        <circle cx="{points[-1][0]:.1f}" cy="{points[-1][1]:.1f}" r="5"/>
      </svg>
      <div class="chart-scale"><span>1년 전</span><span>최근</span></div>
    </figure>"""


def _comparison(visual_data: dict | None) -> str:
    if not visual_data or visual_data.get("kind") != "technical":
        return ""
    asset = float(visual_data.get("asset_return", 0.0))
    benchmark = float(visual_data.get("benchmark_return", 0.0))
    benchmark_name = html.escape(str(visual_data.get("benchmark_name", "지수")), quote=True)
    maximum = max(abs(asset), abs(benchmark), 1.0)

    def row(label: str, value: float, primary: bool) -> str:
        width = max(3.0, abs(value) / maximum * 100)
        tone = "negative" if value < 0 else ("primary" if primary else "benchmark")
        return (
            f'<div class="compare-row"><div class="compare-label"><span>{label}</span>'
            f'<strong>{value:+.1f}%</strong></div><div class="compare-track">'
            f'<i class="{tone}" style="width:{width:.1f}%"></i></div></div>'
        )

    relative = asset - benchmark
    return (
        '<section class="compare-card"><div class="section-head"><span>지수와 비교</span>'
        f'<strong>{relative:+.1f}%p</strong></div>'
        + row("이 종목", asset, True)
        + row(benchmark_name, benchmark, False)
        + "</section>"
    )


def _range_bar(visual_data: dict | None) -> str:
    if not visual_data or visual_data.get("kind") != "technical":
        return ""
    position = max(0.0, min(100.0, float(visual_data.get("range_position", 50.0))))
    return f"""
    <section class="range-card"><div class="section-head"><span>1년 가격 구간</span><strong>{position:.0f}% 지점</strong></div>
      <div class="range-track"><i style="left:{position:.1f}%"></i></div>
      <div class="range-labels"><span>1년 저점</span><span>1년 고점</span></div>
    </section>"""


def _market_overview(visual_data: dict | None) -> str:
    if not visual_data or visual_data.get("kind") != "market":
        return ""
    rows = visual_data.get("rows", [])
    cards = []
    for row in rows:
        name = html.escape(str(row.get("name", "시장")), quote=True)
        one_month = float(row.get("one_month", 0.0))
        three_month = float(row.get("three_month", 0.0))
        one_year = float(row.get("one_year", 0.0))
        tone = "positive" if one_year >= 0 else "negative"
        cards.append(
            f'<article class="market-row {tone}"><div><strong>{name}</strong>'
            f'<small>1년 {one_year:+.1f}%</small></div><dl>'
            f'<div><dt>1개월</dt><dd>{one_month:+.1f}%</dd></div>'
            f'<div><dt>3개월</dt><dd>{three_month:+.1f}%</dd></div>'
            f'<div><dt>20일선</dt><dd>{float(row.get("ma20_gap", 0.0)):+.1f}%</dd></div>'
            "</dl></article>"
        )
    if not cards:
        return ""
    return (
        '<section class="market-card"><div class="section-head"><span>시장 한눈에 보기</span>'
        '<small>기간별 수익률</small></div><div class="market-list">'
        + "".join(cards)
        + "</div></section>"
    )


def _report_html(
    *,
    title: str,
    subject: str,
    basic_analysis: str,
    ai_label: str,
    ai_opinion: str,
    source: str,
    visual_data: dict | None = None,
    ai_engine: str = "",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    metrics = _technical_metrics(basic_analysis)
    metric_html = "".join(
        f'<article class="metric {tone}"><span>{html.escape(label)}</span>'
        f'<strong>{html.escape(value)}</strong><small>{html.escape(note)}</small></article>'
        for label, value, note, tone in metrics
    )
    supporting = _supporting_text(basic_analysis)
    verdict, opinion_body = _verdict(ai_opinion)
    engine_mark = _engine_mark(ai_engine, ai_label)
    visuals = (
        _sparkline(visual_data)
        + _comparison(visual_data)
        + _range_bar(visual_data)
        + _market_overview(visual_data)
    )
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(title)} · {html.escape(subject)}</title>
<style>
:root{{--ink:#1d211f;--muted:#66706a;--line:#d9ded9;--paper:#f3f1e9;--card:#fffefb;--green:#176149;--green-soft:#e7f1eb;--sand:#eee8da;--warn:#a04d32;--shadow:#35544314}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}} body{{margin:0;background:radial-gradient(circle at 85% 3%,#e5eee8 0,transparent 27%),var(--paper);color:var(--ink);font-family:"Pretendard Variable","Pretendard","Malgun Gothic","Apple SD Gothic Neo",-apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif;line-height:1.58;word-break:keep-all;overflow-wrap:anywhere}}
main{{width:min(100%,760px);margin:auto;padding:28px 18px 48px}} header{{padding:0 2px 18px}}
.eyebrow{{font-size:11px;letter-spacing:.16em;font-weight:800;color:var(--green)}}
h1{{font-size:34px;line-height:1.08;letter-spacing:-.045em;margin:9px 0 7px;text-wrap:balance}} .subject{{font-size:17px;color:var(--muted);font-variant-numeric:tabular-nums}}
.meta{{display:flex;gap:7px;flex-wrap:wrap;margin-top:18px}} .pill{{border:1px solid var(--line);border-radius:8px;background:#fff9;padding:6px 9px;font-size:11px;font-weight:650}}
.metric-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:4px 0 12px}} .metric{{min-width:0;background:var(--card);border-radius:14px;padding:14px 13px 13px;box-shadow:0 8px 22px var(--shadow)}}
.metric span,.metric small{{display:block;color:var(--muted);font-size:11px}} .metric strong{{display:block;font-size:22px;line-height:1.15;margin:8px 0 5px;letter-spacing:-.035em;font-variant-numeric:tabular-nums}} .metric.positive strong{{color:var(--green)}} .metric.negative strong{{color:var(--warn)}}
.chart-card,.compare-card,.range-card,.market-card,.card{{background:var(--card);border-radius:18px;margin:12px 0;box-shadow:0 10px 28px var(--shadow)}}
.chart-card{{padding:17px 16px 11px}} figcaption,.section-head{{display:flex;align-items:baseline;justify-content:space-between;gap:12px;font-size:13px;font-weight:750}} figcaption small{{font-size:11px;color:var(--muted);font-weight:550}}
.price-chart{{display:block;width:100%;height:auto;margin-top:9px;overflow:visible}} .price-chart line{{stroke:#e6e9e5;stroke-width:1}} .price-chart polygon{{fill:#dcece3;opacity:.78}} .price-chart polyline{{fill:none;stroke:var(--green);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;vector-effect:non-scaling-stroke}} .price-chart circle{{fill:var(--card);stroke:var(--green);stroke-width:4;vector-effect:non-scaling-stroke}}
.chart-scale,.range-labels{{display:flex;justify-content:space-between;color:var(--muted);font-size:10px;margin-top:3px}}
.compare-card,.range-card{{padding:17px 16px}} .section-head strong{{color:var(--green);font-size:17px;font-variant-numeric:tabular-nums}} .compare-row{{margin-top:13px}} .compare-label{{display:flex;justify-content:space-between;font-size:12px}} .compare-label strong{{font-variant-numeric:tabular-nums}} .compare-track{{height:8px;border-radius:3px;background:#edf0ec;margin-top:6px;overflow:hidden}} .compare-track i{{display:block;height:100%;border-radius:3px;background:var(--green)}} .compare-track i.benchmark{{background:#9ca69f}} .compare-track i.negative{{background:var(--warn)}}
.range-track{{height:10px;border-radius:3px;background:linear-gradient(90deg,#dce6df,#b7d0c0 55%,#6f9f84);margin-top:16px;position:relative}} .range-track i{{position:absolute;top:50%;width:18px;height:18px;border:4px solid var(--card);border-radius:50%;background:var(--green);box-shadow:0 1px 6px #173d2e55;transform:translate(-50%,-50%)}}
.market-card{{padding:18px 16px}} .market-card .section-head small{{font-size:11px;color:var(--muted);font-weight:550}} .market-list{{margin-top:11px}} .market-row{{display:grid;grid-template-columns:minmax(84px,1fr) 2fr;gap:12px;align-items:center;padding:12px 0;border-top:1px solid #e8ebe7}} .market-row:first-child{{border-top:0}} .market-row>div strong,.market-row>div small{{display:block}} .market-row>div strong{{font-size:14px}} .market-row>div small{{font-size:12px;color:var(--green);font-variant-numeric:tabular-nums}} .market-row.negative>div small{{color:var(--warn)}} .market-row dl{{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:0}} .market-row dl div{{background:#f3f5f2;border-radius:8px;padding:7px}} .market-row dt{{font-size:9px;color:var(--muted)}} .market-row dd{{margin:2px 0 0;font-size:12px;font-weight:750;font-variant-numeric:tabular-nums}}
.card{{padding:20px}} .label{{font-size:11px;letter-spacing:.07em;font-weight:800;color:var(--muted);margin-bottom:6px}} .opinion{{border-left:5px solid var(--green);background:#f6fbf8}} .opinion-head{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:14px}} .engine-identity{{display:flex;align-items:center;gap:10px;min-width:0}} .engine{{font-size:12px;font-weight:800;color:var(--green);line-height:1.35}} .engine-mark{{width:34px;height:34px;flex:0 0 34px;border-radius:10px;display:grid;place-items:center;background:#eef2ef;color:#17201b}} .engine-mark svg{{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}} .engine-mark.claude{{background:#f4e2d5;color:#c45d31}} .engine-mark.claude svg{{stroke-width:2.7}} .engine-mark.codex{{background:#17201b;color:#fff}} .engine-mark.free{{background:#dceee4;color:var(--green);font-size:17px}} .verdict{{font-size:12px;font-weight:750;background:var(--green-soft);color:var(--green);padding:5px 8px;border-radius:7px;white-space:nowrap}}
.rich{{font-size:14px;max-width:65ch}} .rich p{{margin:0 0 11px;text-wrap:pretty}} .rich p:last-child{{margin-bottom:0}} .rich p strong{{display:block;font-size:12px;margin-bottom:3px;color:var(--ink)}} .rich p span{{display:block}} .rich h3{{font-size:14px;margin:18px 0 8px}} .rich ul{{margin:0 0 12px;padding:0;list-style:none}} .rich li{{position:relative;padding-left:16px;margin:0 0 8px}} .rich li:before{{content:"";position:absolute;left:1px;top:.72em;width:5px;height:5px;border-radius:50%;background:var(--green)}} .rich a{{color:var(--green);font-weight:700;text-decoration-thickness:1px;text-underline-offset:2px}}
.evidence summary{{cursor:pointer;font-size:14px;font-weight:800;list-style:none}} .evidence summary::-webkit-details-marker{{display:none}} .evidence summary:after{{content:"접기";float:right;font-size:11px;color:var(--muted);font-weight:600}} .evidence:not([open]) summary:after{{content:"펼치기"}} .evidence .rich{{margin-top:16px;padding-top:15px;border-top:1px solid var(--line)}}
.source{{font-size:12px;color:var(--muted)}} .boundary{{background:#fff9ef;border:1px solid #e8d3ad;box-shadow:none;font-size:12px}} footer{{font-size:10px;color:#7a817d;margin-top:22px;text-align:center}}
@media(max-width:560px){{main{{padding:22px 14px 40px}}h1{{font-size:29px}}.metric-grid{{grid-template-columns:repeat(2,1fr)}}.metric strong{{font-size:21px}}.card{{padding:17px;border-radius:16px}}.chart-card,.compare-card,.range-card,.market-card{{border-radius:16px}}.market-row{{grid-template-columns:88px 1fr;gap:8px}}.market-row dl{{gap:4px}}.market-row dl div{{padding:6px 5px}}}}
</style></head><body><main>
<header><div class="eyebrow">THE CAMP · TRADING SYSTEM</div>
<h1>{html.escape(title)}</h1><div class="subject">{html.escape(subject)}</div>
<div class="meta"><span class="pill">{now} 기준</span><span class="pill">모의투자 학습용</span><span class="pill">사람 승인</span></div></header>
{f'<section class="metric-grid">{metric_html}</section>' if metric_html else ''}
{visuals}
<section class="card opinion"><div class="opinion-head"><div class="engine-identity">{engine_mark}<div><div class="label">AI 최종 의견</div><div class="engine">{html.escape(ai_label)}</div></div></div><div class="verdict">{html.escape(verdict)}</div></div><div class="rich">{_rich_text(opinion_body)}</div></section>
{f'<details class="card evidence" open><summary>분석 근거 자세히 보기</summary><div class="rich">{_rich_text(supporting)}</div></details>' if supporting else ''}
<section class="card"><div class="label">데이터 출처</div><div class="source">{_rich_text(source)}</div></section>
<section class="card boundary">AI 의견은 분석을 돕지만 주문값을 만들거나 바꾸지 않습니다. 주문은 규칙 코드가 계산하고 사람이 Telegram 버튼으로 승인합니다.</section>
<footer>THE CAMP · 모의투자로 배우는 안전한 자동화 구조</footer>
</main></body></html>"""


def _preview_ready(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _stop_browser(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=1)
    except (OSError, ProcessLookupError):
        return
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=1)
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            pass


def _run_browser(command: list[str], preview_path: Path) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=os.name != "nt",
            creationflags=creationflags,
        )
    except OSError as error:
        return f"브라우저 시작 실패: {error}"

    deadline = time.monotonic() + 12
    previous_size = -1
    stable_checks = 0
    try:
        while time.monotonic() < deadline:
            if _preview_ready(preview_path):
                size = preview_path.stat().st_size
                stable_checks = stable_checks + 1 if size == previous_size else 0
                previous_size = size
                if process.poll() is not None or stable_checks >= 2:
                    return ""
            return_code = process.poll()
            if return_code is not None:
                return f"브라우저 응답 코드 {return_code}"
            time.sleep(0.1)
        return "" if _preview_ready(preview_path) else "브라우저 응답 시간 초과"
    finally:
        _stop_browser(process)


def _render_preview(html_path: Path, preview_path: Path, *, height: int = 1600) -> str:
    browser = _browser()
    if browser is None:
        return "PNG 미리보기를 만들 브라우저를 찾지 못했습니다. HTML 보고서는 정상입니다."
    with tempfile.TemporaryDirectory(
        prefix=".preview-browser-", dir=preview_path.parent
    ) as profile:
        common = [
            browser,
            "--no-sandbox",
            "--disable-gpu",
            "--disable-crash-reporter",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-scrollbars",
            f"--user-data-dir={profile}",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1000",
            # CSS 폭은 휴대폰 540px로 유지하고 실제 픽셀만 2배로 만든다.
            # Telegram에서 긴 사진을 확대해도 글자와 차트가 흐려지지 않는다.
            "--force-device-scale-factor=2",
            f"--window-size=540,{height}",
            f"--screenshot={preview_path}",
            html_path.resolve().as_uri(),
        ]
        failures = []
        for headless_option in ("--headless=new", "--headless"):
            failure = _run_browser(
                [common[0], headless_option, *common[1:]], preview_path
            )
            if not failure:
                return ""
            failures.append(failure)
    return f"PNG 미리보기 생성 실패: {failures[-1]}"


def _preview_height(
    basic_analysis: str,
    ai_opinion: str,
    visual_data: dict | None,
) -> int:
    """내용은 자르지 않되 footer 뒤의 고정 공백은 만들지 않는 CSS 높이."""
    text_length = len(basic_analysis) + len(ai_opinion)
    kind = str((visual_data or {}).get("kind") or "")
    if kind == "technical":
        height = 1360
        if "5일 평균보다" in basic_analysis:
            height += 170
        if text_length > 1000:
            height += (text_length - 1000) // 2
        return min(3200, height)
    if kind == "market":
        rows = len((visual_data or {}).get("rows", []))
        return min(3200, 850 + rows * 92 + max(0, text_length - 700) // 2)
    return min(3200, max(900, 720 + text_length // 3))


def build_analysis_artifacts(
    state_dir: Path,
    *,
    title: str,
    subject: str,
    basic_analysis: str,
    ai_label: str,
    ai_opinion: str,
    source: str,
    visual_data: dict | None = None,
    ai_engine: str = "",
) -> AnalysisArtifacts:
    content = {
        "title": title,
        "subject": subject,
        "basic_analysis": basic_analysis,
        "ai_label": ai_label,
        "ai_opinion": ai_opinion,
        "source": source,
        "visual_data": visual_data,
        "ai_engine": ai_engine,
    }
    report_id = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    target = state_dir / "analysis-reports"
    target.mkdir(parents=True, exist_ok=True)
    html_path = target / f"analysis-{report_id}.html"
    preview_path = target / f"analysis-{report_id}.png"
    temporary = html_path.with_name(f".{html_path.name}.{os.getpid()}.tmp")
    temporary.write_text(_report_html(**content), encoding="utf-8")
    os.replace(temporary, html_path)
    preview_height = _preview_height(basic_analysis, ai_opinion, visual_data)
    notice = _render_preview(html_path, preview_path, height=preview_height)
    return AnalysisArtifacts(
        html_path=html_path,
        preview_path=preview_path if preview_path.is_file() else None,
        preview_notice=notice,
    )

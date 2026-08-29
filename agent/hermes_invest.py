"""Hermes Telegram 스킬이 호출하는 결정적 투자 명령.

AI가 읽고 말하는 일과 주문 계획·승인 상태를 분리한다. 실제 계좌에는 닿지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common import judge, market  # noqa: E402
from common.analysis_report import build_analysis_artifacts  # noqa: E402
from common.kis import KISClient  # noqa: E402
from common.kis_catalog import render_catalog  # noqa: E402
from common.plan_store import cancel_plan, load_plan_record, save_pending_plan  # noqa: E402
from common.reference_runtime import approve_reference_plan, create_reference_plan  # noqa: E402
from common.stocks import NAME_TO_CODE  # noqa: E402
from common.us_committee import load_advisory, load_reference_packet  # noqa: E402
from common.us_mock import LocalMockBroker  # noqa: E402
from common.us_reference import adopt_proposal, load_adopted_spec, save_adopted_spec  # noqa: E402

FIXTURES = ROOT / "src" / "common" / "fixtures"
STATE = ROOT / ".state"
PLAN_ID = re.compile(r"^[0-9a-f]{64}$")
COURSE_ACCOUNT = "course"
KIS_PAPER_ACCOUNT = "kis-paper"
ACCOUNT_TYPES = {COURSE_ACCOUNT, KIS_PAPER_ACCOUNT}
ANALYSIS_INDICATORS = {"basic", "ma5"}

COURSE_UPDATE_PROMPT = """\
`.agents/skills/environment/SKILL.md`를 처음부터 끝까지 읽고 그 절차대로 이 실습 폴더의
수업 자료를 최신으로 맞춰 줘. 학생 파일(`내-투자-판단.md`, `내-투자-스펙.md`, `.env`)과
학생이 고친 파일을 덮어쓰지 마. 충돌이나 확인이 필요하면 변경을 강행하지 말고 🟡 카드로
끝내. 안전하게 맞춘 뒤 `python verify.py`(맥에서 python이 없으면 python3)를 실행해.
Hermes gateway 재시작은 이 요청을 보낸 프로그램이 처리하므로 실행하지 마. 최종 답은
environment 스킬의 🔄 상태 카드 한 장만 출력해."""

FUNDAMENTAL_RULES = """\
너는 공식 기업 자료를 확인하고 최종 의견을 말하는 읽기 전용 분석가다.

웹을 쓸 수 있다면 아래 순서로 최신 공식 자료를 직접 확인한다.
1) 회사 투자자 정보(IR)·실적 발표
2) 한국 기업은 DART 공시, 미국 기업은 SEC 공시

지켜라.
- 공식 자료를 못 찾거나 웹을 쓸 수 없으면 추측하지 말고 「공식 근거 확인 불가」라고 쓴다.
- 「확인한 사실」에서 사업이 돈을 버는 방식과 최근 매출·이익·현금·부채의 방향을 쉽게 쓴다.
- 마지막에는 「관찰 의견: 긍정 / 엇갈림 / 주의」 중 하나와 다음에 확인할 위험을 쓴다.
- 숫자는 공식 자료에 실제로 있는 것만 쓰고, 기준일과 원문 URL을 같은 줄에 붙인다.
- 최대 여덟 줄. 투자 추천이 아니라 사람이 더 확인할 질문으로 끝낸다.
- 주문 모듈이나 계좌에는 접근하지 않는다."""

PLAN_REVIEW_RULES = """\
너는 이미 규칙 코드가 만든 모의주문 계획을 읽는 안전 검토자다.

지켜라.
- 주문 종목·방향·수량·지정가를 바꾸거나 새 숫자를 제안하지 않는다.
- 승인·매수·매도를 대신 결정하지 않는다.
- 계획에서 사람이 승인 전에 확인할 위험만 쉬운 말로 최대 세 줄 쓴다.
- 재료에 없는 사실은 지어내지 않는다. 주문 도구·계좌·파일을 호출하지 않는다."""

TECHNICAL_REVIEW_RULES = """\
너는 규칙 코드가 계산한 기본 기술적 분석을 읽는 최종 검토자다.

지켜라.
- 첫 줄은 반드시 「관찰 의견: 강한 흐름 / 엇갈림 / 약한 흐름」 중 하나로 쓴다.
- 이어서 그 의견의 근거 두 개와 다음에 확인할 위험 하나를 쉬운 말로 쓴다.
- 재료의 숫자를 바꾸거나 재료에 없는 숫자·뉴스·재무 사실을 만들지 않는다.
- 매수·매도·목표가·주문 수량을 제안하지 않는다. 최대 네 줄로 끝낸다."""

MARKET_REVIEW_RULES = """\
너는 여러 시장의 가격 지표를 읽는 최종 검토자다.

지켜라.
- 첫 줄은 반드시 「시장 의견: 강함 / 엇갈림 / 약함」 중 하나로 쓴다.
- 가장 강한 곳, 가장 약한 곳, 다음에 확인할 위험을 재료에 있는 숫자로만 설명한다.
- 시장 전체를 한 방향으로 단정하지 말고 자료가 부족하면 부족하다고 쓴다.
- 매수·매도·목표가·주문 수량을 제안하지 않는다. 최대 네 줄로 끝낸다."""

COMBINED_REVIEW_RULES = """\
너는 규칙 코드의 기술적 분석을 읽고, 공식 기업 자료까지 확인하는 읽기 전용 분석가다.

지켜라.
- 웹을 쓸 수 있다면 회사 IR·실적 발표를 먼저 보고, 한국 기업은 DART, 미국 기업은 SEC를 확인한다.
- 「펀더멘탈 확인」 두세 줄에 사업과 최근 매출·이익·현금·부채의 방향을 쉽게 쓴다.
- 공식 자료에서 확인한 숫자만 기준일과 원문 URL을 같은 줄에 붙인다.
- 마지막은 반드시 「종합 의견: 긍정 / 엇갈림 / 주의」 중 하나로 시작한다.
- 기술적 근거 하나, 펀더멘탈 근거 하나, 두 분석이 충돌하거나 비어 있는 지점 하나를 쓴다.
- 공식 자료를 못 찾으면 추측하지 말고 「공식 근거 확인 불가」라고 쓴다.
- 매수·매도·목표가·주문 수량을 제안하지 않는다. 전체 여덟 줄 이내로 끝낸다."""

HYPOTHESIS_REVIEW_RULES = """\
너는 이미 고정된 수업용 후보 선정 가설의 약점을 읽는 검토자다.

지켜라.
- 첫 줄은 반드시 「관찰: 설명 가능한 후보 선별」이라고 쓴다.
- 이어서 장점 한 줄, 가장 큰 약점 한 줄, 다음에 검증할 질문 한 줄만 쓴다.
- 시가총액 상위 30, 현재가 > 20일선 > 60일선, 공식 수급·실적 확인이라는 조건을 바꾸지 않는다.
- 후보 세 개를 주문·추천·목표가로 바꾸지 않는다.
- 수익이나 지수 초과성과를 검증했다고 말하지 않는다."""

MARKET_GROUPS = {
    "코스피": (("코스피", "^KS11"),),
    "kospi": (("코스피", "^KS11"),),
    "코스닥": (("코스닥", "^KQ11"),),
    "kosdaq": (("코스닥", "^KQ11"),),
    "s&p500": (("S&P500", "^GSPC"),),
    "sp500": (("S&P500", "^GSPC"),),
    "나스닥": (("나스닥", "^IXIC"),),
    "nasdaq": (("나스닥", "^IXIC"),),
    "한국": (("코스피", "^KS11"), ("코스닥", "^KQ11")),
    "한국증시": (("코스피", "^KS11"), ("코스닥", "^KQ11")),
    "미국": (("S&P500", "^GSPC"), ("나스닥", "^IXIC"), ("다우", "^DJI")),
    "미국증시": (("S&P500", "^GSPC"), ("나스닥", "^IXIC"), ("다우", "^DJI")),
    "세계": (
        ("코스피", "^KS11"), ("S&P500", "^GSPC"), ("나스닥", "^IXIC"),
        ("닛케이225", "^N225"), ("유로스톡스50", "^STOXX50E"), ("상하이종합", "000001.SS"),
    ),
    "세계증시": (
        ("코스피", "^KS11"), ("S&P500", "^GSPC"), ("나스닥", "^IXIC"),
        ("닛케이225", "^N225"), ("유로스톡스50", "^STOXX50E"), ("상하이종합", "000001.SS"),
    ),
    "글로벌": (
        ("코스피", "^KS11"), ("S&P500", "^GSPC"), ("나스닥", "^IXIC"),
        ("닛케이225", "^N225"), ("유로스톡스50", "^STOXX50E"), ("상하이종합", "000001.SS"),
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _target(raw: str) -> tuple[str, str]:
    label = raw.strip().split()[0] if raw.strip() else ""
    if not label:
        return "", ""
    return label, NAME_TO_CODE.get(label, market.TICKERS.get(label, label.upper()))


def _technical_packet(raw: str) -> dict:
    label, code = _target(raw)
    if not code:
        raise ValueError(
            "종목명이나 티커를 뒤에 적어 주세요. 예: /ts_analyze 삼성전자 또는 /ts_analyze AAPL"
        )
    symbol = market.to_symbol(code)
    closes = market.history(symbol, "1y")
    if len(closes) < 2:
        raise market.MarketError(f"{label}의 과거 값이 충분하지 않습니다.")
    info = market.profile(symbol)
    current = closes[-1]
    ma20 = market.moving_average(closes, 20)
    ma60 = market.moving_average(closes, 60)
    ma5 = market.moving_average(closes, 5)
    one_year = market.change_pct(closes)
    high, low = max(closes), min(closes)
    high_gap = (current / high - 1) * 100 if high else 0.0
    range_position = (current - low) / (high - low) * 100 if high != low else 50.0
    domestic = symbol.endswith((".KS", ".KQ"))
    benchmark_name = "코스피" if domestic else "S&P500"
    benchmark_return = market.change_pct(
        market.history(market.TICKERS[benchmark_name], "1y")
    )
    display = info.get("name") or label
    return {
        "label": label,
        "code": code,
        "symbol": symbol,
        "display": display,
        "one_year": one_year,
        "ma20_gap": (current / ma20 - 1) * 100 if ma20 else None,
        "ma60_gap": (current / ma60 - 1) * 100 if ma60 else None,
        "ma5_gap": (
            (current / ma5 - 1) * 100
            if ma5 and _selected_analysis_indicator() == "ma5"
            else None
        ),
        "high_gap": high_gap,
        "range_position": range_position,
        "volatility": market.volatility_pct(closes),
        "benchmark_name": benchmark_name,
        "benchmark_return": benchmark_return,
        "relative_return": one_year - benchmark_return,
        "series": closes[-120:],
    }


def _technical_text(packet: dict) -> str:
    ma5_gap = packet.get("ma5_gap")
    ma20_gap = packet["ma20_gap"]
    ma60_gap = packet["ma60_gap"]
    lines = [
        f"[기본 분석 · 규칙 코드]\n[기술적 분석] {packet['display']} ({packet['symbol']})",
        "",
        f"1년 가격 변화 {packet['one_year']:+.1f}%",
    ]
    if ma5_gap is not None:
        lines.append(f"5일 평균보다 {ma5_gap:+.1f}%")
    lines += [
        f"20일 평균보다 {ma20_gap:+.1f}%" if ma20_gap is not None else "20일 평균: 계산 불가",
        f"60일 평균보다 {ma60_gap:+.1f}%" if ma60_gap is not None else "60일 평균: 계산 불가",
        f"1년 고점보다 {packet['high_gap']:+.1f}% · 저점~고점 구간의 {packet['range_position']:.0f}% 지점",
        f"하루 등락폭 평균 {packet['volatility']:.2f}%",
        f"같은 기간 {packet['benchmark_name']} {packet['benchmark_return']:+.1f}% · 지수보다 {packet['relative_return']:+.1f}%p",
        "",
        "가격 움직임과 추세를 숫자로 확인하는 기술적 분석입니다.",
        "매수·매도 신호가 아니며 주문과 연결되지 않습니다.",
        "출처: Yahoo Finance 시세 · 학습용 조회 경로 · 주문 계산에는 사용하지 않음",
    ]
    return "\n".join(lines)


def technical(raw: str) -> str:
    return _technical_text(_technical_packet(raw))


def _ai_opinion(
    material: str,
    *,
    question: str,
    rules: str,
    heading: str,
    research: bool = False,
) -> tuple[str, judge.AskResult]:
    result = judge.ask_with_status(
        재료=material, 질문=question, 규칙=rules, research=research
    )
    route = judge.route_report(result)
    if not result.ok:
        return "\n".join([
            route,
            f"[{heading} 미실행] {result.notice}",
            "기본 분석은 위에 그대로 남아 있으며 AI 의견만 빠졌습니다.",
        ]), result
    label = judge.engine_details(
        result.engine, result.model, result.effort, result.transport
    )
    return "\n".join([
        route,
        f"[{heading} · {label} · 주문 권한 없음]",
        result.text,
        "AI 의견은 주문값을 만들거나 바꾸지 않습니다.",
    ]), result


def _report_suffix(
    *,
    title: str,
    subject: str,
    basic_analysis: str,
    result: judge.AskResult,
    source: str,
    visual_data: dict | None = None,
) -> str:
    report_lines = basic_analysis.splitlines()
    while report_lines and report_lines[0].startswith("["):
        report_lines.pop(0)
    while report_lines and not report_lines[0].strip():
        report_lines.pop(0)
    report_analysis = "\n".join(report_lines) or basic_analysis
    ai_label = (
        judge.engine_details(
            result.engine, result.model, result.effort, result.transport
        )
        if result.ok else "AI 최종 의견 미실행"
    )
    ai_opinion = result.text if result.ok else (result.notice or "AI 경로가 응답하지 않았습니다.")
    try:
        artifacts = build_analysis_artifacts(
            STATE,
            title=title,
            subject=subject,
            basic_analysis=report_analysis,
            ai_label=ai_label,
            ai_opinion=ai_opinion,
            source=source,
            visual_data=visual_data,
            ai_engine=result.engine if result.ok else "",
        )
    except (OSError, RuntimeError, ValueError) as error:
        return f"[HTML 보고서 생성 실패] {error}\n텍스트 분석은 위에 그대로 남아 있습니다."
    lines = ["[모바일 보고서] PNG 미리보기와 HTML 원문을 함께 보냅니다."]
    if artifacts.preview_notice:
        lines.append(f"[미리보기 안내] {artifacts.preview_notice}")
    lines.append(artifacts.media_directives())
    return "\n".join(lines)


def technical_review(raw: str, *, with_artifacts: bool = False) -> str:
    packet = _technical_packet(raw)
    base = _technical_text(packet)
    opinion, result = _ai_opinion(
        base,
        question="이 기본 기술적 분석이 보여 주는 흐름과 주의점을 최종 검토해 주세요.",
        rules=TECHNICAL_REVIEW_RULES,
        heading="AI 최종 의견",
    )
    output = f"{base}\n\n{opinion}"
    if with_artifacts:
        output += "\n\n" + _report_suffix(
            title="기술적 분석",
            subject=f"{packet['display']} ({packet['symbol']})",
            basic_analysis=base,
            result=result,
            source="Yahoo Finance 시세 · 학습용 조회 경로 · 주문 계산에는 사용하지 않음",
            visual_data={
                "kind": "technical",
                "series": packet["series"],
                "asset_return": packet["one_year"],
                "benchmark_name": packet["benchmark_name"],
                "benchmark_return": packet["benchmark_return"],
                "range_position": packet["range_position"],
            },
        )
    return output


def fundamental(raw: str, *, with_artifacts: bool = False) -> str:
    """Claude ACP → Claude CLI → Codex CLI → Nous 순서로 공식 자료를 읽는다."""
    label, code = _target(raw)
    if not code:
        raise ValueError(
            "종목명이나 티커를 뒤에 적어 주세요. 예: /ts_analyze 삼성전자 또는 /ts_analyze AAPL"
        )
    result = judge.ask_with_status(
        재료=(
            f"회사: {label}\n식별자: {code}\n"
            f"확인 날짜: {datetime.now().strftime('%Y-%m-%d')}\n"
            "공식 자료가 확인될 때만 사실로 적는다."
        ),
        질문="이 회사의 사업과 재무를 이해하기 위해 지금 확인할 핵심을 정리해 주세요.",
        규칙=FUNDAMENTAL_RULES,
        research=True,
    )
    route = judge.route_report(result)
    if not result.ok:
        output = "\n".join([
            f"[펀더멘탈 분석 · {label} · AI 미실행]",
            route,
            result.notice,
            "공식 근거를 확인하지 못했으므로 내용을 지어내지 않았습니다.",
            "계좌 조회·규칙 계산·모의주문은 그대로 동작합니다.",
        ])
    else:
        output = "\n".join([
            f"[펀더멘탈 분석 · {label}]",
            route,
            f"[AI 최종 의견 · {judge.engine_details(result.engine, result.model, result.effort, result.transport)} · 주문 권한 없음]",
            result.text,
            "",
            "원문과 기준일을 사람이 확인하세요. 이 결과는 주문값을 바꾸지 않습니다.",
        ])
    if with_artifacts:
        output += "\n\n" + _report_suffix(
            title="펀더멘탈 분석",
            subject=f"{label} ({code})",
            basic_analysis="공식 IR·DART·SEC 자료에서 확인한 사실과 기준일·원문을 본문에 표시했습니다.",
            result=result,
            source="회사 IR·DART·SEC 공식 자료 · 본문의 기준일과 원문 URL 확인",
        )
    return output


def _period_change(closes: list[float], trading_days: int) -> float:
    if len(closes) < 2:
        return 0.0
    start = closes[max(0, len(closes) - trading_days - 1)]
    return (closes[-1] / start - 1) * 100 if start else 0.0


def _market_key(raw: str) -> str:
    return raw.strip().lower().replace(" ", "")


def _market_rows(raw: str) -> tuple[str, list[dict], list[str]]:
    key = _market_key(raw)
    if not key:
        raise ValueError(
            "시장을 적어 주세요. 예: /ts_analyze 코스피, /ts_analyze 미국, /ts_analyze 세계 증시"
        )
    selection = MARKET_GROUPS.get(key)
    if selection is None:
        raise ValueError(
            "시장 분석은 코스피·코스닥·S&P500·나스닥·한국·미국·세계 증시 중에서 골라 주세요."
        )
    rows: list[dict] = []
    failures: list[str] = []
    for name, symbol in selection:
        try:
            closes = market.history(symbol, "1y")
            if len(closes) < 2:
                raise market.MarketError("과거 값이 충분하지 않습니다.")
            ma20 = market.moving_average(closes, 20)
            current = closes[-1]
            rows.append({
                "name": name,
                "symbol": symbol,
                "one_month": _period_change(closes, 21),
                "three_month": _period_change(closes, 63),
                "one_year": market.change_pct(closes),
                "ma20_gap": (current / ma20 - 1) * 100 if ma20 else 0.0,
                "volatility": market.volatility_pct(closes),
            })
        except market.MarketError as error:
            failures.append(f"{name}: {error}")
    if not rows:
        raise market.MarketError("시장 시세를 하나도 가져오지 못했습니다. " + " · ".join(failures))
    label = {
        "한국": "한국 증시", "한국증시": "한국 증시",
        "미국": "미국 증시", "미국증시": "미국 증시",
        "세계": "세계 증시", "세계증시": "세계 증시", "글로벌": "세계 증시",
    }.get(key, rows[0]["name"])
    return label, rows, failures


def _market_text(label: str, rows: list[dict], failures: list[str]) -> str:
    lines = [f"[기본 분석 · 규칙 코드]\n[시장 분석] {label}", ""]
    for row in rows:
        lines.append(
            f"{row['name']} · 1개월 {row['one_month']:+.1f}% · "
            f"3개월 {row['three_month']:+.1f}% · 1년 {row['one_year']:+.1f}% · "
            f"20일 평균보다 {row['ma20_gap']:+.1f}% · 하루 등락폭 {row['volatility']:.2f}%"
        )
    if failures:
        lines += ["", "가져오지 못한 시장"] + [f"- {item}" for item in failures]
    lines += [
        "",
        "출처: Yahoo Finance 시세 · 학습용 조회 경로 · 주문 계산에는 사용하지 않음",
    ]
    return "\n".join(lines)


def market_review(raw: str, *, with_artifacts: bool = False) -> str:
    label, rows, failures = _market_rows(raw)
    base = _market_text(label, rows, failures)
    opinion, result = _ai_opinion(
        base,
        question="이 시장 지표들이 함께 보여 주는 흐름과 위험을 최종 검토해 주세요.",
        rules=MARKET_REVIEW_RULES,
        heading="AI 최종 의견",
    )
    output = f"{base}\n\n{opinion}"
    if with_artifacts:
        output += "\n\n" + _report_suffix(
            title="시장 분석",
            subject=label,
            basic_analysis=base,
            result=result,
            source="Yahoo Finance 시세 · 학습용 조회 경로 · 주문 계산에는 사용하지 않음",
            visual_data={"kind": "market", "rows": rows},
        )
    return output


def combined_analysis(raw: str, *, with_artifacts: bool = False) -> str:
    packet = _technical_packet(raw)
    technical_base = _technical_text(packet)
    label, code = _target(raw)
    material = "\n".join([
        technical_base,
        "",
        "[펀더멘탈 확인 대상]",
        f"회사: {label}",
        f"식별자: {code}",
        f"확인 날짜: {datetime.now().strftime('%Y-%m-%d')}",
        "공식 자료가 확인될 때만 사실로 적는다.",
    ])
    opinion, result = _ai_opinion(
        material,
        question=(
            "이 기술적 분석을 읽고 공식 기업 자료를 한 번 확인한 뒤, "
            "펀더멘탈 확인과 최종 종합 의견을 함께 주세요."
        ),
        rules=COMBINED_REVIEW_RULES,
        heading="AI 종합 의견",
        research=True,
    )
    output = f"{technical_base}\n\n{opinion}"
    if with_artifacts:
        output += "\n\n" + _report_suffix(
            title="기술적·펀더멘탈 종합 분석",
            subject=f"{packet['display']} ({packet['symbol']})",
            basic_analysis=material,
            result=result,
            source="Yahoo Finance 시세 + 회사 IR·DART·SEC 공식 자료",
            visual_data={
                "kind": "technical",
                "series": packet["series"],
                "asset_return": packet["one_year"],
                "benchmark_name": packet["benchmark_name"],
                "benchmark_return": packet["benchmark_return"],
                "range_position": packet["range_position"],
            },
        )
    return output


def rule() -> str:
    if _selected_account() == KIS_PAPER_ACCOUNT:
        course = _course_agent()
        portfolio = course.load_portfolio()
        tolerance = course.load_number("rules.md", "허용 오차", 5)
        max_weight = course.load_number("guardrails.md", "한 종목 최대 비중", 40)
        min_cash = course.load_number("guardrails.md", "현금 최소 보유", 5)
        lines = [
            "[현재 규칙 · KIS 모의투자 계좌] 사람이 채택해 저장한 목표",
            "",
            "후보 조회와 AI 분석만으로 종목을 자동 교체하지 않습니다.",
            "내-투자-스펙.md에서 채택한 아래 목표만 주문 코드가 읽습니다.",
            "",
        ]
        lines.extend(
            f"- {item['name']} ({item['code']}) 목표 {item['target']:g}%"
            for item in portfolio
        )
        lines += [
            "",
            f"- 목표와 현재가 {tolerance:g}%p 이상 벌어지면 조정 후보",
            f"- 한 종목 최대 {max_weight:g}% · 현금 최소 {min_cash:g}%",
            "- 가드레일 위반 시 주문 차단 · 사람 승인 전에는 주문 없음",
            "",
            "후보 조건이나 전제가 달라질 때만 /ts_rule 로 다시 검토합니다.",
        ]
        return "\n".join(lines)

    path = STATE / "us-active-spec.json"
    if not path.is_file():
        return "저장된 수업 규칙이 없습니다. /ts_rule 에서 가설 근거 검토를 선택해 주세요."
    spec = load_adopted_spec(path)
    packet = load_reference_packet(FIXTURES, spec.market)
    names = packet.get("names") or {}
    lines = [
        "[현재 규칙] 처음 한 번 채택해 저장한 수업 예제",
        "",
        "최근 한 달을 빼고 그전 1년 동안 강했던 미국 대형주를",
        "다음 한 달 같은 비중으로 보유합니다.",
        "",
    ]
    lines.extend(
        f"- {names.get(ticker, ticker)} ({ticker}) {weight:g}%"
        for ticker, weight in spec.weights.items()
    )
    lines += [
        f"- 현금 {spec.cash_weight:g}%",
        f"- 한 종목 최대 비중 {spec.max_position_weight:g}%",
        "",
        "이 규칙은 매 주문마다 다시 채택하지 않습니다.",
        "근거를 다시 볼 때만 /ts_rule 로 돌아갑니다.",
    ]
    return "\n".join(lines)


def hypothesis_review() -> str:
    """고정 후보 선정 가설의 쓰임과 한계를 읽는다. 규칙·주문은 바꾸지 않는다."""
    material = "\n".join([
        "기준점: 지수 투자를 기본 비교선으로 둔다.",
        "후보군: KIS 국내주식 시가총액 상위 결과에서 앞 30개만 본다.",
        "가격 조건: 현재가가 20일 이동평균 위, 20일 이동평균이 60일 이동평균 위.",
        "위험 확인: KIS 수급·재무 순위와 회사 IR·DART 공식 원문을 확인한다.",
        "출력: 사람이 더 볼 검토 후보 최대 3개. 자동 매수·종목 교체가 아니다.",
        "한계: 현재 구성 종목 치우침, 거래비용, 과열, 시장 국면, 공식 자료 지연.",
        "검증 범위: 같은 입력에서 후보가 다시 나오는지만 수업에서 확인한다.",
        "지수 초과성과: 별도 백테스트 전에는 검증되지 않았다고 표시한다.",
    ])
    result = judge.ask_with_status(
        재료=material,
        질문="이 후보 선정 가설의 쓰임과 가장 큰 약점을 학생 눈높이로 검토해 주세요.",
        규칙=HYPOTHESIS_REVIEW_RULES,
    )
    route = judge.route_report(result)
    header = "[후보 선정 가설 · 검토만 · 주문 권한 없음]"
    fixed = "\n".join([
        "관찰: 설명 가능한 후보 선별",
        "장점: 큰 종목부터 같은 이동평균 조건으로 줄여 선택 이유를 다시 확인할 수 있습니다.",
        "약점: 현재 상위 종목과 최근 가격만 보면 시장 국면·거래비용·생존편향을 놓칠 수 있습니다.",
        "다음 질문: 같은 기간 코스피와 비용 후 결과를 비교해도 후보 규칙이 남는가?",
    ])
    opinion = result.text if result.ok else fixed
    status = (
        f"AI 검토 · {judge.engine_details(result.engine, result.model, result.effort, result.transport)}"
        if result.ok
        else f"AI 검토 미실행 · {result.notice} · 고정 설명 사용"
    )
    return "\n".join([
        header,
        material,
        "",
        route,
        f"[{status}]",
        opinion,
        "",
        "후보는 주문이 아닙니다. 현재 목표 포트폴리오는 바뀌지 않았습니다.",
        "평소에는 /ts_status → /ts_order_plan → 사람 승인으로 진행합니다.",
    ])


def adopt(proposal_id: str) -> str:
    proposal_path = STATE / "us-proposal.json"
    if not proposal_path.is_file():
        raise ValueError("판단 제안이 없습니다. 먼저 /ts_rule 에서 가설 근거 검토를 선택해 주세요.")
    proposal = load_advisory(proposal_path)
    spec = adopt_proposal(proposal, proposal_id, max_position_weight=40)
    save_adopted_spec(spec, STATE / "us-active-spec.json")
    return "수업 규칙으로 채택해 저장했습니다. 평소에는 /ts_status → /ts_order_plan → 승인으로 갑니다. 대화와 결과는 자동으로 남습니다."


def adopt_latest() -> str:
    """채택 버튼이 눌린 직후, 방금 만든 제안을 내부 번호로 채택한다."""
    proposal_path = STATE / "us-proposal.json"
    if not proposal_path.is_file():
        raise ValueError("판단 제안이 없습니다. 먼저 /ts_rule 에서 가설 근거 검토를 선택해 주세요.")
    return adopt(load_advisory(proposal_path).proposal_id)


def _session_ids() -> tuple[str, int, int]:
    # Hermes gateway 0.20+ keeps these values in task-local ContextVars so
    # simultaneous Telegram chats cannot overwrite each other.  Plain CLI and
    # tests still use environment variables, hence the small compatibility
    # fallback.
    try:
        from gateway.session_context import get_session_env
    except ImportError:
        get_session_env = os.environ.get
    platform = get_session_env("HERMES_SESSION_PLATFORM", "")
    chat = get_session_env("HERMES_SESSION_CHAT_ID", "")
    user = get_session_env("HERMES_SESSION_USER_ID", "")
    chat_type = get_session_env("HERMES_SESSION_CHAT_TYPE", "")

    # Hermes currently dispatches plugin-registered quick commands before it
    # binds the per-message ContextVars.  The course bot is intentionally a
    # single-user/private-chat setup, so direct commands can safely recover the
    # same ids from the values written by setup_course.py.  Routed AI skills
    # still use the request-scoped values above.
    if not chat:
        project_env = _read_env_file(ROOT / ".env")
        hermes_env = _read_env_file(Path.home() / ".hermes" / ".env")
        chat = (
            project_env.get("TELEGRAM_CHANNEL_ID", "")
            or hermes_env.get("TELEGRAM_HOME_CHANNEL", "")
        ).strip()
        allowed = hermes_env.get("TELEGRAM_ALLOWED_USERS", "").split(",", 1)[0].strip()
        if not user:
            user = allowed or chat
        if chat:
            platform = platform or "telegram"
            chat_type = chat_type or ("private" if not chat.startswith("-") else "group")
    try:
        chat_id = int(chat)
    except ValueError as error:
        raise ValueError("텔레그램 대화와 사용자를 확인하지 못했습니다.") from error
    try:
        user_id = int(user)
    except ValueError as error:
        # Telegram private chats use the person's user id as the chat id. Some
        # Hermes adapter versions omit source.user_id for a slash command even
        # though the private chat id is present. Falling back is safe only for
        # a direct message; group chats still require an explicit sender id.
        if platform == "telegram" and chat_type in {"", "dm", "private"}:
            user_id = chat_id
        else:
            raise ValueError("텔레그램 대화와 사용자를 확인하지 못했습니다.") from error
    return platform, chat_id, user_id


def _pending_path(chat_id: int) -> Path:
    return STATE / f"hermes-plan-{str(chat_id).replace('-', 'n')}.json"


def _settings_path(chat_id: int, user_id: int) -> Path:
    chat = str(chat_id).replace("-", "n")
    return STATE / f"hermes-settings-{chat}-{user_id}.json"


def _write_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _digest(value: dict) -> str:
    canonical = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _selected_account() -> str:
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("계좌 선택은 Hermes가 연결된 텔레그램에서 확인합니다.")
    path = _settings_path(chat_id, user_id)
    if not path.is_file():
        return COURSE_ACCOUNT
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("계좌 설정이 손상되었습니다. /ts_config 에서 다시 선택해 주세요.") from error
    account_type = str(record.get("account_type") or "")
    if (
        int(record.get("chat_id", 0)) != chat_id
        or int(record.get("user_id", 0)) != user_id
        or account_type not in ACCOUNT_TYPES
    ):
        raise ValueError("계좌 설정이 현재 사용자와 맞지 않습니다. /ts_config 에서 다시 선택해 주세요.")
    return account_type


def _selected_analysis_indicator() -> str:
    """Telegram 설정의 추가 지표. 일반 CLI와 첫 실행은 안전한 기본값이다."""
    try:
        platform, chat_id, user_id = _session_ids()
    except ValueError:
        return "basic"
    if platform != "telegram":
        return "basic"
    path = _settings_path(chat_id, user_id)
    if not path.is_file():
        return "basic"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "basic"
    if int(record.get("chat_id", 0)) != chat_id or int(record.get("user_id", 0)) != user_id:
        return "basic"
    value = str(record.get("analysis_indicator") or "basic")
    return value if value in ANALYSIS_INDICATORS else "basic"


def _indicator_label(value: str) -> str:
    return "기본 · 20일선·60일선" if value == "basic" else "확장 · 5일선 추가"


def _account_label(account_type: str) -> str:
    return "수업용 계좌" if account_type == COURSE_ACCOUNT else "KIS 모의투자 계좌"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _looks_like_kis_credentials(values: dict[str, str]) -> bool:
    key = values.get("KIS_APP_KEY", "")
    secret = values.get("KIS_APP_SECRET", "")
    account_number = values.get("KIS_ACCOUNT", "")
    return (
        len(key) >= 20
        and len(secret) >= 40
        and len(account_number) == 8
        and account_number.isdigit()
        and not any(word in key + secret for word in ("여기에", "앱키", "시크릿"))
    )


def _official_kis_settings_ready() -> bool:
    path = Path.home() / "KIS" / "config" / "kis_devlp.yaml"
    if not path.is_file():
        return False
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return (
        len(values.get("paper_app", "")) >= 20
        and len(values.get("paper_sec", "")) >= 40
        and len(values.get("my_paper_stock", "")) == 8
        and values.get("my_paper_stock", "").isdigit()
    )


def _record_account_type(record: dict) -> str:
    explicit = str(record.get("account_type") or "")
    if explicit in ACCOUNT_TYPES:
        return explicit
    environment = str((record.get("plan") or {}).get("environment") or "")
    return COURSE_ACCOUNT if environment == "local_mock" else ""


def _expire_old_pending(path: Path) -> bool:
    """유효한 승인 대기 계획만 True. 지난 계획은 닫아 계좌 전환을 막지 않는다."""
    if not path.is_file():
        return False
    try:
        record = load_plan_record(path)
        if record.get("status") != "pending":
            return False
        expires_at = datetime.fromisoformat(
            str(record.get("expires_at") or "").replace("Z", "+00:00")
        )
    except (OSError, TypeError, ValueError):
        return False
    if datetime.now(timezone.utc) <= expires_at:
        return True
    record["status"] = "expired"
    record["failure_reason"] = "approval expired"
    _write_atomic(path, record)
    return False


def settings() -> str:
    """입력 없이 버튼으로 고를 계좌 종류와 분리 원칙을 보여 준다."""
    current = _selected_account()
    indicator = _selected_analysis_indicator()
    return "\n".join([
        "[설정]",
        f"현재 선택: {_account_label(current)}",
        f"기술적 분석 지표: {_indicator_label(indicator)}",
        "",
        "수업용 계좌 · 미국주식 고정 가격 · KIS 키 없이 토요일에도 동작",
        "KIS 모의투자 계좌 · 국내주식 증권사 모의 서버 · KIS 연결값 필요",
        "",
        "두 계좌의 현금과 보유 주식은 서로 이어지거나 복사되지 않습니다.",
        "선택한 계좌가 잔고·보유 주식·주문 계획·승인 실행에 함께 적용됩니다.",
        "KIS가 실패해도 수업용 계좌로 몰래 주문하지 않습니다.",
        "실계좌 선택은 이 수업에서 제공하지 않습니다.",
        "분석 지표는 주문 계산과 연결되지 않습니다.",
    ])


def status() -> str:
    """선택 질문 없이 계좌·보유 주식·대기 주문을 한 번에 읽는다."""
    current = _selected_account()
    return "\n\n".join([
        "\n".join([
            "[현재 상태]",
            f"현재 계좌: {_account_label(current)}",
            "잔고·보유 주식·대기 주문을 한 번에 확인했습니다.",
        ]),
        account(),
        holdings(),
        pending_orders(),
        "계좌를 바꾸려면 /ts_config 를 사용하세요.",
    ])


def _kis_paper_client() -> KISClient:
    """환경변수의 KIS_ENV 값과 무관하게 국내주식 모의 서버만 연다."""
    try:
        return KISClient(mode="live", env="paper")
    except RuntimeError:
        project = _read_env_file(ROOT / ".env")
        if _looks_like_kis_credentials(project) or not _official_kis_settings_ready():
            raise
        recovered = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "recover_kis_settings.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if recovered.returncode != 0:
            raise RuntimeError(
                "공식 KIS 설정에서 모의 키를 복구하지 못했습니다: "
                + _short_update_error(recovered.stderr or recovered.stdout)
            )
        return KISClient(mode="live", env="paper")


def set_account_type(account_type: str) -> str:
    """현재 Telegram 사용자의 계좌 종류를 명시적으로 전환한다."""
    target = account_type.strip().lower()
    if target not in ACCOUNT_TYPES:
        raise ValueError("선택할 수 있는 계좌는 수업용 계좌와 KIS 모의투자 계좌뿐입니다.")
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("계좌 전환은 Hermes가 연결된 텔레그램에서만 진행합니다.")
    if _expire_old_pending(_pending_path(chat_id)):
        raise ValueError("승인 대기 중인 주문 계획이 있습니다. 먼저 승인하거나 보류한 뒤 계좌를 바꿔 주세요.")
    current = _selected_account()
    if current == target:
        return f"[계좌 설정]\n이미 {_account_label(target)}를 사용하고 있습니다."

    if target == KIS_PAPER_ACCOUNT:
        try:
            _kis_paper_client().get_balance()
        except (OSError, RuntimeError, ValueError) as error:
            raise ValueError(
                "KIS 모의투자 계좌 연결을 확인하지 못해 전환하지 않았습니다.\n"
                f"{error}\n\n현재 수업용 계좌 설정은 그대로 유지됩니다."
            ) from error

    path = _settings_path(chat_id, user_id)
    previous = {}
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    _write_atomic(path, {
        **previous,
        "schema_version": 1,
        "account_type": target,
        "chat_id": chat_id,
        "user_id": user_id,
        "updated_at": _now(),
    })
    return "\n".join([
        "[계좌 설정 완료]",
        f"이제 {_account_label(target)}를 사용합니다.",
        "잔고·보유 주식·주문 계획·승인 실행이 모두 이 계좌를 따릅니다.",
        "두 계좌의 자산은 서로 섞이지 않습니다.",
    ])


def set_analysis_indicator(indicator: str) -> str:
    """기술적 분석 표시만 바꾼다. 규칙·계좌·주문에는 닿지 않는다."""
    target = indicator.strip().lower()
    if target not in ANALYSIS_INDICATORS:
        raise ValueError("분석 지표는 기본 또는 5일선 추가만 선택할 수 있습니다.")
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("분석 지표 설정은 Hermes가 연결된 텔레그램에서 진행합니다.")
    path = _settings_path(chat_id, user_id)
    previous = {}
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    _write_atomic(path, {
        **previous,
        "schema_version": 1,
        "account_type": str(previous.get("account_type") or COURSE_ACCOUNT),
        "analysis_indicator": target,
        "chat_id": chat_id,
        "user_id": user_id,
        "updated_at": _now(),
    })
    return "\n".join([
        "[기술적 분석 지표 설정 완료]",
        f"이제 {_indicator_label(target)}로 표시합니다.",
        "같은 종목을 /ts_analyze로 다시 보면 전과 뒤를 비교할 수 있습니다.",
        "현재 규칙·가드레일·계좌·주문 계획은 바뀌지 않았습니다.",
    ])


def _money(value: int, currency: str) -> str:
    return f"${value / 100:,.2f}" if currency == "USD" else f"{value:,}원"


def _signed_money(value: int, currency: str) -> str:
    sign = "+" if value > 0 else "" if value == 0 else "−"
    absolute = abs(value) if value < 0 else value
    return sign + _money(absolute, currency)


def _course_broker() -> tuple[dict, LocalMockBroker]:
    selection = json.loads(
        (FIXTURES / "reference_selection.json").read_text(encoding="utf-8")
    )
    market_name = str(selection["reference_market"]).upper()
    packet = load_reference_packet(FIXTURES, market_name)
    broker = LocalMockBroker(
        market=market_name,
        currency=packet["currency"],
        prices=packet["prices"],
        initial_cash=packet["initial_cash"],
        ledger_path=STATE / f"{market_name.lower()}-ledger.json",
    )
    return packet, broker


def _course_cost_basis(broker: LocalMockBroker) -> dict[str, int]:
    """체결 기록을 재생해 수업용 계좌의 종목별 평균 매입단가를 구한다."""
    state: dict[str, tuple[int, int]] = {}
    for order in broker.get_orders():
        if not order.get("ok") or not order.get("fill_price"):
            continue
        ticker = str(order.get("ticker") or "")
        qty = int(order.get("qty") or 0)
        price = int(order.get("fill_price") or 0)
        held, cost = state.get(ticker, (0, 0))
        if order.get("side") == "buy":
            state[ticker] = (held + qty, cost + qty * price)
        elif order.get("side") == "sell" and held > 0:
            sold = min(qty, held)
            average = cost / held
            remaining = held - sold
            state[ticker] = (remaining, int(round(average * remaining)))
    return {
        ticker: int(round(cost / qty))
        for ticker, (qty, cost) in state.items()
        if qty > 0
    }


def tools_catalog(raw: str = "") -> str:
    """공식 166개 API 색인을 모델 호출 없이 즉시 검색한다."""
    return render_catalog(raw)


def account() -> str:
    """주문을 만들지 않고 선택한 계좌의 합계만 보여 준다."""
    if _selected_account() == KIS_PAPER_ACCOUNT:
        client = _kis_paper_client()
        balance = client.get_balance()
        holdings_value = sum(int(item["eval_amt"]) for item in balance["holdings"])
        purchase_value = sum(int(item.get("purchase_amt") or 0) for item in balance["holdings"])
        profit = holdings_value - purchase_value
        profit_rate = profit / purchase_value * 100 if purchase_value else 0.0
        total = int(balance["cash"]) + holdings_value
        masked = f"****{client.account[-4:]}" if client.account else "연결됨"
        return "\n".join([
            "[계좌 · KIS 모의투자 계좌]",
            f"계좌 {masked} · 국내주식 · 증권사 모의 서버",
            f"총자산 {_money(total, 'KRW')}",
            f"현금 {_money(int(balance['cash']), 'KRW')}",
            f"보유 주식 평가금액 {_money(holdings_value, 'KRW')}",
            f"보유 주식 매입금액 {_money(purchase_value, 'KRW')}",
            f"평가손익 {_signed_money(profit, 'KRW')} ({profit_rate:+.2f}%)",
            f"보유 종목 {len(balance['holdings'])}개",
            "",
            "수업용 계좌와 별도이며 실제 돈이 움직이는 실계좌가 아닙니다.",
        ])

    packet, broker = _course_broker()
    balance = broker.get_balance()
    cost_basis = _course_cost_basis(broker)
    holdings_value = sum(
        int(qty) * int(packet["prices"].get(ticker, 0))
        for ticker, qty in balance["holdings"].items()
    )
    purchase_value = sum(
        int(qty) * int(cost_basis.get(ticker, packet["prices"].get(ticker, 0)))
        for ticker, qty in balance["holdings"].items()
    )
    profit = holdings_value - purchase_value
    profit_rate = profit / purchase_value * 100 if purchase_value else 0.0
    total = int(balance["cash"]) + holdings_value
    market_label = "미국" if balance["market"] == "US" else "한국"
    return "\n".join([
        "[계좌 · 수업용 모의계좌]",
        f"계좌 course-local-{balance['market'].lower()} · {market_label} 주식",
        f"총자산 {_money(total, balance['currency'])}",
        f"현금 {_money(balance['cash'], balance['currency'])}",
        f"보유 주식 평가금액 {_money(holdings_value, balance['currency'])}",
        f"보유 주식 매입금액 {_money(purchase_value, balance['currency'])}",
        f"평가손익 {_signed_money(profit, balance['currency'])} ({profit_rate:+.2f}%)",
        f"보유 종목 {len(balance['holdings'])}개 · 장부 버전 {balance['revision']}",
        "",
        f"{packet['as_of']} 고정 수업 가격 기준이며 실제 계좌가 아닙니다.",
    ])


def holdings() -> str:
    """주문을 만들지 않고 선택한 계좌의 보유 종목만 보여 준다."""
    if _selected_account() == KIS_PAPER_ACCOUNT:
        balance = _kis_paper_client().get_balance()
        positions = balance["holdings"]
        if not positions:
            return "\n".join([
                "[보유 주식 · KIS 모의투자 계좌]",
                "보유 종목이 없습니다.",
                f"현금 {_money(int(balance['cash']), 'KRW')}",
                "",
                "수업용 계좌와 별도입니다. 주문 계획은 /ts_order_plan 에서 확인하세요.",
            ])
        total = int(balance["cash"]) + sum(int(item["eval_amt"]) for item in positions)
        lines = ["[보유 주식 · KIS 모의투자 계좌]", ""]
        for item in sorted(positions, key=lambda row: str(row["code"])):
            value = int(item["eval_amt"])
            purchase = int(item.get("purchase_amt") or 0)
            profit = int(item.get("profit_amt") or (value - purchase))
            profit_rate = float(item.get("profit_rate") or (profit / purchase * 100 if purchase else 0))
            weight = value / total * 100 if total else 0.0
            lines += [
                f"{item['name']} ({item['code']}) · {int(item['qty'])}주 · 비중 {weight:.1f}%",
                f"  매입 {_money(purchase, 'KRW')} → 현재 {_money(value, 'KRW')}",
                f"  손익 {_signed_money(profit, 'KRW')} ({profit_rate:+.2f}%)",
            ]
        lines += [
            "",
            f"현금 {_money(int(balance['cash']), 'KRW')}",
            f"총자산 {_money(total, 'KRW')}",
            "KIS 국내주식 모의 서버 기준이며 수업용 계좌와 별도입니다.",
        ]
        return "\n".join(lines)

    packet, broker = _course_broker()
    balance = broker.get_balance()
    cost_basis = _course_cost_basis(broker)
    positions = balance["holdings"]
    if not positions:
        return "\n".join([
            "[보유 주식 · 수업용 모의계좌]",
            "보유 종목이 없습니다.",
            f"현금 {_money(balance['cash'], balance['currency'])}",
            "",
            "주문 계획은 /ts_order_plan 에서 확인할 수 있습니다.",
        ])

    holdings_value = sum(
        int(qty) * int(packet["prices"].get(ticker, 0))
        for ticker, qty in positions.items()
    )
    total = int(balance["cash"]) + holdings_value
    lines = ["[보유 주식 · 수업용 모의계좌]", ""]
    for ticker, qty in sorted(positions.items()):
        price = int(packet["prices"].get(ticker, 0))
        value = int(qty) * price
        average = int(cost_basis.get(ticker, price))
        purchase = int(qty) * average
        profit = value - purchase
        profit_rate = profit / purchase * 100 if purchase else 0.0
        weight = value / total * 100 if total else 0.0
        name = packet.get("names", {}).get(ticker, ticker)
        lines += [
            f"{name} ({ticker}) · {qty}주 · 비중 {weight:.1f}%",
            f"  매입 {_money(purchase, balance['currency'])} → 현재 {_money(value, balance['currency'])}",
            f"  손익 {_signed_money(profit, balance['currency'])} ({profit_rate:+.2f}%)",
        ]
    lines += [
        "",
        f"현금 {_money(balance['cash'], balance['currency'])}",
        f"총자산 {_money(total, balance['currency'])}",
        f"{packet['as_of']} 고정 수업 가격 기준이며 실제 계좌가 아닙니다.",
    ]
    return "\n".join(lines)


def pending_orders() -> str:
    """현재 Telegram 사용자의 승인 대기 계획과 미체결 기록을 보여 준다."""
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("대기 주문은 Hermes가 연결된 텔레그램에서 확인합니다.")

    account_type = _selected_account()
    currency = "USD" if account_type == COURSE_ACCOUNT else "KRW"
    waiting: list[str] = []
    pending = _pending_path(chat_id)
    if pending.is_file():
        record = load_plan_record(pending)
        belongs_to_user = (
            int(record.get("channel_id", 0)) == chat_id
            and int(record.get("sender_id", 0)) == user_id
        )
        expires_at = str(record.get("expires_at", ""))
        not_expired = bool(expires_at) and datetime.now(timezone.utc) <= datetime.fromisoformat(
            expires_at.replace("Z", "+00:00")
        )
        same_account = _record_account_type(record) == account_type
        if belongs_to_user and same_account and record.get("status") == "pending" and not_expired:
            for order in record.get("plan", {}).get("orders", []):
                verb = "매수" if order.get("side") == "buy" else "매도"
                ticker = order.get("ticker") or order.get("code")
                if account_type == COURSE_ACCOUNT:
                    detail = f"지정가 {_money(int(order.get('limit_price', 0)), currency)}"
                else:
                    detail = "시장가 · 승인 전"
                waiting.append(f"{verb} {ticker} {int(order.get('qty', 0))}주 · {detail}")

    if account_type == COURSE_ACCOUNT:
        _, broker = _course_broker()
        unfilled = [order for order in broker.get_orders() if not order.get("ok")]
        title = "[대기 주문 · 수업용 계좌]"
        empty_note = "수업용 모의 주문은 승인 뒤 바로 체결됩니다."
    else:
        unfilled = _kis_paper_client().get_pending_orders()
        title = "[대기 주문 · KIS 모의투자 계좌]"
        empty_note = "KIS 국내주식 모의 서버의 오늘 미체결 주문까지 확인했습니다."
    if not waiting and not unfilled:
        return "\n".join([
            title,
            "승인 대기 계획 없음",
            "미체결 주문 없음",
            "",
            empty_note,
        ])

    lines = [title]
    if waiting:
        lines += ["", "승인 대기 계획"] + [f"- {item}" for item in waiting]
        lines.append("Telegram 승인·보류 버튼을 기다리고 있습니다.")
    else:
        lines += ["", "승인 대기 계획 없음"]
    if unfilled:
        lines += ["", "미체결 주문 기록"]
        for order in unfilled:
            verb = "매수" if order.get("side") == "buy" else "매도"
            ticker = order.get("ticker") or order.get("code")
            if account_type == COURSE_ACCOUNT:
                detail = order.get("message", "미체결")
            else:
                price = int(order.get("price") or 0)
                detail = f"주문가 {_money(price, 'KRW')}" if price else "시장가"
            lines.append(f"- {verb} {ticker} {int(order.get('qty', 0))}주 · {detail}")
        if account_type == COURSE_ACCOUNT:
            lines.append("이 기록은 현재 거래소에 살아 있는 주문이 아닙니다.")
        else:
            lines.append("KIS 국내주식 모의 서버의 오늘 미체결 주문입니다.")
    else:
        lines += ["", "미체결 주문 없음"]
    return "\n".join(lines)


_COURSE_AGENT_MODULE = "_thecamp_course_rebalance_agent"


def _course_agent():
    """Hermes의 top-level ``agent`` 패키지와 겹치지 않게 수업 agent.py를 읽는다."""
    path = ROOT / "agent" / "agent.py"
    loaded = sys.modules.get(_COURSE_AGENT_MODULE)
    if loaded is not None and Path(loaded.__file__).resolve() == path.resolve():
        return loaded
    spec = importlib.util.spec_from_file_location(_COURSE_AGENT_MODULE, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("수업 주문 계산기를 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_COURSE_AGENT_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_COURSE_AGENT_MODULE, None)
        raise
    return module


def _paper_spec_hash() -> str:
    spec_dir = ROOT / "agent" / "spec"
    return _digest({
        name: (spec_dir / name).read_text(encoding="utf-8")
        for name in ("portfolio.md", "rules.md", "guardrails.md")
    })


def _paper_balance_hash(balance: dict) -> str:
    holdings = [
        {
            "code": str(item.get("code") or ""),
            "name": str(item.get("name") or ""),
            "qty": int(item.get("qty") or 0),
            "eval_amt": int(item.get("eval_amt") or 0),
        }
        for item in balance.get("holdings") or []
    ]
    holdings.sort(key=lambda item: item["code"])
    return _digest({"cash": int(balance.get("cash") or 0), "holdings": holdings})


def _paper_account_hash(client: KISClient) -> str:
    return hashlib.sha256(str(client.account).encode("utf-8")).hexdigest()


def _paper_report(client: KISClient, balance: dict):
    return _course_agent().build_report(False, kis=client, balance=balance)


def _orders_from_report(report) -> tuple[list[dict], list[str]]:
    blocks = [
        item
        for callout in report.callouts
        if "주문 차단" in callout.heading
        for item in callout.items
    ]
    if report.mode_label is None:
        blocks.extend(report.notes or ["계좌를 계산할 수 없습니다"])
    orders = [] if blocks else [
        {
            "code": str(row.code),
            "name": str(row.name),
            "side": "buy" if row.action == "매수" else "sell",
            "qty": int(row.qty),
        }
        for row in report.comparison
        if row.needs_adjust and int(row.qty) > 0 and row.action in {"매수", "매도"}
    ]
    orders.sort(key=lambda order: (0 if order["side"] == "sell" else 1, order["code"]))
    return orders, blocks


def _new_paper_plan(client: KISClient, balance: dict, *, now: str) -> dict:
    report = _paper_report(client, balance)
    orders, blocks = _orders_from_report(report)
    created = datetime.fromisoformat(now.replace("Z", "+00:00"))
    content = {
        "schema_version": 1,
        "account_type": KIS_PAPER_ACCOUNT,
        "environment": "kis_paper",
        "market": "KR",
        "currency": "KRW",
        "account_hash": _paper_account_hash(client),
        "balance_hash": _paper_balance_hash(balance),
        "spec_hash": _paper_spec_hash(),
        "created_at": now,
        "expires_at": (created + timedelta(minutes=15)).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z"),
        "orders": orders,
        "blocks": blocks,
    }
    return {"plan_id": _digest(content), **content}


def _save_paper_plan(
    path: Path,
    plan_data: dict,
    *,
    channel_id: int,
    sender_id: int,
    message_id: int,
) -> None:
    content = {key: value for key, value in plan_data.items() if key != "plan_id"}
    if _digest(content) != plan_data.get("plan_id"):
        raise ValueError("변경되거나 손상된 KIS 모의투자 계획은 저장할 수 없습니다.")
    _write_atomic(path, {
        "schema_version": 2,
        "status": "pending",
        "account_type": KIS_PAPER_ACCOUNT,
        "plan_id": plan_data["plan_id"],
        "channel_id": int(channel_id),
        "sender_id": int(sender_id),
        "message_id": int(message_id),
        "created_at": plan_data["created_at"],
        "expires_at": plan_data["expires_at"],
        "failure_reason": "",
        "results": [],
        "plan": plan_data,
    })


@contextmanager
def _paper_claim_lock(path: Path) -> Iterator[None]:
    lock = path.with_name(f".{path.name}.paper-lock")
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RuntimeError("주문 승인이 이미 처리 중입니다.") from error
    try:
        yield
    finally:
        lock.rmdir()


def _fail_paper_record(path: Path, record: dict, reason: str) -> None:
    record["status"] = "failed"
    record["failure_reason"] = reason
    _write_atomic(path, record)


def _approve_paper_plan(
    pending: Path,
    *,
    plan_id: str,
    chat_id: int,
    user_id: int,
) -> list[dict]:
    """저장한 수량 그대로 KIS 모의 서버에 한 번만 주문한다."""
    client = _kis_paper_client()
    balance = client.get_balance()
    fresh_report = _paper_report(client, balance)
    fresh_orders, fresh_blocks = _orders_from_report(fresh_report)

    with _paper_claim_lock(pending):
        record = load_plan_record(pending)
        if record.get("plan_id") != plan_id:
            raise RuntimeError("wrong plan_id")
        if int(record.get("channel_id", 0)) != chat_id:
            raise RuntimeError("wrong channel")
        if int(record.get("sender_id", 0)) != user_id:
            raise RuntimeError("wrong sender")
        if int(record.get("message_id", 0)) != 0:
            raise RuntimeError("wrong message")
        if record.get("status") != "pending":
            raise RuntimeError(f"plan is already {record.get('status')}")
        plan_data = record.get("plan") or {}
        content = {key: value for key, value in plan_data.items() if key != "plan_id"}
        if plan_data.get("plan_id") != plan_id or _digest(content) != plan_id:
            _fail_paper_record(pending, record, "tampered plan digest")
            raise RuntimeError("주문 계획이 변경되었거나 손상되었습니다.")
        if datetime.now(timezone.utc) > datetime.fromisoformat(
            str(record.get("expires_at") or "").replace("Z", "+00:00")
        ):
            record["status"] = "expired"
            record["failure_reason"] = "approval expired"
            _write_atomic(pending, record)
            raise RuntimeError("주문 승인 시간이 지났습니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if _selected_account() != KIS_PAPER_ACCOUNT:
            _fail_paper_record(pending, record, "selected account changed")
            raise RuntimeError("선택한 계좌가 바뀌었습니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if plan_data.get("account_hash") != _paper_account_hash(client):
            _fail_paper_record(pending, record, "KIS account changed")
            raise RuntimeError("KIS 모의투자 계좌가 바뀌었습니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if plan_data.get("spec_hash") != _paper_spec_hash():
            _fail_paper_record(pending, record, "spec changed")
            raise RuntimeError("수업 규칙이 바뀌었습니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if plan_data.get("balance_hash") != _paper_balance_hash(balance):
            _fail_paper_record(pending, record, "balance changed")
            raise RuntimeError("KIS 모의투자 잔고가 바뀌었습니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if fresh_blocks or fresh_orders != plan_data.get("orders"):
            _fail_paper_record(pending, record, "prices or guardrails changed")
            raise RuntimeError("시세 또는 가드레일 결과가 바뀌었습니다. /ts_order_plan 으로 다시 확인해 주세요.")
        record["status"] = "executing"
        record["failure_reason"] = ""
        _write_atomic(pending, record)

    results: list[dict] = []
    failure = ""
    try:
        for order in plan_data["orders"]:
            result = client.place_order(
                order["code"], order["side"], int(order["qty"]), name=order["name"]
            )
            results.append(result)
            if not result.get("ok"):
                failure = str(result.get("msg") or "KIS 모의 주문이 거절되었습니다.")
                break
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"

    with _paper_claim_lock(pending):
        record = load_plan_record(pending)
        if record.get("status") != "executing" or record.get("plan_id") != plan_id:
            raise RuntimeError("주문 실행 상태가 손상되었습니다.")
        record["status"] = "failed" if failure else "executed"
        record["failure_reason"] = failure
        record["results"] = results
        _write_atomic(pending, record)
    if failure:
        raise RuntimeError(
            "KIS 모의 주문을 다시 시도하지 않았습니다. 일부 주문이 전송됐을 수 있으니 "
            f"/ts_status 와 KIS 앱에서 대기 주문을 확인하세요. ({failure})"
        )
    return results


def _stored_plan_id(pending: Path) -> str:
    try:
        plan_id = str(load_plan_record(pending)["plan_id"])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("승인 대기 중인 주문 계획이 없습니다. /ts_order_plan 으로 다시 만들어 주세요.") from error
    if not PLAN_ID.fullmatch(plan_id):
        raise ValueError("저장된 주문 계획이 손상되었습니다. /ts_order_plan 으로 다시 만들어 주세요.")
    return plan_id


def plan(approved_id: str = "", *, approve_latest: bool = False, cancel_latest: bool = False) -> str:
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("주문 계획과 승인은 Hermes가 연결된 텔레그램에서만 진행합니다.")
    pending = _pending_path(chat_id)
    if approve_latest and cancel_latest:
        raise ValueError("승인과 보류를 동시에 처리할 수 없습니다.")
    if approve_latest:
        approved_id = _stored_plan_id(pending)
    if cancel_latest:
        plan_id = _stored_plan_id(pending)
        cancel_plan(
            pending,
            plan_id=plan_id,
            channel_id=chat_id,
            sender_id=user_id,
            message_id=0,
        )
        return "[보류] 주문 계획을 실행하지 않았습니다. 주문은 전송되지 않았습니다."
    if approved_id:
        if not PLAN_ID.fullmatch(approved_id):
            raise ValueError("화면에 나온 64자리 주문 계획 번호를 그대로 보내 주세요.")
        record = load_plan_record(pending)
        record_account = _record_account_type(record)
        selected_account = _selected_account()
        if record_account != selected_account:
            raise RuntimeError("선택한 계좌와 주문 계획의 계좌가 다릅니다. /ts_order_plan 으로 다시 만들어 주세요.")
        if record_account == KIS_PAPER_ACCOUNT:
            fills = _approve_paper_plan(
                pending,
                plan_id=approved_id,
                chat_id=chat_id,
                user_id=user_id,
            )
            lines = [f"[주문 전송] KIS 모의투자 계좌 · {len(fills)}건", ""]
            for fill in fills:
                verb = "매수" if fill["side"] == "buy" else "매도"
                order_no = f" · 주문번호 {fill['order_no']}" if fill.get("order_no") else ""
                lines.append(f"{verb} {fill['code']} {fill['qty']}주{order_no}")
            lines += [
                "",
                "같은 계획은 다시 실행할 수 없습니다.",
                "KIS 증권사 모의 서버에 보낸 주문이며 실계좌 주문이 아닙니다.",
            ]
            return "\n".join(lines)
        fills = approve_reference_plan(
            FIXTURES,
            STATE,
            pending,
            plan_id=approved_id,
            channel_id=chat_id,
            sender_id=user_id,
            message_id=0,
            now=_now(),
        )
        lines = [f"[체결] 수업용 계좌 · {len(fills)}건", ""]
        for fill in fills:
            verb = "매수" if fill["side"] == "buy" else "매도"
            lines.append(f"{verb}  {fill['ticker']}  {fill['qty']}주")
        lines += ["", "같은 계획 번호는 다시 사용할 수 없습니다.", "실제 돈은 움직이지 않았습니다."]
        return "\n".join(lines)

    if _selected_account() == KIS_PAPER_ACCOUNT:
        client = _kis_paper_client()
        balance = client.get_balance()
        plan_data = _new_paper_plan(client, balance, now=_now())
        if plan_data["blocks"]:
            return "[주문 계획 · 차단 · KIS 모의투자 계좌]\n" + "\n".join(
                f"- {item}" for item in plan_data["blocks"]
            )
        if not plan_data["orders"]:
            return "[주문 계획 · 주문 없음 · KIS 모의투자 계좌]\n현재 규칙의 허용 오차 안이라 주문할 내용이 없습니다."
        _save_paper_plan(
            pending,
            plan_data,
            channel_id=chat_id,
            sender_id=user_id,
            message_id=0,
        )
        lines = ["[주문 계획] KIS 모의투자 계좌 · 아직 주문 아님", ""]
        for order in plan_data["orders"]:
            verb = "매수" if order["side"] == "buy" else "매도"
            lines.append(f"{verb} {order['name']} ({order['code']}) {order['qty']}주 · 시장가")
        lines += [
            "",
            "Telegram 승인 선택: 2분",
            "아래 Telegram 버튼에서 사람이 승인해야 KIS 모의 서버로 주문을 보냅니다.",
            "승인 직전 잔고·시세·가드레일이 달라지면 실행하지 않고 새 계획을 요구합니다.",
            "수업용 계좌와 별도이며 실계좌 주문은 지원하지 않습니다.",
        ]
        return "\n".join(lines)

    order_plan = create_reference_plan(FIXTURES, STATE, now=_now())
    if order_plan.blocks:
        return "[주문 계획 · 차단]\n" + "\n".join(f"- {x}" for x in order_plan.blocks)
    save_pending_plan(
        pending,
        order_plan,
        channel_id=chat_id,
        sender_id=user_id,
        message_id=0,
    )
    lines = ["[주문 계획] 수업용 계좌 · 아직 주문 아님", ""]
    for order in order_plan.orders:
        verb = "매수" if order.side == "buy" else "매도"
        lines.append(
            f"{verb}  {order.ticker}  {order.qty}주 · 지정가 {_money(order.limit_price, order_plan.currency)}"
        )
    lines += [
        "",
        "Telegram 승인 선택: 2분",
        "아래 Telegram 버튼에서 사람이 승인해야만 모의 체결됩니다.",
        "내부 계획 번호는 화면에 숨겨 두며 AI가 승인 결정을 대신할 수 없습니다.",
    ]
    return "\n".join(lines)


def review_pending_plan() -> str:
    """승인 전 계획을 AI가 설명하되 숫자와 실행 권한은 갖지 않는다."""
    platform, chat_id, user_id = _session_ids()
    if platform != "telegram":
        raise ValueError("주문 계획 검토는 Hermes가 연결된 텔레그램에서만 진행합니다.")
    record = load_plan_record(_pending_path(chat_id))
    if int(record.get("channel_id", 0)) != chat_id or int(record.get("sender_id", 0)) != user_id:
        raise ValueError("다른 사용자의 주문 계획은 검토할 수 없습니다.")
    if record.get("status") != "pending":
        raise ValueError("승인 대기 중인 주문 계획이 없습니다. /ts_order_plan 으로 다시 만들어 주세요.")

    plan_data = record.get("plan", {})
    currency = str(plan_data.get("currency", "USD"))
    account_type = _record_account_type(record)
    material = [
        f"규칙 코드가 만든 승인 대기 계획 · {_account_label(account_type)}"
    ]
    for order in plan_data.get("orders", []):
        verb = "매수" if order.get("side") == "buy" else "매도"
        ticker = order.get("ticker") or order.get("code")
        if account_type == COURSE_ACCOUNT:
            detail = f"지정가 {_money(int(order.get('limit_price', 0)), currency)}"
        else:
            detail = "KIS 국내주식 시장가"
        material.append(f"{verb} {ticker} {int(order.get('qty', 0))}주 · {detail}")
    material += [
        "사람 승인 전에는 실행되지 않음",
        "승인 시 규칙 실행기가 사용자·유효시간·잔고·가드레일을 다시 검사함",
        f"{_account_label(account_type)}이며 실계좌 아님",
    ]
    result = judge.ask_with_status(
        재료="\n".join(material),
        질문="이 계획을 승인하기 전에 사람이 확인할 점만 설명해 주세요.",
        규칙=PLAN_REVIEW_RULES,
    )
    route = judge.route_report(result)
    if not result.ok:
        return "\n".join([
            route,
            f"[AI 위험 검토 미실행] {result.notice}",
            "계획은 규칙 코드가 이미 계산했으므로 승인·보류 버튼은 계속 사용할 수 있습니다.",
        ])
    return "\n".join([
        route,
        f"[AI 위험 검토 · {judge.engine_details(result.engine, result.model, result.effort, result.transport)} · 주문 권한 없음]",
        result.text,
        "AI는 계획의 숫자를 바꾸지 않았고 승인도 대신하지 않습니다.",
    ])


def log_judgment(text: str) -> str:
    value = text.strip().replace("|", "·").replace("\n", " ")
    if not value:
        raise ValueError(
            "이유를 뒤에 적어 주세요. 예: /ts_memory 오늘은 움직이지 않았다"
        )
    path = ROOT / "내-투자-판단.md"
    body = path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%m/%d")
    row = f"| | {today} | | | {value} |"
    marker = "| | | | | |"
    body = body.replace(marker, f"{row}\n{marker}", 1) if marker in body else body.rstrip() + f"\n{row}\n"
    path.write_text(body, encoding="utf-8")
    return f"[기록] {today}\n{value}\n\n내-투자-판단.md에 남겼습니다."


def _course_update_agents() -> list[tuple[str, list[str]]]:
    """실습 폴더를 수정할 코딩 도구. 분석 경로와 권한을 섞지 않는다."""
    agents: list[tuple[str, list[str]]] = []
    claude = shutil.which("claude")
    if claude:
        agents.append(("Claude Code · Sonnet · effort low · 실습 폴더 수정", [
            claude,
            "--print",
            "--permission-mode", "acceptEdits",
            "--allowedTools",
            (
                "Read,Edit,Write,Glob,Grep,"
                "Bash(git fetch *),Bash(git status *),Bash(git pull *),"
                "Bash(python verify.py),Bash(python3 verify.py)"
            ),
            "--model", "sonnet",
            "--effort", "low",
            "--no-session-persistence",
            COURSE_UPDATE_PROMPT,
        ]))
    codex = shutil.which("codex")
    if codex:
        agents.append(("Codex CLI · 현재 설정 · effort low", [
            codex,
            "exec",
            "--cd", str(ROOT),
            "--sandbox", "workspace-write",
            "--ephemeral",
            "--config", 'model_reasoning_effort="low"',
            COURSE_UPDATE_PROMPT,
        ]))
    return agents


@contextmanager
def _course_update_guard() -> Iterator[None]:
    """같은 노트북에서 업데이트 버튼을 여러 번 눌러도 한 번만 실행한다."""
    path = STATE / "course-update.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError(
            "수업 자료 업데이트가 이미 진행 중입니다. 완료 카드가 올 때까지 기다려 주세요."
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"{os.getpid()} {_now()}\n")
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _short_update_error(value: str) -> str:
    clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value or "").strip()
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    return (lines[-1] if lines else "응답 없음")[:300]


def _probe_command(command: list[str], *, success_text: str = "", timeout: int = 30) -> bool:
    try:
        done = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if done.returncode != 0:
        return False
    return not success_text or success_text.lower() in (done.stdout + done.stderr).lower()


def _find_executable(name: str) -> str | None:
    """GUI·백그라운드 실행에서도 사용자 설치 CLI를 찾는다.

    Windows의 Docker Desktop과 macOS의 ``User`` 설치는 새 터미널을 열기 전이나
    launchd에서 PATH에 아직 보이지 않을 수 있다. 학생에게 재설치를 요구하기 전에
    제품이 쓰는 사용자 경로를 확인한다.
    """
    found = shutil.which(name)
    if found:
        return found

    home = Path.home()
    executable = f"{name}.exe" if os.name == "nt" else name
    candidates: list[Path] = []
    if name == "hermes":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(Path(local_app_data) / "hermes" / "bin" / "hermes.exe")
        candidates.append(home / "AppData" / "Local" / "hermes" / "bin" / "hermes.exe")
    candidates += [
        home / ".local" / "bin" / executable,
        home / ".docker" / "bin" / executable,
    ]
    if name == "docker":
        candidates += [
            home / "Applications" / "Docker.app" / "Contents" / "Resources" / "bin" / "docker",
            Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
        ]
        for variable in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA"):
            root = os.environ.get(variable)
            if root:
                candidates.append(Path(root) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe")
    return next((str(path) for path in candidates if path.is_file()), None)


def _hermes_runtime_paths(hermes_bin: str | None) -> tuple[Path, Path]:
    """Return the active Hermes home and secret env on every supported OS.

    Native Windows uses ``%LOCALAPPDATA%\\hermes`` rather than ``~/.hermes``.
    Asking Hermes itself first also respects profiles and ``HERMES_HOME``.
    """
    fallback_home = Path(
        os.environ.get("HERMES_HOME")
        or (
            str(Path(os.environ["LOCALAPPDATA"]) / "hermes")
            if os.environ.get("LOCALAPPDATA")
            else str(Path.home() / ".hermes")
        )
    ).expanduser()
    config_path = fallback_home / "config.yaml"
    env_path = fallback_home / ".env"
    if not hermes_bin:
        return fallback_home, env_path

    for args, kind in ((["config", "path"], "config"), (["config", "env-path"], "env")):
        try:
            done = subprocess.run(
                [hermes_bin, *args],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        value = (done.stdout or "").strip()
        if done.returncode != 0 or not value:
            continue
        if kind == "config":
            config_path = Path(value).expanduser()
        else:
            env_path = Path(value).expanduser()
    return config_path.parent, env_path


def _hermes_portal_authenticated(hermes_bin: str | None) -> bool:
    """모델을 호출하지 않고 Nous Portal 로그인 완료 여부만 확인한다."""
    return bool(hermes_bin) and _probe_command(
        [hermes_bin, "portal", "info"], success_text="✓ logged in", timeout=8
    )


def doctor() -> str:
    """모델·외부 계좌 호출 없이 수업 환경의 필수 연결을 빠르게 점검한다."""
    verify_ok = _probe_command([sys.executable, str(ROOT / "verify.py")])
    hermes_bin = _find_executable("hermes")
    hermes_home, _ = _hermes_runtime_paths(hermes_bin)
    gateway_ok = bool(hermes_bin) and _probe_command(
        [hermes_bin, "gateway", "status"], success_text="pid", timeout=8
    )
    docker_bin = _find_executable("docker")
    docker_ok = bool(docker_bin) and _probe_command([docker_bin, "ps"], timeout=5)
    container_ok = docker_ok and _probe_command(
        [docker_bin, "inspect", "-f", "{{.State.Running}}", "kis-trade-mcp"],
        success_text="true",
        timeout=5,
    )
    hermes_mcp_ok = bool(hermes_bin) and _probe_command(
        [hermes_bin, "mcp", "list"], success_text="kis-trade-mcp", timeout=5
    )
    installed_plugin = hermes_home / "plugins" / "thecamp-invest" / "__init__.py"
    plugin_ok = installed_plugin.is_file() and "/ts_doctor" in installed_plugin.read_text(
        encoding="utf-8", errors="ignore"
    )
    project_env = _read_env_file(ROOT / ".env")
    kis_ok = _looks_like_kis_credentials(project_env)
    kis_recoverable = _official_kis_settings_ready()
    telegram_ok = bool(project_env.get("TELEGRAM_BOT_TOKEN")) and bool(
        project_env.get("TELEGRAM_CHANNEL_ID")
    )
    claude_bin = _find_executable("claude")
    claude_acp_ready = bool(claude_bin) and judge.acp_worker.available()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    mark = lambda value: "✅" if value else "❌"
    lines = [
        "[수업 환경 진단 · 모델 사용 안 함]",
        f"{mark(verify_ok)} 실습 코드 · verify.py 5/5",
        f"{mark(gateway_ok)} Hermes gateway · 실행 상태",
        f"{mark(plugin_ok)} Telegram 수업 명령 · 최신 플러그인",
        f"{mark(telegram_ok)} Telegram 연결값 · 저장됨",
        (
            "✅ Claude 분석 연결 · ACP 어댑터 준비 · 기존 Claude 로그인 사용"
            if claude_acp_ready
            else "🟡 Claude ACP 어댑터 미준비 · Claude CLI/Codex/무료 폴백 사용"
        ),
    ]
    if container_ok and hermes_mcp_ok:
        lines.append("✅ KIS Trading MCP · 166 API(8개 분야) · Hermes 연결")
    elif docker_ok:
        lines.append("🟡 Docker Desktop · 실행 중 · KIS MCP 연결은 복구 필요")
    elif docker_bin:
        lines.append("🟡 Docker Desktop · 앱이 꺼졌거나 daemon 연결 안 됨 · 2분 뒤 폴백")
    else:
        lines.append("🟡 Docker Desktop · 설치 필요 · 불가하면 수업용 5개로 계속")
    if kis_ok:
        lines.append("✅ KIS 모의투자 설정 · 프로젝트에 저장됨")
    elif kis_recoverable:
        lines.append("🛟 KIS 모의투자 설정 · 공식 설정에서 복구 가능")
    else:
        lines.append("⚪ KIS 모의투자 설정 · 선택 사항, 수업용 계좌 사용 가능")
    lines += [
        f"📌 수업 자료 버전 {version}",
        "",
        "비밀값과 계좌 금액은 표시하지 않았고 외부 주문·잔고 조회도 하지 않았습니다.",
        "연결별 로그인 상태는 /ts_auth 에서 확인합니다.",
    ]
    return "\n".join(lines)


def auth_status() -> str:
    """Hermes·코딩 CLI·KIS 자격 상태만 읽고 비밀값은 출력하지 않는다."""
    hermes_bin = _find_executable("hermes")
    claude_bin = _find_executable("claude")
    codex_bin = _find_executable("codex")
    _, hermes_env_path = _hermes_runtime_paths(hermes_bin)
    gateway_ok = bool(hermes_bin) and _probe_command(
        [hermes_bin, "gateway", "status"], success_text="pid", timeout=8
    )
    mcp_ok = bool(hermes_bin) and _probe_command(
        [hermes_bin, "mcp", "list"], success_text="kis-trade-mcp", timeout=5
    )
    claude_ok = bool(claude_bin) and _probe_command(
        [claude_bin, "auth", "status"], success_text="logged", timeout=5
    )
    claude_acp_ready = claude_ok and judge.acp_worker.available()
    codex_ok = bool(codex_bin) and _probe_command(
        [codex_bin, "login", "status"], success_text="logged in", timeout=5
    )
    free_auth_ok = _hermes_portal_authenticated(hermes_bin)
    project_env = _read_env_file(ROOT / ".env")
    hermes_env = _read_env_file(hermes_env_path)
    telegram_ok = bool(hermes_env.get("TELEGRAM_BOT_TOKEN"))
    kis_ok = _looks_like_kis_credentials(project_env)
    try:
        current = _account_label(_selected_account())
    except ValueError:
        # /ts_auth is normally called from Telegram, but instructors also run
        # it from a terminal while preparing class. Authentication checks must
        # still finish when no chat-scoped account selection exists.
        current = _account_label(COURSE_ACCOUNT)
    mark = lambda value: "✅" if value else "❌"
    lines = [
        "[연결 상태 · 모델 사용 안 함]",
        f"{mark(gateway_ok and telegram_ok)} Telegram ↔ Hermes gateway",
        f"{mark(claude_ok)} Claude Code · auth status",
        f"{mark(claude_acp_ready)} Claude 분석 연결 · ACP · 같은 로그인 사용",
        f"{mark(codex_ok)} Codex CLI · login status",
        (
            "✅ Hermes 무료 라우터 · Nous :free 로그인"
            if free_auth_ok
            else "❌ Hermes 무료 라우터 · Nous Portal 로그인 필요"
        ),
        f"{mark(mcp_ok)} KIS Trading MCP · 166 API(8개 분야)",
        f"{mark(kis_ok)} KIS 모의투자 자격값 · 비밀 저장됨",
        f"현재 계좌: {current}",
    ]
    if not kis_ok and _official_kis_settings_ready():
        lines.append("🛟 KIS 공식 설정에 복구 가능한 모의 키가 있습니다.")
    lines += [
        "",
        "AI 분석 경로: Claude ACP → Claude CLI → Codex CLI → Nous 무료 모델",
        "이 명령은 로그인 여부만 확인하며 AI 호출·잔고 조회·주문을 하지 않습니다.",
    ]
    return "\n".join(lines)


def _student_settings_paths() -> list[Path]:
    """업데이트가 절대 바꾸면 안 되는 학생별 설정·연습 장부."""
    paths = [
        ROOT / ".env",
        ROOT / "내-투자-판단.md",
        ROOT / "내-투자-스펙.md",
        Path.home() / ".hermes" / ".env",
        Path.home() / "KIS" / "config" / "kis_devlp.yaml",
    ]
    if STATE.is_dir():
        for pattern in (
            "hermes-settings-*.json",
            "hermes-plan-*.json",
            "*-ledger.json",
        ):
            paths.extend(sorted(STATE.glob(pattern)))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        marker = str(path.resolve(strict=False))
        if marker not in seen:
            seen.add(marker)
            unique.append(path)
    return unique


@contextmanager
def _preserve_student_settings() -> Iterator[None]:
    """코딩 도구가 실수해도 학생의 비밀값·계좌 선택·연습 결과를 되돌린다."""
    paths = _student_settings_paths()
    with tempfile.TemporaryDirectory(prefix="thecamp-student-settings-") as temporary:
        backup_root = Path(temporary)
        backups: list[tuple[Path, Path]] = []
        for index, original in enumerate(paths):
            if not original.is_file():
                continue
            backup = backup_root / str(index)
            shutil.copy2(original, backup)
            backups.append((original, backup))
        try:
            yield
        finally:
            for original, backup in backups:
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, original)


def _refresh_course_connection() -> None:
    """새 플러그인·명령 메뉴를 복사하고, 답장을 보낸 뒤 gateway를 다시 읽힌다."""
    setup = subprocess.run(
        [sys.executable, str(ROOT / "hermes" / "setup_course.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if setup.returncode != 0:
        raise RuntimeError(
            "Telegram 수업 연결 갱신 실패: " + _short_update_error(setup.stderr or setup.stdout)
        )
    restart_script = ROOT / "hermes" / "restart_gateway_later.py"
    command = [sys.executable, str(restart_script), "--delay", "8"]
    options: dict = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        options["start_new_session"] = True
    subprocess.Popen(command, **options)


def update_course() -> str:
    """Claude Code 우선, Codex 폴백으로 수업 자료를 안전하게 맞춘다."""
    agents = _course_update_agents()
    if not agents:
        raise ValueError(
            "업데이트를 맡길 Claude Code나 Codex CLI가 없습니다. 코딩 앱에서 먼저 설치해 주세요."
        )
    attempts: list[str] = []
    with _course_update_guard():
        for label, command in agents:
            try:
                with _preserve_student_settings():
                    done = subprocess.run(
                        command,
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        timeout=600,
                    )
            except (OSError, subprocess.TimeoutExpired) as error:
                attempts.append(f"{label}: {type(error).__name__}")
                continue
            if done.returncode != 0:
                attempts.append(f"{label}: {_short_update_error(done.stderr or done.stdout)}")
                continue

            verify = subprocess.run(
                [sys.executable, str(ROOT / "verify.py")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=120,
            )
            if verify.returncode != 0:
                return "\n".join([
                    done.stdout.strip(),
                    "",
                    f"🛠 맡은 도구: {label}",
                    "❌ 업데이트 뒤 5/5 확인이 통과하지 않았습니다.",
                    _short_update_error(verify.stdout or verify.stderr),
                    "Telegram 연결은 이전 상태로 유지했습니다.",
                ]).strip()

            _refresh_course_connection()
            result = done.stdout.strip() or "🔄 실습 환경 · 업데이트\n✅ 맞춤과 5/5 확인 완료"
            return "\n".join([
                result,
                "",
                f"🛠 맡은 도구: {label}",
                "✅ python verify.py 5/5",
                "🔁 Telegram 연결은 이 답장 뒤 자동으로 다시 읽습니다.",
            ])

    raise RuntimeError(
        "업데이트를 맡길 코딩 도구가 모두 응답하지 않았습니다.\n" + "\n".join(attempts)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes Telegram 투자 명령")
    sub = parser.add_subparsers(dest="command", required=True)
    tech = sub.add_parser("tech")
    tech.add_argument("target")
    tech_review_cmd = sub.add_parser("tech-review")
    tech_review_cmd.add_argument("target")
    fund = sub.add_parser("fundamental")
    fund.add_argument("target")
    market_cmd = sub.add_parser("market-review")
    market_cmd.add_argument("target")
    combined_cmd = sub.add_parser("combined")
    combined_cmd.add_argument("target")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("auth")
    sub.add_parser("update")
    sub.add_parser("settings")
    account_type_cmd = sub.add_parser("set-account", help=argparse.SUPPRESS)
    account_type_cmd.add_argument("account_type", choices=sorted(ACCOUNT_TYPES))
    indicator_cmd = sub.add_parser("set-indicator", help=argparse.SUPPRESS)
    indicator_cmd.add_argument("indicator", choices=sorted(ANALYSIS_INDICATORS))
    sub.add_parser("account")
    sub.add_parser("holdings")
    sub.add_parser("pending-orders")
    sub.add_parser("rule")
    sub.add_parser("hypothesis-review", help=argparse.SUPPRESS)
    adopt_cmd = sub.add_parser("adopt")
    adopt_cmd.add_argument("proposal_id")
    sub.add_parser("adopt-latest", help=argparse.SUPPRESS)
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--approve", default="", help=argparse.SUPPRESS)
    plan_cmd.add_argument("--approve-latest", action="store_true", help=argparse.SUPPRESS)
    plan_cmd.add_argument("--cancel-latest", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("review-plan", help=argparse.SUPPRESS)
    log_cmd = sub.add_parser("log")
    log_cmd.add_argument("text")
    args = parser.parse_args()

    try:
        if args.command == "tech":
            output = technical(args.target)
        elif args.command == "tech-review":
            output = technical_review(args.target, with_artifacts=True)
        elif args.command == "fundamental":
            output = fundamental(args.target, with_artifacts=True)
        elif args.command == "market-review":
            output = market_review(args.target, with_artifacts=True)
        elif args.command == "combined":
            output = combined_analysis(args.target, with_artifacts=True)
        elif args.command == "status":
            output = status()
        elif args.command == "doctor":
            output = doctor()
        elif args.command == "auth":
            output = auth_status()
        elif args.command == "update":
            output = update_course()
        elif args.command == "settings":
            output = settings()
        elif args.command == "set-account":
            output = set_account_type(args.account_type)
        elif args.command == "set-indicator":
            output = set_analysis_indicator(args.indicator)
        elif args.command == "account":
            output = account()
        elif args.command == "holdings":
            output = holdings()
        elif args.command == "pending-orders":
            output = pending_orders()
        elif args.command == "rule":
            output = rule()
        elif args.command == "hypothesis-review":
            output = hypothesis_review()
        elif args.command == "adopt":
            output = adopt(args.proposal_id)
        elif args.command == "adopt-latest":
            output = adopt_latest()
        elif args.command == "plan":
            output = plan(
                args.approve,
                approve_latest=args.approve_latest,
                cancel_latest=args.cancel_latest,
            )
        elif args.command == "review-plan":
            output = review_pending_plan()
        else:
            output = log_judgment(args.text)
    except (OSError, RuntimeError, ValueError, market.MarketError) as error:
        raise SystemExit(str(error)) from error
    print(output)


if __name__ == "__main__":
    main()

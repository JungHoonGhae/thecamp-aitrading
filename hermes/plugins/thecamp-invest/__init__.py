"""The Camp 수업용 Hermes Telegram 명령.

공개 명령은 모두 ``/ts_*``라서 Hermes 기본 명령과 겹치지 않는다. 단순 조회와 기록은
결정적 helper를 바로 호출하고, 웹 조사·가설 검토·승인 버튼이 필요한 명령만 내부 스킬로
넘긴다.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Callable


HELP = """\
[내 투자 에이전트]

/ts_help                       수업 명령 전체 보기
/ts_update                     최신 강의자료 받기·5/5 확인·연결 갱신
/ts_doctor                     실습 코드·설정·gateway 빠른 진단
/ts_auth                       Hermes·Claude·Codex·KIS 연결 상태
/ts_status                     잔고·보유 주식·대기 주문을 한 번에 확인
/ts_tools [찾을 말]            KIS 공식 166개 전략 재료 빠르게 검색
/ts_config                     계좌 종류·기술적 분석 지표 설정
/ts_analyze [종목명·티커·시장] 기술적·펀더멘탈·둘 다·시장 중 선택
/ts_rule                       현재 규칙 또는 기본 분석 규칙의 근거·한계 확인
/ts_order_plan                 모의주문안을 계산하고 승인·보류 버튼 선택
/ts_memory [선택: 기억할 말]   자동 기록 조회·필요한 원칙만 기억

핵심 흐름: /ts_status → /ts_analyze → /ts_order_plan → 승인 또는 보류
처음 설정할 때만 /ts_config와 /ts_rule을 사용합니다.
대화와 실행 결과는 Hermes가 자동으로 남기며 /ts_memory에서 돌아볼 수 있습니다.
버튼을 고르지 않아 오래 "Working"이면 /stop을 한 번 누른 뒤 다시 시작하세요.
/stop은 기다리는 AI 작업만 멈추며 주문을 실행하지 않습니다.
"""


def _repo_root() -> Path:
    marker = Path(__file__).with_name(".repo-path")
    if marker.is_file():
        candidate = Path(marker.read_text(encoding="utf-8").strip()).expanduser().resolve()
        if (candidate / "agent" / "hermes_invest.py").is_file():
            return candidate

    # 저장소에서 직접 검사할 때: REPO/hermes/plugins/thecamp-invest/__init__.py
    source_candidate = Path(__file__).resolve().parents[3]
    if (source_candidate / "agent" / "hermes_invest.py").is_file():
        return source_candidate

    cwd = Path.cwd().resolve()
    if (cwd / "agent" / "hermes_invest.py").is_file():
        return cwd
    raise RuntimeError("수업 저장소 위치를 찾지 못했습니다. Hermes 수업 연결을 다시 설치해 주세요.")


_HELPER_MODULE = "_thecamp_course_hermes_invest"


def _helper():
    repo = _repo_root()
    helper_path = repo / "agent" / "hermes_invest.py"
    loaded = sys.modules.get(_HELPER_MODULE)
    if loaded is not None and Path(loaded.__file__).resolve() == helper_path.resolve():
        return loaded

    # Hermes itself already imports a top-level package named `agent`.  A plain
    # `from agent import hermes_invest` therefore resolves to Hermes internals,
    # not this course repository.  Load the exact file under a unique name.
    spec = importlib.util.spec_from_file_location(_HELPER_MODULE, helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("수업 명령 파일을 불러올 수 없습니다. Hermes 수업 연결을 다시 설치해 주세요.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HELPER_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_HELPER_MODULE, None)
        raise
    return module


async def _call(method: str, raw_args: str = "") -> str:
    def run() -> str:
        helper = _helper()
        fn = getattr(helper, method)
        return fn(raw_args) if method in {"technical", "fundamental", "log_judgment", "tools_catalog"} else fn()

    try:
        return await asyncio.to_thread(run)
    except Exception as error:
        return f"[수업 명령 실패]\n{error}"


def _direct(method: str) -> Callable[[str], object]:
    def handler(raw_args: str):
        return _call(method, raw_args)

    return handler


def _unreachable(_: str) -> str:
    return "수업 명령 연결을 다시 불러와 주세요: /restart"


def _register_public(ctx, name: str, handler, description: str) -> None:
    """Hermes keeps hyphens; Telegram renders the same command with underscores."""
    ctx.register_command(name, handler=handler, description=description)


ROUTED = {
    "ts-config": "thecamp-settings",
    "ts-analyze": "thecamp-analyze",
    "ts-order-plan": "thecamp-plan",
    "ts-memory": "thecamp-memory",
}

ALIASES = {
    "ts-view-help": "ts-help",
    "ts-settings": "ts-config",
    "ts-update-settings": "ts-config",
    "ts-account": "ts-status",
    "ts-check-account": "ts-status",
    "ts-holdings": "ts-status",
    "ts-check-holdings": "ts-status",
    "ts-pending-orders": "ts-status",
    "ts-check-pending-orders": "ts-status",
    "ts-technical": "ts-analyze",
    "ts-analyze-technical": "ts-analyze",
    "ts-fundamental": "ts-analyze",
    "ts-analyze-fundamental": "ts-analyze",
    "ts-review": "ts-rule",
    "ts-hypothesis": "ts-rule",
    "ts-review-hypothesis": "ts-rule",
    "ts-check-rule": "ts-rule",
    "ts-plan": "ts-order-plan",
    "ts-create-plan": "ts-order-plan",
    "ts-write-log": "ts-memory",
    "ts-log": "ts-memory",
}


def _pre_gateway_dispatch(event=None, **_: object):
    """Rewrite Telegram's /ts_* text to the internal skill before dispatch."""
    text = str(getattr(event, "text", "") or "").lstrip()
    if not text.startswith("/"):
        compact = text.lower().replace(" ", "")
        account_words = ("계좌상태", "내계좌", "잔고", "보유주식", "평가손익", "수익중", "+인가", "플러스인가", "마이너스인가")
        if any(word in compact for word in account_words):
            return {"action": "rewrite", "text": "/ts-status"}
        tool_words = ("166개", "어떤도구", "무슨도구", "전략재료", "mcp재료", "mcp도구")
        if any(word in compact for word in tool_words):
            return {"action": "rewrite", "text": f"/ts-tools {text}"}
        memory_words = (
            "기억해줘", "기억해둘", "기억해도", "잊지마",
            "앞으로도기억", "다음에도기억",
        )
        if any(word in compact for word in memory_words):
            return {"action": "rewrite", "text": f"/thecamp-memory {text}"}
        return None
    head, _, tail = text.partition(" ")
    telegram_name = head[1:].split("@", 1)[0].lower()
    original = telegram_name.replace("_", "-")
    command = ALIASES.get(original, original)
    target = ROUTED.get(command)
    if target is None and command == original and telegram_name == command:
        return None
    rewritten = f"/{target or command} {tail}".strip()
    return {"action": "rewrite", "text": rewritten}


def _review(ctx):
    """Return a native choice request instead of asking an LLM to build a menu."""

    async def handler(raw_args: str):
        selected = raw_args.strip()
        if not selected:
            return {
                "__hermes_choice__": True,
                "question": "무엇을 검토할까요?",
                "choices": ["📌 현재 규칙", "🔎 기본 분석 규칙의 근거와 한계"],
                "timeout_message": (
                    "선택 시간이 끝났습니다. 검토와 주문은 실행되지 않았습니다. "
                    "다시 보려면 /ts_rule 을 보내 주세요."
                ),
            }
        if "현재 규칙" in selected:
            return await _call("rule")
        if "근거" in selected or "한계" in selected:
            return await _call("hypothesis_review")
        return "아래 버튼 중 하나를 선택해 주세요. 다시 보려면 /ts_rule 을 보내 주세요."

    return handler


def register(ctx) -> None:
    _register_public(ctx, "ts-help", lambda _: HELP, "수업 명령 전체 보기")
    _register_public(
        ctx,
        "ts-update",
        _direct("update_course"),
        "최신 강의자료 받기·5/5 확인·연결 갱신",
    )
    _register_public(
        ctx,
        "ts-doctor",
        _direct("doctor"),
        "실습 코드·설정·gateway 빠른 진단",
    )
    _register_public(
        ctx,
        "ts-auth",
        _direct("auth_status"),
        "Hermes·Claude·Codex·KIS 연결 상태",
    )
    _register_public(
        ctx,
        "ts-status",
        _direct("status"),
        "총자산·현금·종목별 매입/평가/손익·대기 주문을 한 번에 확인",
    )
    _register_public(
        ctx,
        "ts-tools",
        _direct("tools_catalog"),
        "[찾을 말] KIS 공식 166개 전략 재료 빠르게 검색",
    )
    routed_descriptions = {
        "ts-config": "계좌 종류·기술적 분석 지표 설정",
        "ts-analyze": "[종목명·티커·시장] 기술적·펀더멘탈·둘 다·시장 중 선택",
        "ts-order-plan": "현재 잔고와 목표 비중을 비교해 모의주문안 계산",
        "ts-memory": "[선택: 기억할 말] 자동 기록 조회·필요한 원칙만 기억",
    }
    for public, description in routed_descriptions.items():
        _register_public(ctx, public, _unreachable, description)
    _register_public(
        ctx,
        "ts-rule",
        _review(ctx),
        "현재 규칙 또는 기본 분석 규칙의 근거와 한계를 버튼으로 선택",
    )
    ctx.register_hook("pre_gateway_dispatch", _pre_gateway_dispatch)

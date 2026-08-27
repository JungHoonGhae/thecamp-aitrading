"""분석 예제 셋이 함께 쓰는 준비물.

에이전트(agent/agent.py)가 이미 읽고 있는 **내 스펙**을 그대로 다시 읽는다.
분석 예제가 따로 노는 게 아니라, 같은 표 네 칸을 본다는 뜻이다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from agent import load_forbidden, load_portfolio  # noqa: E402
from common.kis import KISClient  # noqa: E402

__all__ = ["ROOT", "KISClient", "load_forbidden", "load_portfolio",
           "blocked_by", "rule", "head", "bullet", "pad"]


def pad(text: str, width: int) -> str:
    """한글은 터미널에서 두 칸을 차지한다. f-string 의 :<14 로는 표가 어긋난다."""
    import unicodedata
    used = sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)
    return text + " " * max(0, width - used)


def blocked_by(name: str, forbidden: list[str]) -> str:
    """종목 이름이 스펙 ④ 「하지 마」 에 걸리면 그 단어를 돌려준다.

    가드레일과 같은 판정이다 — 분석 단계에서 미리 걸러 두면
    주문 단계까지 갔다가 차단당하는 일이 줄어든다.
    """
    for word in forbidden:
        if word in name:
            return word
    return ""


def rule(text: str = "") -> None:
    print(f"\n{'─' * 58}")
    if text:
        print(text)
        print("─" * 58)


def head(title: str, subtitle: str = "") -> None:
    print(f"\n{title}")
    if subtitle:
        print(subtitle)
    print("─" * 58)


def bullet(text: str) -> None:
    print(f"  · {text}")

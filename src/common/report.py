"""점검·리밸런싱 보고의 구조화된 표현 (Report) — agent.py 와 discord.py 가 공유하는 seam.

agent.py 는 이 타입들로 Report 를 만들기만 하고, 렌더링(평문/Components v2)은 모른다.
discord.py(그리고 개인 슬래시봇)는 Report 를 받아 렌더링만 하고, agent.py 의 문구를
regex 로 되짚어 파싱하지 않는다 — 문자열 한 번 뭉쳤다가 다시 파싱하던 예전 구조의
드리프트(2026-07-17 웹훅·슬래시봇에서 각각 발생)를 구조적으로 막는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ComparisonRow:
    name: str
    code: str
    target_pct: float
    current_pct: float
    action: str  # "매수" | "매도" | "유지"
    qty: int
    needs_adjust: bool


@dataclass
class PreviewRow:
    name: str
    verb: str  # "매수" | "매도"
    qty: int
    amount: int


@dataclass
class ExecutionRow:
    name: str
    verb: str
    qty: int
    ok: bool
    msg: str


@dataclass
class Callout:
    heading: str  # 이미 완성된 제목 문구 (예: "⛔ 가드레일 위반 (주문 차단):")
    items: list[str]


@dataclass
class ExecuteResult:
    kind: str  # "preview" | "blocked" | "no_orders" | "executed"
    lines: list[str] = field(default_factory=list)  # preview/blocked/no_orders 용 완성 문구
    execution_kind: str = ""  # "executed" 일 때: "시뮬레이션" | "실계좌 모의투자"
    rows: list[ExecutionRow] = field(default_factory=list)  # "executed" 일 때만


@dataclass
class Report:
    """mode_label 이 None 이면 '계좌가 비어 있습니다' 류의 단순 메시지 — notes 만 본다."""
    mode_label: str | None = None  # "모의데이터" | "실계좌"
    title: str = ""
    total_won: int = 0
    cash_won: int = 0
    comparison: list[ComparisonRow] = field(default_factory=list)
    callouts: list[Callout] = field(default_factory=list)
    preview: list[PreviewRow] = field(default_factory=list)
    execute_result: ExecuteResult | None = None
    notes: list[str] = field(default_factory=list)  # 이미 "※ " 등이 포함된 완성 문구
    chart_url: str | None = None


def to_plain_text(r: Report) -> str:
    """웹훅 미설정 화면 출력 · verify.py 가 grep 하는 정확한 한글 문구를 만든다."""
    if r.mode_label is None:
        return "\n".join(r.notes)

    lines = [f"[{r.mode_label}] {r.title}",
             f"총 자산: {r.total_won:,}원 (현금 {r.cash_won:,}원)", ""]

    for row in r.comparison:
        flag = "  ⚠️조정필요" if row.needs_adjust else ""
        lines.append(
            f"- {row.name}({row.code}): 목표 {row.target_pct:.0f}% / "
            f"현재 {row.current_pct:.1f}% → {row.action} 약 {row.qty}주{flag}")

    for c in r.callouts:
        lines += ["", c.heading] + [f"- {i}" for i in c.items]

    if r.preview:
        lines += ["", "리밸런싱 미리보기:"]
        lines += [f"- {p.name}: {p.verb} {p.qty}주 (약 {p.amount:,}원)" for p in r.preview]
    else:
        lines += ["", "리밸런싱할 주문이 없습니다 (허용 오차 이내)."]

    er = r.execute_result
    if er:
        if er.kind == "executed":
            lines += ["", f"[실행] 가드레일 통과분 주문 전송 — {er.execution_kind}…"]
            for e in er.rows:
                mark = "✅" if e.ok else "❌"
                lines.append(f"  {mark} {e.name} {e.verb} {e.qty}주 — {e.msg}")
        else:
            lines += [""] + er.lines

    for n in r.notes:
        lines += ["", n]

    return "\n".join(lines)

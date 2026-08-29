"""나만의 AI 투자 에이전트 (미니).

하는 일:
  1) spec/ 의 마크다운(목표 포트폴리오·규칙·가드레일)을 읽는다.
  2) KIS(mock/live)로 현재 계좌 상태를 조회한다.
  3) 목표 비중과 현재 비중을 비교해 "무엇을 얼마나 사고팔지" 계산한다(미리보기).
  4) 가드레일을 점검한다. 위반이 있으면 주문을 "차단"한다.
  5) --execute 를 붙이면, 가드레일을 통과한 주문만 모의투자로 실행한다.
  6) 결과를 텔레그램(또는 화면)으로 보고한다.

신뢰 게이트: 기본은 미리보기(주문 없음) → --execute 로 확인 실행 → 가드레일이 최종 차단.

실행:  python agent/agent.py                     # 미리보기만 (mock, 기본)
       python agent/agent.py --execute           # 가드레일 통과분 주문 (mock=연습 계좌 체결)
       python agent/agent.py --reset-mock        # 연습 계좌를 처음 상태로
       KIS_MODE=live python agent/agent.py --execute   # 증권사 모의투자 (평일·장중)
"""
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from common.kis import KISClient, reset_mock_ledger  # noqa: E402
from common.telegram import report  # noqa: E402
from common.chart import overview_chart_url  # noqa: E402
from common.report import (  # noqa: E402
    Callout, ComparisonRow, ExecutionRow, ExecuteResult, PreviewRow, Report,
)

SPEC = Path(__file__).parent / "spec"


def load_portfolio() -> list[dict]:
    """portfolio.md 의 표에서 목표 비중을 읽는다."""
    rows = []
    for line in (SPEC / "portfolio.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d{6})\s*\|\s*(.+?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|", line)
        if m:
            rows.append({"code": m.group(1), "name": m.group(2),
                         "target": float(m.group(3))})
    return rows


def load_number(filename: str, label: str, default: float) -> float:
    """rules.md / guardrails.md 에서 'label ... 숫자%' 형태의 값을 읽는다."""
    text = (SPEC / filename).read_text(encoding="utf-8")
    m = re.search(re.escape(label) + r"[^0-9]*(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else default


def load_forbidden() -> list[str]:
    """guardrails.md 「하지 마」 소절의 굵은 항목을 읽는다 (내-투자-스펙.md ④ 에서 온 값)."""
    text = (SPEC / "guardrails.md").read_text(encoding="utf-8")
    sect = re.search(r"## 하지 마 \(금지\)\n(.*?)(?=\n## |\Z)", text, re.S)
    return re.findall(r"- \*\*(.+?)\*\*", sect.group(1)) if sect else []


def load_schedule() -> str:
    """rules.md 의 리밸런싱 주기 문장을 읽는다 (내-투자-스펙.md ② 에서 온 값)."""
    text = (SPEC / "rules.md").read_text(encoding="utf-8")
    m = re.search(r"^- \*\*리밸런싱 주기\*\*:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else ""


def schedule_note(schedule: str) -> str:
    """오늘이 내가 정한 점검일인지 한 줄로 알려준다. ② 를 고치면 이 줄이 바뀐다."""
    if not schedule:
        return ""
    today = "월화수목금토일"[datetime.now().weekday()]
    is_today = "매일" in schedule or f"{today}요일" in schedule or f"매{today}" in schedule
    if is_today:
        return f"※ 점검 주기는 「{schedule}」 — 오늘이 그날입니다."
    return (f"※ 점검 주기는 「{schedule}」 — 오늘은 그날이 아닙니다. "
            "연습 삼아 지금 돌려보는 건 언제든 괜찮습니다.")


def build_report(
    execute: bool,
    *,
    kis: KISClient | None = None,
    balance: dict | None = None,
) -> Report:
    """계좌를 점검하고 (신뢰 게이트에 따라) 리밸런싱까지 실행한 뒤, 구조화된 Report 를 만든다.

    KIS·telegram 을 모르는 순수 계산이 아니라 여전히 I/O 를 포함하지만, 적어도 반환값이
    Report 하나라 — main() 은 같은 함수를 그대로 불러 쓸 수 있다.
    """
    kis = kis or KISClient()
    portfolio = load_portfolio()
    tolerance = load_number("rules.md", "허용 오차", 5)
    max_weight = load_number("guardrails.md", "한 종목 최대 비중", 40)
    min_cash = load_number("guardrails.md", "현금 최소 보유", 5)
    forbidden = load_forbidden()
    schedule = load_schedule()

    bal = balance if balance is not None else kis.get_balance()
    held = {h["code"]: h for h in bal["holdings"]}

    # 총 자산 = 예수금 + 보유 종목 평가금액 합
    total = bal["cash"] + sum(h["eval_amt"] for h in bal["holdings"])
    if total == 0:
        return Report(notes=["계좌가 비어 있습니다. 예수금/보유 종목을 확인하세요."])

    mode_label = (
        "모의투자 · 수업용" if kis.mode == "mock"
        else ("실전" if kis.env == "real" else "모의투자")
    )
    comparison: list[ComparisonRow] = []
    callouts: list[Callout] = []
    warnings: list[str] = []   # 참고용 경고 (실행은 막지 않음)
    blocks: list[str] = []     # 하드 가드레일 위반 → 실제 주문 차단
    plan: list[dict] = []      # 리밸런싱 주문 계획 [{code,name,side,qty,price}]
    chart_rows: list[dict] = []  # 차트용 [{name,target,current}]

    # 목표 비중 합이 100인지 확인 (스펙을 잘못 고치면 계산 기준이 틀어짐)
    target_sum = sum(item["target"] for item in portfolio)
    if abs(target_sum - 100) > 0.5:
        blocks.append(f"목표 비중 합이 {target_sum:.0f}%입니다 (100%가 아니면 리밸런싱 기준이 틀어짐)")

    for item in portfolio:
        cur_amt = held.get(item["code"], {}).get("eval_amt", 0)
        cur_w = cur_amt / total * 100
        gap = item["target"] - cur_w  # +면 더 사야, -면 팔아야
        price = kis.get_price(item["code"])["price"]
        gap_amt = round(total * gap / 100)
        qty = abs(gap_amt) // price if price else 0
        chart_rows.append({"name": item["name"], "target": item["target"], "current": cur_w})
        action = "매수" if gap > 0 else ("매도" if gap < 0 else "유지")
        needs_adjust = abs(gap) >= tolerance
        comparison.append(ComparisonRow(item["name"], item["code"], item["target"],
                                         cur_w, action, qty, needs_adjust))
        # ④「하지 마」에 적은 말이 종목 이름에 들어 있으면 차단한다. 학생이 표를 고치면
        # 결과가 실제로 바뀌는 자리 — 여기가 없으면 ④ 는 적어도 아무 일이 안 일어난다.
        hit = next((f for f in forbidden if f and f in item["name"]), None)
        if hit:
            blocks.append(f"{item['name']} — 스펙 ④에 적은 「{hit}」 에 걸립니다 (이 종목 주문 차단)")
        elif item["target"] > max_weight:
            blocks.append(f"{item['name']} 목표비중 {item['target']:.0f}% > 한도 {max_weight:.0f}% (이 종목 주문 차단)")
        elif action in ("매수", "매도") and qty > 0 and needs_adjust:
            plan.append({"code": item["code"], "name": item["name"],
                         "side": "buy" if gap > 0 else "sell", "qty": qty, "price": price})

    # 목표 비중 합은 100(=현금 0%)인데 가드레일은 현금을 남기라고 한다. 그대로 두면
    # 학생이 --execute 한 번에 현금을 다 쓰고, 그 뒤로 매번 "현금 부족" 경고를 본다.
    # 경고로 알리는 대신 살 때 먼저 지킨다 — 가드레일이 실제로 주문을 조절하는 자리다.
    budget = (bal["cash"]
              + sum(p["qty"] * p["price"] for p in plan if p["side"] == "sell")
              - total * min_cash / 100)
    trimmed = False
    for p in plan:
        if p["side"] != "buy":
            continue
        afford = max(int(budget // p["price"]), 0) if p["price"] else 0
        if afford < p["qty"]:
            p["qty"] = afford
            trimmed = True
        budget -= p["qty"] * p["price"]
    plan = [p for p in plan if p["qty"] > 0]
    if trimmed:
        warnings.append(f"현금을 최소 {min_cash:.0f}% 남기려고 매수 수량을 줄였습니다")

    # 비교표의 수량을 "실제로 낼 주문"과 일치시킨다. 안 맞추면 표엔 '매수 1주'인데
    # 아래엔 '주문 없음'이 떠서 학생이 어느 쪽을 믿어야 할지 모른다.
    planned = {p["code"]: p["qty"] for p in plan}
    for i, row in enumerate(comparison):
        if not row.needs_adjust:
            continue
        qty = planned.get(row.code, 0)
        reason = "" if qty else (
            "현금 최소선을 지키느라 이번엔 건너뜁니다" if row.qty else
            "1주 값이 커서 이번엔 건너뜁니다")
        comparison[i] = replace(row, qty=qty, skip_reason=reason)

    cash_w = bal["cash"] / total * 100
    if cash_w < min_cash:
        warnings.append(f"현금 비중 {cash_w:.1f}% < 최소 {min_cash:.0f}%")

    if blocks:
        callouts.append(Callout("⛔ 가드레일 위반 (주문 차단):", blocks))
    if warnings:
        callouts.append(Callout("가드레일 경고:", warnings))

    preview = [
        PreviewRow(p["name"], "매수" if p["side"] == "buy" else "매도", p["qty"], p["qty"] * p["price"])
        for p in plan
    ]

    # 신뢰 게이트: 기본은 미리보기, --execute 일 때만 실행, 가드레일이 최종 차단
    if not execute:
        er = ExecuteResult("preview", lines=[
            "※ 미리보기입니다. 실제 주문하려면 --execute 를 붙이세요.",
            "  (가드레일 위반이 있으면 --execute 여도 차단됩니다.)",
        ])
    elif blocks:
        er = ExecuteResult("blocked", lines=[
            "⛔ 가드레일 위반이 있어 실제 주문을 실행하지 않았습니다. 스펙을 고쳐 다시 시도하세요."])
    elif not plan:
        er = ExecuteResult("no_orders", lines=["실행할 주문이 없습니다."])
    else:
        if kis.mode == "mock":
            kind = "수업용 연습 계좌"
        elif kis.env == "real":
            kind = "실전"
        else:
            kind = "모의투자"
        fills = sorted(plan, key=lambda p: 0 if p["side"] == "sell" else 1)
        rows = []
        for p in fills:
            r = kis.place_order(p["code"], p["side"], p["qty"], name=p["name"])
            verb = "매수" if p["side"] == "buy" else "매도"
            rows.append(ExecutionRow(p["name"], verb, p["qty"], r["ok"], r.get("msg", "")))
        er = ExecuteResult("executed", execution_kind=kind, rows=rows)

    # 목표 vs 현재 비중을 차트 이미지로 함께 보고 (텔레그램에서 그림으로 보임)
    # 한 장이면 된다. 여러 장을 보내면 폰에서 번갈아 봐야 한다.
    charts = [overview_chart_url(chart_rows, cash_w)]

    return Report(
        mode_label=mode_label,
        title="포트폴리오 점검 결과",
        total_won=total,
        cash_won=bal["cash"],
        comparison=comparison,
        callouts=callouts,
        preview=preview,
        execute_result=er,
        notes=[n for n in (schedule_note(schedule),
                           "※ 이 실습은 모의투자까지입니다. 실전(실계좌) 매매는 범위 밖입니다.") if n],
        charts=charts,
    )


def main() -> None:
    if "--reset-mock" in sys.argv:
        reset_mock_ledger()
        print("수업용 연습 계좌를 처음 상태로 되돌렸습니다.")
        return
    execute = "--execute" in sys.argv
    try:
        report(build_report(execute))
    except RuntimeError as e:
        # RuntimeError 는 우리가 학생에게 하려던 말이다. traceback 에 묻지 않는다.
        print(f"\n{e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

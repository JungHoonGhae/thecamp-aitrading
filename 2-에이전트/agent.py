"""나만의 AI 투자 에이전트 (미니).

하는 일:
  1) spec/ 의 마크다운(목표 포트폴리오·규칙·가드레일)을 읽는다.
  2) KIS(mock/live)로 현재 계좌 상태를 조회한다.
  3) 목표 비중과 현재 비중을 비교해 "무엇을 얼마나 사고팔지" 계산한다.
  4) 가드레일을 점검하고, 결과를 디스코드(또는 화면)로 보고한다.

실제 매수/매도 주문은 넣지 않는다. 점검·보고까지만.

실행:  python agent.py            # mock 모드 (기본)
       KIS_MODE=live python agent.py   # 실제 모의투자 키로
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.kis import KISClient  # noqa: E402
from common.discord import report  # noqa: E402

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


def main() -> None:
    kis = KISClient()
    portfolio = load_portfolio()
    tolerance = load_number("rules.md", "허용 오차", 5)
    max_weight = load_number("guardrails.md", "한 종목 최대 비중", 40)
    min_cash = load_number("guardrails.md", "현금 최소 보유", 5)

    bal = kis.get_balance()
    held = {h["code"]: h for h in bal["holdings"]}

    # 총 자산 = 예수금 + 보유 종목 평가금액 합
    total = bal["cash"] + sum(h["eval_amt"] for h in bal["holdings"])
    if total == 0:
        report("계좌가 비어 있습니다. 예수금/보유 종목을 확인하세요.")
        return

    lines = [f"[{'모의데이터' if kis.mode == 'mock' else '실계좌'}] 포트폴리오 점검 결과",
             f"총 자산: {total:,}원 (현금 {bal['cash']:,}원)", ""]
    warnings = []

    # 목표 비중 합이 100인지 확인 (스펙을 잘못 고치면 계산 기준이 틀어짐)
    target_sum = sum(item["target"] for item in portfolio)
    if abs(target_sum - 100) > 0.5:
        warnings.append(f"목표 비중 합이 {target_sum:.0f}%입니다 (portfolio.md 에서 100%로 맞추세요)")

    for item in portfolio:
        cur_amt = held.get(item["code"], {}).get("eval_amt", 0)
        cur_w = cur_amt / total * 100
        gap = item["target"] - cur_w  # +면 더 사야, -면 팔아야
        price = kis.get_price(item["code"])["price"]
        gap_amt = round(total * gap / 100)
        qty = abs(gap_amt) // price if price else 0
        action = "매수" if gap > 0 else ("매도" if gap < 0 else "유지")
        flag = "  ⚠️조정필요" if abs(gap) >= tolerance else ""
        lines.append(
            f"- {item['name']}({item['code']}): 목표 {item['target']:.0f}% / "
            f"현재 {cur_w:.1f}% → {action} 약 {qty}주{flag}")
        if item["target"] > max_weight:
            warnings.append(f"{item['name']} 목표비중 {item['target']:.0f}% > 한도 {max_weight:.0f}%")

    cash_w = bal["cash"] / total * 100
    if cash_w < min_cash:
        warnings.append(f"현금 비중 {cash_w:.1f}% < 최소 {min_cash:.0f}%")

    if warnings:
        lines += ["", "가드레일 경고:"] + [f"- {w}" for w in warnings]
    lines += ["", "※ 이 에이전트는 점검·보고만 합니다. 실제 주문은 넣지 않습니다."]
    report("\n".join(lines))


if __name__ == "__main__":
    main()

"""미국·한국 주식 참조 제안을 채택하고 로컬 모의계좌에서 실행한다.

두 사람 개입을 명령행에서 분리한다.
  1) --adopt 제안번호
  2) --approve 주문계획번호 --execute
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common.us_committee import load_advisory, load_reference_packet  # noqa: E402
from common.us_mock import LocalMockBroker  # noqa: E402
from common.us_reference import (  # noqa: E402
    Guardrails,
    adopt_proposal,
    build_order_plan,
    execute_approved_plan,
    save_adopted_spec,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


def money(value: int, currency: str) -> str:
    if currency == "USD":
        return f"${value / 100:,.2f}"
    return f"{value:,}원"


def main() -> None:
    parser = argparse.ArgumentParser(description="미국·한국 주식 참조 에이전트")
    parser.add_argument("--market", type=str.upper, choices=("US", "KR"), default="US")
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--spec-output", type=Path)
    parser.add_argument("--adopt", default="", help="사람이 채택한 제안 번호")
    parser.add_argument("--approve", default="", help="사람이 승인한 주문 계획 번호")
    parser.add_argument("--max-weight", type=float, default=40, help="한 종목 최대 비중(퍼센트)")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--reset-mock", action="store_true")
    args = parser.parse_args()

    packet = load_reference_packet(FIXTURES, args.market)
    proposal_path = args.proposal or ROOT / ".state" / f"{args.market.lower()}-proposal.json"
    ledger_path = args.ledger or ROOT / ".state" / f"{args.market.lower()}-ledger.json"
    broker = LocalMockBroker(
        market=args.market,
        currency=packet["currency"],
        prices={k: int(v) for k, v in packet["prices"].items()},
        initial_cash=int(packet["initial_cash"]),
        ledger_path=ledger_path,
    )
    if args.reset_mock:
        broker.reset()
        market_label = "미국 주식" if args.market == "US" else "한국 주식"
        print(f"{market_label} 로컬 모의계좌를 처음 상태로 되돌렸습니다.")
        return

    if not proposal_path.is_file():
        raise SystemExit("판단 제안이 없습니다. 먼저 python agent/committee.py 를 실행하세요.")
    proposal = load_advisory(proposal_path)
    if proposal.market != args.market:
        raise SystemExit("판단 제안과 선택한 시장이 다릅니다.")
    if not args.adopt:
        raise SystemExit(
            "첫 번째 사람 확인이 필요합니다.\n"
            f"제안을 채택한다면 --adopt {proposal.proposal_id} 를 붙이세요."
        )

    spec = adopt_proposal(
        proposal,
        args.adopt,
        max_position_weight=args.max_weight,
    )
    spec_output = (
        args.spec_output
        or ROOT / ".state" / f"{args.market.lower()}-active-spec.json"
    )
    save_adopted_spec(spec, spec_output)
    balance = broker.get_balance()
    plan = build_order_plan(
        spec,
        account_id=f"course-local-{args.market.lower()}",
        cash=balance["cash"],
        holdings=balance["holdings"],
        ledger_revision=balance.get("revision", 0),
        prices=broker.prices,
        quote_timestamp=f"{packet['as_of']}-01T00:00:00Z",
        guardrails=Guardrails(
            max_weight=args.max_weight,
            min_cash=10,
            forbidden_tickers=("TQQQ", "SQQQ", "UPRO", "SPXU"),
        ),
    )

    market_label = "미국 주식" if args.market == "US" else "한국 주식"
    print(f"\n규칙 코드 · {market_label} 주문 미리보기")
    print("─" * 58)
    print(f"채택한 제안 번호: {spec.source_proposal_id}")
    print(f"채택 스펙 해시: {spec.spec_hash}")
    if plan.blocks:
        for reason in plan.blocks:
            print(f"차단: {reason}")
    elif not plan.orders:
        print("실행할 주문이 없습니다.")
    else:
        for order in plan.orders:
            verb = "매수" if order.side == "buy" else "매도"
            print(
                f"  {order.ticker:<6} {verb} {order.qty}주 · "
                f"지정가 {money(order.limit_price, plan.currency)}"
            )
    print(f"주문 계획 번호: {plan.plan_id}")

    if not args.execute:
        print("미리보기입니다. 주문하려면 정확한 계획 번호를 다시 승인해야 합니다.")
        return
    if not args.approve:
        raise SystemExit(
            "두 번째 사람 확인이 필요합니다.\n"
            f"--approve {plan.plan_id} 를 붙여 정확한 주문을 승인하세요."
        )

    fills = execute_approved_plan(plan, args.approve, broker)
    print("\n로컬 모의계좌 체결")
    for fill in fills:
        verb = "매수" if fill["side"] == "buy" else "매도"
        mark = "완료" if fill["ok"] else "실패"
        print(f"  {mark} · {fill['ticker']} {verb} {fill['qty']}주 · {fill['message']}")
    after = broker.get_balance()
    print(f"남은 현금: {money(after['cash'], plan.currency)}")
    print("실제 돈이 움직이지 않은 수업용 체결입니다.")


if __name__ == "__main__":
    main()

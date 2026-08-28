"""고정 참조 실험을 한 번 검토해 읽기 전용 판단 제안을 만든다.

실행:
  python agent/committee.py
  python agent/committee.py --with-ai

이 파일은 제안을 저장할 뿐 주문 모듈이나 브로커를 부르지 않는다.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common.us_committee import (  # noqa: E402
    build_reference_advisory,
    load_reference_packet,
    save_advisory,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


def main() -> None:
    parser = argparse.ArgumentParser(description="미국·한국 주식 참조 실험 · 읽기 전용")
    parser.add_argument("--market", type=str.upper, choices=("US", "KR"), default="US")
    parser.add_argument("--with-ai", action="store_true", help="설치된 AI로 약점과 다음 질문을 한 번 검토")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    packet = load_reference_packet(FIXTURES, args.market)
    ask_fn = None
    if args.with_ai:
        from common import judge

        if judge.available():
            ask_fn = judge.ask
        else:
            print("설치된 AI를 찾지 못해 수업용 고정 설명을 사용합니다.")

    proposal = build_reference_advisory(packet, ask_fn=ask_fn)
    output = args.output or ROOT / ".state" / f"{args.market.lower()}-proposal.json"
    save_advisory(proposal, output)

    market_label = "미국 주식" if args.market == "US" else "한국 주식"
    print(f"\n참조 실험 · {market_label} 판단 제안")
    print("─" * 58)
    print(packet["fixture_notice"])
    print(f"자료 기준일: {packet['as_of']}")
    earlier = packet["result"]["periods"]["earlier"]
    later = packet["result"]["periods"]["later"]
    print(
        f"이전 구간 비용 후 {earlier['net_compounded_return']:+.1%} · "
        f"벤치마크 차이 {earlier['net_excess_return']:+.1%}p"
    )
    print(
        f"나중 구간 비용 후 {later['net_compounded_return']:+.1%} · "
        f"벤치마크 차이 {later['net_excess_return']:+.1%}p"
    )
    print("\n[AI 검토 · 주문 권한 없음]")
    print(f"약점: {proposal.review.weakness}")
    print(f"반대 근거: {proposal.review.contrary_evidence}")
    print(f"다음 질문: {proposal.review.next_question}")

    print("\n스펙 변경안")
    for ticker, weight in proposal.suggested_weights.items():
        print(f"  {ticker:<6} {weight:g}%")
    print(f"  현금   {proposal.cash_weight:g}%")
    print("\n매도·손절 제안")
    print(
        f"  {proposal.exit_policy.rebalance_months}개월마다 다시 순위를 매겨 "
        "목표 밖 종목은 매도"
    )
    print(
        f"  고점 대비 -{proposal.exit_policy.stop_loss_review_pct:g}%이면 자동 매도하지 않고 "
        "원문과 가설을 다시 검토"
    )
    print(f"\n제안 번호: {proposal.proposal_id}")
    print("아직 주문이 아닙니다. 이 제안을 채택할지는 사람이 정합니다.")
    print(f"저장: {output}")


if __name__ == "__main__":
    main()

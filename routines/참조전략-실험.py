"""참조 실험 — 고정 US/KR 참조 결과를 같은 조건으로 읽는다.

카테고리: 정보수집 (읽기만 합니다. 주문이 나가지 않습니다)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _routine import ROOT, 루틴, 정보수집

sys.path.insert(0, str(ROOT / "src"))

from common import judge  # noqa: E402
from common.us_committee import (  # noqa: E402
    build_reference_advisory,
    load_reference_packet,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"


def main() -> None:
    selection = json.loads(
        (FIXTURES / "reference_selection.json").read_text(encoding="utf-8")
    )
    routine = 루틴(
        "참조 실험",
        정보수집,
        출처=["고정 manifest", "고정 US/KR 결과"],
    )
    routine.칸("한 가지 규칙")
    routine.줄("미국 대형주: 직전 한 달을 빼고 1년 성적이 상위인 종목을 다음 한 달 같은 금액으로 담습니다.")
    routine.줄("순위 밖이면 다음 달 점검에서 바꿉니다. 한국에 같은 규칙을 쓰면 수업 본편으로 쓰지 않습니다.")

    if "--compare" in sys.argv:
        from common.reference_compare import compare_rebalance  # noqa: E402

        comparison = compare_rebalance(FIXTURES)
        routine.칸("선택 비교 · 리밸런싱 주기")
        routine.줄(comparison["note"])
        for market, label in (("US", "미국"), ("KR", "한국")):
            monthly = comparison["markets"][market]["frozen_monthly"]["later"]
            snap_m = comparison["markets"][market]["snapshot_monthly"]
            snap_q = comparison["markets"][market]["snapshot_compare"]
            routine.칸(f"{label} · 나중 구간 고정 결과(매월)")
            routine.줄(
                f"비용 후 {monthly['net_compounded_return']:+.1%} · "
                f"벤치마크 차이 {monthly['net_excess_return']:+.1%}p · "
                f"매수 회전율 합 {monthly['buy_turnover']:.1f}"
            )
            routine.칸(f"{label} · 짧은 스냅샷 청산 시점")
            routine.줄(
                f"매월: 리밸런싱 달 {', '.join(snap_m['rebalance_months'])} · "
                f"매수 회전율 {snap_m['buy_turnover']:.2f}"
            )
            routine.줄(
                f"{comparison['compare_rebalance_months']}개월: "
                f"리밸런싱 달 {', '.join(snap_q['rebalance_months']) or '없음'} · "
                f"매수 회전율 {snap_q['buy_turnover']:.2f}"
            )
        if "--no-send" in sys.argv:
            print(routine.본문())
        else:
            routine.보내기()
        return

    for market, label in (("US", "미국"), ("KR", "한국")):
        result = json.loads(
            (FIXTURES / f"{market.lower()}_momentum_result.json").read_text(
                encoding="utf-8"
            )
        )
        later = result["periods"]["later"]
        routine.칸(f"{label} 고정 바스켓 · 2021~2025")
        routine.줄(
            f"비용 후 누적 {later['net_compounded_return']:+.1%} · "
            f"벤치마크 차이 {later['net_excess_return']:+.1%}p"
        )
        routine.줄(
            f"최대낙폭 {later['maximum_drawdown']:.1%} · "
            f"매수 회전율 합 {later['buy_turnover']:.1f}"
        )

    routine.칸("수업에서 쓸 결과")
    routine.줄(f"참조 시장: {selection['reference_market']}")
    routine.줄("고점 대비 -10%는 재검토 표시이며 자동 손절이 아닙니다.")
    routine.줄("고정 종목 바스켓의 생존편향이 있어 시장 전체 성과로 일반화하지 않습니다.")

    if "--with-ai" in sys.argv and judge.available():
        packet = load_reference_packet(FIXTURES, selection["reference_market"])
        proposal = build_reference_advisory(packet, ask_fn=judge.ask)
        routine.칸("AI가 한 번 검토한 것 · 주문 권한 없음")
        routine.줄(f"약점: {proposal.review.weakness}")
        routine.줄(f"반대 근거: {proposal.review.contrary_evidence}")
        routine.줄(f"다음 질문: {proposal.review.next_question}")

    if "--no-send" in sys.argv:
        print(routine.본문())
    else:
        routine.보내기()


if __name__ == "__main__":
    main()

"""내 전략 백테스팅 — 내가 정한 규칙이 과거에는 통했을까.

카테고리: 정보수집 (읽기만 합니다. 주문이 나가지 않습니다)

무엇을 하나:
  내 스펙 ①(목표 비중)과 ②(점검 주기)를 **과거 시세에 그대로 돌려 본다.**
  같은 기간 그냥 사서 묻어 둔 것(가만히), 그리고 코스피와 견준다.
  수익률·최대낙폭(MDD)·리밸런싱 횟수를 낸다.

왜 이게 필요한가:
  스펙을 정할 때 우리는 "이게 좋겠지" 하고 정했다. 그 말이 맞았는지
  **확인할 방법이 지금까지 없었다.** 과거 시세를 붙이면 확인이 된다.

⚠️ 과거에 통했다고 앞으로 통하지는 않는다.
  기간을 바꾸면 답이 바뀐다. 그게 이 도구로 배울 첫 교훈이다.
  이건 「내 규칙이 어떤 모양인지」 보는 자로 쓴다. 예언이 아니다.

혼자 돌리기:   python routines/내전략-백테스팅.py
"""
import sys

from _routine import ROOT, 루틴, 정보수집

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from agent import load_number, load_portfolio  # noqa: E402
from common import judge, market  # noqa: E402

# ────────────────────────────────────────────────────────────
# 지시사항
# ────────────────────────────────────────────────────────────
기간 = "1y"          # 1mo · 3mo · 6mo · 1y · 2y · 5y — 바꿔 보세요. 답이 바뀝니다.
리밸런싱_간격 = 20    # 며칠마다 목표 비중으로 되돌릴 것인가 (20 ≈ 한 달)
AI판단 = True
# ────────────────────────────────────────────────────────────


def 최대낙폭(자산: list[float]) -> float:
    """고점 대비 가장 많이 빠졌던 폭(%). 버틸 수 있었겠는지를 보는 숫자."""
    peak, worst = 자산[0], 0.0
    for v in 자산:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst * 100


def 돌려보기(시세: dict[str, list[float]], 목표: dict[str, float],
           간격: int) -> tuple[list[float], int]:
    """목표 비중으로 시작해 간격마다 되돌린다. 자산 곡선과 리밸런싱 횟수."""
    길이 = min(len(v) for v in 시세.values())
    보유 = {c: 목표[c] / 100 for c in 시세}          # 처음에 목표대로 담는다
    자산, 횟수 = [1.0], 0
    for i in range(1, 길이):
        for c in 보유:                                # 하루치 가격 변화를 반영
            보유[c] *= 시세[c][i] / 시세[c][i - 1]
        총 = sum(보유.values())
        자산.append(총)
        if 간격 and i % 간격 == 0:                     # 점검일이면 목표로 되돌린다
            보유 = {c: 총 * 목표[c] / 100 for c in 보유}
            횟수 += 1
    return 자산, 횟수


def main() -> None:
    r = 루틴("내 전략 백테스팅", 정보수집, 출처=["market", "spec"])
    holdings = load_portfolio()
    오차 = load_number("rules.md", "허용 오차", 5)

    시세: dict[str, list[float]] = {}
    for h in holdings:
        try:
            closes = market.history(market.to_symbol(h["code"]), 기간)
        except market.MarketError as e:
            r.줄(f"{h['name']} 을(를) 못 가져왔습니다: {e}")
            continue
        if len(closes) > 5:
            시세[h["code"]] = closes

    if len(시세) < 2:
        r.줄("과거 시세를 두 종목 이상 못 가져왔습니다. 잠시 뒤 다시 해 보세요.").보내기()
        return

    목표 = {h["code"]: h["target"] for h in holdings if h["code"] in 시세}
    합 = sum(목표.values()) or 1
    목표 = {c: w / 합 * 100 for c, w in 목표.items()}   # 빠진 종목이 있으면 100으로 다시 맞춘다

    내전략, 횟수 = 돌려보기(시세, 목표, 리밸런싱_간격)
    가만히, _ = 돌려보기(시세, 목표, 0)                  # 리밸런싱 없이 그대로 두기

    r.칸(f"기간 {기간} · {len(내전략)}거래일")
    r.줄(f"내 규칙(={리밸런싱_간격}일마다 되돌림)  {(내전략[-1] - 1) * 100:+.1f}%  "
         f"최대낙폭 {최대낙폭(내전략):.1f}%  리밸런싱 {횟수}회")
    r.줄(f"가만히 두기                {(가만히[-1] - 1) * 100:+.1f}%  "
         f"최대낙폭 {최대낙폭(가만히):.1f}%")
    try:
        kospi = market.history(market.TICKERS["코스피"], 기간)
        r.줄(f"코스피                    {market.change_pct(kospi):+.1f}%  "
             f"최대낙폭 {최대낙폭(kospi):.1f}%")
    except market.MarketError:
        pass

    차이 = (내전략[-1] - 가만히[-1]) * 100
    r.칸("읽는 법")
    r.줄(f"되돌리기가 {'도움이 됐습니다' if 차이 > 0 else '오히려 손해였습니다'} "
         f"({차이:+.1f}%p).")
    r.줄(f"허용 오차 {오차:.0f}%p 를 좁히면 더 자주 되돌립니다. 수수료와 세금은 여기 안 들어 있습니다.")
    r.줄("기간을 바꿔서 다시 돌려 보세요. 답이 바뀌면 그건 규칙이 아니라 운이었다는 뜻입니다.")

    if AI판단:
        본 = judge.ask(재료=r.본문(),
                      질문="이 결과에서 사람이 오해하기 쉬운 지점 하나만 짚어라.")
        if 본:
            r.칸("AI가 짚은 것")
            for line in 본.splitlines():
                if line.strip():
                    r.줄(line.strip())

    r.보내기()


if __name__ == "__main__":
    main()

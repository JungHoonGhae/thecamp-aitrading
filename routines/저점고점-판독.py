"""저점·고점 판독 — 지금 이 가격이 어디쯤인지.

카테고리: 매매제안 (제안만 합니다. 주문은 나가지 않습니다)

무엇을 하나:
  내 종목이 최근 1년 안에서 어디쯤 있는지 — 최저·최고 사이 몇 %인지,
  평균선 위인지 아래인지, 요즘 얼마나 흔들리는지 — 를 한 줄로 판독한다.

왜 이게 필요한가:
  「비싸다 / 싸다」는 느낌으로 말하게 된다. 느낌은 어제 뉴스에 흔들린다.
  같은 자를 매번 대면 최소한 **어제의 나와 오늘의 나는 같은 기준**을 쓴다.

⚠️ 이 판독은 사라거나 팔라는 말이 아니다.
  바닥에서 더 내려가고 꼭대기에서 더 오른다. 위치는 위치일 뿐이다.
  숫자는 질문을 만들 뿐이고, 답은 스펙 ①~④ 와 내가 낸다.

혼자 돌리기:   python routines/저점고점-판독.py
"""
import sys

from _routine import ROOT, 루틴, 매매제안

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from agent import load_portfolio  # noqa: E402
from common import judge, market  # noqa: E402

# ────────────────────────────────────────────────────────────
# 지시사항
# ────────────────────────────────────────────────────────────
기간 = "1y"           # 어느 구간 안에서의 위치인가
평균선 = 60           # 며칠 평균과 견줄 것인가
바닥권 = 25           # 이 % 아래면 바닥권으로 본다
꼭대기권 = 75         # 이 % 위면 꼭대기권으로 본다
AI판단 = True
# ────────────────────────────────────────────────────────────


def 판독(위치: float, 평균대비: float) -> str:
    """위치와 평균선을 합쳐 한 단어로."""
    if 위치 <= 바닥권:
        return "바닥권" if 평균대비 < 0 else "바닥권이지만 반등 중"
    if 위치 >= 꼭대기권:
        return "꼭대기권" if 평균대비 > 0 else "꼭대기권에서 꺾이는 중"
    return "가운데"


def main() -> None:
    r = 루틴("저점·고점 판독", 매매제안)
    r.칸(f"최근 {기간} 안에서 지금 위치")

    본 = []
    for h in load_portfolio():
        try:
            closes = market.history(market.to_symbol(h["code"]), 기간)
        except market.MarketError as e:
            r.줄(f"{h['name']} — 못 가져왔습니다: {e}")
            continue
        if len(closes) < 20:
            r.줄(f"{h['name']} — 데이터가 모자랍니다")
            continue

        저, 고, 지금 = min(closes), max(closes), closes[-1]
        위치 = (지금 - 저) / (고 - 저) * 100 if 고 > 저 else 50.0
        ma = market.moving_average(closes, 평균선)
        평균대비 = (지금 / ma - 1) * 100 if ma else 0.0
        vol = market.volatility_pct(closes)

        눈금 = "▁▂▃▄▅▆▇█"[min(7, int(위치 / 12.5))]
        r.줄(f"{h['name']} {눈금} {위치:.0f}% · {판독(위치, 평균대비)}")
        r.줄(f"   지금 {지금:,.0f} (최저 {저:,.0f} / 최고 {고:,.0f}) · "
             f"{평균선}일선 {평균대비:+.1f}% · 흔들림 {vol:.2f}%")
        본.append((h["name"], 위치))

    if 본:
        낮은 = min(본, key=lambda x: x[1])
        높은 = max(본, key=lambda x: x[1])
        r.칸("한눈에")
        r.줄(f"가장 낮은 자리 — {낮은[0]} ({낮은[1]:.0f}%)")
        r.줄(f"가장 높은 자리 — {높은[0]} ({높은[1]:.0f}%)")
        r.줄("위치가 낮다고 싸고 높다고 비싼 것이 아닙니다. 왜 그 자리인지가 남습니다.")

    if AI판단:
        답 = judge.ask(재료=r.본문(),
                      질문="위치만 보고 판단할 때 빠지기 쉬운 함정 하나만 짚어라.")
        if 답:
            r.칸("AI가 짚은 것")
            for line in 답.splitlines():
                if line.strip():
                    r.줄(line.strip())

    r.보내기()


if __name__ == "__main__":
    main()

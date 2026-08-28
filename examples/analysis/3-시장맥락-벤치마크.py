"""시장 맥락 — 내 포트폴리오는 코스피를 이겼나.

무엇을 하나:
  KIS 밖에서 과거 시세를 가져와 → 내 종목이 6개월 동안 얼마나 갔는지 보고
  → 같은 기간 코스피와 견주고 → 원달러·공포지수로 시장 분위기를 붙인다.
  코인을 보는 분을 위해 업비트 시세도 같은 자리에 놓는다.

왜 이게 필요한가:
  KIS 모의투자는 **지금 값 한 점**만 준다. 한 점으로는
  "비싼가 싼가", "요즘 흔들리나", "시장보다 잘했나" 를 물을 수 없다.
  그 질문을 하려고 밖에서 데이터를 붙인다. 1주차에 배운 그 방법이다.

⚠️ 주식·지수·환율은 **비공식** 소스(야후)다. 공부용이다. 코인은 업비트 **공식** 시세다.
   주문은 언제나 공식(KIS)으로만 나간다. 이 파일은 읽기만 한다.

실행:  python examples/analysis/3-시장맥락-벤치마크.py
"""
import sys

from _lab import ROOT, bullet, head, load_portfolio, pad

sys.path.insert(0, str(ROOT / "src"))
from common import crypto, market  # noqa: E402

# ────────────────────────────────────────────────────────────
# 여기를 고쳐 보세요
# ────────────────────────────────────────────────────────────
기간 = "6mo"                        # 1mo · 3mo · 6mo · 1y · 5y
평균선_일수 = 20                     # 며칠 평균과 견줄 것인가
볼_코인 = ["비트코인", "이더리움"]      # 관심 없으면 [] 로 비우세요
# ────────────────────────────────────────────────────────────


def main() -> None:
    holdings = load_portfolio()

    # ── 1. 내 종목 ──────────────────────────────────────────
    head(f"내 종목 · 최근 {기간}",
         f"수익률 · {평균선_일수}일 평균 대비 · 하루 평균 등락폭")
    print(f"  {pad('종목', 20)}{pad('수익률', 12)}{pad(f'{평균선_일수}일선', 12)}흔들림")

    수익률들 = []
    for h in holdings:
        try:
            closes = market.history(market.to_symbol(h["code"]), 기간)
        except market.MarketError as e:
            print(f"  {pad(h['name'], 20)}— {e}")
            continue
        if len(closes) < 5:
            print(f"  {pad(h['name'], 20)}— 데이터가 모자랍니다")
            continue
        ret = market.change_pct(closes)
        ma = market.moving_average(closes, 평균선_일수)
        위치 = (closes[-1] / ma - 1) * 100 if ma else 0
        vol = market.volatility_pct(closes)
        수익률들.append((h["target"], ret))
        print(f"  {pad(h['name'], 20)}{pad(f'{ret:+.1f}%', 12)}"
              f"{pad(f'{위치:+.1f}%', 12)}{vol:.2f}%")

    # ── 2. 코스피와 견주기 ──────────────────────────────────
    head("코스피와 견주면", "목표 비중으로 가중해서 계산합니다")
    try:
        kospi = market.change_pct(market.history(market.TICKERS["코스피"], 기간))
        무게합 = sum(w for w, _ in 수익률들) or 1
        내_수익 = sum(w * r for w, r in 수익률들) / 무게합
        차이 = 내_수익 - kospi
        bullet(f"내 포트폴리오 {내_수익:+.1f}%")
        bullet(f"코스피      {kospi:+.1f}%")
        bullet(f"차이        {차이:+.1f}%p — "
               f"{'시장보다 나았습니다' if 차이 > 0 else '시장을 못 따라갔습니다'}")
        print("\n  ※ 6개월 한 번으로 실력을 말할 수 없습니다. 이건 「지금 어디쯤인가」입니다.")
    except market.MarketError as e:
        bullet(f"코스피를 못 가져왔습니다 — {e}")

    # ── 3. 시장 분위기 ──────────────────────────────────────
    head("시장 분위기", "내 종목 밖의 숫자. 왜 움직였는지 짐작할 재료")
    for 이름 in ("원달러", "공포지수", "S&P500"):
        try:
            bullet(f"{이름} {market.last(market.TICKERS[이름]):,.2f}")
        except market.MarketError as e:
            bullet(f"{이름} — {e}")

    # ── 4. 코인 ─────────────────────────────────────────────
    if 볼_코인:
        head("코인", "업비트 공식 시세입니다. 주문은 이 수업에서 다루지 않습니다")
        try:
            for c in crypto.ticker(볼_코인):
                closes = crypto.history(c["name"], 90)
                bullet(f"{c['name']} {c['price']:,.0f}원 "
                       f"(전일 {c['change_pct']:+.2f}% · 90일 {market.change_pct(closes):+.1f}% "
                       f"· 흔들림 {market.volatility_pct(closes):.2f}%)")
        except crypto.CryptoError as e:
            bullet(f"업비트에서 못 가져왔습니다 — {e}")

    head("다음", "숫자는 질문을 만들 뿐, 답은 아닙니다")
    bullet("눈에 띄는 줄 하나를 골라 AI에게 물어보세요. 「왜 그런지 짐작되는 이유를 말해 줘」")
    bullet("코스피를 못 따라갔다면, 그게 내 스펙 ① 때문인지 시장 때문인지 갈라 보세요.")
    bullet("섹터 쏠림: python examples/analysis/4-섹터-쏠림점검.py")


if __name__ == "__main__":
    main()

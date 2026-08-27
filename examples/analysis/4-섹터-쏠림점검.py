"""섹터 분석 — 나는 분산했다고 생각했는데, 정말 그런가.

무엇을 하나:
  내 종목이 각각 어느 바닥(섹터)의 회사인지 찾아 → 섹터별로 비중을 합쳐 →
  한 바닥에 쏠려 있으면 알려준다. 종목별 한 줄 요약도 같이 준다.

왜 이게 필요한가:
  종목을 다섯 개로 나눴다고 분산이 아니다. 다섯 개가 전부 반도체면
  반도체가 흔들릴 때 다섯 개가 같이 흔들린다.
  스펙 ④ 의 「한 종목 몰빵」은 종목 단위로만 막는다. **섹터 몰빵은 아무도 안 막는다.**
  그 빈자리를 이 예제가 보여준다.

실행:  python examples/analysis/4-섹터-쏠림점검.py
"""
import sys
from collections import defaultdict

from _lab import ROOT, bullet, head, load_portfolio, pad

sys.path.insert(0, str(ROOT / "src"))
from common import market  # noqa: E402

# ────────────────────────────────────────────────────────────
# 여기를 고쳐 보세요
# ────────────────────────────────────────────────────────────
섹터_경고선 = 50      # 한 섹터가 이 %를 넘으면 쏠림으로 본다
기간 = "6mo"         # 섹터별 성과를 볼 기간
# ────────────────────────────────────────────────────────────


def main() -> None:
    holdings = load_portfolio()

    head("종목별 · 어느 바닥의 회사인가", f"내 종목 {len(holdings)}개")
    print(f"  {pad('종목', 20)}{pad('섹터', 14)}{pad('비중', 8)}산업")

    by_sector: dict[str, float] = defaultdict(float)
    수익: dict[str, list[tuple[float, float]]] = defaultdict(list)

    for h in holdings:
        try:
            symbol = market.to_symbol(h["code"])
            info = market.profile(symbol)
        except market.MarketError as e:
            print(f"  {pad(h['name'], 20)}— {e}")
            continue
        sector = info["sector"]
        by_sector[sector] += h["target"]
        비중 = f"{h['target']:.0f}%"
        print(f"  {pad(h['name'], 20)}{pad(sector, 14)}{pad(비중, 8)}{info['industry']}")
        try:
            수익[sector].append((h["target"], market.change_pct(market.history(symbol, 기간))))
        except market.MarketError:
            pass

    # ── 섹터별로 묶어 본다 ──────────────────────────────────
    head("섹터별 비중", f"한 섹터가 {섹터_경고선}% 를 넘으면 쏠림입니다")
    total = sum(by_sector.values()) or 1
    쏠림 = []
    for sector, weight in sorted(by_sector.items(), key=lambda kv: -kv[1]):
        share = weight / total * 100
        bar = "█" * max(1, round(share / 4))
        rows = 수익.get(sector, [])
        w = sum(x for x, _ in rows) or 1
        ret = sum(x * r for x, r in rows) / w if rows else 0.0
        print(f"  {pad(sector, 14)}{pad(f'{share:5.1f}%', 9)}{pad(bar, 28)}{ret:+6.1f}%")
        if share >= 섹터_경고선:
            쏠림.append((sector, share))

    if 쏠림:
        head("⚠️ 쏠려 있습니다", "틀렸다는 뜻은 아닙니다. 알고 있느냐가 중요합니다")
        for sector, share in 쏠림:
            bullet(f"{sector} 가 {share:.0f}% 입니다. "
                   f"이 바닥이 흔들리면 내 계좌의 {share:.0f}% 가 같이 흔들립니다.")
        bullet("스펙 ④ 「한 종목 몰빵」은 종목만 봅니다. 섹터 쏠림은 막아 주지 않습니다.")
    else:
        head("쏠림 없음", f"모든 섹터가 {섹터_경고선}% 아래입니다")

    head("다음", "여기서 갈라집니다")
    bullet("괜찮다고 보면 그대로 둡니다. 확신이 있으면 쏠림도 선택입니다.")
    bullet("아니라고 보면 스펙 ① 을 고칩니다. 다른 바닥 회사를 하나 넣어 보세요.")
    bullet("AI에게 물어보세요. 「내 섹터 분포를 보고, 빠진 바닥이 뭔지 한 줄로 말해 줘」")


if __name__ == "__main__":
    main()

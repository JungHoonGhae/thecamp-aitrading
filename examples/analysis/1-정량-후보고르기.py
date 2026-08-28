"""정량 분석 — 숫자만 보고 후보를 고른다.

무엇을 하나:
  시가총액 상위 목록을 받아 → 내 스펙 ④ 「하지 마」에 걸리는 종목을 빼고
  → 숫자 기준 하나로 줄을 세워 → 후보를 보여준다.

왜 정량인가:
  여기서 쓰는 재료는 전부 숫자다. 시총, 등락률, 현재가.
  판단이 들어가지 않으므로 **같은 입력이면 늘 같은 답**이 나온다.
  「왜 이 종목이냐」에 답할 수 있는 유일한 층이다.

실행:  python examples/analysis/1-정량-후보고르기.py
"""
from _lab import (KISClient, blocked_by, bullet, head, load_forbidden,
                  load_portfolio, pad)

# ────────────────────────────────────────────────────────────
# 여기를 고쳐 보세요 — 이 세 줄이 이 분석의 전부입니다
# ────────────────────────────────────────────────────────────
TOP_N = 10          # 시총 상위 몇 개를 볼 것인가
많이_빠진_순 = True   # True: 오늘 많이 내린 순 / False: 많이 오른 순
최소_시총_조 = 50     # 이보다 작은 회사는 후보에서 뺀다 (조 단위)
# ────────────────────────────────────────────────────────────


def main() -> None:
    kis = KISClient()
    forbidden = load_forbidden()
    mine = {r["code"] for r in load_portfolio()}

    head("정량 분석 · 숫자로 후보 고르기",
         f"시총 상위 {TOP_N}개 → 스펙 ④ 제외 → "
         f"{'많이 빠진' if 많이_빠진_순 else '많이 오른'} 순")

    rows = kis.get_market_cap_top(TOP_N)
    후보, 제외 = [], []
    for r in rows:
        시총_조 = r["시총_억"] / 10_000
        걸린말 = blocked_by(r["name"], forbidden)
        if 걸린말:
            제외.append(f"{r['name']} — 스펙 ④ 「{걸린말}」")
        elif 시총_조 < 최소_시총_조:
            제외.append(f"{r['name']} — 시총 {시총_조:,.0f}조 (기준 {최소_시총_조}조 미만)")
        else:
            후보.append({**r, "시총_조": 시총_조})

    후보.sort(key=lambda r: r["등락률"], reverse=not 많이_빠진_순)

    print(f"  {pad('종목', 20)}{pad('시총', 12)}{pad('등락률', 11)}내 계좌")
    for r in 후보:
        보유 = "보유 중" if r["code"] in mine else "-"
        시총 = f"{r['시총_조']:,.0f}조"
        등락 = f"{r['등락률']:+.2f}%"
        print(f"  {pad(r['name'], 20)}{pad(시총, 12)}{pad(등락, 11)}{보유}")

    if 제외:
        head("후보에서 뺀 것", "내가 스펙에 적은 말이 여기서 이미 걸러 냅니다")
        for x in 제외:
            bullet(x)

    head("다음", "이 목록은 「살 종목」이 아니라 「더 볼 종목」입니다")
    bullet("숫자는 무엇을 볼지만 정합니다. 왜 담을지는 다음 두 예제에서 봅니다.")
    bullet("정성(뉴스): python examples/analysis/2-정성-뉴스브리프.py")
    bullet("시장 맥락: python examples/analysis/3-시장맥락-벤치마크.py")


if __name__ == "__main__":
    main()

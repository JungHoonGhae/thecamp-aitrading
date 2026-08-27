"""정성 분석 — 숫자로 안 잡히는 것을 모아 AI에게 넘긴다.

무엇을 하나:
  내 포트폴리오 종목의 뉴스 제목을 모아 → 한 장짜리 브리프로 정리해 → 파일로 남긴다.
  그 파일을 AI에게 주고 판단을 시킨다.

왜 코드가 판단하지 않나:
  「이 뉴스가 악재인가」는 같은 입력에도 사람마다 답이 다르다.
  코드가 점수를 매기면 그 판단이 어디서 나왔는지 아무도 설명하지 못한다.
  그래서 **모으는 일만 코드가 하고, 읽는 일은 AI와 내가** 한다.
  1주차에 배운 「AI가 못 보던 데이터를 붙인다」가 여기서 그대로 쓰인다.

실행:  python examples/analysis/2-정성-뉴스브리프.py
"""
from _lab import KISClient, ROOT, bullet, head, load_portfolio

# ────────────────────────────────────────────────────────────
# 여기를 고쳐 보세요
# ────────────────────────────────────────────────────────────
종목당_뉴스 = 3                       # 종목마다 제목 몇 개까지
브리프_파일 = ROOT / "내-뉴스-브리프.md"   # 이 파일을 AI에게 준다
# ────────────────────────────────────────────────────────────

질문 = """\
위 브리프를 읽고 세 가지만 답해 줘. 주문은 넣지 마.

1. 내 종목 중 지금 확인이 필요해 보이는 것 하나와, 그 이유가 된 제목.
2. 제목만으로는 판단할 수 없어서 더 봐야 하는 것.
3. 이 중 내-투자-스펙.md 의 ④ 「하지 마」 와 부딪히는 게 있나.

없으면 없다고 해 줘. 억지로 찾지 마. 수익은 단정하지 마."""


def main() -> None:
    kis = KISClient()
    holdings = load_portfolio()

    head("정성 분석 · 읽을 거리 모으기",
         f"내 종목 {len(holdings)}개 · 종목당 제목 {종목당_뉴스}개")

    lines = ["# 뉴스 브리프", "", "> 코드가 모으기만 했습니다. 판단은 아직 없습니다.", ""]
    빈_종목 = []
    for h in holdings:
        try:
            news = kis.get_news(h["code"])[:종목당_뉴스]
        except RuntimeError as e:
            print(f"  {h['name']}: 못 가져왔습니다 — {e}")
            continue
        if not news:
            빈_종목.append(h["name"])
            continue
        print(f"\n  {h['name']} ({h['code']})")
        lines.append(f"## {h['name']} ({h['code']})")
        for n in news:
            print(f"    · {n['title']}")
            lines.append(f"- {n['date']} · {n['source']} — {n['title']}")
        lines.append("")

    if 빈_종목:
        head("제목이 없는 종목", "연습 데이터라 일부는 비어 있습니다")
        for name in 빈_종목:
            bullet(name)

    lines += ["---", "", 질문, ""]
    브리프_파일.write_text("\n".join(lines), encoding="utf-8")

    head("다음 — 판단은 AI와 내가 합니다")
    bullet(f"브리프를 남겼습니다: {브리프_파일.name}")
    bullet("코딩 앱에 이 한 줄을 보내세요.")
    print(f"\n    {브리프_파일.name} 를 읽고 거기 적힌 세 질문에 답해 줘. 주문은 넣지 마.\n")
    bullet("AI 답이 내 생각과 다르면 그렇게 말하세요. 그게 이 단계의 목적입니다.")


if __name__ == "__main__":
    main()

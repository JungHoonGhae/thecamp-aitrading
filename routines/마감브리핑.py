"""마감 브리핑 — 장 끝난 뒤 오늘을 정리한다.

카테고리: 맞춤알림 (읽기만 합니다. 주문이 나가지 않습니다)

무엇이 오나:
  오늘 시장이 어떻게 끝났는지 · 내 계좌가 목표와 얼마나 벌어졌는지 · 오늘 나온 뉴스 제목.

아침과 무엇이 다른가:
  아침은 「오늘 무엇을 볼까」다. 마감은 「오늘 무슨 일이 있었나」다.
  같은 재료를 보지만 묻는 것이 다르다. 그래서 AI에게 던지는 질문도 다르다.

혼자 돌리기:   python routines/마감브리핑.py
정해진 시각에: hermes 에게 「마감브리핑.py 를 평일 오후 4시에 no-agent 로 실행해줘」
"""
import sys

from _routine import ROOT, 루틴, 맞춤알림

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from agent import load_portfolio, load_schedule, schedule_note  # noqa: E402
from common import judge, market  # noqa: E402
from common.kis import KISClient  # noqa: E402

# ────────────────────────────────────────────────────────────
# 지시사항 — 내 브리핑에 무엇을 담을지
# ────────────────────────────────────────────────────────────
볼_시장 = ["코스피", "원달러", "공포지수"]
종목당_뉴스 = 1
AI판단 = True        # 규칙 결과를 AI가 한 번 읽고 짚어 줍니다 (claude·codex·hermes)
# ────────────────────────────────────────────────────────────


def main() -> None:
    r = 루틴("마감 브리핑", 맞춤알림, 출처=["market", "kis", "spec"])
    kis = KISClient()
    holdings = load_portfolio()

    # 1. 시장 분위기
    r.칸("오늘 시장은 이렇게 끝났습니다")
    for 이름 in 볼_시장:
        try:
            closes = market.history(market.TICKERS[이름], "1mo")
            지금 = closes[-1] if closes else market.last(market.TICKERS[이름])
            어제 = closes[-2] if len(closes) > 1 else 지금
            변화 = (지금 / 어제 - 1) * 100 if 어제 else 0
            r.줄(f"{이름} {지금:,.2f} ({변화:+.2f}%)")
        except market.MarketError as e:
            r.줄(f"{이름} — 못 가져왔습니다: {e}")

    # 2. 내 계좌
    try:
        bal = kis.get_balance()
        held = {h["code"]: h for h in bal.get("holdings", [])}
        cash = int(bal.get("cash", 0))
        total = cash + sum(int(h.get("eval_amt", 0)) for h in held.values())
        r.칸("내 계좌")
        r.줄(f"총 자산 {total:,}원 (현금 {cash:,}원)")
        for h in holdings:
            amt = int(held.get(h["code"], {}).get("eval_amt", 0))
            share = amt / total * 100 if total else 0
            표시 = "" if abs(share - h["target"]) < 5 else "  ← 벌어짐"
            r.줄(f"{h['name']} {share:.1f}% / 목표 {h['target']:.0f}%{표시}")
    except RuntimeError as e:
        r.칸("내 계좌").줄(f"못 가져왔습니다: {e}")

    # 3. 뉴스 제목
    r.칸("오늘 나온 뉴스 제목")
    for h in holdings:
        try:
            news = kis.get_news(h["code"])[:종목당_뉴스]
        except RuntimeError:
            continue
        for n in news:
            r.줄(f"· {h['name']} — {n['title']}")

    # 4. 다음 점검일
    r.칸("다음")
    r.줄(schedule_note(load_schedule()).lstrip("※ ").strip())

    # 5. AI가 짚은 것 — 여기까지가 규칙, 여기부터가 판단
    if AI판단:
        본 = judge.ask(재료=r.본문(),
                      질문="오늘 하루를 돌아볼 때, 내일 확인해야 할 것 하나만 짚어라.")
        if 본:
            r.칸("AI가 짚은 것")
            for line in 본.splitlines():
                if line.strip():
                    r.줄(line.strip())
        elif judge.available():
            r.칸("AI가 짚은 것").줄("이번엔 답을 못 받았습니다. 규칙 결과만 보냅니다.")

    r.줄("")
    r.줄("오늘 흔들렸다면 /journal 로 한 줄 남겨 두세요. 3·4주차가 읽습니다.")
    r.보내기()


if __name__ == "__main__":
    main()

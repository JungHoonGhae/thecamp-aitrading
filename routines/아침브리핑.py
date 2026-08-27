"""아침 브리핑 — 장 열기 전에 알아야 할 것만 한 장으로.

카테고리: 맞춤알림 (읽기만 합니다. 주문이 나가지 않습니다)

무엇이 오나:
  내 계좌 · 시장 분위기 · 내 종목 뉴스 제목 · 오늘이 점검일인지.
  일일이 열어 보던 것을 한 번에 받는다.

혼자 돌리기:   python routines/아침브리핑.py
정해진 시각에: hermes 에게 「아침브리핑.py 를 평일 오전 8시에 no-agent 로 실행해줘」
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
    r = 루틴("아침 브리핑", 맞춤알림, 출처=["market", "kis", "spec"])
    kis = KISClient()
    holdings = load_portfolio()

    # 1. 시장 분위기
    r.칸("오늘 시장")
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
    r.칸("뉴스 제목")
    for h in holdings:
        try:
            news = kis.get_news(h["code"])[:종목당_뉴스]
        except RuntimeError:
            continue
        for n in news:
            r.줄(f"· {h['name']} — {n['title']}")

    # 4. 오늘 할 일
    r.칸("오늘")
    r.줄(schedule_note(load_schedule()).lstrip("※ ").strip())

    # 5. AI가 짚은 것 — 여기까지가 규칙, 여기부터가 판단
    if AI판단:
        본 = judge.ask(재료=r.본문(),
                      질문="위 브리핑에서 사람이 오늘 확인해야 할 것만 짚어라.")
        if 본:
            r.칸("AI가 짚은 것")
            for line in 본.splitlines():
                if line.strip():
                    r.줄(line.strip())
        elif judge.available():
            r.칸("AI가 짚은 것").줄("이번엔 답을 못 받았습니다. 규칙 결과만 보냅니다.")

    r.줄("")
    r.줄("판단은 사람이 합니다. 이 알림은 재료입니다.")
    r.보내기()


if __name__ == "__main__":
    main()

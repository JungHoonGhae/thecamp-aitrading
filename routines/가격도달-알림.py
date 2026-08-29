"""가격 도달 알림 — 값이 바뀐 순간에만 온다.

카테고리: 정보수집 (읽기만 합니다. 주문이 나가지 않습니다)

`가격도달-감시.py` 와 짝입니다.
  · 감시 — 지금 상태 한 줄만 찍습니다. hermes 가 그 줄을 견줍니다.
  · 알림 — 직전 상태를 스스로 기억했다가, 달라졌을 때만 보냅니다. 이 파일입니다.

왜 둘인가:
  hermes 를 쓰면 견주는 일을 대신해 줍니다(감시). 하지만 그 결과를 텔레그램으로
  보내려면 hermes 에도 봇을 넣어야 하고, 그러면 내 봇과 같은 봇을 두 곳에서
  가져가려 해서 충돌합니다. 그래서 **견주는 일도 여기서 하고, 보내는 것도 여기서** 합니다.
  hermes 는 정해진 시각에 이 파일을 깨우기만 합니다.

  같은 알림이 반복되지 않는 것이 요점입니다. 상태가 그대로면 조용합니다.

혼자 돌리기:  python routines/가격도달-알림.py
예약:        hermes cron 으로 10분마다 --no-agent 실행
"""
import sys

from _routine import ROOT, 루틴, 정보수집

sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from common import judge, market  # noqa: E402

# ────────────────────────────────────────────────────────────
# 지시사항 — 무엇을 얼마에 지켜볼 것인가
# ────────────────────────────────────────────────────────────
관심 = [
    {"이름": "삼성전자", "코드": "005930", "아래로": 250_000, "위로": 300_000},
    {"이름": "현대차", "코드": "005380", "아래로": 380_000, "위로": 450_000},
    {"이름": "코스피", "코드": "^KS11", "아래로": 6_500, "위로": 7_200},
]
AI판단 = True
기억 = ROOT / ".state" / "가격도달.txt"     # 직전 상태. 지워도 다음 실행에 다시 만들어진다
# ────────────────────────────────────────────────────────────


def 상태(값: float, 아래로: float, 위로: float) -> str:
    if 값 <= 아래로:
        return "아래로 내려옴"
    if 값 >= 위로:
        return "위로 올라감"
    return "사이"


def main() -> None:
    지금 = {}
    값들 = {}
    for w in 관심:
        try:
            v = market.last(market.to_symbol(w["코드"]))
        except market.MarketError:
            continue                       # 못 가져온 것은 아예 빼둔다. 잠깐 끊겼다고 알리지 않는다
        지금[w["이름"]] = 상태(v, w["아래로"], w["위로"])
        값들[w["이름"]] = v

    if not 지금:
        print("시세를 하나도 못 가져왔습니다. 이번엔 넘어갑니다.")
        return

    직전 = {}
    if 기억.is_file():
        for line in 기억.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                직전[k.strip()] = v.strip()

    바뀐 = {k: v for k, v in 지금.items() if 직전.get(k) != v}

    기억.parent.mkdir(exist_ok=True)
    기억.write_text("\n".join(f"{k}={v}" for k, v in sorted(지금.items())), encoding="utf-8")

    if not 직전:
        print("처음 실행입니다. 지금 상태를 기억해 두었습니다. 다음부터 바뀔 때만 알립니다.")
        return
    if not 바뀐:
        print("바뀐 것이 없습니다. 조용히 넘어갑니다.")   # 알림을 보내지 않는다
        return

    r = 루틴("가격 도달", 정보수집, 출처=["market"])
    r.칸("바뀐 것")
    for 이름, 새 in 바뀐.items():
        r.줄(f"{이름} — {직전.get(이름, '모름')} → {새} (지금 {값들[이름]:,.0f})")
    r.칸("그대로인 것")
    for 이름, v in 지금.items():
        if 이름 not in 바뀐:
            r.줄(f"{이름} — {v}")

    if AI판단:
        ai_result = judge.ask_with_status(
            재료=r.본문(), 질문="이 변화에서 사람이 확인할 것 하나만 짚어라."
        )
        if ai_result.ok:
            r.칸("AI가 짚은 것")
            for line in ai_result.text.splitlines():
                if line.strip():
                    r.줄(line.strip())
        else:
            r.칸("AI 검토 미실행").줄(ai_result.notice)

    r.보내기()


if __name__ == "__main__":
    main()

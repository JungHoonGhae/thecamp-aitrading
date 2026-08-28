---
name: portfolio-check
description: "내 투자 스펙(agent/spec)대로 계좌를 점검·제안하고, 요청 시 가드레일 통과분을 모의투자로 리밸런싱까지 실행한다. '포트폴리오 점검', '리밸런싱 확인/실행', '내 종목 점검해줘', '조정해줘' 요청 시 사용."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [portfolio, rebalancing, 점검, 리밸런싱, 포트폴리오, kis]
    related_skills: []
---

# 포트폴리오 점검·리밸런싱 (ai-trading-lab)

두 가지 모드가 있다. `REPO` 는 사용자의 저장소 절대경로다(모르면 물어본다).

**① 점검(기본)** — "점검해줘 / 내 종목 어때 / 리밸런싱 확인":

```bash
python REPO/agent/agent.py
```

미리보기만 한다(주문 없음). 무엇을 얼마나 사고팔지 "제안"까지 보여준다.

**② 리밸런싱 실행** — "리밸런싱 실행해줘 / 제안대로 조정해줘":

```bash
python REPO/agent/agent.py --execute
```

가드레일을 통과한 주문만 **모의투자**로 전송된다. 실행 전 사용자에게
"모의투자로 주문이 나갑니다"를 한 줄로 확인받는다. 가드레일 위반이 있으면
에이전트가 스스로 차단하므로 결과를 그대로 전달하면 된다.

- 이 스크립트는 `REPO/agent/spec/` 의 마크다운(목표 비중·규칙·한도)을 읽어, KIS(기본
  mock)로 현재 계좌와 비교해 "무엇을 얼마나 사고팔지"를 계산해 출력한다.
- 2주차 미국 대형주 후보는 이 스킬과 별개다. 정보만 보려면
  `python REPO/routines/참조전략-실험.py --no-send`,
  채택·로컬 모의는 `python REPO/agent/committee.py` 와
  `python REPO/agent/us_agent.py --adopt …` 를 쓴다. 주문 기본은 로컬 모의이며,
  텔레그램 `/rebalance` 는 저장된 주문 계획 해시가 같을 때만 한 번 실행한다.
- **출력 텍스트를 그대로 사용자에게 전달**한다. 별도 해석을 덧붙이려면 초보자 눈높이로
  한두 줄만 요약한다.

## 지켜야 할 선
- 주문 기본은 **모의투자** — 실전은 졸업 스위치(KIS_ENV=real + 이중 확인)를 사용자가 직접 켠 경우에만이며, 이 스킬이 대신 켜주지 않는다.
- --execute 는 사용자가 명시적으로 원할 때만. 애매하면 점검(①)으로 답한다.
- 수익을 단정하지 않는다. 예제 규칙은 학습용이다.

## 정기 실행으로 바꾸려면
사용자가 "매주 아침 자동으로 점검해서 보내줘"라고 하면 hermes 내장 cronjob 으로 예약한다.
- 점검만: **no_agent=True + `~/.hermes/scripts/portfolio-check.py`**
- 리밸런싱까지(완전체): **no_agent=True + `~/.hermes/scripts/portfolio-rebalance.py`**
  (가드레일 통과분만 모의 주문 — 예약 등록 전에 이 점을 사용자에게 한 번 확인)
둘 다 LLM 없이 스크립트만 실행한다(무료·결정적). 텔레그램 보고는 에이전트가 `.env` 의
봇으로 직접 보낸다. 스크립트가 아직
`~/.hermes/scripts/` 에 없으면 먼저 복사·경로수정하도록 안내한다. 자세한 절차는 저장소
`lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md` 참고.

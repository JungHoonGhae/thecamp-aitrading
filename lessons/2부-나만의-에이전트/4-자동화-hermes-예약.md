# 2부 · 4 — 자동화: 자는 동안 (hermes)

여기까지 오면 완성한 점검(`agent/agent.py`)을 **손 안 대고 정해진 시각에** 돌립니다.
이 강의에서 말한 **"자동화 에이전트"** 가 여기입니다. 도구 이름은 hermes-agent.

같은 실행은 `agent/agent.py` 한 줄입니다. 시작하는 방법만 두 가지입니다.

- **B. hermes (본편)** — 말로 예약·즉석 점검. 무료 Nous 로그인.
- **A. OS 예약 (폴백)** — 설치가 **20분**을 넘기면 crontab / 작업 스케줄러 / 화면.

설치가 막혀도 오늘 본편(참조 실험 → 가드레일 → 로컬 모의 승인)은 이미 끝난 상태입니다.

> 자동화는 코드를 새로 짜는 게 아닙니다. 이미 만든 걸 정해진 시각에 시작하는 것뿐입니다.
> 텔레그램은 에이전트가 `.env` 봇으로 직접 보냅니다.

---

## B. 본편 — hermes-agent

패키지는 [`hermes/`](../../hermes/README.md) 에 있습니다.

### B0. 한 번만 세우기 (무료)
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash   # mac/Linux/WSL2
hermes setup --portal    # Nous Portal 무료 로그인 (추가 카드 없음)
hermes --tui             # 채팅이 되면 성공
```

> 수업 경로는 **Nous Portal** 입니다. 이미 쓰는 Claude Code / Codex 를 hermes 에
> 다시 붙일 필요 없습니다. (Claude Pro 로는 hermes Anthropic 로그인이 안 됩니다.)

### B1. 스크립트 넣기
```bash
mkdir -p ~/.hermes/scripts
cp hermes/scripts/portfolio-check.py ~/.hermes/scripts/
# 파일을 열어 REPO 를 내 저장소 절대경로로 수정
```

### B2. 말로 예약
hermes 채팅에:
```
portfolio-check.py 를 매주 월요일 아침 8시에 no-agent 로 실행해줘.
```
- `no-agent` = 숫자는 스크립트가 계산 (공짜·매번 같음). 텔레그램은 에이전트가 보냄.
- "지금 점검해줘"는 스킬을 넣은 뒤 채팅으로도 됩니다:
  `hermes skills install ./hermes/skills/portfolio-check`

점검·보고만. hermes 가 주문을 넣게 하지 않습니다.
(`portfolio-rebalance.py` 는 `--execute` 라서, 원할 때만 · 가드레일 통과분만.)

---

## A. 폴백 — OS 예약

hermes 가 안 되면 이것만으로도 자는 동안 돌아갑니다.
봇: [`lessons/참고/telegram-봇-가이드.md`](../참고/telegram-봇-가이드.md)

**mac / Linux** — `crontab -e`:
```
0 8 * * 1 python /내/저장소/절대경로/agent/agent.py
```
`python` 이 없으면 `python3`.

**Windows** — 작업 스케줄러 → 매주 월 08:00 → `python C:\내\저장소\경로\agent\agent.py`

지금 확인: `python agent/agent.py` 한 번에 텔레그램이 오면 예약만 남은 겁니다.

## ☑️ 넘어가도 되는 신호
- hermes 채팅에서 예약이 등록됐거나, "점검해줘"에 보고가 왔다.
  (막혔으면 A로 텔레그램 한 통 + crontab 한 줄이면 통과)

> 🧭 **초록이(진행 도우미)에게** — 막혔으면 이 한 줄을 복붙하세요:
> `.agents/skills/assistant/SKILL.md 대로, 내가 지금 어느 단계에서 막혔는지 진단하고 다음 행동을 하나만 알려줘.`

---
◀ [이전: 3-재실행-리밸런싱](3-재실행-리밸런싱.md) · 다음 ▶ [**5-넓히기-루틴과-데이터**](5-넓히기-루틴과-데이터.md)

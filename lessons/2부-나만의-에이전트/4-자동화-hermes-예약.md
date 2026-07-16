# 2부 · 4 — 자동화: 정해진 시각에 (자는 동안 AI가 시장을 지켜본다)

여기까지 오면 완성한 점검(`agent/agent.py`)을 **손 안 대고 정해진 시각에 자동 실행 →
디스코드로 보고**받게 만듭니다. 이게 이 실습의 목적지입니다.

방법은 두 가지 — 편한 걸 고르세요.
- **A. OS 스케줄러** (누구나, 가장 간단) — mac/Linux `crontab`, Windows 작업 스케줄러.
- **B. 내 hermes-agent** (무료, 자연어로 관리 + 디스코드 배달) — 더 똑똑하게.

> 어느 쪽이든 **점검·보고까지만** 합니다. 실제 매수/매도 주문은 넣지 않습니다.
> 그리고 자동화는 코드를 새로 짜는 게 아니라, **이미 만든 걸 예약해 굴리는** 것뿐입니다.
> (코드 수정이 필요하면 Claude Code / Codex 로.)

---

## A. OS 스케줄러로 (가장 간단)

디스코드로 받고 싶으면 웹훅 URL을 먼저 만드세요 → `lessons/참고/discord-웹훅-가이드.md`.

**mac / Linux** — 터미널에 `crontab -e` 후 한 줄 추가(매주 월 08:00):
```
0 8 * * 1 DISCORD_WEBHOOK="웹훅URL" python /내/저장소/절대경로/agent/agent.py
```

**Windows** — "작업 스케줄러"에서 새 작업 → 트리거(매주 월 08:00) → 동작:
`python C:\내\저장소\경로\2부-나만의-에이전트\agent.py` (환경변수에 DISCORD_WEBHOOK 설정)

이게 "자는 동안 자동 실행"의 가장 단순한 형태입니다.

---

## B. 내 hermes-agent 에 주입 (무료, 자연어 관리)

hermes 는 자연어로 예약을 걸고 디스코드로 배달해줘서 편합니다. **무료**로 세울 수 있습니다.

hermes 에 넣을 것은 [`hermes/`](../../hermes/README.md) **통합 패키지 폴더에 전부** 있습니다
(hermes 홈과 같은 구조 — scripts/ 는 예약용, skills/ 는 채팅용):
- `hermes/scripts/portfolio-check.py` — 예약 실행 스크립트(크로스플랫폼 `.py`)
- `hermes/skills/portfolio-check/SKILL.md` — 채팅에서 "포트폴리오 점검해줘"로 부르는 스킬

### B0. hermes 무료로 세우기 (한 번만)
공식 원칙: **기본 채팅이 될 때까지 다른 기능을 붙이지 않는다.**
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash   # mac/Linux/WSL2
hermes setup --portal    # Nous Portal 무료 로그인 + 무료 모델 (OAuth, 과금 없음)
hermes --tui             # 기본 채팅부터 확인
```

### B1. 디스코드 연결
```bash
hermes gateway setup      # Discord 선택 → 봇 연결 (Connected Platforms: discord)
```

### B2. 스크립트를 hermes 에 넣기 (한 번만)
hermes 는 `~/.hermes/scripts/` 아래 스크립트를 실행합니다. 그리로 복사하고 경로만 바꾸세요.
```bash
mkdir -p ~/.hermes/scripts
cp hermes/scripts/portfolio-check.py ~/.hermes/scripts/
# ~/.hermes/scripts/portfolio-check.py 를 열어 REPO 를 내 저장소 절대경로로 수정
```

### B3. 예약은 hermes 에게 '말로' 시키면 됩니다 (native)
hermes 에는 예약(cron) 관리 기능이 내장돼 있어, **채팅에 자연어로 말하면 알아서 등록**합니다.
CLI 명령을 외울 필요가 없습니다. hermes 채팅에 이렇게:
```
portfolio-check.py 를 매주 월요일 아침 8시에 no-agent 로 실행해서 디스코드로 보내줘.
```
- hermes 가 스스로 예약 잡을 만들어 줍니다. "지금 예약 목록 보여줘", "이 예약 지워줘"도
  전부 말로 하면 됩니다.
- `no-agent` = LLM 없이 스크립트 출력을 그대로 디스코드로 → 무료·결정적.

> (참고) 같은 걸 CLI 로 직접 하려면:
> `hermes cron create "0 8 * * 1" --name weekly-portfolio-check --no-agent --script portfolio-check.py --deliver discord`
> 하지만 **자연어로 시키는 게 정석**입니다.

### B4. (선택) 채팅에서 즉석 점검 — 스킬 주입
정기 예약 말고, 채팅에서 "내 포트폴리오 점검해줘"로 즉석 실행하고 싶으면 스킬을 넣으세요.
```bash
hermes skills install ./hermes/skills/portfolio-check
```
이후 채팅에서 "내 포트폴리오 점검해줘"라고 하면 hermes 가 `agent/agent.py` 를 실행해 보고합니다.

## 안전
- 점검·보고까지만. hermes 가 실제 주문을 넣게 하지 않습니다.
- 무료 티어 품질·한도는 시점마다 다르니 시연/자동화 전 리허설.

## ☑️ 넘어가도 되는 신호
- 예약이 등록됐고, 정해진 시각(또는 "점검해줘" 한마디)에 **디스코드로 점검 보고**가 도착했다.

> 🧭 **초록이(진행 도우미)에게** — 막혔으면 이 한 줄을 복붙하세요:
> `.agents/skills/assistant/SKILL.md 대로, 내가 지금 어느 단계에서 막혔는지 진단하고 다음 행동을 하나만 알려줘.`

---
◀ [이전: 3-재실행-리밸런싱](3-재실행-리밸런싱.md) · 다음 ▶ [**마무리 · 신뢰 게이트**](../9-마무리/README.md)

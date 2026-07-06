# 3단계 — 정해진 시각에 자동으로 (자는 동안 AI가 시장을 지켜본다)

여기까지 오면 완성한 점검(`2-에이전트/agent.py`)을 **손 안 대고 정해진 시각에 자동 실행 →
디스코드로 보고**받게 만듭니다. 이게 이 실습의 목적지입니다.

방법은 두 가지 — 편한 걸 고르세요.
- **A. OS 스케줄러** (누구나, 가장 간단) — mac/Linux `crontab`, Windows 작업 스케줄러.
- **B. 내 hermes-agent** (무료, 자연어로 관리 + 디스코드 배달) — 더 똑똑하게.

> 어느 쪽이든 **점검·보고까지만** 합니다. 실제 매수/매도 주문은 넣지 않습니다.
> 그리고 자동화는 코드를 새로 짜는 게 아니라, **이미 만든 걸 예약해 굴리는** 것뿐입니다.
> (코드 수정이 필요하면 Claude Code / Codex 로.)

---

## A. OS 스케줄러로 (가장 간단)

디스코드로 받고 싶으면 웹훅 URL을 먼저 만드세요 → `docs/discord-웹훅-가이드.md`.

**mac / Linux** — 터미널에 `crontab -e` 후 한 줄 추가(매주 월 08:00):
```
0 8 * * 1 DISCORD_WEBHOOK="웹훅URL" python /내/저장소/절대경로/2-에이전트/agent.py
```

**Windows** — "작업 스케줄러"에서 새 작업 → 트리거(매주 월 08:00) → 동작:
`python C:\내\저장소\경로\2-에이전트\agent.py` (환경변수에 DISCORD_WEBHOOK 설정)

이게 "자는 동안 자동 실행"의 가장 단순한 형태입니다.

---

## B. 내 hermes-agent 에 주입 (무료, 자연어 관리)

hermes 는 자연어로 예약을 걸고 디스코드로 배달해줘서 편합니다. **무료**로 세울 수 있습니다.

이 폴더 구성
- `scripts/portfolio-check.py` — 예약 실행 스크립트(크로스플랫폼 `.py`)
- `skill/portfolio-check/SKILL.md` — 채팅에서 "포트폴리오 점검해줘"로 부르는 스킬

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

### B2. 자동 점검 예약 — no-agent (LLM 안 씀, 결정적)
hermes 는 `~/.hermes/scripts/` 아래 스크립트만 실행합니다. 그리로 복사하고 경로만 바꾸세요.
```bash
mkdir -p ~/.hermes/scripts
cp 3-자동화/scripts/portfolio-check.py ~/.hermes/scripts/
# ~/.hermes/scripts/portfolio-check.py 를 열어 REPO 를 내 저장소 절대경로로 수정
```
매주 월요일 아침 점검 등록(출력이 그대로 디스코드로):
```bash
hermes cron create "0 8 * * 1" \
  --name "weekly-portfolio-check" \
  --no-agent \
  --script portfolio-check.py \
  --deliver discord
```
- `"0 8 * * 1"` = 매주 월 08:00 (`"every 1d at 09:00"` 같은 자연어도 됨)
- `--no-agent` = LLM 없이 stdout 을 그대로 배달 → 무료·결정적. 확인: `hermes cron list`

### B3. (선택) 채팅으로 부르기 — 스킬 주입
```bash
hermes skills install ./3-자동화/skill/portfolio-check
```
설치되면 `~/.hermes/skills/portfolio-check/` 에 들어갑니다. 이후 채팅에서 "내 포트폴리오
점검해줘"라고 하면 hermes 가 `2-에이전트/agent.py` 를 실행해 보고합니다.

## 안전
- 점검·보고까지만. hermes 가 실제 주문을 넣게 하지 않습니다.
- 무료 티어 품질·한도는 시점마다 다르니 시연/자동화 전 리허설.

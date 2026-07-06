# 내 hermes-agent 에 주입해서 자동으로 돌리기

이 폴더의 것들을 내 hermes-agent 에 넣으면, 완성한 포트폴리오 점검(`part2/agent.py`)을
**정해진 시각에 자동 실행 → 디스코드 보고**까지 시킬 수 있다.

- **hermes 가 코드를 짜거나 고치지 않는다.** 코드 수정이 필요하면 Claude Code / Codex 로
  한다(이 저장소 실습 도구). hermes 는 "이미 완성된 걸 예약해서 굴리는" 역할만.
- **무료로 돌아간다.** hermes 는 Nous Portal 무료 로그인으로 세우고, 자동 점검은 LLM 을
  아예 안 쓰는 `no-agent` 모드로 실행한다.
- **OS 를 안 가린다.** 예약 스크립트는 `.py`(어느 OS든 Python 으로 실행)로 제공한다.

이 폴더 구성
- `scripts/portfolio-check.py` — 예약 실행용 스크립트(크로스플랫폼)
- `skill/portfolio-check/SKILL.md` — hermes 채팅에서 "포트폴리오 점검해줘"로 부르는 스킬

---

## 0. hermes 무료로 세우기 (한 번만)

공식 원칙: **기본 채팅이 될 때까지 다른 기능을 붙이지 않는다.**

```bash
# 설치 (mac/Linux/WSL2). Windows 는 WSL2 권장.
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Nous Portal 무료 로그인 + 무료 모델 설정 (OAuth, API 키·과금 없음)
hermes setup --portal

# 기본 채팅부터 확인
hermes --tui
```

## 1. 디스코드 연결

```bash
hermes gateway setup      # Discord 선택 → 봇 연결
```
상태에 `Connected Platforms: discord` 가 보이면 성공.

## 2-A. (권장) 자동 점검 예약 — no-agent, LLM 안 씀

hermes 는 `~/.hermes/scripts/` 아래 스크립트만 실행한다. 그리로 복사하고 경로만 바꾼다.

```bash
mkdir -p ~/.hermes/scripts
cp hermes/scripts/portfolio-check.py ~/.hermes/scripts/
# ~/.hermes/scripts/portfolio-check.py 를 열어 REPO 를 내 저장소 절대경로로 수정
```

그다음 매주 월요일 아침 점검을 등록한다(출력이 그대로 디스코드로 간다):

```bash
hermes cron create "0 8 * * 1" \
  --name "weekly-portfolio-check" \
  --no-agent \
  --script portfolio-check.py \
  --deliver discord
```

- `"0 8 * * 1"` = 매주 월 08:00. (`"every 1d at 09:00"` 같은 자연어도 됨)
- `--no-agent` = LLM 없이 스크립트 stdout 을 그대로 배달 → 무료·결정적.
- 확인: `hermes cron list`

## 2-B. (선택) 채팅으로 부르기 — 스킬 주입

hermes 채팅에서 "포트폴리오 점검해줘"로 바로 부르고 싶으면 스킬을 설치한다.

```bash
hermes skills install ./hermes/skill/portfolio-check
```
설치되면 `~/.hermes/skills/portfolio-check/` 에 들어간다. 이후 채팅에서
"내 포트폴리오 점검해줘"라고 하면 hermes 가 `part2/agent.py` 를 실행해 결과를 보고한다.
(이 방식은 무료 모델을 쓰지만 LLM 을 거치므로, 정기 자동화는 2-A 가 더 확실하다.)

## 굳이 hermes 없이도
자동화 없이 그냥 정해진 시각 실행만 원하면, OS 기본 스케줄러(mac/Linux `crontab`,
Windows 작업 스케줄러)로 `python part2/agent.py` 를 걸어도 된다. hermes 는 "자연어로
관리 + 디스코드 배달"이 편해서 쓰는 것.

## 안전
- 이 점검은 조회·보고까지만. hermes 가 실제 매수/매도 주문을 넣게 하지 않는다.
- 무료 티어 품질·한도는 시점마다 다르니 시연 전 리허설.

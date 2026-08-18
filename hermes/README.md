# hermes 통합 패키지

**2회차 목적지** — 말로 예약을 거는 자동화 에이전트입니다.
설치가 막히면 OS 예약(crontab)이 폴백입니다. 실행은 언제나 `agent/agent.py` 입니다.

수업 모델은 **Nous Portal** (`hermes setup --portal`, 무료 로그인)입니다.
구조는 hermes 홈(`~/.hermes/`)과 같은 모양이라, 그대로 얹으면 됩니다.

```
hermes/
├── scripts/portfolio-check.py       ← 예약용: 점검·제안 (미리보기, 주문 없음)
├── scripts/portfolio-rebalance.py   ← 예약용: 점검·제안 + 모의 리밸런싱 실행 (완전체)
└── skills/portfolio-check/          ← 채팅용: "점검해줘" / "리밸런싱 실행해줘"
```

## 설치 (한 번만)

```bash
# 1) 예약용 스크립트 복사 (둘 다)
mkdir -p ~/.hermes/scripts
cp hermes/scripts/portfolio-check.py hermes/scripts/portfolio-rebalance.py ~/.hermes/scripts/
# 복사한 두 파일을 열어 REPO 를 내 저장소 절대경로로 수정

# 2) (선택) 채팅용 스킬 설치
hermes skills install ./hermes/skills/portfolio-check
```

## 예약 걸기 — hermes 채팅에 이 한 문장

점검·제안만 (안전 기본값):
```
portfolio-check.py 를 매주 월요일 아침 8시에 no-agent 로 실행해줘.
```

제안 + 모의 리밸런싱까지 (완전체 — 가드레일 통과분만 모의 주문):
```
portfolio-rebalance.py 를 매주 월요일 아침 8시에 no-agent 로 실행해줘.
```

텔레그램 보고는 에이전트가 `.env` 의 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHANNEL_ID` 로
직접 보냅니다 (3~4회차와 같은 이름).

## 내 스펙이 자동으로 반영됩니다

스크립트는 실행할 때마다 `agent/spec/` 을 새로 읽습니다.
즉 **스펙(목표 비중·규칙·가드레일)을 고치면, 예약된 실행에도 다음 회차부터
자동 반영**됩니다 — hermes 쪽은 아무것도 다시 만질 필요가 없습니다.
보고에는 **목표 vs 현재 비중 차트 이미지**가 함께 담깁니다.

> 자세한 절차는 [`../lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md`](../lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md).
> 수업 예약은 `portfolio-check.py`(점검·보고만). `portfolio-rebalance.py` 는 `--execute` 라서
> 원할 때만 · 가드레일 통과분만 모의 주문입니다.

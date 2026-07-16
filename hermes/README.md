# hermes 통합 패키지

내 hermes-agent 에 넣을 것이 **이 폴더에 전부** 들어 있습니다.
구조는 hermes 홈(`~/.hermes/`)과 같은 모양이라, 그대로 얹으면 됩니다.

```
hermes/
├── scripts/portfolio-check.py     ← 예약(cron) 실행용 스크립트
└── skills/portfolio-check/        ← 채팅에서 "포트폴리오 점검해줘"로 부르는 스킬
```

## 설치 (한 번만)

```bash
# 1) 예약용 스크립트 복사
mkdir -p ~/.hermes/scripts
cp hermes/scripts/portfolio-check.py ~/.hermes/scripts/
# 복사한 파일을 열어 REPO 를 내 저장소 절대경로로 수정

# 2) (선택) 채팅용 스킬 설치
hermes skills install ./hermes/skills/portfolio-check
```

## 예약 걸기 — hermes 채팅에 이 한 문장

```
portfolio-check.py 를 매주 월요일 아침 8시에 no-agent 로 실행해서 디스코드로 보내줘.
```

## 내 스펙이 자동으로 반영됩니다

스크립트는 실행할 때마다 `agent/spec/` 을 새로 읽습니다.
즉 **스펙(목표 비중·규칙·가드레일)을 고치면, 예약된 실행에도 다음 회차부터
자동 반영**됩니다 — hermes 쪽은 아무것도 다시 만질 필요가 없습니다.
보고에는 **목표 vs 현재 비중 차트 이미지**가 함께 담깁니다.

> 자세한 절차·안전 원칙은 [`../4-자동화-hermes-예약.md`](../lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md) 참조.
> 점검·보고까지만 합니다 — 실제 주문은 넣지 않습니다.

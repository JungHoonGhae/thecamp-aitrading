# Hermes 수업 연결

학생은 Telegram에서 요청하고 결과를 확인합니다. Hermes는 요청을 분류해 KIS, 규칙 코드,
Claude, Codex 또는 Nous에 연결합니다. AI는 분석을 설명하고, 주문 수량은 규칙 코드가
계산합니다. 모의주문은 사람이 승인한 뒤에만 실행됩니다.

```text
Telegram → Hermes → KIS·AI·규칙 코드 → Telegram 결과
                                         └→ 사람 승인 → 모의계좌
```

## 구성

```text
hermes/
├── setup_course.py                  Telegram·플러그인·명령 메뉴 연결
├── plugins/thecamp-invest/          /ts_* 공개 명령 11개
├── scripts/morning-brief.py         읽기 전용 아침 브리핑
└── skills/                           분석·설정·주문안·기록 작업
```

## 처음 연결할 때

코딩 앱에서 아래 명령을 한 번 실행합니다.

```bash
python hermes/setup_course.py --managed-telegram
```

Telegram이 열리면 사람이 `Create Bot`과 `START`를 누릅니다. 토큰과 대화 ID는 로컬 비밀
저장소에 저장되며 화면에 다시 표시하지 않습니다. 이미 연결값이 프로젝트에 있으면
`--from-project-env`를 사용합니다.

연결 결과는 Telegram에서 확인합니다.

```text
/ts_doctor
/ts_auth
/ts_help
```

- `/ts_doctor`: 필수 연결 항목이 모두 `✅`
- `/ts_auth`: `Telegram ↔ Hermes`가 `✅`, AI 작업 경로가 한 개 이상 표시
- `/ts_help`: 핵심 순서와 `/ts_*` 명령 11개가 표시

하나라도 `❌`이거나 2분 동안 답이 없으면 다음 단계로 넘어가지 않고 표시된 원인을
확인합니다.

## 자주 쓰는 흐름

```text
계좌 확인   /ts_status
분석        /ts_analyze [종목명·시장]
모의주문안  /ts_order_plan → 승인 또는 보류
```

필요할 때만 `/ts_tools`, `/ts_config`, `/ts_rule`, `/ts_memory`를 사용합니다. 강사가 수업
자료를 바꿨을 때만 `/ts_update`를 보냅니다. 업데이트는 Claude Code를 먼저 사용하고,
응답하지 않으면 Codex CLI로 넘깁니다. 학생의 `.env`, 스펙, 판단 기록, 계좌 장부는 보존합니다.

## 아침 브리핑 자동화

먼저 Telegram에서 수동 실행합니다.

```text
아침 브리핑 지금 실행해 줘.
```

시장, 내 계좌, 보유 종목의 점검 결과가 도착하면 자동화 코드는 정상입니다. 주문안은 만들지
않고 주문도 실행하지 않습니다.

그다음 예약합니다.

```text
평일 오전 8시에 아침 브리핑 보내 줘. 예약 이름과 시각도 보여 줘.
```

정상 결과에는 `수업 아침 브리핑`, `평일 오전 8시`, `morning-brief.py`, `no-agent`가
표시됩니다. 노트북이 꺼져 있으면 실행되지 않습니다.

## 안전 경계

- 예약 작업은 조회와 보고만 합니다.
- AI 작업자는 주문값을 만들거나 승인을 대신하지 않습니다.
- 주문은 `/ts_order_plan`에서 별도로 만들고 사람이 버튼으로 승인합니다.
- 수업 기본 계좌는 로컬 연습 계좌 또는 KIS 모의투자 계좌입니다. 실계좌는 수업 범위 밖입니다.

자세한 실습은
[`../lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md`](../lessons/2부-나만의-에이전트/4-자동화-hermes-예약.md)를 봅니다.

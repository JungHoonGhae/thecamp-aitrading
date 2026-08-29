---
name: thecamp-settings
description: "Telegram 버튼으로 계좌 종류와 기술적 분석 지표를 설정한다."
---

# 설정

이 명령은 Hermes가 연결된 Telegram 대화에서만 사용한다. 입력값을 요구하지 않고 설정 종류와
값을 버튼으로 고른다. 계좌와 분석 표시는 서로 영향을 주지 않는다.

1. 현재 계좌와 두 계좌의 차이를 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" settings
```

2. `아래 버튼 하나를 눌러야 다음 단계로 갑니다. 기다리는 동안 조회·주문은 실행되지
   않으며, 2분 안에 고르지 않으면 자동 종료됩니다.`라고 먼저 알린다. 이어서 반드시
   `clarify` 도구를 호출해 아래 두 설정 종류를 Telegram 버튼으로 보여 준다.

- `🏦 계좌 종류`
- `📈 기술적 분석 지표`

3. 계좌 종류를 고르면 다시 같은 2분 안내를 보여 주고 `clarify`로 아래 둘을 보여 준다.

- `✅ 수업용 계좌`
- `🏦 KIS 모의투자 계좌`

첫 번째 선택이면 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" set-account course
```

두 번째 선택이면 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" set-account kis-paper
```

4. 기술적 분석 지표를 고르면 다시 같은 2분 안내를 보여 주고 `clarify`로 아래 둘을 보여 준다.

- `기본 · 20일선·60일선`
- `5일선 추가`

첫 번째면 `set-indicator basic`, 두 번째면 `set-indicator ma5`를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" set-indicator basic
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" set-indicator ma5
```

helper가 KIS 연결 실패나 승인 대기 계획을 알리면 그 문구를 그대로 보여 주고 끝낸다. 다른
계좌로 자동 전환하거나 같은 작업을 재시도하지 않는다. 실계좌 선택지는 만들지 않는다.
분석 지표 변경은 화면 표시만 바꾸며 현재 규칙·가드레일·계좌·주문 계획을 바꾸지 않는다.

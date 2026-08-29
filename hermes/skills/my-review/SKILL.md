---
name: thecamp-review
description: "저장된 현재 규칙 또는 수업 가설의 근거·약점을 Telegram 버튼으로 골라 검토한다."
---

# 규칙 검토

이 명령은 주문값을 계산하거나 실행하지 않는다.

1. `아래 버튼 하나를 눌러야 다음 단계로 갑니다. 기다리는 동안 검토·주문은 실행되지
   않으며, 2분 안에 고르지 않으면 자동 종료됩니다.`라고 먼저 알린다. 이어서 반드시
   `clarify` 도구를 호출해 아래 두 선택지를 Telegram 버튼으로 보여 준다.

- `📌 현재 규칙`
- `🔎 가설 근거와 약점`

2. 현재 규칙을 고르면 아래를 실행하고 출력을 그대로 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" rule
```

3. 가설 근거와 약점을 고르면 아래를 실행하고 출력을 그대로 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" hypothesis-review
```

이 검토는 이미 고정된 수업 예제의 쓰임과 약점을 읽을 뿐이다. 두 번째 채택 질문을 띄우지
않고, 종목·비중·계좌·주문 계획을 바꾸지 않는다. 평소 흐름은
`/ts_status → /ts_order_plan → 승인`이라고 안내한다. 대화와 실행 결과는 Hermes 세션에 자동으로
남으며 `/ts_memory`에서 돌아볼 수 있다고 덧붙인다.

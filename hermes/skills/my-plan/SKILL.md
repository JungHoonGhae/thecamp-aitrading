---
name: thecamp-plan
description: "규칙 코드로 주문 계획을 만들고 사람이 정확한 번호를 승인할 때만 모의 체결한다."
---

# 주문 계획과 사람 승인

이 명령은 Hermes가 연결된 Telegram 대화에서만 사용한다. `/ts_config`에서 선택한 수업용
계좌 또는 KIS 모의투자 계좌를 사용하며 실계좌에는 닿지 않는다.

1. 현재 수업 저장소에서 아래를 실행하고 주문 계획을 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" plan
```

2. 출력에 `주문 계획 · 차단` 또는 `주문 계획 · 주문 없음`이 있으면 이유만 보여 주고 버튼을
   만들지 않는다.
3. 정상 계획이면 아래를 실행해 Claude ACP → Claude CLI → Codex CLI → Nous 무료 모델 순서의
   위험 검토와 사용된 경로를
   계획 아래에 보여 준다. 이 검토는 숫자를 바꾸거나 승인하지 못하며, 모두 실패해도 계속한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" review-plan
```

4. `아래 버튼 하나를 눌러야 다음 단계로 갑니다. 기다리는 동안 주문은 실행되지 않으며,
   2분 안에 고르지 않으면 자동 보류됩니다.`라고 먼저 알린다. 이어서 반드시 `clarify`
   도구를 호출해 아래 두 선택지를 Telegram 버튼으로 보여 준다.

- `✅ 이 계획 승인`
- `🟡 보류`

5. clarify 결과가 정확히 `✅ 이 계획 승인`일 때만 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" plan --approve-latest
```

6. 보류나 그 밖의 응답이면 아래를 실행해 계획을 닫는다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" plan --cancel-latest
```

내부 계획 번호를 사용자에게 보여 주거나 복사시키지 않는다. 다른 대화·다른 사용자·15분이
지난 계획, 이미 실행된 계획, 바뀐 계좌·잔고·시세·규칙, 가드레일 위반은 helper가 차단하며
그 오류를 그대로 알린다. 화면의 순서는 `규칙 계산 → AI 위험 검토 → 사람 승인 → 규칙 실행`이다.
Claude·Codex·무료 모델은 읽고 설명할 뿐이며 주문값 변경과 API 실행 권한이 없다. 수업용
계좌는 로컬에서 체결하고, KIS 모의투자 계좌는 KIS 국내주식 모의 서버에 주문한다. 둘은 서로
대체하거나 자산을 섞지 않으며 실계좌 주문은 하지 않는다.

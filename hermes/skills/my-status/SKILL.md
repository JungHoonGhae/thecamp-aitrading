---
name: thecamp-status
description: "선택한 계좌의 잔고·보유 주식·대기 주문을 한 번에 확인하는 이전 연결용 스킬이다."
---

# 상태 확인 — 이전 연결 호환용

공개 `/ts_status` 명령은 플러그인이 아래 결정적 helper를 직접 호출한다. AI 모델이나
`clarify` 버튼을 사용하지 않는다. 이전에 저장된 내부 호출이 이 스킬에 도착한 경우에도
질문하지 말고 아래 명령을 한 번만 실행한 뒤 출력을 그대로 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" status
```

계좌 변경은 `/ts_config`에서 한다.

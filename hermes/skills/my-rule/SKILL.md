---
name: thecamp-rule
description: "처음 한 번 채택해 저장한 현재 수업 규칙을 보여 준다."
---

# 현재 규칙

현재 수업 저장소에서 아래를 실행하고 출력을 그대로 전달한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" rule
```

새 가설이나 종목 메뉴를 만들지 않는다. 저장된 규칙이 없다는 결과면 `/ts_rule`에서 가설
근거 검토를 선택하라고 안내한다.

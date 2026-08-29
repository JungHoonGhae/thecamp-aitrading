---
name: thecamp-log
description: "산·판·안 움직인 이유를 학생 말 그대로 투자 판단 기록에 남긴다."
---

# 판단 기록

`/ts_log` 뒤의 사용자 문장을 그대로 기록한다. 문장이 없으면 이유 하나만 물어본다. 내용을
요약하거나 투자 원칙을 지어내지 않는다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" log "USER_TEXT"
```

쉘 인용이 안전하도록 터미널 도구의 인자 배열이나 동등하게 안전한 호출 방식을 사용한다.
출력을 그대로 전달한다.

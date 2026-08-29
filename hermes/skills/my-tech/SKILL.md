---
name: thecamp-tech
description: "종목의 가격 흐름을 지수와 비교한다. AI 판단과 주문은 하지 않는다."
---

# 기술적 분석

사용자가 `/ts_analyze` 뒤에 적은 종목 이름·6자리 코드·해외 티커 하나를 대상으로 한다.

1. 종목이 없으면 하나만 물어본다.
2. 이 스킬 폴더의 상위 경로가 아니라, 현재 수업 저장소의 `agent/hermes_invest.py`를 찾는다.
3. 사용 가능한 Python 실행 파일로 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" tech TARGET
```

출력을 그대로 전달한다. 별도의 매수·매도 해석을 덧붙이지 않는다. 실행이 실패하면 오류를
숨기지 말고 시장 데이터 서버·인터넷·종목 기호 중 화면에 나온 원인을 짧게 알린다.

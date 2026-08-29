---
name: thecamp-fund
description: "공식 공시와 회사 자료를 우선해 기업의 사업·재무 질문을 정리한다."
---

# 펀더멘탈 분석

사용자가 `/ts_analyze` 뒤에 적은 회사 하나를 읽기 전용으로 조사한다. 회사가 없으면
하나만 물어본다. 회사가 있으면 반드시 아래 공통 라우터를 실행하고 그 출력을 그대로 보여
준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" fundamental "회사 또는 티커"
```

공통 라우터는 Claude ACP → Claude CLI → Codex CLI → Nous Portal의 사용 가능한 무료 모델
순서로 공식 IR·DART·SEC
조사를 시도하며, 실패한 경로와 실제 응답한 작업자를 함께 표시한다. 이 스킬이 따로 내용을
지어내거나 작업자
순서를 바꾸지 않는다. 모든 경로가 실패하면 `공식 근거 확인 불가` 상태를 그대로 보여 준다.

어느 작업자도 주문·매수·매도·목표가를 제안하지 않고 계좌와 주문 도구를 호출하지 않는다.

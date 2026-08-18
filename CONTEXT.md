# ai-trading-lab

패스트캠퍼스 강의용 실습 저장소. 학생의 투자 스펙(마크다운)을 읽어 계좌를 점검하고,
가드레일을 통과한 리밸런싱만 모의투자로 실행한 뒤 텔레그램으로 보고하는 미니 에이전트.

## Language

**스펙(Spec)**:
`agent/spec/*.md` — 학생이 마크다운으로 선언한 목표 비중·규칙·가드레일. 코드가 아니라 선언이며,
`내-투자-스펙.md` → `sync_spec.py` 를 통해 여기로 반영된다.
_Avoid_: 설정(config), 전략 파일

**가드레일(Guardrail)**:
스펙에 선언된, 위반 시 주문을 하드하게 차단하는 규칙(예: 한 종목 최대 비중). 경고(Warning)와
달리 실행을 막는다.
_Avoid_: 제약(constraint), 검증(validation)

**신뢰 게이트(Trust gate)**:
읽기 전용 → 미리보기 → 모의 자동 → 실전으로, 권한을 신뢰가 쌓인 만큼만 단계적으로 여는 이
강의의 핵심 설계 원칙. 토요 수업의 본편은 mock 연습 계좌(체결이 다음 조회에 보임)이고,
평일 전환은 `.env` 의 `KIS_MODE=live`, 실전은 졸업 스위치 두 줄이다.
_Avoid_: 안전장치(safety feature) — 신뢰 게이트는 완전한 안전을 단정하지 않는다.

**Report**:
`common/report.py` 에 정의된, 점검·리밸런싱 결과를 담는 구조화된 데이터(dataclass). `agent.py`
가 만들고, `telegram.py` 가 평문(화면) 또는 텔레그램 메시지로 렌더링만
한다. agent.py 와 렌더러 사이의 seam — 렌더러는 Report 의 필드를 읽을 뿐, agent.py 가 만든
문자열을 다시 파싱하지 않는다(2026-07-17, 이 규칙이 깨졌을 때 실제로 버그가 났다).
_Avoid_: 보고서 문자열(report string), 메시지(message) — Report 는 문자열이 아니라 타입이다.

**Hermes**:
2회차 목적지인 자동화 에이전트(`hermes-agent`). 같은 `agent/agent.py` 를 말로 예약·즉석 점검한다.
수업 로그인은 Nous Portal(`hermes setup --portal`). 막히면 OS crontab 이 폴백.
_Avoid_: 숙제용 선택 도구 — 기획·랜딩의 「자는 동안 에이전트」 약속이다.

**졸업 스위치(Graduation switch)**:
`KIS_ENV=real` + `KIS_REAL_ACK=REAL-MONEY-OK` 이중 확인으로만 열리는, 실전(실계좌) 매매
전환 스위치. 이 강의 범위 밖이며 기본은 항상 모의투자다.
_Avoid_: 실전 모드(live mode) — live 는 mock 이 아니라는 뜻일 뿐, paper/real 을 구분하지 않는다.

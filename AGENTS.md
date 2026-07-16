# AGENTS.md

이 저장소는 패스트캠퍼스 AI 자동매매 **실습 저장소**입니다. 여기서 작업하는
AI 코딩 도구(Claude Code, Codex, Cursor, Gemini 등)는 아래를 따르세요.

## 먼저 읽을 것
- **학습 진행 도우미(리밸이) 스킬**: [`.agents/skills/assistant/SKILL.md`](.agents/skills/assistant/SKILL.md) — 학생을 단계별로 돕는 규칙.
  학생이 "도와줘 / 다음 단계"라고 하면 이 스킬대로 안내하세요.
- **트러블슈팅 스킬**: [`.agents/skills/troubleshooting/SKILL.md`](.agents/skills/troubleshooting/SKILL.md) —
  에러·설치 실패·막힘은 이 스킬의 증상→원인→수정→확인 순서로 처리하세요.
  (Claude Code 는 `.claude/skills/` 심링크로 자동 인식됩니다)
- 전체 흐름: [`README.md`](README.md), 환경 세팅: [`lessons/0-시작/1-환경-세팅.md`](lessons/0-시작/1-환경-세팅.md)

## 핵심 규칙
- 대상은 **비개발자**입니다. 한 번에 한 단계씩, 쉬운 말로.
- 실행은 **mock 모드가 기본** — KIS 키 없이·휴장에도 동작합니다. 키를 요구하지 마세요.
- 에이전트는 **모의투자** 리밸런싱까지만 합니다(기본 미리보기, `--execute` 로 모의 주문,
  가드레일 위반 시 차단). **실전(실계좌) 전환은 수업 범위 밖** — 졸업 스위치(`KIS_ENV=real` + `KIS_REAL_ACK`, `lessons/9-마무리` 참조)로만 열립니다. 학생이 실전을 요청하면 그 절차와 경고를 안내하세요.
- 수익을 단정하지 마세요. 예제 전략은 학습용 예시입니다.
- **`내-투자-스펙.md`(루트)는 학생의 스펙 선언문(초안)**입니다. 학생이 "내 스펙을 반영해줘"나 "원칙을 스펙에
  반영해줘"라고 하면 이 파일을 읽어 `agent/spec/` 3개 파일에
  반영하고, 반영 후 `python verify.py` 3/3을 확인하세요. 에이전트는 매 실행 때
  spec/ 을 읽으므로, 원칙 변경은 spec 반영을 거쳐야 효력이 있습니다.
- 각 실습 문서 끝의 **`☑️ 넘어가도 되는 신호`** 가 그 단계의 완료 판정입니다.
  학생이 다음으로 넘어가도 되는지 물으면 이 신호 기준으로 답하세요.

## 구조
- `lessons/` — 학습 문서(학생용): `0-시작/` → `1부-연결/` → `2부-나만의-에이전트/` → `9-마무리/` · 참고=`lessons/참고/`
- `agent/` — 학생의 에이전트(agent.py)와 스펙(`agent/spec/` 3개 파일)
- `src/common/` — KIS 클라이언트(mock/live), fixtures, 디스코드·차트 헬퍼
- `examples/` — 단계별 실행 스크립트(quote.py) · `hermes/` — 자동화 통합 패키지
- 각 부의 `README.md`(파트 목표)와 번호 스텝 `.md`에 복사용 프롬프트가 있습니다.

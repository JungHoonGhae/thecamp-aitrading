# AGENTS.md

이 저장소는 패스트캠퍼스 AI 자동매매 **실습 저장소**입니다. 여기서 작업하는
AI 코딩 도구(Claude Code, Codex, Cursor, Gemini 등)는 아래를 따르세요.

## 먼저 읽을 것
- **환경 설치·유지 스킬**: [`.agents/skills/environment/SKILL.md`](.agents/skills/environment/SKILL.md) —
  받기·맞춤·체크리스트. 학생이 「수업 자료 업데이트 해 줘」「실습 환경 설치해 줘」라고 하면 이 스킬이 한다.
  `git pull` 을 학생에게 시키지 않는다. 맞춘 뒤에는 **🔄 / 📦 상태 카드**로만 답한다.
  카드의 📌 버전은 루트 [`VERSION`](VERSION) 과 [`CHANGELOG.md`](CHANGELOG.md) 맨 위 칸이다.
- **학습 진행 도우미(초록이) 스킬**: [`.agents/skills/assistant/SKILL.md`](.agents/skills/assistant/SKILL.md) — 학생을 단계별로 돕는 규칙.
  학생이 "도와줘 / 다음 단계"라고 하면 이 스킬대로 안내하세요.
- **스킬과 MCP**: [`.agents/skills/skill-vs-mcp/SKILL.md`](.agents/skills/skill-vs-mcp/SKILL.md) —
  「스킬과 MCP 가 뭐가 다른지 가르쳐 줘」. 찾기 숙제 전에 한 질문씩. 답은 📘 카드.
  장터는 AI가 연다. 단계 끝은 **🧃 한입**, 덩어리 끝은 **🪞 회고** (`assistant/references/digest.md`).
- **공식 도구 (평일 숙제)**: [`.agents/skills/kis-trading-mcp/SKILL.md`](.agents/skills/kis-trading-mcp/SKILL.md) —
  코딩도우미(334, 보기·주문 없음)와 트레이딩 MCP(166, Docker·호출). 섞으면 주문이 안 나갑니다.
- **트러블슈팅 스킬**: [`.agents/skills/troubleshooting/SKILL.md`](.agents/skills/troubleshooting/SKILL.md) —
  에러·설치 실패·막힘은 이 스킬의 증상→원인→수정→확인 순서로 처리하세요.
  (Claude Code 는 `.claude/skills/` **실제 폴더**를 읽습니다. Windows 에서 심링크는 깨집니다.)
- 전체 흐름: [`README.md`](README.md), 환경 세팅: [`lessons/0-시작/1-환경-세팅.md`](lessons/0-시작/1-환경-세팅.md)

## 핵심 규칙
- 대상은 **비개발자**입니다. 한 번에 한 단계씩, 쉬운 말로.
- 실행은 **mock 모드가 기본** — KIS 키 없이·휴장에도 동작합니다. 키를 요구하지 마세요.
- 에이전트는 **모의투자** 리밸런싱까지만 합니다(기본 미리보기, `--execute` 로 모의 주문,
  가드레일 위반 시 차단). **실전(실계좌) 전환은 수업 범위 밖** — 졸업 스위치(`KIS_ENV=real` + `KIS_REAL_ACK`, `lessons/9-마무리` 참조)로만 열립니다. 학생이 실전을 요청하면 그 절차와 경고를 안내하세요.
- 수익을 단정하지 마세요. 예제 전략은 학습용 예시입니다.
- **`내-투자-스펙.md`(루트)는 학생의 스펙 선언문(단일 입력)**입니다. 학생이 "내 스펙을
  반영해줘"라고 하면 손으로 옮기지 말고 **`python sync_spec.py`** 를 실행하세요
  (표 ①~④ → `agent/spec/` 3개 파일 결정적 반영). 반영 후 `python verify.py` 5/5 확인.
  에이전트는 매 실행 때 spec/ 을 읽으므로, 스펙 변경은 sync 를 거쳐야 효력이 있습니다.
- 각 실습 문서 끝의 **`☑️ 넘어가도 되는 신호`** 가 그 단계의 완료 판정입니다.
  학생이 다음으로 넘어가도 되는지 물으면 이 신호 기준으로 답하세요.

## 구조
- `lessons/` — 학습 문서(학생용): `0-시작/` → `1부-연결/` → `2부-나만의-에이전트/` → `9-마무리/` · 참고=`lessons/참고/`
- `agent/` — 학생의 에이전트(agent.py)와 스펙(`agent/spec/` 3개 파일)
- `src/common/` — KIS 클라이언트(mock/live), fixtures, 텔레그램·차트 헬퍼
- `examples/` — 단계별 실행 스크립트(quote.py) · `hermes/` — 자동화 통합 패키지
- 각 부의 `README.md`(파트 목표)와 번호 스텝 `.md`에 복사용 프롬프트가 있습니다.

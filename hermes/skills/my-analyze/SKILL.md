---
name: thecamp-analyze
description: "종목·한국·미국·세계 증시의 기본 분석을 만들고 Claude·Codex 우선 AI 최종 의견을 붙인다."
---

# 종목 분석

`/ts_analyze` 뒤의 종목 이름·6자리 코드·해외 티커 또는 시장 이름을 대상으로 한다. 값이
없으면 `종목명·티커·코스피·코스닥·한국·미국·세계 증시` 중 하나만 물어본다.

1. `아래 버튼 하나를 눌러야 다음 단계로 갑니다. 기다리는 동안 분석·주문은 실행되지
   않으며, 2분 안에 고르지 않으면 자동 종료됩니다.`라고 먼저 알린다. 이어서 반드시
   `clarify` 도구를 호출해 아래 선택지를 Telegram 버튼으로 보여 준다.

- `📈 기술적 분석`
- `🏢 펀더멘탈 분석`
- `🔎 둘 다 분석`
- `🌍 시장 분석`

2. 기술적 분석을 고르면 종목을 하나의 인자로 전달해 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" tech-review TARGET
```

이 경로는 Yahoo Finance 과거 시세로 기본 지표를 계산한 뒤 Claude ACP → Claude CLI → Codex CLI → Nous 무료 모델
순서로 최종 의견을 받는다. 실제 응답한 작업자와 실패한 경로를 함께 표시한다.

3. 펀더멘탈 분석을 고르면 같은 종목을 하나의 인자로 전달해 아래를 실행한다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" fundamental TARGET
```

이 경로는 Claude ACP → Claude CLI → Codex CLI → Nous 무료 모델 순서로 공식 IR·DART·SEC 조사와 최종 의견을 시도한다. 실제
응답한 작업자와 실패한 경로를 숨기지 않는다. 어느 경로도 주문값을 만들거나 주문 도구를
호출하지 않는다.

4. 둘 다 분석을 고르면 아래 한 명령을 실행한다. 기본 기술적 분석, 펀더멘탈 분석, 마지막 AI
   종합 의견 순서로 보여 준다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" combined TARGET
```

5. 시장 분석을 고르면 아래를 실행한다. 지원 입력은 코스피·코스닥·S&P500·나스닥·한국·미국·
   세계 증시다.

```text
python "${HERMES_SKILL_DIR}/../../../agent/hermes_invest.py" market-review TARGET
```

6. helper 출력 끝에 `MEDIA:/절대경로.png`와 `MEDIA:/절대경로.html` 줄이 있으면 두 줄을
   마지막 응답에 **한 글자도 바꾸지 말고 각각 독립된 줄로 복사**한다. Markdown 링크,
   `file://` 링크, `PNG 미리보기: 열기`, `HTML 원문: 열기`로 바꾸지 않는다. Gateway가 PNG는
   Telegram 사진으로, HTML은 Telegram 문서 파일로 직접 첨부한다. 첨부 줄을 요약하거나
   코드 블록·인용문 안에 넣지 않는다.

모든 경로에서 규칙 코드의 기본 결과는 AI 실패와 관계없이 남긴다. AI 표시는 `Claude`,
`Codex`, 실제 무료 모델 이름, 또는 `AI 최종 의견 미실행` 중 실제 결과와 정확히 맞춘다.
분석과 의견은 주문값에 연결하지 않는다.

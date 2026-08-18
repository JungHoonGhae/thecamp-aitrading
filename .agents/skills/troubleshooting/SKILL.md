---
name: troubleshooting
description: >
  ai-trading-lab 실습 중 에러·설치 실패·실행 막힘을 진단하고 고치는 자가수리 가이드.
  학생이 "에러 났어", "안 돼", "설치가 안 돼", "실행이 안 돼", "막혔어"라고 하거나
  command not found, ModuleNotFoundError, KeyError, FastMCP, .env not found,
  Authentification token fail, unexpected keyword argument, Invalid request parameters 같은
  에러 문구가 보이면 반드시 이 스킬을 사용한다. 증상의 에러 원문을 먼저 확인하고,
  아래 표의 증상→원인→수정→확인 순서로 처리한다.
---

# 트러블슈팅 (ai-trading-lab)

학생의 화면에 뜬 **에러 원문**을 먼저 받아서 아래 증상과 대조한다.
고친 뒤에는 반드시 **확인 명령**까지 돌려 "고쳐졌다"를 판정하고 다음 단계로 보낸다.
학생에게는 원인을 한 줄 쉬운 말로 설명해주면 학습 효과가 크다.

## 환경 문제

### 1. `command not found: python` / `'python'은(는) 내부 또는 외부 명령...이 아닙니다`
- **원인**: Python 미설치 또는 PATH 미등록.
- **수정**: `lessons/0-시작/1-환경-세팅.md` 의 부트스트랩 프롬프트로 환경(패키지매니저·git·Python)부터 세팅.
- **확인**: `python --version` → `Python 3.x.x` 가 나오면 성공.

### 2. `ModuleNotFoundError: No module named ...`
- **원인**: 의존성 미설치 (또는 다른 Python 환경에서 실행).
- **수정**: 저장소 루트에서 의존성 설치 후 재실행 (`lessons/0-시작/1-환경-세팅.md` 참조).
- **확인**: 같은 명령 재실행 시 에러 없이 결과 출력.

### 3. 한글 폴더 경로 오류 (`No such file or directory` 인데 경로에 한글 포함)
- **원인**: 셸이 한글·공백 경로를 잘라 읽음.
- **수정**: 경로 전체를 따옴표로 감싸 실행. 예: `python examples/quote.py`
- **확인**: 명령이 실행되고 결과가 출력됨.

### 4. live 모드 오류 (키·인증·`장 운영시간이 아닙니다` 류)
- **원인**: KIS 키 문제이거나 휴장 시간.
- **수정**: 우선 mock 으로 되돌린다 — 환경변수 `KIS_MODE` 제거(또는 `KIS_MODE=` 빈 값).
  실습 전체는 mock 만으로 완주 가능하다.
- **확인**: `python examples/quote.py 005930` 이 mock 데이터로 정상 출력.

### 4-1. live 모드에서 "KIS API 호출 실패" (`src/common/kis.py` 자체 클라이언트)
- **원인**: 십중팔구 **토큰 발급(oauth2/tokenP) 1분당 1회 제한**. 에러 보고 바로
  재실행하면 자격증명 문제로 착각하기 쉽지만 실은 rate limit이다. (KIS MCP 컨테이너와
  동일한 함정 — `lessons/참고/kis-mcp-연동-가이드.md` 참고)
- **수정**: 1분 기다렸다가 한 번만 재실행. 그래도 안 되면 `.env` 의
  `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT` 값을 확인.
- **확인**: `KIS_MODE=live python examples/quote.py 005930` 이 정상 시세로 응답.

### 4-1-b. `Get Authentification token fail!` — 연달아 실행했을 때

- **원인**: KIS 접근토큰 발급은 **앱키당 1분에 1회**. 예전엔 실행할 때마다 새로 받아서,
  `agent.py` 미리보기 → `--execute` 를 연달아 하면 두 번째가 거부됐다.
- **수정(2026-08-18 반영)**: 토큰을 저장소 루트 `.kis_token.json` 에 만료시각과 함께
  캐시해 재사용한다(파일권한 0600, gitignore, 앱키 원문 미저장). 최신 코드면 안 난다.
- **그래도 나면**: `.kis_token.json` 을 지우고 **1분 기다렸다가** 한 번만 재실행.
  앱을 재시작할 필요는 없다(메시지가 오해를 부른다).
- **확인**: 미리보기와 `--execute` 를 연달아 실행해도 둘 다 정상 응답.

### 4-2. live 모드에서 서버 응답에 `"초당 거래건수를 초과하였습니다"` (EGW00201)
- **원인**: KIS 모의투자 서버의 **초당 호출 제한**. `kis.py`가 호출 사이 대기하긴 하지만,
  잔고 조회 직후 바로 시세를 여러 종목 연속 조회하면(예: `agent.py`가 포트폴리오
  5종목을 순회) 타이밍이 빠듯해질 수 있다. 2026-07-17 실제 모의계좌로 재현·확인,
  대기시간을 0.5초 → 1.0초로 늘려 해결(커밋 반영됨).
- **수정**: 이미 코드에 반영돼 있어 최신 코드라면 보통 발생하지 않는다. 그래도 나면
  잠깐(수 초) 기다렸다가 재실행 — 토큰 문제(4-1)와 달리 1분씩 기다릴 필요는 없다.
- **확인**: `KIS_MODE=live python agent/agent.py` 가 끝까지(리밸런싱 미리보기까지) 정상 출력.

### 4-3. 텔레그램 보고가 안 온다 (`[텔레그램 전송 실패]` / 화면만 출력)
- **원인**: 봇에게 `/start` 를 안 보냈거나, `TELEGRAM_CHANNEL_ID` 가 틀렸거나, 토큰이 잘렸다.
- **수정**: `lessons/참고/telegram-봇-가이드.md` 순서대로 봇에게 `/start` → getUpdates 에서
  chat id 를 다시 복사 → `.env` 의 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHANNEL_ID` 확인.
  없어도 실습은 된다 — 보고는 화면에 나온다.
- **확인**: `python agent/agent.py` stderr 에 `[텔레그램으로 보고 전송 완료]`, 텔레그램에 같은 점검 보고.

### 4-4. MCP 도구가 안 보인다 / `kis-lab` 연결 실패 (수업 경로)

- **증상**: 등록했는데 도구 목록에 `search_api` 가 없다. 또는 서버가 바로 죽는다.
- **가장 흔한 원인**: 등록은 됐는데 **AI 도구를 안 껐다 켰다.** 실행 중인 대화 세션에는
  새로 등록한 MCP 가 안 붙는다. `claude mcp list` 에 `✔ Connected` 인데 도구가 안 보이면
  거의 이것이다. → AI 도구를 재시작(또는 Claude Code `/mcp` 에서 재연결).
- **그다음 원인**: 등록 명령의 경로가 **절대경로가 아니거나** 오타. 또는 `python3` 가 없음.
- **수정**:
  1. `python3 <저장소>/agent/mcp_server.py` 를 그냥 실행해 본다 — 아무 것도 안 뜨고
     입력을 기다리면 **정상**이다(Ctrl+C 로 나온다). 에러가 뜨면 그 에러가 원인.
  2. `python verify.py` 가 5/5 인지 본다. MCP 서버 점검이 거기 들어 있다.
  3. 다시 등록: `claude mcp add kis-lab -- python3 <절대경로>/agent/mcp_server.py`
     (`python3` 가 없으면 `python` 으로)
- **확인**: `claude mcp list` 에 `kis-lab ... ✔ Connected`.

---

## 아래는 수업 중엔 안 씁니다 — 수업 후 심화(Docker) 전용

> **조교/AI 안내**: 수업의 MCP 경로는 위 `kis-lab`(설치 없음) **하나**다.
> 학생이 아래 증상을 들고 오면, 공식 Trading MCP를 스스로 붙이는 중인 것이다.
> 수업 시간에는 이 트리로 들어가지 말고 `kis-lab` 으로 되돌린다.

## KIS Trading MCP 자가수리 (검증된 3가지 — 라이브러리 드리프트 대응)

학생이 공식 Trading MCP를 직접 붙이다 막히면 아래로 안내한다.
(강의 당일엔 강사가 미리 고친 이미지를 쓰므로 보통 불필요. 상세: `lessons/참고/kis-mcp-연동-가이드.md`)

### 5. 컨테이너가 뜨자마자 죽고 `FastMCP() no longer accepts stateless_http`
- **원인**: fastmcp 라이브러리 버전업으로 인자가 제거됨 (라이브러리 드리프트).
- **수정**: `server.py` 의 `FastMCP(...)` 에서 `stateless_http=False,` 한 줄 삭제
  (+`fastmcp` 버전 핀 고정).
- **확인**: 컨테이너 재기동 후 `docker ps` 에서 Up 상태 유지, 로그에 서버 리슨 메시지.

### 6. `.env.<ENV> not found`
- **원인**: `ENV` 값에 해당하는 `.env` 파일이 없음.
- **수정**: `.env.live` 에 `MCP_TYPE=sse / MCP_HOST=0.0.0.0 / MCP_PORT=3000 / MCP_PATH=/sse`
  를 두고 그 이름을 `ENV` 로 지정.
- **확인**: 컨테이너가 에러 없이 기동.

### 7. 호출 시 `KeyError: 'my_acct'`
- **원인**: `KIS_PROD_TYPE` 환경변수 누락 → 설정의 `my_prod`(계좌상품코드)가 빈 값으로
  생성돼 인증 코드가 계좌를 선택하지 못함. (계좌번호 문제처럼 보이지만 상품코드 문제)
- **수정**: 컨테이너 실행에 `-e KIS_PROD_TYPE="01"` 추가 후 재기동. 컨테이너가 설정을
  매번 재생성하므로 yaml 직접 수정보다 환경변수가 확실하다.
- **확인**: MCP 도구 호출(시세·잔고 조회 등)이 정상 응답.

### 8. `Get Authentification token fail! You have to restart your app!!!`
- **원인**: KIS 접근토큰 발급은 **앱키당 1분에 1회** 제한. 연속 재시도가 계속 실패를 만든다.
  자격증명 문제가 아니며, 앱 재시작도 필요 없다 (메시지가 오해 유발).
- **수정**: 1분 기다린 뒤 한 번만 재호출.
- **확인**: 같은 호출이 `success: true` 로 응답.

### 9. `TypeError: inquire_price() got an unexpected keyword argument 'stock_name'`
- **원인**: MCP 래퍼가 종목명→코드 변환은 해놓고 `stock_name` 인자를 실행 코드에
  그대로 넘기는 버그.
- **수정**: 시세류 API는 공식 파라미터명으로 호출 —
  `{ "env_dv": "demo", "fid_cond_mrkt_div_code": "J", "fid_input_iscd": "005930" }`.
  종목코드는 `find_stock_code` 로 먼저 변환.
- **확인**: `inquire_price` 가 `stck_prpr`(현재가) 포함 JSON 응답.

### 10. 모든 MCP 도구 호출이 즉시 `Invalid request parameters` (-32602)
- **원인**: MCP 서버(컨테이너)를 재시작해서 AI 도구 쪽 세션의 초기화 핸드셰이크가 무효화됨.
  파라미터 문제가 아니다 — 서버 로그엔 "Received request before initialization was complete".
- **수정**: AI 도구에서 MCP 재연결 — Claude Code: `/mcp` → 해당 서버 reconnect.
  Codex 등 다른 도구: 세션(도구) 재시작.
- **확인**: 아무 도구나 호출해 정상 응답.

> 이 항목들은 "AI가 깨진 도구를 스스로 진단·수리한다"는 강의 서사의 실물 예시다.
> 학생에게 원인을 설명하며 고치게 하면 학습 효과가 크다
> (당일 리스크가 크면 미리 고친 버전을 쓰게 한다).

## 여기 없는 에러라면 (에스컬레이션)

1. 에러 원문 전체를 받아 원인을 진단하되, **고치기 전에 무엇을 바꿀지 한 줄로 설명**한다.
2. 15분 넘게 막히면 붙잡지 않는다 — mock 모드로 되돌려 실습 진도를 먼저 완주하게 하고,
   막힌 지점은 에러 원문과 함께 강사에게 전달하도록 안내한다.

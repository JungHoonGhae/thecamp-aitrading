---
name: troubleshooting
description: >
  실습이 이미 깨졌을 때. "에러 났어", "안 돼", "설치가 안 돼", "실행이 안 돼",
  "막혔어", "고쳐줘", "강사에게 보여줘", "손을 들어" 또는
  command not found, ModuleNotFoundError, Permission denied, KeyError, FastMCP,
  .env not found, Authentification token fail, unexpected keyword argument,
  Invalid request parameters, TimeoutError, 초당 거래건수를 초과, UnicodeDecodeError, cp949,
  "매수가 안 돼", "주문이 미리보기에서 멈춰", "실행이 false", 글자 깨짐(紐⑥쓽二쇰Ц),
  "코딩도우미", "kis-code-assistant", "kis-trade-mcp", "docker", "WSL", "my_acct".
  "실습 환경 설치해 줘" "수업 자료 업데이트 해 줘" "맞춰 줘"처럼 아직 안 깨진 받기·맞춤은 여기가 아니다 — environment 스킬.
---

# 트러블슈팅 (ai-trading-lab)

학생의 화면에 뜬 **에러 원문**을 먼저 받아서 아래 증상과 대조한다.
표에 있으면 **수정 한 번** 하고 **확인 명령**까지 돌려 "고쳐졌다"를 판정한 뒤
다음 단계로 보낸다. 원인은 한 줄 쉬운 말로 말한다.

표에 없거나, 한 번 고쳤는데도 확인이 실패하거나, 관리자 암호·회사 보안·설치 권한처럼
학생이 혼자 열기 어려운 문제면 **수정을 더 하지 않고** 맨 아래 강사 칸을 채운다.

고치기 **전에** environment 스킬의 「매번 먼저」를 한 번 한다. 원본이 앞선 옛 코드로
씨름하지 않는다. 맞췄으면 그 스킬의 **🔄 업데이트** 카드를 먼저 보여 준다.
「스킬이 설치되지 않았다」면 ROOT 를 연 뒤 맞추고, `.agents/skills/` 아래 SKILL.md 를
파일로 읽는다. Windows 는 `python` 이다. 학생에게 `git pull` 을 치게 하지 마라.

## 환경 문제

### 0. 지금 폴더가 실습 루트가 아님 (`verify.py` 없음 / lessons 만 보임)
- **원인**: `lessons/` 나 `agent/` 안에서 명령을 돌렸거나, 복사본이 여러 개다.
- **수정**: `AGENTS.md` · `verify.py` · `lessons/` · `agent/` 가 **한 폴더**에 있는 곳으로 이동.
  GitHub 페이지를 사람에게 열라고 하지 말고, 네가 그 폴더를 연다. ZIP 본은 버리고 `git clone` 본만 쓴다.
- **확인**: 그 폴더에서 `python verify.py` 에 「실습 환경이 준비되었습니다」.

### 0-1. 「environment 스킬이 설치되지 않았다」
- **원인**: 실습 폴더를 열기 전에 붙여넣었거나, Windows 가 `.claude/skills/` 심링크를 파일로 받아 Claude 가 못 읽음.
- **수정**: `verify.py` 가 보이는 ROOT 를 연다. 학생이 「수업 자료 업데이트 해 줘」라고 한 것과 같이
  environment 스킬 「매번 먼저」대로 맞춘다. 그다음 `.agents/skills/environment/SKILL.md` 를
  파일로 읽어 그대로 한다. 앱을 한 번 끄고 연다.
- **확인**: 같은 명령을 다시 붙였을 때 스킬 내용대로 설치·확인이 시작된다.

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
- **원인**: KIS 모의투자 서버의 **초당 호출 제한**(토큰 발급 제한 4-1과 별개다).
  2026-07-17 에 호출 사이 대기를 0.5초 → 1.0초로 늘렸는데, 그 대기가 **프로세스
  안에서만** 유효해서 실제로는 안 막혔다. 수업 흐름은 `quote.py` → `agent.py` →
  `agent.py --execute` 로 매번 새 프로세스라, 직전 호출이 0.1초 전인지 알 수 없다.
  2026-08-21 장중 모의계좌에서 그대로 재현됐다.
- **수정(2026-08-21 반영)**: 마지막 호출 시각을 저장소 루트 `.kis_last_call` 에 남겨
  프로세스가 바뀌어도 간격(0.6초)을 지킨다. 한동안 안 썼으면 안 기다리므로 평소엔
  오히려 빨라졌다. 조회는 걸려도 자동으로 한 번 더 시도한다(**주문은 재시도하지
  않는다 — 중복 체결이 나므로**).
- **그래도 나면**: 잠깐(수 초) 기다렸다가 재실행 — 토큰 문제(4-1)와 달리 1분씩 기다릴
  필요는 없다. 여러 개를 동시에 돌리고 있으면 하나만 남긴다.
- **확인**: `KIS_MODE=live python agent/agent.py` 가 끝까지(리밸런싱 미리보기까지) 정상 출력.

### 4-2-b. live 인데 이미 산 종목을 **매일 또 사라고 한다** / 총자산이 실제보다 크다
- **증상**: 매수가 체결됐는데 다음 점검에서 현금이 그대로고, 방금 산 종목이 전부
  "목표 비중 미달 → 매수"로 나온다. 그대로 두면 예수금이 바닥날 때까지 계속 산다.
- **원인**: KIS 잔고 응답의 예수금 필드가 여러 개다. `dnca_tot_amt`(D+0)는 **오늘 산
  금액이 아직 안 빠져 있다.** 이 값을 쓰면 "현금 1천만원 그대로 + 주식 8백만원어치"가
  되어 총자산이 부풀려지고, 비중이 전부 목표 미달로 계산된다.
  2026-08-21 장중 모의계좌에서 실측(총자산이 18,672,500원으로 표시됨).
- **수정(2026-08-21 반영)**: `prvs_rcdl_excc_amt`(가수도정산금액 = 정산까지 반영된
  주문가능 현금)를 쓴다. 최신 코드면 안 난다.
- **확인**: `PYTHONPATH=src python3 -m common.kis` 가 "kis 자가 검사 통과". 이어서
  `KIS_MODE=live python agent/agent.py` 의 총자산이 실제 계좌 평가금액과 맞는지 본다.

### 4-2-c. `TimeoutError: The read operation timed out` / 응답이 30초 넘게 안 온다
- **원인**: KIS **모의투자 서버가 느린 것**이지 설정 문제가 아니다. 2026-08-21 장중
  실측에서 잔고 조회가 9.9~14.8초, 시세도 9.5초가 나왔다(연결·TLS는 0.03초 — 네트워크가
  아니라 서버 응답 시간이다). 예전 타임아웃이 정확히 10초여서 경계에 걸려 있었다.
- **수정(2026-08-21 반영)**: 타임아웃 30초, 그리고 초과 시 traceback 대신 안내 문구가
  나온다(예전엔 학생 화면에 raw traceback 이 떴다).
- **그래도 나면**: 잠시 뒤 같은 명령을 재실행. 급하면 mock 으로 진행한다(4번).
- **확인**: 같은 명령이 정상 응답. 오래 걸려도 실패는 아니다.

### 4-3. 텔레그램 보고가 안 온다 (`[텔레그램 전송 실패]` / 화면만 출력)
- **원인**: 봇에게 `/start` 를 안 보냈거나, `TELEGRAM_CHANNEL_ID` 가 틀렸거나, 토큰이 잘렸다.
- **수정**: `lessons/참고/telegram-봇-가이드.md` 순서대로 봇에게 `/start` → getUpdates 에서
  chat id 를 다시 복사 → `.env` 의 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHANNEL_ID` 확인.
  없어도 실습은 된다 — 보고는 화면에 나온다.
- **확인**: `python agent/agent.py` stderr 에 `[텔레그램으로 보고 전송 완료]`, 텔레그램에 같은 점검 보고.

### 4-4. MCP 도구가 안 보인다 / `kis-lecture-lab` 연결 실패 (수업 경로)

- **증상**: 등록했는데 도구 목록에 `search_api` 가 없다. 또는 서버가 바로 죽는다.
- **가장 흔한 원인**: 등록은 됐는데 **AI 도구를 안 껐다 켰다.** 실행 중인 대화 세션에는
  새로 등록한 MCP 가 안 붙는다. `claude mcp list` 에 `✔ Connected` 인데 도구가 안 보이면
  거의 이것이다. → AI 도구를 재시작(또는 Claude Code `/mcp` 에서 재연결).
- **그다음 원인**: 등록 명령의 경로가 **절대경로가 아니거나** 오타. 또는 `python3` 가 없음.
- **수정**:
  1. `python3 <저장소>/agent/mcp_server.py` 를 그냥 실행해 본다 — 아무 것도 안 뜨고
     입력을 기다리면 **정상**이다(Ctrl+C 로 나온다). 에러가 뜨면 그 에러가 원인.
  2. `python verify.py` 가 5/5 인지 본다. MCP 서버 점검이 거기 들어 있다.
  3. 다시 등록: `claude mcp add kis-lecture-lab -- python3 <절대경로>/agent/mcp_server.py`
     (`python3` 가 없으면 `python` 으로). Codex 면 `codex mcp add kis-lecture-lab -- python3 <절대경로>/agent/mcp_server.py`
- **확인**: `claude mcp list` 에 `kis-lecture-lab ... ✔ Connected`. Codex 면 `codex mcp list` 에 `kis-lecture-lab` 이 있다.

### 4-5. 코딩도우미로 샀는데 잔고가 그대로다

- **원인**: 코딩도우미 MCP(334)는 문서·샘플만 준다. **주문을 넣지 않는다.**
- **수정**: `kis-trade-mcp`(트레이딩 MCP) 로 `env_dv=demo` 주문을 다시 한다.
  붙어 있지 않으면 `.agents/skills/kis-trading-mcp/SKILL.md`.
- **확인**: 트레이딩 MCP 응답에 주문 접수/체결 칸이 있고, 잔고 조회가 따라간다.

### 4-6. Windows — 조회는 되는데 매수만 안 된다 / `UnicodeDecodeError: 'cp949'` (수업 랩)

- **증상**: 현재가·잔고는 잘 나오는데 주문만 **미리보기에서 멈춘다**(`"실행": false`).
  confirm 을 아무리 정확히 넣어도 같다. 또는 한글을 넣는 순간 MCP 서버가 죽고
  `UnicodeDecodeError: 'cp949' codec can't decode byte ...` 가 뜬다.
  `side 는 buy(매수) 또는 sell(매도) 입니다. 받은 값: '紐⑥쓽二쇰Ц'` 처럼
  **깨진 글자가 그대로 보이는** 것도 같은 원인이다.
- **원인**: 한국어 Windows 의 파이썬은 파이프를 `cp949` 로 읽는다. MCP 는 UTF-8 로 보내므로
  `"모의주문"`·`"매수"` 같은 한글 인자가 깨져서 도착한다. 숫자·영문(종목코드)뿐인 조회는
  멀쩡하고 **한글이 필요한 주문만** 막히는 이유가 이것이다.
- **수정**: 저장소를 최신으로 받는다 — `git pull`. 지금 `agent/mcp_server.py` 는 stdin/stdout 을
  UTF-8 로 못 박고, 깨져 들어온 한글도 되살린다. 받은 뒤 **AI 도구를 껐다 켠다**.
- **그래도면**: 등록 명령이 `python3` 로 돼 있는지 본다. Windows 에는 `python3` 가 없다 —
  `claude mcp add kis-lecture-lab -- python <절대경로>\agent\mcp_server.py` 로 다시 등록한다.
- **확인**: `search_api` 에 `삼성전자` 를 넣으면 `005930` 이 나온다. 이어서 주문을
  confirm 까지 넣어 부르면 `"실행": true` 와 `주문 전송 완료 되었습니다.` 가 나온다.

---

## 평일 숙제 — 공식 트레이딩 MCP · Docker

> **조교/AI 안내**: 토요일 수업 경로는 `kis-lecture-lab` **하나**다.
> 평일 숙제는 코딩도우미(334, 보기)와 트레이딩 MCP(166, 호출·주문)다.
> 코딩도우미로 주문했다고 하면 주문이 안 나간 것이다 — `kis-trade-mcp` 로 다시.
> Docker/WSL 이 15분 넘게 막히면 강사 칸. 수업 시간(토)에는 이 트리로 들어가지 말고
> `kis-lecture-lab` 으로 되돌린다.
> 상세: `.agents/skills/kis-trading-mcp/SKILL.md` · `lessons/참고/kis-mcp-연동-가이드.md`

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

## 강사에게 이 칸을 보여주세요

아래 중 **하나**면 수정을 더 하지 않는다.

- 표에 없는 에러
- 표의 수정을 한 번 했는데 확인이 실패
- 관리자 암호, 회사 보안·MDM, VPN/프록시, 설치 권한 거부
- git·Python 설치를 OS가 막음
- 고치려면 실습 폴더 밖 시스템 설정을 깊게 건드려야 함
- 학생이 강사·손을 들라고 함
- `python verify.py` 가 「실습 환경이 아직 준비되지 않았습니다」를 냄

`python verify.py` 가 이미 강사 칸을 냈으면 **그 칸을 다시 쓰지 말고** 화면에 남긴다.

그 외에는 학생에게 이 한 줄을 먼저 말한다.

> 이 칸을 강사에게 보여주세요. 손을 들어도 됩니다.

그다음 코드 블록:

```
강사에게 이 칸을 보여주세요

지금:
폴더:
컴퓨터:
증상:
이미 한 일:
추정:
부탁:
```

채우는 법:

- **지금** — 환경 세팅 / MCP / 숙제처럼 지금 단계와 돌리던 명령
- **폴더** — `verify.py` 가 있는 실습 폴더 절대경로
- **컴퓨터** — OS와 코딩 앱. `uname` 과 이 대화로 네가 채운다. 학생에게 다시 묻지 않는다
- **증상** — 에러에서 핵심 3~8줄. 긴 traceback 대신 마지막 에러 줄과 그 위 몇 줄
- **이미 한 일** — 네가 시도한 수정 한두 개
- **추정** — 원인 한 줄
- **부탁** — 강사가 지금 할 일 한 줄. live 가 막혔으면 mock 으로 오늘 진도

`KIS_APP_KEY` · `KIS_APP_SECRET` · 계좌번호 · 토큰은 칸에 쓰지 않는다. 있으면 「키는 가림」.
칸을 낸 뒤에는 다른 설치·수정을 이어서 하지 않는다.

예:

```
강사에게 이 칸을 보여주세요

지금: 환경 세팅 · python verify.py
폴더: /Users/학생/thecamp-aitrading
컴퓨터: macOS · Claude
증상: Permission denied: /usr/local/bin/python3
이미 한 일: Homebrew로 Python 설치 시도 → 권한 거부
추정: 회사 노트북이라 관리자 없이 설치가 안 됨
부탁: 관리자 암호로 Python 설치. 안 되면 오늘 mock으로 진도
```

# KIS Trading MCP 연동 가이드 (검증본)

> AI가 실제 KIS 모의투자를 조회·주문하게 하는 공식 MCP 연동법.
> **이 문서의 수정 사항은 실제로 검증됨** — 삼성전자 모의 현재가 조회 성공 확인(2026-07).
> 강의 당일엔 **강사가 미리 고쳐 빌드한 이미지**를 쓰므로, 학생은 아래를 몰라도 됩니다.
> 이 문서는 "수업 후 스스로 실제 버전을 붙일" 사람과, "왜 이렇게 고치는지" 이해할 사람용입니다.

---

## 0. 왜 Docker인가 (부담이 아니라 해결책)
공식 Trading MCP는 컨테이너로 돕니다. 학생마다 OS·파이썬·라이브러리가 제각각이어도
**컨테이너 안은 누구에게나 똑같습니다**(환경 통일). 이게 MCP를 Docker로 주는 이유입니다.

## 1. 준비물
- Docker Desktop (mac/Windows(WSL2))
- KIS **모의투자** Open API: `앱키` · `시크릿` · **모의 증권계좌 8자리**
- 공식 저장소: `koreainvestment/open-trading-api` 의 `MCP/Kis Trading MCP`

## 2. 강의용(편의) — 미리 고쳐진 이미지로
```bash
# 강사가 배포한 이미지 로드 (예: tar 배포 시)
docker load -i kis-trade-mcp.tar

# 모의 키로 실행 (실전 키 없이 모의만으로 동작)
# ⚠️ KIS_PROD_TYPE=01 이 빠지면 인증에서 KeyError: 'my_acct' 로 죽음 (아래 수정 ③)
# ⚠️ 3000번 포트를 다른 프로그램이 쓰고 있으면 -p 13000:3000 처럼 왼쪽 숫자만 바꾸면 됨
docker run -d --name kis-trade-mcp -p 3000:3000 \
  -e ENV="live" \
  -e KIS_PROD_TYPE="01" \
  -e KIS_PAPER_APP_KEY="<모의앱키>" -e KIS_PAPER_APP_SECRET="<모의시크릿>" \
  -e KIS_PAPER_STOCK="<모의계좌8자리>" \
  kis-trade-mcp
```
그다음 AI 도구에 MCP 등록(SSE) — Claude Code라면 한 줄:
```bash
claude mcp add --transport sse kis-trade http://localhost:3000/sse
```
(설정 파일 방식은 `lessons/1부-연결/mcp.example.json` 참조)

확인: AI에게 "모의투자로 삼성전자 현재가 알려줘".

> **컨테이너를 재시작했다면 AI 도구도 재연결** — 서버가 다시 뜨면 기존 MCP 세션이
> 무효화돼 모든 도구 호출이 `Invalid request parameters`(-32602)로 즉시 실패합니다.
> Claude Code에선 `/mcp` 에서 해당 서버 reconnect (또는 도구 재시작).

## 3. 실전(원본) 연동 — 직접 고쳐 붙이기
공식 원본은 현재(2026-07 기준) 최신 라이브러리와 **3곳이 어긋나** 그대로는 안 뜹니다.
아래가 **검증된 수정 3가지**입니다. (AI에게 이 파일을 주고 "이대로 고쳐줘" 해도 됩니다.)

### 수정 ①  FastMCP 버전 비호환 → 인자 제거
- **증상**: 컨테이너가 뜨자마자 죽음.
  `TypeError: FastMCP() no longer accepts stateless_http`
- **원인**: `pyproject.toml` 이 `fastmcp>=2.11.2`(상한 없음) → 최신이 깔리며 `stateless_http` 인자 제거됨
- **수정**: `server.py` 의 `FastMCP(...)` 호출에서 `stateless_http=False,` 한 줄 삭제
  (근본적으론 `fastmcp` 버전을 검증본으로 **핀 고정**하는 게 안전)

### 수정 ②  실행 환경 파일 필요
- **증상**: `Environment variable file .env.live not found`
- **원인**: 서버가 `ENV` 값에 해당하는 `.env.<ENV>` 파일에서 전송설정을 읽음
- **수정**: `.env.live`(또는 `.env.paper`)에 아래를 두고 `ENV`를 그 이름으로:
  ```
  MCP_TYPE=sse
  MCP_HOST=0.0.0.0
  MCP_PORT=3000
  MCP_PATH=/sse
  ```

### 수정 ③  `KeyError: 'my_acct'` — 계좌상품코드 누락 (핵심)
- **증상**: 도구 호출은 되는데 인증에서 `KeyError: 'my_acct'`
- **원인**: `KIS_PROD_TYPE` 환경변수를 안 주면 설정 파일의 `my_prod`(계좌상품코드)가
  빈 값으로 생성되고, 인증 코드가 계좌를 고르지 못해 `my_acct` 키가 만들어지지 않음.
  에러 문구만 보면 계좌번호 문제 같지만 실제론 상품코드 문제라 진단이 어렵다.
- **수정(검증됨)**: `docker run` 에 `-e KIS_PROD_TYPE="01"` 추가 (종합계좌 01).
  컨테이너가 설정 파일을 매번 재생성하므로, 파일을 직접 고치는 것보다 환경변수가 확실하다.
- **결과(검증)**: `env_dv=demo` 로 `inquire_price` 호출 → `success: true`, 실제 모의 시세 수신
  (예: 삼성전자 `stck_prpr` 등 정상 응답)

> 참고: 호출은 성공하지만 임시경로 로그에 `<coroutine object Context.get_state>` 문자열이
> 남는 비치명 버그가 있습니다(동작엔 영향 없음). 라이브러리 버전 드리프트의 흔적입니다.

## 3.5 붙인 뒤에 밟기 쉬운 함정 2가지 (검증됨, 2026-07)

### 함정 A  토큰 발급은 **1분당 1회** — 재시도가 오히려 독
- **증상**: `Get Authentification token fail! You have to restart your app!!!`
- **원인**: KIS 접근토큰 발급(tokenP)은 앱키당 1분 1회 제한. 실패했다고 바로 재시도하면
  계속 이 메시지만 나온다. **자격증명 문제가 아니다** (같은 키로 curl 직접 발급은 성공 확인).
- **수정**: 1분 기다렸다가 한 번만 다시 호출. 앱을 재시작할 필요 없음(메시지가 오해 유발).

### 함정 B  종목명 검색 파라미터(`stock_name`)는 시세 조회에서 깨짐
- **증상**: `TypeError: inquire_price() got an unexpected keyword argument 'stock_name'`
  (종목코드 변환까진 되고 실행에서 죽음 — MCP 래퍼의 버그)
- **수정**: 시세류 API는 공식 파라미터명으로 직접 호출:
  ```
  api_type: inquire_price
  params: { "env_dv": "demo", "fid_cond_mrkt_div_code": "J", "fid_input_iscd": "005930" }
  ```
  종목코드를 모를 땐 `find_stock_code` 로 먼저 변환한 뒤 코드만 넘긴다.

## 4. 업데이트가 계속되게 (썩지 않게)
하드 포크는 시간이 지나면 다시 깨집니다. 유지 전략:
- **핀 고정 + 얇은 패치 오버레이**: 원본을 특정 커밋으로 고정하고, 위 3가지 수정만 얹어 재현 가능하게
- **skill 자가수리**: 새로 깨지면 AI가 증상→원인→수정을 스스로 적용(`.agents/skills/assistant` 진단 가이드)
- (선택) **정기 점검 자동화**: GitHub Actions로 주기적으로 빌드·조회 테스트 → 깨지면 알림
  (tossinvest-cli 유지보수 자동화와 같은 접근)

## 5. 안전
- **모의투자만** 사용(실제 돈 아님). 실전 키는 강의에서 다루지 않음.
- 주문 도구는 조회와 분리해 다루고, 실행은 명시적으로 확인한 뒤에만.

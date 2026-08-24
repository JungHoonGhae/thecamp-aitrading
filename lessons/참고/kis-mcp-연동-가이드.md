# KIS Trading MCP 연동 가이드 (검증본)

> AI가 실제 KIS 모의투자를 조회·주문하게 하는 **공식 트레이딩 MCP** 연동법.
> **2026-08-24 갱신.** 예전에 적어 둔 「수정 3가지」는 **이제 필요 없다.**
> 공식이 2026-07-28 커밋 `b093e42` 에서 고쳤다. 없는 문제를 고치려 들지 마라.
> 먼저 공식 저장소를 최신으로 받는 것이 순서다.
> 평일 숙제 순서는 `.agents/skills/kis-trading-mcp/SKILL.md` 가 정한다. 이 문서는 설치·패치 세부다.
> 코딩도우미 MCP(문서 334개)는 여기가 아니다. 그 손으로는 주문이 안 나간다.
> 호출·주문은 Kis Trading MCP(166개, Docker)만. `env_dv=demo`. 실전(`real`)은 숙제 아님.

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
그다음 **내가 쓰는 AI 도구**에 MCP 등록(SSE). 도구별로 한 줄씩:

```bash
# Claude Code
claude mcp add --transport sse kis-trade http://localhost:3000/sse

# Codex CLI (mcp-remote 브리지로 SSE 연결)
codex mcp add kis-trade -- npx -y mcp-remote http://localhost:3000/sse
```

그 밖의 도구(Cursor, Gemini CLI 등 MCP 지원 에이전트)는 설정 파일에 아래 중 하나를 넣는다:
- SSE를 직접 지원하면: `{ "type": "sse", "url": "http://localhost:3000/sse" }`
- stdio만 지원하면(범용): `{ "command": "npx", "args": ["-y", "mcp-remote", "http://localhost:3000/sse"] }`

(설정 파일 예시: `lessons/1부-연결/mcp.example.json`)

확인: AI에게 "모의투자로 삼성전자 현재가 알려줘".

> **컨테이너를 재시작했다면 AI 도구도 재연결** — 서버가 다시 뜨면 기존 MCP 세션이
> 무효화돼 모든 도구 호출이 `Invalid request parameters`(-32602)로 즉시 실패합니다.
> Claude Code는 `/mcp` 에서 해당 서버 reconnect, Codex 등 다른 도구는 세션 재시작.

## 3. 원본으로 붙일 때 — 지금은 고칠 게 없다

예전에는 세 군데를 손봐야 했다. **지금은 아니다.** (2026-08-24 공식 소스 확인)

| 예전 수정 | 지금 |
| -- | -- |
| `server.py` 의 `stateless_http=False` 삭제 | 소스에 그 인자가 없다 |
| `.env.live` 직접 만들기 | 저장소에 **이미 들어 있다** |
| `KIS_PROD_TYPE=01` 누락 | 코드 기본값이 `"01"` 이다 (그래도 명시해 주면 확실하다) |

그러니 순서는 이것뿐이다.

```
git clone https://github.com/koreainvestment/open-trading-api.git
cd "open-trading-api/MCP/Kis Trading MCP"
docker build -t kis-trade-mcp .
```

## 3-0. ⚠️ stdio 로 붙이지 마라

공식 문서에 「대안: stdio 로컬 연동(고급)」이 있다. **쓰지 마라.**
2026-08-24 확인 결과 서버는 뜨고 도구 목록도 보이는데, **모든 API 호출이 죽는다.**

```
AttributeError: 'tuple' object has no attribute 'my_url'
```

인증 상태가 API 를 실행하는 자식 프로세스로 넘어가지 않는다. 붙은 것처럼 보여서 더 위험하다.
**Docker + SSE 만 쓴다.**

## 3-1. ⚠️ 가장 잘 막히는 곳 — 설정 파일에 한글이 남는다

**증상**: 조회를 부르면 traceback 끝에 이렇게 나온다.

```
UnicodeEncodeError: 'latin-1' codec can't encode characters in position 0-3
```

**원인**: 이 MCP 는 `~/KIS/config/kis_devlp.yaml` 을 쓴다. 없으면 공식 템플릿을 받아
환경변수로 채우는데, **템플릿에는 `"앱키"` · `"증권계좌"` 같은 한글 자리표시자가 들어 있다.**
안 채운 칸의 한글이 그대로 HTTP 헤더에 실려 나가고, 헤더는 한글을 못 실어서 거기서 죽는다.

**더 고약한 것**: 그 파일이 **이미 있으면 환경변수를 무시하고 그 파일을 쓴다.**
한 번 반쯤 채운 채로 만들어 두면 그 뒤로 계속 막힌다. (2026-08-24 실측)

**수정**: 안 쓰는 칸도 **한글을 지운다.** 실전을 안 쓰면 빈 문자열 `""` 로 둔다.
[`kis_devlp.example.yaml`](kis_devlp.example.yaml) 을 복사해 채우는 게 가장 안전하다.
AI에게 그 파일을 주고 「내 키로 채워 줘」 하면 된다.

**확인**: 같은 조회가 숫자로 응답한다.

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
- **공식을 먼저 최신으로**: 우리가 겪은 문제는 대부분 공식이 이미 고쳤다. 패치를 쌓기 전에 `git pull`
- **skill 자가수리**: 새로 깨지면 AI가 증상→원인→수정을 스스로 적용(`.agents/skills/assistant` 진단 가이드)
- (선택) **정기 점검 자동화**: GitHub Actions로 주기적으로 빌드·조회 테스트 → 깨지면 알림
  (tossinvest-cli 유지보수 자동화와 같은 접근)

## 5. 안전
- **모의투자만** 사용(실제 돈 아님). 실전 키는 강의에서 다루지 않음.
- 주문 도구는 조회와 분리해 다루고, 실행은 명시적으로 확인한 뒤에만.

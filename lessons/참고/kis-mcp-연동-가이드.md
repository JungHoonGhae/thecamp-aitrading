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
docker run -d --name kis-trade-mcp -p 3000:3000 \
  -e ENV="live" \
  -e KIS_APP_KEY="<모의앱키>" -e KIS_APP_SECRET="<모의시크릿>" \
  -e KIS_PAPER_APP_KEY="<모의앱키>" -e KIS_PAPER_APP_SECRET="<모의시크릿>" \
  -e KIS_PAPER_STOCK="<모의계좌8자리>" \
  kis-trade-mcp
```
그다음 AI 도구에 MCP 등록(SSE):
```json
{ "mcpServers": { "kis-trade-mcp": {
  "command": "npx", "args": ["-y", "mcp-remote", "http://localhost:3000/sse"] } } }
```
확인: AI에게 "모의투자로 삼성전자 현재가 알려줘".

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

### 수정 ③  모의계좌 설정 누락 (핵심)
- **증상**: 도구 호출은 되는데 인증에서 `KeyError: 'my_acct'`
- **원인**: 설정 템플릿엔 `my_acct_stock`/`my_paper_stock`만 있고, 실행 코드는 `my_acct`를 기대(스키마 불일치)
- **수정**: 생성된 `~/KIS/config/kis_devlp.yaml` 에 아래 추가/보정:
  ```
  my_acct: "<모의계좌8자리>"
  my_prod: "01"
  ```
- **결과(검증)**: `env_dv=demo` 로 `inquire_price` 호출 → `success: true`, 실제 모의 시세 수신
  (예: 삼성전자 `stck_prpr` 등 정상 응답)

> 참고: 호출은 성공하지만 임시경로 로그에 `<coroutine object Context.get_state>` 문자열이
> 남는 비치명 버그가 있습니다(동작엔 영향 없음). 라이브러리 버전 드리프트의 흔적입니다.

## 4. 업데이트가 계속되게 (썩지 않게)
하드 포크는 시간이 지나면 다시 깨집니다. 유지 전략:
- **핀 고정 + 얇은 패치 오버레이**: 원본을 특정 커밋으로 고정하고, 위 3가지 수정만 얹어 재현 가능하게
- **skill 자가수리**: 새로 깨지면 AI가 증상→원인→수정을 스스로 적용(`.agents/skills/assistant` 진단 가이드)
- (선택) **정기 점검 자동화**: GitHub Actions로 주기적으로 빌드·조회 테스트 → 깨지면 알림
  (tossinvest-cli 유지보수 자동화와 같은 접근)

## 5. 안전
- **모의투자만** 사용(실제 돈 아님). 실전 키는 강의에서 다루지 않음.
- 주문 도구는 조회와 분리해 다루고, 실행은 명시적으로 확인한 뒤에만.

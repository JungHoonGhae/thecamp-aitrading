---
name: environment
description: >
  ai-trading-lab 환경 설치·유지·경로. GitHub 주소, git clone, git pull,
  작업 루트 확인, 권한 설정, 환경설치 체크리스트(verify.py).
  학생이 "설치해줘", "저장소 받아", "업데이트", "git pull", "폴더가 어디야",
  "준비됐는지 확인해줘", "환경설치 체크리스트"라고 하면 반드시 이 스킬을 쓴다.
  GitHub 페이지를 사람에게 구경시키지 않는다. 주소는 네가 clone/pull 하는 원본이다.
---

# 환경 설치·유지 (ai-trading-lab)

GitHub 주소는 **사람이 보는 화면이 아니다.** 네가 받아오고, 고친 코드를 따라잡는 원본이다.
학생에게 브라우저에서 저장소를 열라고 하지 마라. 주소를 받으면 네가 clone 하거나 pull 한다.

원본: `https://github.com/JungHoonGhae/thecamp-aitrading`  
**ZIP 으로 받지 않는다.** 받으면 나중에 `git pull` 을 못 해서 교실 환경이 갈라진다.

## 작업 루트 (ROOT)

아래가 **한 폴더**에 보이면 그곳이 루트다.

- `AGENTS.md`
- `verify.py`
- `lessons/`
- `agent/`

`lessons/`, `agent/`, `examples/` **안에서** 명령을 돌리지 마라.
모든 명령의 작업 폴더는 ROOT 의 **절대경로**다. 상대경로로 추측하지 마라.

루트가 아니면 먼저 clone 하거나, 이미 받은 폴더를 연다.
학생에게 지금 쓰는 절대경로를 한 줄로 말해 준다.

## 단계 (확인한 뒤에만 다음)

한 번에 한 단계. 각 단계가 끝난 뒤에만 다음으로 간다.

1. **git** — 없으면 OS에 맞게 설치한다. ZIP 으로 우회하지 않는다.
2. **받기** — ROOT 가 없으면 `git clone` 한다. 공개 주소라 GitHub 계정은 필요 없다. 로그인 창이 뜨면 취소하고 HTTPS 주소로 다시 받는다. 이미 있으면 그 폴더를 연다.
3. **권한** — 학생이 이 대화에서 허락한 범위에서 네가 직접 한다. Claude 면 `~/.claude/settings.json` 의 `permissions.defaultMode: bypassPermissions` 와 `skipDangerousModePermissionPrompt: true`. Codex 면 `approval_policy = "never"`, `sandbox_mode = "workspace-write"`, `[sandbox_workspace_write] network_access = true`. 이미 맞으면 건너뛴다. 바꿨으면 앱을 한 번 끄고 켠다. 파일만 바꾸고도 매번 물으면, 그 앱의 권한 모드를 같은 뜻으로 맞춘다.
4. **확인** — ROOT 에서 `python verify.py` (없으면 `python3`). 화면 첫 줄은 `환경설치 체크리스트`.
   성공 문장은 **「실습 환경이 준비되었습니다」**.
   실패 문장은 **「실습 환경이 아직 준비되지 않았습니다」** 와 강사 칸. 그 칸을 화면에 남기고 설치를 더 밀어붙이지 않는다.
5. **유지** — 강사가 업데이트하라 하면 ROOT 에서 `git pull`, 그다음 4번을 다시 한다. 학생이 파일을 직접 고친 뒤라 충돌하면, 고친 내용을 한 줄로 물어보고 그다음에 맞춘다.
6. **학습** — 환경이 된 뒤에만 `lessons/` 순서로 보낸다. 붙여넣을 문장은 네가 지어내지 말고, 그 문서의 `📋` 블록을 **연 다음** 그대로 쓰게 한다.

Docker는 1주차 세팅에 넣지 않는다. `kis-lecture-lab` 은 Docker가 없다. 공식 트레이딩 MCP를 붙일 때만
`lessons/참고/kis-mcp-연동-가이드.md` 대로 Docker를 설치한다.

## 경로가 섞일 때

| 증상 | 원인 | 할 일 |
|---|---|---|
| `verify.py` 를 못 찾음 | lessons 나 agent 안에서 실행 | ROOT 절대경로로 이동 |
| MCP 등록이 안 됨 | `mcp_server.py` 상대경로 | `ROOT/agent/mcp_server.py` 절대경로 |
| 한글·공백 경로에서 깨짐 | 따옴표 없음 | 경로 전체를 따옴표로 |
| 어떤 폴더인지 모름 | 홈에 여러 복사본 | `AGENTS.md` 가 있는 쪽만 쓴다. 다른 복사는 닫는다 |

## 학생에게 말하는 법

전문용어 대신 이렇게 말한다.

- GitHub → "네가 받아올 원본 주소"
- clone → "노트북에 받기"
- pull → "수업 자료를 최신으로 맞추기"
- ROOT → "실습 폴더. `verify.py` 가 보이는 곳"

한 번에 한 가지만 시킨다. 브라우저로 GitHub를 구경하는 숙제를 주지 않는다.

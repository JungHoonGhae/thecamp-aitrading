"""자가 점검 — 실습이 돌아갈 준비가 됐는지 한 번에 확인하고, 안 되면 **다음 한 걸음**을 알려준다.

강사가 예제를 고친 뒤 "다 살아있나" 확인하거나, 학생이 "세팅이 됐나" 볼 때 쓴다.
실행:  python verify.py     (아무 인자 없음, 항상 mock)

실패했을 때 이 파일이 하는 일이 중요하다. 학생은 traceback 을 읽을 줄 모른다.
그래서 **원인 한 줄 + 다음 행동 한 줄**만 낸다. 두 개 이상 제안하지 않는다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MIN_PY = (3, 9)

# 자주 나오는 실패를 학생 말로 옮긴다. (증상에 들어 있는 문구, 원인, 다음 행동)
HINTS = [
    ("No module named",
     "실습 폴더 밖에서 실행했거나 파일이 빠졌습니다.",
     "저장소 폴더 안에서 다시 실행하세요. 그래도 안 되면 저장소를 다시 내려받으세요."),
    ("cp949",
     "화면 출력 인코딩 문제입니다.",
     "AI에게 이 줄을 그대로 보여주세요 — 저장소가 UTF-8로 맞추게 돼 있어 보통은 안 나옵니다."),
    ("FileNotFoundError",
     "필요한 파일을 못 찾았습니다.",
     "저장소 폴더 안에서 실행 중인지 확인하세요 (verify.py 와 lessons 폴더가 보여야 합니다)."),
    ("can't open file",
     "실습 파일 하나가 없어졌거나 이름이 바뀌었습니다.",
     "저장소를 다시 내려받으면 가장 빠릅니다. 고친 기억이 있으면 그 파일을 되돌리세요."),
    ("① ",
     "내-투자-스펙.md 표의 값이 형식에 안 맞습니다.",
     "AI에게 '내-투자-스펙.md 표를 형식에 맞게 고쳐줘' 라고 하세요."),
]


def preflight() -> list[tuple[str, str]]:
    """실행 점검 전에, 실행 자체를 막는 것부터 본다. [(원인, 다음 행동)] 를 돌려준다.

    common.* 를 import 하기 전에 돌아야 한다 — 파이썬이 낮거나 폴더가 틀리면
    import 단계에서 traceback 으로 죽어 버려서, 학생이 아무 안내도 못 받는다.
    """
    problems = []
    if sys.version_info < MIN_PY:
        cur = ".".join(map(str, sys.version_info[:3]))
        problems.append((
            f"Python 이 {cur} 인데 이 실습은 {MIN_PY[0]}.{MIN_PY[1]} 이상이 필요합니다.",
            "AI에게 'Python 3.9 이상을 설치해줘' 라고 하세요. "
            "(맥은 python3 로 실행하면 되는 경우가 많습니다)"))
    if not (ROOT / "lessons").is_dir() or not (ROOT / "agent" / "agent.py").is_file():
        problems.append((
            "실습 저장소 폴더가 아닌 곳에서 실행한 것 같습니다.",
            "verify.py 와 lessons 폴더가 함께 보이는 폴더로 이동해 다시 실행하세요."))
    return problems


def env_notes() -> list[str]:
    """치명적이진 않지만 알고 있어야 할 것. 실패로 치지 않는다."""
    notes = []
    mode = os.getenv("KIS_MODE", "")
    # 문자열 포함으로 보지 않는다. `.env.example` 은 `# KIS_MODE=live` 를 주석으로 달고 있어서
    # 그대로 복사한 학생 전원에게 헛경고가 떴다. 주석을 걸러내는 _env_values() 를 쓴다.
    env = _env_values()
    if env:
        if env.get("KIS_MODE", "").lower() == "live" and _looks_unfilled(env.get("KIS_APP_KEY", "")):
            notes.append("`.env` 가 live 인데 키가 예시 그대로입니다 — 수업 중엔 mock 으로 두세요.")
        if env.get("KIS_ENV", "").lower() == "real":
            notes.append("`.env` 에 KIS_ENV=real 이 보입니다. 실전은 수업 범위 밖입니다.")
    if mode == "live":
        notes.append("환경변수 KIS_MODE=live 로 실행 중입니다 (평일·장중에만 값이 옵니다).")
    return notes


def advise(stdout: str, stderr: str) -> tuple[str, str] | None:
    blob = f"{stdout}\n{stderr}"
    for needle, cause, action in HINTS:
        if needle in blob:
            return cause, action
    return None


def run(desc: str, args: list[str], expect: str, stdin: str | None = None) -> bool:
    try:
        # encoding 을 안 주면 윈도우에서 자식 출력을 cp949 로 디코드하려다 깨진다.
        # 이 점검은 **수업 경로(mock)가 도는가** 를 본다. 학생 `.env` 가 숙제 뒤
        # live 로 남아 있으면 키를 못 찾아 실패하는데, 그건 수업 준비와 상관없는
        # 실패다. 2주차 아침에 원인 모를 화면을 보게 된다. 그래서 여기서만 mock 을 강제한다.
        env = {**os.environ, "KIS_MODE": "mock"}
        env.pop("KIS_ENV", None)
        out = subprocess.run([sys.executable, *args], cwd=ROOT, input=stdin, env=env,
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {desc}")
        print(f"      원인: 실행 자체가 안 됐습니다 ({type(e).__name__}).")
        print("      다음: AI에게 이 줄을 그대로 보여주세요.")
        return False

    if out.returncode == 0 and expect in out.stdout:
        print(f"  ✓ {desc}")
        return True

    print(f"  ✗ {desc}")
    # 성공 줄에는 파일 이름을 안 쓴다. 실패했을 때만 어디를 볼지 알려 준다.
    print(f"      (이 단계: {' '.join(args)})")
    hint = advise(out.stdout, out.stderr)
    if hint:
        print(f"      원인: {hint[0]}")
        print(f"      다음: {hint[1]}")
    else:
        tail = (out.stderr.strip() or out.stdout.strip() or "(출력 없음)").splitlines()[-1][:160]
        print(f"      원인: 이 단계가 기대한 결과를 못 냈습니다 — {tail}")
        print("      다음: AI에게 'verify.py 가 이 단계에서 실패했어' 라며 위 줄을 그대로 보여주세요.")
    return False



# ---------------------------------------------------------------------------
# 숙제 환경 점검 (`python verify.py --숙제`)
#
# 기본 점검은 mock 다섯 개만 본다. 그건 토요일 수업 기준이다.
# 평일 숙제는 진짜 서버에 붙기 때문에 볼 것이 다르고, **깨지기 전에** 잡아야 한다.
# 여기 있는 항목은 전부 2026-08-24 에 강사가 직접 당한 것들이다.
# ---------------------------------------------------------------------------

def _env_values() -> dict:
    """저장소 .env 를 읽어 dict 로. 값은 절대 화면에 찍지 않는다."""
    f = ROOT / ".env"
    if not f.is_file():
        return {}
    out = {}
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _looks_unfilled(v: str) -> bool:
    """자리표시자가 그대로인가. 한글이 들어 있으면 십중팔구 안 채운 것이다."""
    if not v:
        return True
    return any("가" <= ch <= "힣" for ch in v)


def homework_checks() -> list[tuple[bool, str, str, str]]:
    """(통과, 항목, 원인, 다음) 목록. 통과면 원인·다음은 빈 문자열."""
    r = []
    env = _env_values()

    # 1. .env 키 세 개
    need = ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT"]
    missing = [k for k in need if _looks_unfilled(env.get(k, ""))]
    if not (ROOT / ".env").is_file():
        r.append((False, "증권사 키가 준비됨", ".env 가 아직 없습니다.",
                  "AI에게 '.env.example 을 복사해 .env 로 만들고 내 KIS 키를 넣어 줘' 라고 하세요."))
    elif missing:
        r.append((False, "증권사 키가 준비됨", f"{', '.join(missing)} 가 비었거나 안내 문구 그대로입니다.",
                  "AI에게 '.env 에 내 모의투자 앱키·시크릿·계좌 8자리를 넣어 줘' 라고 하세요."))
    else:
        r.append((True, "증권사 키가 준비됨", "", ""))

    # 2. 지금 어느 계좌를 보는가
    mode = (env.get("KIS_MODE") or "mock").lower()
    if mode == "mock":
        r.append((True, "어느 계좌를 볼지 정해짐", "", ""))
    elif mode == "live" and env.get("KIS_ENV", "paper").lower() == "real":
        r.append((False, "어느 계좌를 볼지 정해짐", "실전(real) 로 켜져 있습니다. 숙제 범위가 아닙니다.",
                  "AI에게 '.env 의 KIS_ENV 를 지워 줘' 라고 하세요. 모의투자로 돌아옵니다."))
    else:
        r.append((True, "어느 계좌를 볼지 정해짐", "", ""))

    # 3. 공식 손 설정 파일에 한글이 남았나 — 오늘 가장 오래 헤맨 곳
    cfg = Path.home() / "KIS" / "config" / "kis_devlp.yaml"
    if not cfg.is_file():
        r.append((True, "공식 도구 설정", "", ""))   # 안 쓰면 없는 게 정상이다
    else:
        body = [l for l in cfg.read_text(encoding="utf-8", errors="ignore").splitlines()
                if not l.strip().startswith("#")]
        if any("가" <= ch <= "힣" for ch in "\n".join(body)):
            r.append((False, "공식 도구 설정", "~/KIS/config/kis_devlp.yaml 에 한글이 남아 있습니다.",
                      "AI에게 'lessons/참고/kis_devlp.example.yaml 로 다시 만들어 줘' 라고 하세요. "
                      "그대로 두면 latin-1 에러로 죽습니다."))
        else:
            r.append((True, "공식 도구 설정", "", ""))

    # 4. 도커 — 공식 도구를 붙일 사람만 해당한다. 없다고 실패로 세지 않는다.
    #    "깔았는데 안 켬" 이 가장 흔한 막힘이라, 그 상태를 구분해서 알려 준다.
    docker = shutil.which("docker")
    if docker:
        try:
            ok = subprocess.run([docker, "ps"], capture_output=True, timeout=15).returncode == 0
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            r.append((False, "도커가 켜져 있음", "도커는 깔렸는데 실행이 안 되어 있습니다.",
                      "도커 데스크톱 앱을 한 번 켜 주세요. 고래 아이콘이 뜨면 됩니다. "
                      "공식 도구를 안 쓰실 거면 넘어가셔도 됩니다."))
        else:
            r.append((True, "도커가 켜져 있음", "", ""))

    # 장 시간은 항목으로 세지 않는다 — 통과·실패가 아니라 안내다. 아래에서 한 줄로 알려 준다.
    return r


def homework() -> None:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
    print("🧪 숙제 환경 점검")
    print(f"📌 버전 {ver}\n")

    rows = homework_checks()
    for ok, name, cause, action in rows:
        if ok:
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}")
            print(f"      원인: {cause}")
            print(f"      다음: {action}")

    now = datetime.now()
    if now.weekday() >= 5:
        print("\n  · 참고: 주말입니다. 증권사 서버가 쉬어서 live 는 안 됩니다. 평일 9시~15시 반에 하세요.")
    elif not (9 <= now.hour < 16):
        print("\n  · 참고: 지금은 장 시간이 아닙니다. 평일 9시~15시 반에 하세요.")

    print("\n  · 참고: 수업용 도구와 증권사 공식 도구를 동시에 쓰지 마세요.")
    print("    토큰이 1분에 한 번만 나와서 서로 막습니다. 바꿔 쓸 때는 1분 기다리세요.")

    bad = [x for x in rows if not x[0]]
    if bad:
        print(f"\n❌ 숙제 환경이 아직 준비되지 않았습니다 — {len(rows)}개 중 {len(rows)-len(bad)}개만 됩니다")
        print("위 '다음' 한 줄만 해결하고 다시 실행하세요. 나머지는 그대로 두셔도 됩니다.")
        sys.exit(1)
    print("\n✅ 숙제 환경이 준비되었습니다 — 시작하셔도 됩니다")



def main() -> None:
    # 숙제 점검은 보는 것이 다르다 — 다른 함수로 간다.
    if any(a in ("--숙제", "--homework") for a in sys.argv[1:]):
        homework()
        return
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
    print("📦 실습 환경 · 점검")
    print(f"📌 버전 {ver}")
    print("수업 환경이 되는지 하나씩 봅니다\n")

    problems = preflight()
    if problems:
        for cause, action in problems:
            print(f"  ✗ {cause}")
            print(f"      다음: {action}")
        print("\n결과: 시작 전 점검에서 멈췄습니다.")
        print("❌ 실습 환경이 아직 준비되지 않았습니다")
        print("위 '다음' 한 줄만 해결하고 다시 실행하세요.")
        sys.exit(1)

    # preflight 를 통과한 뒤에야 저장소 코드를 불러온다.
    sys.path.insert(0, str(ROOT / "src"))
    from common.kis import reset_mock_ledger  # noqa: E402

    reset_mock_ledger()
    # 항목 이름은 **학생이 할 수 있게 된 일**로 적는다. 파일 이름이나 「Part 1」 같은
    # 내부 구분은 학생에게 뜻이 안 통한다. 실패했을 때만 어느 파일인지 알려 준다.
    checks = [
        ("내가 적은 투자 원칙을 읽습니다", ["sync_spec.py", "--check"], "파싱 결과", None),
        ("종목 시세를 불러옵니다", ["examples/quote.py", "005930"], "현재가", None),
        # Part 1 MCP 서버는 stdin 으로 JSON-RPC 핸드셰이크를 넣어야 한다.
        ("AI가 스스로 시세·잔고를 찾습니다", ["agent/mcp_server.py"], '"name": "search_api"',
         '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}\n'
         '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'),
        ("내 계좌를 점검해 결과를 보여줍니다", ["agent/agent.py"], "리밸런싱 미리보기", None),
        ("연습 계좌에 주문이 들어갑니다", ["agent/agent.py", "--execute"], "주문 전송", None),
    ]
    results = [run(d, a, e, s) for d, a, e, s in checks]
    reset_mock_ledger()

    if (_env_values().get("KIS_MODE") or "mock").lower() == "live":
        print("\n  · 참고: .env 가 live 로 되어 있습니다. 위 점검은 수업용(mock)으로만 돌렸습니다.")
        print("    2주차 수업 전에 「.env 의 KIS_MODE 를 mock 으로 되돌려줘」 라고 하세요.")

    for note in env_notes():
        print(f"\n  · 참고: {note}")

    passed, total = sum(results), len(results)
    if passed == total:
        print("\n✅ 실습 환경이 준비되었습니다 — 위 다섯 가지가 모두 됩니다")
    else:
        print(f"\n❌ 실습 환경이 아직 준비되지 않았습니다 — {total}개 중 {passed}개만 됩니다")
        print("위에서 ✗ 가 뜬 첫 줄의 '다음' 하나만 해결하고 다시 실행하세요.")
        print("나머지는 건드리지 않으셔도 됩니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()

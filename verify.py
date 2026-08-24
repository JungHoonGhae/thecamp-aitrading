"""자가 점검 — 실습이 돌아갈 준비가 됐는지 한 번에 확인하고, 안 되면 **다음 한 걸음**을 알려준다.

강사가 예제를 고친 뒤 "다 살아있나" 확인하거나, 학생이 "세팅이 됐나" 볼 때 쓴다.
실행:  python verify.py     (아무 인자 없음, 항상 mock)

실패했을 때 이 파일이 하는 일이 중요하다. 학생은 traceback 을 읽을 줄 모른다.
그래서 **원인 한 줄 + 다음 행동 한 줄**만 낸다. 두 개 이상 제안하지 않는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
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
    env_file = ROOT / ".env"
    if env_file.is_file():
        text = env_file.read_text(encoding="utf-8", errors="replace")
        if "KIS_MODE=live" in text and "여기에_모의투자_앱키" in text:
            notes.append("`.env` 가 live 인데 키가 예시 그대로입니다 — 수업 중엔 mock 으로 두세요.")
        if "KIS_ENV=real" in text and not text.lstrip().startswith("#"):
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
        out = subprocess.run([sys.executable, *args], cwd=ROOT, input=stdin,
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
    hint = advise(out.stdout, out.stderr)
    if hint:
        print(f"      원인: {hint[0]}")
        print(f"      다음: {hint[1]}")
    else:
        tail = (out.stderr.strip() or out.stdout.strip() or "(출력 없음)").splitlines()[-1][:160]
        print(f"      원인: 이 단계가 기대한 결과를 못 냈습니다 — {tail}")
        print("      다음: AI에게 'verify.py 가 이 단계에서 실패했어' 라며 위 줄을 그대로 보여주세요.")
    return False


def main() -> None:
    ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
    print("📦 실습 환경 · 점검")
    print(f"📌 버전 {ver}")
    print("환경설치 체크리스트 (mock)\n")

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
    checks = [
        ("스펙 문서 파싱 (내-투자-스펙.md)", ["sync_spec.py", "--check"], "파싱 결과", None),
        ("Part 1 직접 호출 (examples/quote.py)", ["examples/quote.py", "005930"], "현재가", None),
        # Part 1 MCP 서버는 stdin 으로 JSON-RPC 핸드셰이크를 넣어야 한다.
        ("Part 1 MCP 서버 (agent/mcp_server.py)", ["agent/mcp_server.py"], '"name": "search_api"',
         '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}\n'
         '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'),
        ("Part 2 에이전트 미리보기 (agent/agent.py)", ["agent/agent.py"], "리밸런싱 미리보기", None),
        ("Part 2 에이전트 모의주문 (--execute)", ["agent/agent.py", "--execute"], "주문 전송", None),
    ]
    results = [run(d, a, e, s) for d, a, e, s in checks]
    reset_mock_ledger()

    for note in env_notes():
        print(f"\n  · 참고: {note}")

    passed, total = sum(results), len(results)
    print(f"\n결과: {passed}/{total} 통과")
    if passed == total:
        print("✅ 실습 환경이 준비되었습니다")
    else:
        print("❌ 실습 환경이 아직 준비되지 않았습니다")
        print("위에서 ✗ 가 뜬 첫 줄의 '다음' 하나만 해결하고 다시 실행하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()

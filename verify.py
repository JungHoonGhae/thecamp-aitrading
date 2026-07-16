"""자가 점검 — 모든 실습 모듈이 mock 모드로 잘 도는지 한 번에 확인한다.

강사가 예제를 고친 뒤 "다 살아있나" 확인하거나, 학생이 "세팅이 됐나" 볼 때 쓴다.
실행:  python verify.py     (아무 인자 없음, 항상 mock)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(desc: str, args: list[str], expect: str) -> bool:
    try:
        out = subprocess.run([sys.executable, *args], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ {desc}: 실행 실패 ({e})")
        return False
    ok = out.returncode == 0 and expect in out.stdout
    mark = "✓" if ok else "✗"
    print(f"  {mark} {desc}")
    if not ok:
        print(f"      exit={out.returncode}, 기대문자열='{expect}' 미포함")
        if out.stderr.strip():
            print(f"      stderr: {out.stderr.strip()[:200]}")
    return ok


def main() -> None:
    print("ai-trading-lab 자가 점검 (mock 모드)\n")
    checks = [
        ("Part 1 직접 호출 (examples/quote.py)", ["examples/quote.py", "005930"], "현재가"),
        ("Part 2 에이전트 미리보기 (agent/agent.py)", ["agent/agent.py"], "리밸런싱 미리보기"),
        ("Part 2 에이전트 모의주문 (--execute)", ["agent/agent.py", "--execute"], "주문 전송"),
    ]
    results = [run(d, a, e) for d, a, e in checks]
    passed, total = sum(results), len(results)
    print(f"\n결과: {passed}/{total} 통과")
    if passed == total:
        print("모두 정상입니다. README 순서대로 실습을 시작하세요.")
    else:
        print("일부 실패. 0-시작/1-환경-세팅.md 로 환경을 다시 확인하거나 강사/조교에게 문의하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()

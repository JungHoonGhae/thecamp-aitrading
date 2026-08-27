"""판단 층 — 규칙이 못 하는 일을 AI에게 넘긴다.

이 저장소는 두 층으로 되어 있다. 섞지 않는 것이 요점이다.

  · 규칙(코드)  — 계산하고, 견주고, 차단한다.
                  같은 입력이면 늘 같은 답. 공짜. agent.py · routines/*.py
  · 판단(AI)    — 「이게 무슨 뜻인가」, 「내가 놓친 게 있나」.
                  답이 매번 조금 다르다. 그래서 **주문에는 닿지 않는다.**

주문은 언제나 규칙이 낸다. AI는 읽고 말할 뿐이다. 이 선을 지켜라.

부르는 순서: claude → codex → hermes. 하나도 없으면 조용히 건너뛴다
(판단이 없어도 루틴은 돌아야 한다).
"""
from __future__ import annotations

import shutil
import subprocess

TIMEOUT = 180

# 앞에 있는 것부터 써 본다. 학생이 이미 쓰는 도구가 1순위다.
ENGINES = [
    ("claude", lambda prompt: ["claude", "-p", prompt]),
    ("codex", lambda prompt: ["codex", "exec", prompt]),
    ("hermes", lambda prompt: ["hermes", "-z", prompt, "--cli"]),
]

DEFAULT_RULES = """\
너는 투자 조언자가 아니다. 아래 재료를 읽고 사람이 확인할 거리만 짚는다.

지켜라.
- 사라거나 팔라고 하지 마라. 수익을 단정하지 마라.
- **재료에 없는 숫자를 지어내지 마라.** 이게 가장 중요하다.
- 한 줄을 쓸 때마다 그 근거가 재료의 어느 줄인지 끝에 대괄호로 밝혀라.
  예: 삼성전자가 목표보다 16.9%p 높다 [내 계좌]
- 재료만으로 판단이 안 되면 그렇게 적어라. 예: 판단 불가 — 재무 자료가 재료에 없음
- 짧게. 세 줄을 넘기지 마라.
- 짚을 게 없으면 「특별히 짚을 것 없음」 한 줄로 끝내라."""

# 재료가 어디서 왔는지. 알림 아래에 그대로 붙여 학생이 출처를 보게 한다.
SOURCE_NOTE = {
    "kis": "한국투자증권 모의투자 (공식)",
    "market": "야후 파이낸스 — 과거시세·지수·환율·업종 (비공식)",
    "crypto": "업비트 시세 (공식)",
    "spec": "내-투자-스펙.md (내가 적음)",
}


def sources_line(used: list[str]) -> str:
    """근거 한 줄. 어떤 데이터를 보고 한 말인지 남긴다."""
    names = [SOURCE_NOTE[k] for k in used if k in SOURCE_NOTE]
    return "근거: " + " · ".join(names) if names else ""


def available() -> str:
    """지금 쓸 수 있는 AI 도구 이름. 없으면 빈 문자열."""
    for name, _ in ENGINES:
        if shutil.which(name):
            return name
    return ""


def ask(재료: str, 질문: str, 규칙: str = DEFAULT_RULES) -> str:
    """재료를 주고 한 마디 받는다. 실패하면 빈 문자열 — 루틴은 계속 돈다."""
    prompt = f"{규칙}\n\n[질문]\n{질문}\n\n[재료]\n{재료}"
    for name, build in ENGINES:
        if not shutil.which(name):
            continue
        try:
            done = subprocess.run(build(prompt), capture_output=True,
                                  text=True, timeout=TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            continue
        out = (done.stdout or "").strip()
        if done.returncode == 0 and out:
            return out
    return ""


def demo() -> None:
    """python src/common/judge.py — 도구가 있으면 실제로 한 번 물어본다."""
    tool = available()
    if not tool:
        print("OK — 쓸 수 있는 AI 도구가 없습니다. 판단 층은 건너뜁니다(정상).")
        return
    answer = ask(재료="삼성전자 36.9% (목표 20%) · 현대차 9.8% (목표 20%)",
                 질문="비중이 목표와 벌어진 종목을 짚어라.")
    assert answer, f"{tool} 가 빈 답을 줬습니다"
    assert len(answer) < 2000, "답이 너무 깁니다"
    print(f"OK — {tool} 응답 {len(answer)}자\n{answer[:200]}")


if __name__ == "__main__":
    demo()

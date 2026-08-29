"""학생 문서 린트 — 용어 정본(CONTEXT.md)과 참조 무결성을 기계로 지킨다.

한 계산이 모든 표면을 받친다: 이 테스트가 통과하면 최종 게이트·verify·강사 점검이
같은 판정을 공유한다. 용어를 바꾸면 CONTEXT.md 와 이 목록을 함께 고칠 것.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 학생이 읽는 문서. CONTEXT.md(금지어를 _Avoid_ 로 명시)와 CHANGELOG.md(이력)는 제외.
STUDENT_DOC_GLOBS = [
    "README.md",
    "AGENTS.md",
    "내-투자-스펙.md",
    "내-투자-판단.md",
    "routines/README.md",
    "hermes/README.md",
    "lessons/**/*.md",
    ".claude/skills/**/*.md",
]

# 폐기어 → 정본 (CONTEXT.md Language 절 참조)
FORBIDDEN = {
    "12-2": "「직전 한 달을 빼고 1년 성적 상위」",
    "12–2": "「직전 한 달을 빼고 1년 성적 상위」",
    "H-12": "학생 화면 금지 (코드 내부만)",
    "롱숏": "학생 화면 금지 (덱 근거 장에서만 정의 후 사용)",
    "참조전략 실험": "참조 실험 (파일명 참조전략-실험.py 는 허용)",
    "로컬 모의계좌": "연습 계좌 / 미국 연습 계좌",
    "수업용 체결": "미국 연습 계좌 체결",
    "최근 월 상위": "직전 한 달을 빼고 1년 성적 상위",
    "python3 ": "python (맥 폴백은 스킬이 안내)",
    "창구": "인터페이스",
}

# 실재하지 않아도 되는 경로 (예시로 든 가상의 파일)
HYPOTHETICAL_PATHS: set[str] = {".state/us-guardrail-demo.json"}

PATH_RE = re.compile(r"(?<![\w/.-])((?:[\w가-힣.-]+/)+[\w가-힣.-]+\.(?:py|md|json))")


def student_docs():
    for pattern in STUDENT_DOC_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                yield path


class ForbiddenTerms(unittest.TestCase):
    def test_no_forbidden_terms(self):
        violations = []
        for path in student_docs():
            text = path.read_text(encoding="utf-8")
            for term, canonical in FORBIDDEN.items():
                for i, line in enumerate(text.splitlines(), 1):
                    if term in line:
                        violations.append(
                            f"{path.relative_to(ROOT)}:{i} 「{term}」 → {canonical}"
                        )
        self.assertEqual([], violations, "\n" + "\n".join(violations))


class ReferencedFilesExist(unittest.TestCase):
    def test_paths_in_docs_exist(self):
        missing = []
        for path in student_docs():
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                for ref in PATH_RE.findall(line):
                    if ref in HYPOTHETICAL_PATHS or "*" in ref or "ROOT/" in ref:
                        continue
                    # 문서 기준 · 저장소 루트 · 스킬 루트 셋 중 하나로 풀리면 통과
                    bases = (ROOT, path.parent, ROOT / ".claude" / "skills")
                    if not any((b / ref).exists() for b in bases):
                        missing.append(f"{path.relative_to(ROOT)}:{i} → {ref}")
        self.assertEqual([], missing, "\n" + "\n".join(missing))


class SkillsDirsIdentical(unittest.TestCase):
    def test_claude_and_agents_skills_match(self):
        claude = ROOT / ".claude" / "skills"
        agents = ROOT / ".agents" / "skills"
        c_files = {p.relative_to(claude) for p in claude.rglob("*") if p.is_file()}
        a_files = {p.relative_to(agents) for p in agents.rglob("*") if p.is_file()}
        self.assertEqual(c_files, a_files, "파일 목록이 다릅니다")
        diff = [
            str(rel)
            for rel in sorted(c_files)
            if (claude / rel).read_bytes() != (agents / rel).read_bytes()
        ]
        self.assertEqual([], diff, ".claude/skills ≠ .agents/skills: " + ", ".join(diff))


if __name__ == "__main__":
    unittest.main()

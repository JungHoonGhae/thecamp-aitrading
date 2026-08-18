"""내-투자-스펙.md 한 장 → agent/spec/ 3개 파일 자동 반영.

내-투자-스펙.md 의 표(①~④)만 고치고 이걸 실행하면:
  ① 종목·비중       → agent/spec/portfolio.md
  ② 주기 · ③ 오차   → agent/spec/rules.md
  ④ 절대 안 하는 것  → agent/spec/guardrails.md 의 "하지 마" 소절

실행:  python sync_spec.py           # 반영 + 요약 출력
       python sync_spec.py --check   # 반영하지 않고 파싱 결과만 확인

종목 이름이 목록(src/common/stocks.py)에 없으면 "이름(코드)" 형태로 적으세요.
반영 후에는 python verify.py 로 5/5 를 확인하세요.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from common.stocks import NAME_TO_CODE  # noqa: E402

SPEC_DOC = ROOT / "내-투자-스펙.md"
SPEC_DIR = ROOT / "agent" / "spec"


def _eun_neun(word: str) -> str:
    """받침이 있으면 '은', 없으면 '는'. 학생이 읽는 문장이라 '은(는)' 을 쓰지 않는다."""
    last = word.strip()[-1:]
    if not ("가" <= last <= "힣"):
        return "은(는)"          # 영문·숫자로 끝나면 판정하지 않는다
    return "은" if (ord(last) - 0xAC00) % 28 else "는"


def fail(msg: str) -> None:
    print(f"✗ {msg}")
    sys.exit(1)


def parse_table() -> dict:
    """내-투자-스펙.md 의 ①~④ 표 행에서 '내 값' 칸을 뽑는다."""
    text = SPEC_DOC.read_text(encoding="utf-8")
    values = {}
    for row in re.findall(r"^\|\s*([①②③④])\s*\|[^|]*\|([^|]*)\|", text, re.M):
        values[row[0]] = row[1].strip()
    for k in "①②③④":
        if k not in values:
            fail(f"내-투자-스펙.md 에서 {k} 행을 찾지 못했습니다. 표의 행을 지우지 말고 값만 고치세요.")
    return values


def parse_portfolio(raw: str) -> list[tuple[str, str, int]]:
    """'삼성전자 40 · 카카오(035720) 30' → [(code, name, weight), ...]"""
    items = []
    for part in re.split(r"[·,]", raw):
        part = part.strip().rstrip("%")
        if not part:
            continue
        m = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)$", part)
        if not m:
            fail(f"① 형식을 읽지 못했습니다: '{part}' — '이름 숫자' 형태로 적으세요 (예: 삼성전자 40)")
        name, weight = m.group(1).strip(), m.group(2)
        code_m = re.match(r"^(.*?)\((\d{6})\)$", name)
        if code_m:
            name, code = code_m.group(1).strip(), code_m.group(2)
        elif name in NAME_TO_CODE:
            code = NAME_TO_CODE[name]
        else:
            fail(f"① '{name}' 의 종목 코드를 모릅니다 — '이름(6자리코드) 숫자' 로 적어주세요. 예: {name}(000000) {weight}")
        items.append((code, name, round(float(weight))))
    total = sum(w for _, _, w in items)
    if abs(total - 100) > 0.5:
        fail(f"① 비중 합이 {total} 입니다 — 100 이 되게 맞춰주세요.")
    return items


def parse_tolerance(raw: str) -> int:
    m = re.search(r"(\d+(?:\.\d+)?)", raw)
    if not m:
        fail(f"③ 에서 숫자를 찾지 못했습니다: '{raw}'")
    return round(float(m.group(1)))


def main() -> None:
    check_only = "--check" in sys.argv
    v = parse_table()
    portfolio = parse_portfolio(v["①"])
    schedule = v["②"]
    tolerance = parse_tolerance(v["③"])
    forbidden = [p.strip() for p in re.split(r"[·,]", v["④"]) if p.strip()]

    print("내-투자-스펙.md 파싱 결과")
    for code, name, w in portfolio:
        print(f"  ① {name}({code}) {w}%")
    print(f"  ② 점검 주기: {schedule}")
    print(f"  ③ 허용 오차: {tolerance}%p")
    print(f"  ④ 금지: {' · '.join(forbidden)}")
    if check_only:
        print("\n(--check 모드 — 파일은 바꾸지 않았습니다)")
        return

    # ① → portfolio.md (표 전체 재생성)
    p = SPEC_DIR / "portfolio.md"
    rows = "\n".join(f"| {c} | {n} | {w} |" for c, n, w in portfolio)
    p.write_text(
        "# 내 포트폴리오 (목표)\n\n"
        "이 파일에 \"어떤 종목을 몇 % 담고 싶은지\"를 적는다.\n"
        "비중의 합은 100이 되게 한다. (종목 코드는 6자리)\n"
        "> 이 파일은 내-투자-스펙.md ① 에서 생성됩니다 — 고치려면 그쪽을 고치고 python sync_spec.py\n\n"
        "| 종목코드 | 이름 | 목표비중(%) |\n|---|---|---|\n" + rows + "\n",
        encoding="utf-8")

    # ②③ → rules.md (주기·오차 줄만 교체, 나머지 보존)
    p = SPEC_DIR / "rules.md"
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"^- \*\*리밸런싱 주기\*\*:.*$", f"- **리밸런싱 주기**: {schedule}", s, flags=re.M)
    s = re.sub(r"^- \*\*허용 오차\*\*:.*$",
               f"- **허용 오차**: 목표 비중과 {tolerance}%p 이상 벌어지면 \"조정 필요\"로 본다.", s, flags=re.M)
    p.write_text(s, encoding="utf-8")

    # ④ → guardrails.md ("하지 마" 소절 불릿만 교체, 한도·나머지 보존)
    p = SPEC_DIR / "guardrails.md"
    s = p.read_text(encoding="utf-8")
    bullets = "\n".join(f"- **{f}**{_eun_neun(f)} 하지 않는다." for f in forbidden)
    bullets += "\n- **실계좌(실전) 주문**은 하지 않는다 — 이 실습은 모의투자까지다."
    pattern = r"(## 하지 마 \(금지\)\n\n(?:>.*\n)*\n?)(?:- .*\n)+"
    s, n = re.subn(pattern, lambda m: m.group(1) + bullets + "\n", s, count=1)
    if n == 0:
        fail("guardrails.md 의 「하지 마 (금지)」 소절을 찾지 못해 ④ 를 반영하지 못했습니다. "
             "그 제목과 아래 목록을 지우지 마세요.")
    p.write_text(s, encoding="utf-8")

    print("\n✓ agent/spec/ 3개 파일에 반영 완료")
    print("다음: python verify.py 로 5/5 확인 → python agent/agent.py 로 새 스펙 점검")


if __name__ == "__main__":
    main()

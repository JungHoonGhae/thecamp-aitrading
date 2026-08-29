"""루틴 공통 — 알림을 만들고 보내는 자리.

**루틴**은 정해진 주기에 혼자 도는 작은 일이다. 결과는 **루틴 알림**으로 온다.
이 폴더의 루틴은 모두 읽고 알리는 일만 한다. 주문은 Telegram의
``/ts_order_plan``에서 사람이 요청하고 승인하는 별도 경로다.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "agent"))

from common.env import load_repo_env  # noqa: E402
from common.report import Report  # noqa: E402
from common.judge import sources_line  # noqa: E402
from common.telegram import report as send  # noqa: E402

정보수집 = "정보수집"
스크리닝 = "스크리닝"
매매제안 = "매매제안"
카테고리들 = (정보수집, 스크리닝, 매매제안)

# 뒤로 호환 — 알림 루틴의 예전 이름만 유지한다.
맞춤알림 = 정보수집


class 루틴:
    """루틴 하나. 줄을 모았다가 한 번에 알림으로 보낸다.

    사용:
        r = 루틴("아침 브리핑", 정보수집)
        r.줄("코스피 +1.2%")
        r.칸("내 종목")
        r.보내기()
    """

    def __init__(self, 이름: str, 카테고리: str = 정보수집, 차트: str | None = None,
                 출처: list[str] | None = None):
        if 카테고리 not in 카테고리들:
            raise ValueError(f"카테고리는 {' · '.join(카테고리들)} 중 하나입니다: {카테고리}")
        self.이름 = 이름
        self.카테고리 = 카테고리
        self.차트 = 차트
        self.출처 = 출처 or []          # 어떤 데이터를 보고 한 말인지. 알림 아래에 남긴다
        self.줄들: list[str] = []
        load_repo_env()

    def 줄(self, text: str = "") -> "루틴":
        self.줄들.append(text)
        return self

    def 칸(self, 제목: str) -> "루틴":
        if self.줄들:
            self.줄들.append("")
        self.줄들.append(f"— {제목} —")
        return self

    def 본문(self) -> str:
        머리 = f"[{self.카테고리}] {self.이름}"
        때 = datetime.now().strftime("%m/%d %H:%M")
        꼬리 = []
        줄 = sources_line(self.출처)
        if 줄:
            꼬리 = ["", "─" * 30, 줄]
        return "\n".join([f"{머리} · {때}", ""] + self.줄들 + 꼬리)

    def 보내기(self) -> None:
        """화면에 찍고, 텔레그램이 설정돼 있으면 그쪽으로도 보낸다."""
        if os.environ.get("THECAMP_STDOUT_ONLY") == "1":
            print(self.본문())
            return
        send(Report(mode_label=None, notes=self.본문().splitlines(),
                    charts=[c for c in [self.차트] if c]))


def 목록() -> list[tuple[str, str, str]]:
    """routines/ 안의 루틴 파일들. (파일명, 카테고리, 한 줄)"""
    rows = []
    for path in sorted(ROOT.glob("routines/[!_]*.py")):
        head = path.read_text(encoding="utf-8").splitlines()
        한줄 = next((l.strip('"""').strip() for l in head[:3] if l.strip()), "")
        text = "\n".join(head[:20])
        카테고리 = next((item for item in 카테고리들 if item in text), 맞춤알림)
        rows.append((path.stem, 카테고리, 한줄))
    return rows

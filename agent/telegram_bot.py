"""텔레그램 봇 — 폰에서 내 시스템을 부린다.

에이전트는 이미 결과를 텔레그램으로 **보낸다**. 이 파일은 반대 방향을 연다.
폰에서 명령을 보내면 그 자리에서 점검·후보·뉴스·리밸런싱이 돈다.

설치는 없다. 표준 라이브러리만 쓴다(urllib). 긴 폴링(long polling)이라
서버도 공인 IP 도 필요 없다. 노트북에서 켜 두기만 하면 된다.

    python agent/telegram_bot.py

안전선 두 가지 — 이건 고치지 마세요.
  1) `.env` 의 TELEGRAM_CHANNEL_ID 와 같은 방에서 온 말만 듣는다.
     봇 이름은 누구나 검색할 수 있다. 이 줄이 없으면 남이 내 계좌를 만진다.
  2) 주문이 나가는 명령(/rebalance)은 **한 번 더 확인**을 받는다.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent

from agent.agent import build_report, load_forbidden, load_number, load_portfolio, load_schedule  # noqa: E402
from common.env import load_repo_env  # noqa: E402
from common import judge, market  # noqa: E402
from common.chart import branded  # noqa: E402
from common.kis import KISClient  # noqa: E402
from common.stocks import NAME_TO_CODE  # noqa: E402
from common.report import to_plain_text  # noqa: E402
from common.plan_store import (  # noqa: E402
    PlanClaimError,
    cancel_plan,
    load_plan_record,
    save_pending_plan,
)
from common.reference_runtime import (  # noqa: E402
    approve_reference_plan,
    create_reference_plan,
)

API = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 50          # 긴 폴링. 이 시간 동안 서버가 답을 붙잡고 있다가 준다.
CONFIRM_WINDOW = 900       # 승인을 기다리는 시간(초). 폰을 바로 못 보는 일이 흔하다

# 텔레그램 명령 메뉴. 이름은 소문자 영문만 된다 — 설명은 한글이어도 된다.
COMMANDS = [
    # 학생 창구는 보기(/config)와 고치기(/update_config). 인터뷰형 /init 은 맨 아래.
    ("config", "지금 스펙. 기본값이 이미 있습니다. 저장소는 건드리지 않습니다"),
    ("update_config", "스펙·루틴·예약을 고친다. 뒤에 바꿀 내용을 적는다"),
    ("status", "총자산·현금·종목별로 몇 주에 얼마인지"),
    ("check", "지금 비중이 목표와 얼마나 벌어졌는지, 무엇을 몇 주 사고팔면 되는지"),
    ("review", "종목의 6개월 성적·업종·뉴스를 모아 AI가 짚어 준다"),
    ("candidates", "시총 상위 중 내 「하지 말 것」에 안 걸리는 종목 목록"),
    ("news", "내 종목별 오늘 뉴스 제목"),
    ("journal", "산 이유·판 이유·안 움직인 이유를 내-투자-판단.md 에 한 줄로"),
    ("routines", "조건이 맞으면 도는 루틴, 원할 때 여는 루틴"),
    ("ask", "물어본다. 저장소를 고치지 않는다. 뒤에 궁금한 것을 적는다"),
    ("update", "수업 자료를 최신으로 맞춘다. 내 스펙·판단은 그대로"),
    ("rebalance", "진입·청산 목록. 승인 버튼을 눌러야 모의 주문이 나간다"),
    ("pending", "승인을 기다리는 주문이 있는지, 몇 분 남았는지"),
    ("doctor", "증권사 연결·스펙·시장 데이터·AI 가 되는지 O/X 로"),
    ("help", "가져가는 것과 명령 목록"),
    ("init", "기본값으로 되돌리기. 뒤에 초기화"),
]

# 예전 이름도 그대로 받는다. 슬라이드·문서에 남아 있어도 깨지지 않게.
LEGACY = {"balance": "status", "spec": "config", "report": "review"}

# 슬래시를 모르는 사람을 위한 말 트리거. 같은 일을 한다.
ALIASES = {
    "점검": "check", "점검해줘": "check", "확인": "check",
    "잔고": "status", "계좌": "status", "상태": "status",
    "후보": "candidates", "종목": "candidates",
    "뉴스": "news", "브리프": "news",
    "스펙": "config", "내스펙": "config", "설정": "config",
    "루틴": "routines", "루틴목록": "routines",
    "분석": "review", "리포트": "review",
    "기록": "journal", "일지": "journal", "메모": "journal",
    "물어봐": "ask", "질문": "ask",
    "업데이트": "update", "맞춰": "update", "자료맞춰": "update",
    "시켜": "update_config", "고쳐": "update_config", "바꿔": "update_config",
    "시작": "init", "처음": "init", "초기화": "init",
    "대기": "pending", "승인대기": "pending",
    "점검": "doctor", "진단": "doctor", "왜안돼": "doctor",
    "리밸런싱": "rebalance", "조정": "rebalance",
    "도움": "help", "도움말": "help", "명령": "help",
}


def _split_names(arg: str) -> tuple[list[str], str]:
    """앞쪽의 아는 종목 이름만 떼어내고, 나머지는 자연어 질문으로 본다."""
    words, names, rest = arg.split(), [], []
    for i, w in enumerate(words):
        if w in NAME_TO_CODE or (w.isdigit() and len(w) == 6):
            names.append(w)
        else:
            rest = words[i:]
            break
    return names, " ".join(rest).strip()


def _returns_chart(rows: list[dict]) -> str:
    """종목별 6개월 수익률 막대. 오른 것과 빠진 것을 색으로 가른다."""
    from common.chart import CANVAS, FONT, GRID, INK, MUTED
    import json as _json
    import urllib.parse as _up
    cfg = {
        "type": "bar",
        "data": {"labels": [r["name"] for r in rows], "datasets": [{
            "label": "6개월 수익률(%)",
            "data": [round(r["ret"], 1) for r in rows],
            "backgroundColor": ["#1B5E45" if r["ret"] >= 0 else "#C2703D" for r in rows],
            "borderWidth": 0}]},
        "options": {
            "title": {"display": True, "text": "6개월 수익률 (%)", "fontSize": 18,
                      "fontStyle": "bold", "fontColor": INK, "fontFamily": FONT, "padding": 14},
            "legend": {"display": False},
            "scales": {
                "yAxes": [{"ticks": {"fontColor": MUTED, "fontSize": 13, "fontFamily": FONT},
                           "gridLines": {"color": GRID, "drawBorder": False}}],
                "xAxes": [{"ticks": {"fontColor": INK, "fontSize": 14, "fontFamily": FONT},
                           "gridLines": {"display": False, "drawBorder": False}}]},
            "plugins": {"datalabels": {"display": False}}},
    }
    q = _up.urlencode({"c": _json.dumps(cfg, ensure_ascii=False, separators=(",", ":")),
                       "w": 620, "h": 340, "bkg": CANVAS})
    return branded(f"https://quickchart.io/chart?{q}")


class Bot:
    def __init__(
        self,
        token: str,
        owner: str,
        *,
        state_dir: Path | None = None,
        fixtures_dir: Path | None = None,
        clock=None,
    ):
        self.token = token
        self.owner = str(owner)
        self.offset = 0
        self.state_dir = state_dir or ROOT / ".state"
        self.fixtures_dir = fixtures_dir or ROOT / "src" / "common" / "fixtures"
        self.clock = clock or (
            lambda: datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        self.pending_file = self.state_dir / "telegram-plan.json"

    # ── 승인 대기 ───────────────────────────────────────────
    @property
    def pending_rebalance(self) -> bool:
        try:
            return load_plan_record(self.pending_file).get("status") == "pending"
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    # ── 텔레그램 API ────────────────────────────────────────
    def call(self, method: str, payload: dict) -> dict:
        req = urllib.request.Request(
            API.format(token=self.token, method=method),
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "User-Agent": "ai-trading-lab (bot, 1.0)"},
        )
        with urllib.request.urlopen(req, timeout=POLL_SECONDS + 15) as resp:
            return json.loads(resp.read().decode())

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None) -> dict:
        """버튼을 주면 메시지 아래에 붙는다. 타이핑 대신 눌러서 답할 수 있다."""
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [text]
        result = {}
        for i, part in enumerate(parts):
            payload = {"chat_id": self.owner, "text": part}
            if buttons and i == len(parts) - 1:
                payload["reply_markup"] = {"inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in buttons]]}
            result = self.call("sendMessage", payload).get("result") or {}
        return result

    def typing(self) -> None:
        """「입력 중」 표시. 오래 걸리는 명령에서 멈춘 것처럼 보이지 않게 한다."""
        try:
            self.call("sendChatAction", {"chat_id": self.owner, "action": "typing"})
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError):
            pass

    def send_photo(self, url: str, caption: str = "") -> None:
        try:
            self.call("sendPhoto", {"chat_id": self.owner, "photo": url,
                                    "caption": caption[:1000]})
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError):
            self.send(f"차트: {url}")

    # ── 명령 ────────────────────────────────────────────────
    def cmd_pending(self) -> None:
        """승인을 기다리는 것이 있나. 눌렀는데 반응이 없을 때 여기부터 본다."""
        try:
            record = load_plan_record(self.pending_file)
        except (OSError, ValueError, json.JSONDecodeError):
            self.send("기다리는 것이 없습니다.")
            return
        if record.get("status") != "pending":
            self.send(f"최근 주문 계획 상태: {record.get('status', '알 수 없음')}")
            return
        expires = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
        now = datetime.fromisoformat(self.clock().replace("Z", "+00:00"))
        seconds = int((expires - now).total_seconds())
        if seconds <= 0:
            self.send("리밸런싱 승인이 시간을 넘겼습니다. /rebalance 부터 다시 하세요.")
            return
        self.send(
            f"정확한 주문 계획이 승인을 기다립니다. {seconds // 60}분 {seconds % 60}초 남았습니다.\n"
            f"계획 해시: {record['plan_id']}\n"
            "승인은 아래 버튼으로만 받습니다.",
            buttons=[("이 계획 승인", record["plan_id"]), ("거절", "rb:no")],
        )

    def cmd_doctor(self) -> None:
        """무엇이 되고 무엇이 안 되나. 「왜 안 되지」의 첫 자리."""
        import shutil
        줄 = ["[점검]", ""]

        def 표시(이름: str, 됨: bool, 말: str = "") -> None:
            줄.append(f"{'O' if 됨 else 'X'}  {이름}{('  ' + 말) if 말 else ''}")

        try:
            bal = KISClient().get_balance()
            표시("증권사 연결", True, f"보유 {len(bal.get('holdings', []))}종목")
        except Exception as e:
            표시("증권사 연결", False, str(e)[:40])
        try:
            rows = load_portfolio()
            표시("내 스펙", bool(rows), f"{len(rows)}종목 · 합 {sum(r['target'] for r in rows):.0f}%")
        except Exception as e:
            표시("내 스펙", False, str(e)[:40])
        try:
            market.last(market.TICKERS["코스피"])
            표시("시장 데이터", True, "코스피·환율")
        except Exception:
            표시("시장 데이터", False, "야후에 못 닿습니다")
        도구 = judge.available()
        표시("AI 판단", bool(도구), 도구 or "클로드·코덱스가 없습니다")
        표시("판단 문서", (ROOT / "내-투자-판단.md").is_file())
        표시("승인 대기", bool(self.pending_rebalance), "있음" if self.pending_rebalance else "없음")

        줄 += ["", "X 가 있어도 대부분 그대로 진행됩니다.",
               "증권사 연결이 X 면 노트북에서 python verify.py 를 돌려 보세요."]
        self.send("\n".join(줄))

    KEEP = ("내-투자-스펙.md", "내-투자-판단.md", ".env")

    def cmd_update(self) -> None:
        """수업 자료를 원본에 맞춘다. 내 스펙·판단·.env 는 되돌리지 않는다.

        코딩 앱의 「수업 자료 업데이트 해 줘」와 같은 일이다.
        """
        import shutil
        import subprocess
        import tempfile

        def git(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(["git", "-C", str(ROOT), *args],
                                  capture_output=True, text=True, timeout=60)

        if not shutil.which("git") or git("rev-parse", "--is-inside-work-tree").returncode != 0:
            self.send("이 폴더는 git 저장소가 아닙니다.\n"
                      "노트북 코딩 앱에 「수업 자료 업데이트 해 줘」라고 보내 주세요.")
            return
        remote = git("remote", "get-url", "origin").stdout.strip()
        if "thecamp-aitrading" not in remote:
            self.send("원본 주소가 수업 저장소가 아닙니다. 맞추지 않았습니다.")
            return

        before = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
        백업 = {}
        tmp = Path(tempfile.mkdtemp(prefix="thecamp-keep-"))
        for name in self.KEEP:
            src = ROOT / name
            if src.is_file():
                dest = tmp / name
                shutil.copy2(src, dest)
                백업[name] = dest

        self.send("수업 자료를 맞추는 중입니다. 몇 초 걸립니다.")
        self.typing()
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"
        if branch == "HEAD":
            branch = "main"
        fetched = git("fetch", "origin", branch)
        if fetched.returncode != 0:
            self.send("원본에 닿지 못했습니다. 노트북 인터넷을 확인해 주세요.")
            shutil.rmtree(tmp, ignore_errors=True)
            return

        pulled = git("pull", "--ff-only", "origin", branch)
        if pulled.returncode != 0:
            git("reset", "--hard", f"origin/{branch}")

        for name, dest in 백업.items():
            shutil.copy2(dest, ROOT / name)
        shutil.rmtree(tmp, ignore_errors=True)

        after = (ROOT / "VERSION").read_text(encoding="utf-8").strip() if (ROOT / "VERSION").is_file() else "?"
        줄 = ["[자료]", f"버전 {after}"]
        if before != after:
            줄[1] = f"버전 {before} → {after}"
            줄.append("수업 자료가 맞춰졌습니다.")
        else:
            줄.append("이미 최신입니다.")
        줄.append("내 스펙 · 판단 · .env 는 그대로입니다.")
        self.send("\n".join(줄))

    def cmd_help(self) -> None:
        lines = [
            "가져가는 것부터입니다. 기본 스펙이 이미 있습니다.",
            "",
            "/config          지금 표. 저장소는 안 고칩니다",
            "/update_config   칸을 고칩니다. 뒤에 바꿀 말을 적습니다",
            "/check           목표가 지금과 얼마나 벌어졌는지. 아직 주문이 아닙니다",
            "/rebalance       진입·청산 목록. 눌러야 모의가 나갑니다",
            "/journal         산 이유, 판 이유, 안 움직인 이유",
            "/routines        조건이 맞으면 도는 것, 원할 때 여는 것",
            "",
            "나머지 명령",
            "",
        ]
        lines += [f"/{name}   {desc}" for name, desc in COMMANDS]
        lines += ["", "슬래시가 번거로우면 「점검」 「잔고」 「고쳐」 처럼 말로 보내도 됩니다."]
        self.send("\n".join(lines))

    # 버튼 이름은 눌러서 받는 것의 이름이다. 「~하기」 같은 동명사 대신 그냥 명사로 적는다.
    NEXT_AFTER_CHECK = [("이대로 모의 주문", "go:rebalance"),
                        ("내 종목 분석", "go:review"),
                        ("오늘 판단 기록", "go:journal")]

    def cmd_check(self) -> None:
        self.typing()
        rep = build_report(execute=False)
        for url in rep.charts:
            self.send_photo(url)
        self.send(to_plain_text(rep), buttons=self.NEXT_AFTER_CHECK)

    def cmd_status(self) -> None:
        self.typing()
        bal = KISClient().get_balance()
        held = {h["code"]: h for h in bal.get("holdings", [])}
        cash = int(bal.get("cash", 0))
        total = cash + sum(int(h.get("eval_amt", 0)) for h in held.values())
        lines = ["[잔고]", f"총 자산 {total:,}원 (현금 {cash:,}원)", ""]
        for row in load_portfolio():
            h = held.get(row["code"], {})
            amt = int(h.get("eval_amt", 0))
            share = amt / total * 100 if total else 0
            lines.append(f"{row['name']} {h.get('qty', 0)}주 · {amt:,}원 "
                         f"({share:.1f}% / 목표 {row['target']:.0f}%)")
        self.send("\n".join(lines),
                  buttons=[("목표 비중 점검", "go:check"),
                           ("내 종목 분석", "go:review")])

    def cmd_candidates(self) -> None:
        kis = KISClient()
        forbidden = load_forbidden()
        mine = {r["code"] for r in load_portfolio()}
        rows = sorted(kis.get_market_cap_top(10), key=lambda r: r["등락률"])
        lines = ["[정량 후보] 시총 상위 · 많이 빠진 순", ""]
        for r in rows:
            hit = next((w for w in forbidden if w in r["name"]), "")
            mark = "⛔ 스펙 ④" if hit else ("보유" if r["code"] in mine else "")
            lines.append(f"{r['name']} {r['등락률']:+.2f}%  {mark}".rstrip())
        lines += ["", "이 목록은 살 종목이 아니라 더 볼 종목입니다."]
        self.send("\n".join(lines))

    def cmd_news(self) -> None:
        kis = KISClient()
        lines = ["[정성 브리프] 제목만 모았습니다. 판단은 아직 없습니다.", ""]
        for row in load_portfolio():
            try:
                news = kis.get_news(row["code"])[:2]
            except RuntimeError:
                continue
            if not news:
                continue
            lines.append(f"· {row['name']}")
            lines += [f"  - {n['title']}" for n in news]
        self.send("\n".join(lines))

    def cmd_config(self) -> None:
        rows = load_portfolio()
        self.send("\n".join([
            "[내 스펙] 기본값이 이미 있습니다. 안 고쳐도 오늘 돕니다.",
            "① " + " · ".join(f"{r['name']} {r['target']:.0f}%" for r in rows),
            f"② 점검 주기: {load_schedule()}",
            f"③ 허용 오차: {load_number('rules.md', '허용 오차', 5):.0f}%p",
            f"④ 하지 마: {' · '.join(load_forbidden()) or '(없음)'}",
            "",
            "고치는 곳은 내-투자-스펙.md 한 곳입니다. 고친 뒤 python sync_spec.py",
        ]))

    def cmd_routines(self) -> None:
        """언제 무엇이 오는지. 파일 경로는 폰에서 쓸모가 없어 적지 않는다."""
        import subprocess
        걸린 = ""
        try:
            out = subprocess.run(["hermes", "cron", "list"], capture_output=True,
                                 text=True, timeout=30).stdout
            걸린 = out
        except (OSError, subprocess.TimeoutExpired):
            pass

        표 = [
            ("평일 08:00", "아침 브리핑", "시장·내 계좌·뉴스. 진입이 아님", "아침브리핑"),
            ("값이 닿을 때만", "가격 도달", "정해 둔 가격. 그대로면 조용", "가격도달"),
            ("평일 16:00", "마감 브리핑", "오늘 무슨 일이 있었나", "마감브리핑"),
        ]
        줄 = ["[루틴] 조건이 맞으면 혼자 도는 것. 진입·청산이 아닙니다", ""]
        for 때, 이름, 무엇, 키 in 표:
            켜짐 = "켜짐" if 키 in 걸린 else "꺼짐"
            줄.append(f"{때}  {이름}  [{켜짐}]")
            줄.append(f"    {무엇}")
        줄 += ["", "스펙의 다시 볼 날  점검 미리보기  살·팔 목록만. 승인은 사람",
               "", "트리거 없음 · 원할 때", ""]
        줄 += ["참조 실험          미국·한국 바스켓을 지수와 다시 본 결과",
               "저점·고점 판독    지금 이 가격이 1년 안에서 어디쯤인지"]
        줄 += ["", "아침·마감 외에 주간·월간·연간 브리핑은 수업 본편이 아닙니다.",
               "칸을 바꾸려면 /update_config 로 말하세요.",
               "예) /update_config 아침 브리핑을 7시로 바꿔 줘"]
        self.send("\n".join(줄))

    ROUTINE_FILES = {"backtest": "참조전략-실험.py", "levels": "저점고점-판독.py"}

    def run_routine(self, key: str) -> None:
        """루틴을 그 자리에서 돌린다. 결과는 루틴이 스스로 보낸다."""
        import subprocess
        파일 = self.ROUTINE_FILES.get(key)
        if not 파일:
            return
        self.send(f"{파일.replace('.py', '')} 를 돌립니다. 30초쯤 걸립니다.")
        self.typing()
        try:
            done = subprocess.run([sys.executable, 파일], cwd=str(ROOT / "routines"),
                                  capture_output=True, text=True, timeout=420)
            if done.returncode != 0:
                self.send(f"돌리다 막혔습니다.\n{(done.stderr or '')[-400:]}")
        except (OSError, subprocess.TimeoutExpired) as e:
            self.send(f"돌리다 막혔습니다: {e}")

    def cmd_review(self, arg: str = "") -> None:
        """종목 리포트. 뒤에 종목 이름과 하고 싶은 말을 자유롭게 붙인다.

        예) /review 삼성전자 현대차 반도체 쏠림이 걱정이야
        코드가 재료를 모으고, 판단은 AI가 한다. 주문은 나가지 않는다.
        """
        names, ask = _split_names(arg)
        if not names:
            names = [r["name"] for r in load_portfolio()]
        if not names:
            self.send("볼 종목이 없습니다. 예) /review 삼성전자 현대차")
            return

        self.typing()
        self.send(f"[리포트] {' · '.join(names)}\n재료를 모으는 중입니다. 잠시만요.")

        재료, rows = [], []
        for name in names[:6]:                      # 한 번에 여섯까지. 그 이상은 읽기 어렵다
            code = NAME_TO_CODE.get(name, name)
            try:
                sym = market.to_symbol(code)
                closes = market.history(sym, "6mo")
                info = market.profile(sym)
            except market.MarketError as e:
                재료.append(f"{name}: 시세를 못 가져왔습니다 ({e})")
                continue
            ret = market.change_pct(closes)
            ma = market.moving_average(closes, 60)
            재료.append(
                f"{name} ({info['sector']}) — 현재 {closes[-1]:,.0f}원 · "
                f"6개월 {ret:+.1f}% · 60일선 대비 {(closes[-1] / ma - 1) * 100:+.1f}% · "
                f"하루 등락폭 평균 {market.volatility_pct(closes):.2f}%")
            rows.append({"name": name, "ret": ret})
            try:
                for n in KISClient().get_news(code)[:2]:
                    재료.append(f"  뉴스: {n['title']}")
            except (RuntimeError, KeyError):
                pass

        try:
            kospi = market.change_pct(market.history(market.TICKERS["코스피"], "6mo"))
            재료.append(f"같은 기간 코스피 {kospi:+.1f}%")
        except market.MarketError:
            pass
        보유 = {r["name"]: r["target"] for r in load_portfolio()}
        재료.append("내 목표 비중 — " + (" · ".join(f"{k} {v:.0f}%" for k, v in 보유.items()) or "없음"))
        재료.append("내 스펙 ④ 하지 마 — " + (" · ".join(load_forbidden()) or "없음"))

        질문 = ask or "이 종목들을 견주고, 내가 확인해야 할 것을 짚어라."
        답 = judge.ask(재료="\n".join(재료), 질문=질문)
        self.send("\n".join(["[리포트] " + " · ".join(names), ""] + 재료))
        if 답:
            self.send("— AI가 짚은 것 —\n" + 답)
        elif judge.available():
            self.send("AI 답을 못 받았습니다. 위 재료만 보냅니다.")
        if len(rows) >= 2:
            self.send_photo(_returns_chart(rows))

    def cmd_journal(self, arg: str = "") -> None:
        """오늘 판단을 한 줄 남긴다. 1주차에 쓴 내-투자-판단.md 의 회차 표에 붙는다.

        예) /journal 삼성전자 안 팔았다. 뉴스 보고 흔들렸는데 규칙대로 뒀다.
        시스템이 낸 숫자가 아니라 **내가 왜 그랬는지**를 남기는 자리다.
        3·4주차가 이 칸을 읽는다.
        """
        문서 = ROOT / "내-투자-판단.md"
        if not arg.strip():
            self.send("남길 말을 뒤에 적어 주세요.\n"
                      "예) /journal 삼성전자 안 팔았다. 뉴스 보고 흔들렸는데 규칙대로 뒀다.")
            return
        if not 문서.is_file():
            self.send("내-투자-판단.md 를 못 찾았습니다.")
            return
        오늘 = datetime.now().strftime("%m/%d")
        한줄 = arg.strip().replace("|", "·").replace("\n", " ")   # 표가 깨지지 않게
        본문 = 문서.read_text(encoding="utf-8")
        표시 = "| | | | | |"
        새줄 = f"| | {오늘} | | | {한줄} |"
        if 표시 in 본문:
            본문 = 본문.replace(표시, f"{새줄}\n{표시}", 1)      # 빈 줄 위에 끼운다
        else:
            본문 = 본문.rstrip() + f"\n{새줄}\n"
        문서.write_text(본문, encoding="utf-8")
        self.send(f"[기록] {오늘}\n{한줄}\n\n"
                  "내-투자-판단.md 회차 표에 남겼습니다. 3·4주차가 이 칸을 읽습니다.")

    ASK_RULES = """\
너는 이 저장소의 안내자다. 사용자가 폰에서 물었다.

할 일
- 묻는 말에만 답한다. 저장소를 고치지 마라. 주문하지 마라.
- 에르메스·예약·루틴이 무엇이냐는 말에, 지금 상태를 학생 말로 짧게 설명한다.

말하지 마라
- 「파일 변경 없음」 「Gateway」 「no-agent」 「작업자」 같은 개발 로그.
- 예약이 안 돌면 이렇게만 말한다: 「노트북의 에르메스가 꺼져 있습니다. 노트북에서 켜 주세요.」
- 에르메스가 시작만 하면: 「정해진 시각에 스크립트를 시작합니다. 주문을 판단하지는 않습니다.」

답은 다섯 줄을 넘기지 마라. 폰으로 읽는다."""

    INIT_RULES = """\
너는 이 저장소(ai-trading-lab)의 작업자다. 사용자의 첫 설정을 돕는다.

순서
1) `.agents/skills/investment-habit-rules/SKILL.md` 를 읽고 그 방식대로 한다.
   투자 습관을 **한 번에 하나씩** 묻는다. 한꺼번에 여러 개를 묻지 마라.
2) 답을 `내-투자-판단.md` 의 「원하는 방식」·「하지 말 것」에 적는다.
   **사용자가 말한 문장만** 적는다. 네가 지어내지 마라.
3) 그 내용으로 `내-투자-스펙.md` 표 ①~④ 를 채우고 `python sync_spec.py` 로 반영한다.
4) `routines/` 의 「지시사항」을 사용자 성향에 맞춘다.
   자주 보고 싶어 하면 주기를 짧게, 느긋하면 길게.
5) 무엇을 어떻게 바꿨는지 **바뀐 것만** 목록으로 알려라.

지켜라
- 주문을 내지 마라. --execute · confirm · KIS_ENV=real 은 절대 쓰지 마라.
- 폰으로 읽는다. 한 번에 다섯 줄을 넘기지 마라.
- 이미 채워져 있으면 「지금 이렇습니다」를 먼저 보여주고 고칠지 묻는다."""

    RESET_RULES = """\
너는 이 저장소(ai-trading-lab)의 작업자다. 사용자가 처음으로 되돌리기를 원한다.

할 일
1) `내-투자-스펙.md` 를 저장소 기본값(시총 상위 다섯 종목 각 20% · 매주 월요일 ·
   허용 오차 5%p · 한 종목 몰빵·레버리지 금지)으로 되돌린다.
2) `python sync_spec.py` 로 반영한다.
3) `python agent/agent.py --reset-mock` 으로 연습 계좌를 처음 상태로 되돌린다.
4) `.state/` 안의 루틴 기억을 지운다.
5) **`내-투자-판단.md` 는 지우지 마라.** 1주차에 사람이 쓴 글이고 3·4주차가 읽는다.
6) 무엇을 되돌렸는지 목록으로 알려라.

주문을 내지 마라. 폰으로 읽는다. 다섯 줄을 넘기지 마라."""

    UPDATE_CONFIG_RULES = """\
너는 이 저장소(ai-trading-lab)의 작업자다. 사용자는 이미 있는 기본 스펙을 칸만 고친다.

할 일
1) `내-투자-스펙.md` 와 `routines/` 지시사항, 예약 시각만 사용자가 말한 칸을 고친다.
   말한 문장만 반영한다. 종목 메뉴를 새로 만들지 마라.
2) 스펙 표를 고쳤으면 `python sync_spec.py` 로 반영한다.
3) 바뀐 것만 목록으로 알려라. 폰으로 읽는다. 다섯 줄을 넘기지 마라.

하지 마라
- 처음부터 성향을 인터뷰하지 마라. 그건 /init 이 아니다.
- 주문을 내지 마라. --execute · confirm · KIS_ENV=real 은 쓰지 마라.
- 산다·판다 문장을 네가 지어내지 마라."""

    def cmd_update_config(self, arg: str = "") -> None:
        """이미 있는 스펙·루틴·예약을 칸만 고친다. 인터뷰가 아니다."""
        if not arg.strip():
            self.send(
                "뒤에 바꿀 칸을 적습니다. 기본 스펙이 이미 있습니다.\n"
                "예) /update_config 아침 브리핑을 7시로 바꿔 줘\n"
                "예) /update_config 허용 오차를 7%p 로\n"
                "지금 표만 보려면 /config"
            )
            return
        도구 = judge.available()
        if not 도구:
            self.send("쓸 수 있는 코딩 앱이 없습니다. 노트북에서 클로드나 코덱스를 켜 주세요.")
            return
        self.send("칸을 고치는 중입니다. 노트북 화면을 봐 주세요.")
        답 = judge.ask(
            재료=f"저장소 위치: {ROOT}",
            질문=arg.strip(),
            규칙=self.UPDATE_CONFIG_RULES,
        )
        self.send(답 or "답을 못 받았습니다. 노트북 화면을 확인해 주세요.")

    def cmd_init(self, arg: str = "") -> None:
        """처음 설정. 투자 성향을 묻고 스펙과 루틴을 맞춘다.

        `/init 초기화` 라고 하면 기본값으로 되돌린다.
        1주차 investment-habit-rules 스킬이 하던 인터뷰를 폰에서 잇는다.
        """
        도구 = judge.available()
        if not 도구:
            self.send("쓸 수 있는 코딩 앱이 없습니다. 노트북에서 클로드나 코덱스를 켜 주세요.")
            return
        되돌리기 = any(w in arg for w in ("초기화", "리셋", "처음으로", "reset"))
        if 되돌리기:
            self.send("[초기화] 기본값으로 되돌립니다. 내-투자-판단.md 는 그대로 둡니다.")
            규칙, 질문 = self.RESET_RULES, "저장소를 처음 상태로 되돌려라."
        else:
            self.send(f"[처음 설정] {도구} 가 투자 성향을 하나씩 묻습니다.\n"
                      "노트북 화면에서 답해 주세요. 다 되면 여기로 알려 드립니다.")
            규칙 = self.INIT_RULES
            질문 = arg.strip() or "첫 설정을 시작하라."
        답 = judge.ask(재료=f"저장소 위치: {ROOT}", 질문=질문, 규칙=규칙)
        self.send(답 or "답을 못 받았습니다. 노트북 화면을 확인해 주세요.")

    def cmd_ask(self, arg: str = "") -> None:
        """폰에서 묻는다. 저장소는 건드리지 않는다. 고치려면 /update_config.

        예) /ask 에르메스가 지금 돌고 있나
            /ask 삼성전자가 목표보다 얼마나 벌어졌지
        """
        if not arg.strip():
            self.send("뒤에 궁금한 것을 적습니다. 저장소는 건드리지 않습니다.\n"
                      "예) /ask 에르메스가 지금 돌고 있나\n"
                      "예) /ask 삼성전자가 목표보다 얼마나 벌어졌지\n"
                      "고치려면 /update_config 를 씁니다.")
            return
        도구 = judge.available()
        if not 도구:
            self.send("쓸 수 있는 코딩 앱이 없습니다. 노트북에서 클로드나 코덱스를 켜 주세요.")
            return
        self.send("잠시만요.")
        답 = judge.ask(재료=f"저장소 위치: {ROOT}", 질문=arg.strip(), 규칙=self.ASK_RULES)
        self.send(답 or "답을 못 받았습니다. 노트북 화면을 확인해 주세요.")

    def cmd_rebalance(self, confirmed: bool = False, *, sender_id: int | None = None) -> None:
        if confirmed:
            self.send("문장으로는 승인하지 않습니다. /pending의 정확한 계획 버튼을 눌러 주세요.")
            return
        try:
            plan = create_reference_plan(
                self.fixtures_dir,
                self.state_dir,
                now=self.clock(),
            )
        except FileNotFoundError:
            self.send(
                "채택한 참조 스펙이 없습니다.\n"
                "먼저 노트북에서 참조 결과를 읽고 제안을 채택하세요."
            )
            return
        if plan.blocks:
            self.send(
                "[리밸런싱] 가드레일이 주문 계획을 차단했습니다.\n"
                + "\n".join(f"- {reason}" for reason in plan.blocks)
            )
            return
        if not plan.orders:
            self.send("[리밸런싱] 현재 목표에 가까워 낼 주문이 없습니다.")
            return

        lines = [
            "[리밸런싱] 정확한 로컬 모의 주문 계획",
            f"시장: {plan.market} · 계좌: {plan.account_id}",
            f"유효시간: {plan.expires_at}",
            "",
        ]
        for order in plan.orders:
            verb = "매수" if order.side == "buy" else "매도"
            lines.append(
                f"- {order.ticker} {verb} {order.qty}주 · 지정가 {order.limit_price:,}"
            )
        lines += [
            "",
            f"계획 해시: {plan.plan_id}",
            "이 해시와 주문 목록 전체가 같을 때만 한 번 실행됩니다.",
        ]
        sent = self.send("\n".join(lines))
        message_id = int(sent.get("message_id", 0))
        if not message_id:
            self.send("승인 메시지 번호를 받지 못해 계획을 저장하지 않았습니다.")
            return
        save_pending_plan(
            self.pending_file,
            plan,
            channel_id=int(self.owner),
            sender_id=int(sender_id if sender_id is not None else self.owner),
            message_id=message_id,
        )
        self.call("editMessageReplyMarkup", {
            "chat_id": self.owner,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": [[
                {"text": "이 계획 승인", "callback_data": plan.plan_id},
                {"text": "거절", "callback_data": "rb:no"},
            ]]},
        })

    # ── 루프 ────────────────────────────────────────────────
    def on_button(self, q: dict) -> None:
        """버튼을 눌렀을 때. 누가 눌렀는지 반드시 확인한다.

        누르고 아무 반응이 없으면 눌린 건지 알 수가 없다. 세 가지로 알린다.
        1) 버튼 위에 뜨는 짧은 알림  2) 원래 메시지의 버튼을 결과 문구로 바꾸기
        3) 진행 중이라는 메시지 — 주문은 몇 초 걸린다
        """
        data = q.get("data", "")
        msg = q.get("message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        if chat != self.owner:
            self.call("answerCallbackQuery", {"callback_query_id": q["id"]})
            return                                   # 내 방이 아니면 무시한다

        if data == "done":
            self.call("answerCallbackQuery", {"callback_query_id": q["id"]})
            return
        self.call("answerCallbackQuery", {"callback_query_id": q["id"]})

        if data.startswith("go:"):
            이름 = data[3:]
            if 이름 == "review":
                self.send("무엇을 볼까요? 「/review 삼성전자 현대차」 처럼 보내 주세요.")
            elif 이름 == "journal":
                self.send("오늘 판단을 적어 주세요. 「/journal 오늘 안 팔았다」 처럼요.")
            elif 이름 == "rebalance":
                self.cmd_rebalance(
                    confirmed=False,
                    sender_id=int((q.get("from") or {}).get("id", self.owner)),
                )
            elif 이름 == "check":
                self.cmd_check()
            elif 이름 in ("backtest", "levels"):
                self.run_routine(이름)
            return
        if data == "rb:no":
            try:
                record = load_plan_record(self.pending_file)
                cancel_plan(
                    self.pending_file,
                    plan_id=record["plan_id"],
                    channel_id=int(chat),
                    sender_id=int((q.get("from") or {}).get("id", 0)),
                    message_id=int(msg.get("message_id", 0)),
                )
                self._replace_buttons(msg, "거절됨 · 주문 없음")
                self.send("거절했습니다. 주문은 나가지 않았습니다.")
            except (OSError, ValueError, PlanClaimError) as error:
                self.send(f"거절할 계획을 확인하지 못했습니다: {error}")
            return
        if len(data) != 64 or any(ch not in "0123456789abcdef" for ch in data):
            self.send("알 수 없는 승인 버튼입니다. /pending에서 다시 확인하세요.")
            return
        self.send("저장된 주문 목록과 해시를 확인한 뒤 로컬 모의계좌에 넣습니다.")
        try:
            fills = approve_reference_plan(
                self.fixtures_dir,
                self.state_dir,
                self.pending_file,
                plan_id=data,
                channel_id=int(chat),
                sender_id=int((q.get("from") or {}).get("id", 0)),
                message_id=int(msg.get("message_id", 0)),
                now=self.clock(),
            )
        except Exception as error:
            self._replace_buttons(msg, "승인 거절됨")
            self.send(f"주문을 실행하지 않았습니다: {error}")
            return
        self._replace_buttons(msg, "실행됨 · 재사용 불가")
        lines = [f"[체결] 로컬 모의계좌 · {len(fills)}건", ""]
        for fill in fills:
            verb = "매수" if fill["side"] == "buy" else "매도"
            lines.append(f"{verb}  {fill['ticker']}  {fill['qty']}주")
        lines.append("\n같은 승인 버튼은 다시 사용할 수 없습니다.")
        self.send("\n".join(lines))

    def _replace_buttons(self, msg: dict, label: str) -> None:
        """누른 뒤에는 버튼을 결과 문구로 바꾼다. 두 번 눌리는 것도 막는다."""
        mid = msg.get("message_id")
        if not mid:
            return
        try:
            self.call("editMessageReplyMarkup", {
                "chat_id": self.owner, "message_id": mid,
                "reply_markup": {"inline_keyboard": [[
                    {"text": label, "callback_data": "done"}]]},
            })
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError):
            pass

    def dispatch(self, text: str, message: dict | None = None) -> None:
        word = text.strip().lstrip("/").split("@")[0].split()[0] if text.strip() else ""
        name = word if word in dict(COMMANDS) else LEGACY.get(word) or ALIASES.get(word, "")

        if self.pending_rebalance:
            if word in ("승인", "예", "네", "yes", "y"):
                self.send("문장으로는 승인하지 않습니다. /pending의 정확한 계획 버튼을 눌러 주세요.")
                return
            if word in ("거절", "취소", "아니", "no", "n"):
                self.send("잘못된 계획을 취소하지 않도록 /pending의 거절 버튼을 눌러 주세요.")
                return
            # 다른 명령은 그대로 받는다. 승인 전에 잔고를 확인하는 건 자연스럽다.
            # 대기는 시간이 지나거나 거절할 때만 풀린다.

        if not name:
            self.send("모르는 명령입니다. /help 를 보내 보세요.")
            return
        if name == "rebalance":
            sender_id = int(
                ((message or {}).get("from") or {}).get("id", self.owner)
            )
            self.cmd_rebalance(confirmed=False, sender_id=sender_id)
        elif name in ("review", "journal", "ask", "init", "update_config"):
            뒤 = text.strip().lstrip("/")[len(word):].strip()
            getattr(self, f"cmd_{name}")(뒤)
        else:
            getattr(self, f"cmd_{name}")()

    def run(self) -> None:
        self.call("setMyCommands", {"commands": [
            {"command": c, "description": d} for c, d in COMMANDS]})
        print("봇이 켜졌습니다. 텔레그램에서 /help 를 보내 보세요. (멈추려면 Ctrl+C)")
        while True:
            try:
                res = self.call("getUpdates", {"offset": self.offset,
                                               "timeout": POLL_SECONDS})
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                print(f"  (연결이 잠깐 끊겼습니다: {e}) 5초 뒤 다시 붙습니다.")
                time.sleep(5)
                continue
            for upd in res.get("result", []):
                self.offset = upd["update_id"] + 1
                if "callback_query" in upd:
                    self.on_button(upd["callback_query"])
                    continue
                msg = upd.get("message") or {}
                if str(msg.get("chat", {}).get("id")) != self.owner:
                    continue  # 내 방이 아니면 무시한다. 이 줄을 지우지 마세요.
                text = msg.get("text", "")
                print(f"  받음: {text}")
                try:
                    self.dispatch(text, msg)
                except Exception as e:  # 명령 하나가 죽어도 봇은 계속 산다
                    self.send(f"명령을 처리하다 막혔습니다: {e}")


def main() -> None:
    import os
    load_repo_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    owner = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    if not token or not owner:
        print("\n.env 에 TELEGRAM_BOT_TOKEN 과 TELEGRAM_CHANNEL_ID 를 넣어 주세요.\n"
              "만드는 법: lessons/참고/telegram-봇-가이드.md\n", file=sys.stderr)
        sys.exit(1)
    try:
        Bot(token, owner).run()
    except KeyboardInterrupt:
        print("\n봇을 껐습니다.")


if __name__ == "__main__":
    main()

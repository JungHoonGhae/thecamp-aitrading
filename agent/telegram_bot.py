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
from datetime import datetime
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent

from agent import build_report, load_forbidden, load_number, load_portfolio, load_schedule  # noqa: E402
from common.env import load_repo_env  # noqa: E402
from common import judge, market  # noqa: E402
from common.chart import branded  # noqa: E402
from common.kis import KISClient  # noqa: E402
from common.stocks import NAME_TO_CODE  # noqa: E402
from common.report import to_plain_text  # noqa: E402

API = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 50          # 긴 폴링. 이 시간 동안 서버가 답을 붙잡고 있다가 준다.
CONFIRM_WINDOW = 900       # 승인을 기다리는 시간(초). 폰을 바로 못 보는 일이 흔하다

# 텔레그램 명령 메뉴. 이름은 소문자 영문만 된다 — 설명은 한글이어도 된다.
COMMANDS = [
    # 이름은 코딩 앱(클로드 코드)에 있는 것과 맞춘다. 처음 봐도 짐작이 된다.
    # 순서가 곧 하루 순서다. 설명은 무엇을 하고 무엇이 남는지만 적는다.
    ("init", "투자 성향을 하나씩 물어 내 종목·비중·주기를 정해 준다"),
    ("status", "총자산·현금·종목별로 몇 주에 얼마인지"),
    ("check", "지금 비중이 목표와 얼마나 벌어졌는지, 무엇을 몇 주 사고팔면 되는지"),
    ("config", "내가 정한 종목·비중·점검 주기·하지 말 것"),
    ("review", "종목의 6개월 성적·업종·뉴스를 모아 AI가 짚어 준다"),
    ("candidates", "시총 상위 중 내 「하지 말 것」에 안 걸리는 종목 목록"),
    ("news", "내 종목별 오늘 뉴스 제목"),
    ("journal", "오늘 판단을 내-투자-판단.md 에 한 줄로 남긴다"),
    ("routines", "몇 시에 무엇이 자동으로 오는지"),
    ("ask", "물어본다. 저장소를 고치지 않는다. 뒤에 궁금한 것을 적는다"),
    ("update_config", "스펙·루틴·예약을 고친다. 뒤에 바꿀 내용을 적는다"),
    ("rebalance", "목표 비중이 되도록 모의 주문을 넣는다. 승인 버튼을 눌러야 나간다"),
    ("pending", "승인을 기다리는 주문이 있는지, 몇 분 남았는지"),
    ("doctor", "증권사 연결·스펙·시장 데이터·AI 가 되는지 O/X 로"),
    ("help", "명령 목록을 보여준다"),
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
    def __init__(self, token: str, owner: str):
        self.token = token
        self.owner = str(owner)
        self.offset = 0
        # 승인 대기는 파일에 둔다. 메모리에 두면 봇을 껐다 켜거나 다른 창에서
        # 요청했을 때 「시간이 지났습니다」가 되어 버린다.
        self.pending_file = ROOT / ".state" / "pending.txt"

    # ── 승인 대기 ───────────────────────────────────────────
    @property
    def pending_rebalance(self) -> float:
        try:
            return float(self.pending_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return 0.0

    @pending_rebalance.setter
    def pending_rebalance(self, value: float) -> None:
        if value:
            self.pending_file.parent.mkdir(exist_ok=True)
            self.pending_file.write_text(str(value), encoding="utf-8")
        else:
            self.pending_file.unlink(missing_ok=True)

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

    def send(self, text: str, buttons: list[tuple[str, str]] | None = None) -> None:
        """버튼을 주면 메시지 아래에 붙는다. 타이핑 대신 눌러서 답할 수 있다."""
        parts = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [text]
        for i, part in enumerate(parts):
            payload = {"chat_id": self.owner, "text": part}
            if buttons and i == len(parts) - 1:
                payload["reply_markup"] = {"inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in buttons]]}
            self.call("sendMessage", payload)

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
        남은 = self.pending_rebalance
        if not 남은:
            self.send("기다리는 것이 없습니다.")
            return
        초 = CONFIRM_WINDOW - (time.time() - 남은)
        if 초 <= 0:
            self.pending_rebalance = 0.0
            self.send("리밸런싱 승인이 시간을 넘겼습니다. /rebalance 부터 다시 하세요.")
            return
        self.send(f"리밸런싱이 승인을 기다립니다. {int(초 // 60)}분 {int(초 % 60)}초 남았습니다.\n"
                  "승인하려면 「승인」, 그만두려면 「거절」 이라고 보내세요.",
                  buttons=[("승인", "rb:ok"), ("거절", "rb:no")])

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

    def cmd_help(self) -> None:
        lines = ["누르면 무엇이 오는지 적어 두었습니다. 위에서부터 하루 순서입니다.", ""]
        lines += [f"/{name}   {desc}" for name, desc in COMMANDS]
        lines += ["", "슬래시가 번거로우면 「점검」 「잔고」 「후보」 처럼 말로 보내도 됩니다."]
        self.send("\n".join(lines))

    # 버튼 이름은 「무엇을 하는지」가 아니라 「누르면 무엇이 오는지」로 적는다.
    NEXT_AFTER_CHECK = [("이대로 주문", "go:rebalance"),
                        ("종목 하나 뜯어보기", "go:review"),
                        ("오늘 판단 적기", "go:journal")]

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
                  buttons=[("목표와 견주기", "go:check"),
                           ("종목 하나 뜯어보기", "go:review")])

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
            "[내 스펙]",
            "① " + " · ".join(f"{r['name']} {r['target']:.0f}%" for r in rows),
            f"② 점검 주기: {load_schedule()}",
            f"③ 허용 오차: {load_number('rules.md', '허용 오차', 5):.0f}%p",
            f"④ 하지 마: {' · '.join(load_forbidden()) or '(없음)'}",
            "",
            "고치는 곳은 내-투자-스펙.md 한 곳입니다. 고친 뒤 python sync_spec.py",
        ]))

    def cmd_routines(self) -> None:
        lines = ["[루틴] 정해진 주기에 혼자 도는 것들", ""]
        for path in sorted((ROOT / "routines").glob("[!_]*.py")):
            doc = path.read_text(encoding="utf-8").splitlines()
            한줄 = doc[0].lstrip('"').strip() if doc else path.stem
            카테고리 = next((l.split(":", 1)[1].split("(")[0].strip()
                          for l in doc[:8] if l.startswith("카테고리:")), "정보수집")
            lines.append(f"· {한줄}")
            lines.append(f"  [{카테고리}]  python routines/{path.name}")
        lines += ["", "정해진 시각에 돌리려면 hermes 에게 말로 예약하세요.",
                  "자세한 목록은 routines/README.md 입니다."]
        self.send("\n".join(lines))

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
너는 이 저장소(ai-trading-lab)의 작업자다. 사용자가 폰에서 보낸 부탁이다.

할 수 있는 일
- 내-투자-스펙.md 의 표 ①~④ 를 고치고 python sync_spec.py 로 반영한다.
- routines/ 의 「지시사항」 값을 고친다. 새 루틴 파일을 만든다.
- hermes cron 으로 예약을 걸거나 고치거나 지운다.
- 무엇이든 묻는 말에 답한다.

지켜라
- **주문을 내지 마라.** --execute · confirm · KIS_ENV=real 은 절대 쓰지 마라.
  주문은 사용자가 /rebalance 로 승인해야만 나간다.
- .env 의 값을 화면에 그리지 마라.
- 파일을 고쳤으면 무엇을 어떻게 고쳤는지 한 줄로 알려라.
- 답은 짧게. 다섯 줄을 넘기지 마라. 폰으로 읽는다."""

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
        """폰에서 시스템을 고친다. 스펙·루틴·예약을 말로 바꾼다.

        예) /ask 삼성전자 비중을 30으로 올리고 반영해 줘
            /ask 아침 브리핑을 7시로 바꿔 줘
            /ask 저점고점 판독 기간을 3개월로 바꿔 줘
        코딩 앱(claude·codex)이 저장소에서 직접 고친다. 주문은 못 낸다.
        """
        if not arg.strip():
            self.send("무엇을 할지 뒤에 적어 주세요.\n"
                      "예) /ask 삼성전자 비중을 30으로 올리고 반영해 줘\n"
                      "예) /ask 아침 브리핑을 7시로 바꿔 줘")
            return
        도구 = judge.available()
        if not 도구:
            self.send("쓸 수 있는 코딩 앱이 없습니다. 노트북에서 클로드나 코덱스를 켜 주세요.")
            return
        self.send(f"[{도구}] 저장소에서 작업합니다. 잠시만요.")
        답 = judge.ask(재료=f"저장소 위치: {ROOT}", 질문=arg.strip(), 규칙=self.ASK_RULES)
        self.send(답 or "답을 못 받았습니다. 노트북 화면을 확인해 주세요.")

    def cmd_rebalance(self, confirmed: bool) -> None:
        if not confirmed:
            self.pending_rebalance = time.time()
            self.send("[리밸런싱] 승인이 필요합니다.\n"
                      "실행하면 모의투자로 주문이 나갑니다.\n"
                      "가드레일을 어기는 주문은 승인해도 차단됩니다.\n\n"
                      "아래 버튼을 누르거나, 15분 안에 「승인」 이라고 보내 주세요.",
                      buttons=[("승인", "rb:ok"), ("거절", "rb:no")])
            return
        self.pending_rebalance = 0.0
        rep = build_report(execute=True)
        본문 = to_plain_text(rep)

        # 체결 내역을 먼저, 따로 보낸다. 긴 본문에 섞이면 무엇이 나갔는지 안 보인다.
        er = rep.execute_result
        if er and er.kind == "executed" and er.rows:
            된 = [e for e in er.rows if e.ok]
            안된 = [e for e in er.rows if not e.ok]
            줄 = [f"[체결] {er.execution_kind} · {len(된)}건", ""]
            줄 += [f"{'매수' if e.verb == '매수' else '매도'}  {e.name}  {e.qty}주" for e in 된]
            if 안된:
                줄 += ["", "안 나간 것"]
                줄 += [f"{e.name}  {e.msg}" for e in 안된]
            self.send("\n".join(줄))

        self.send(본문)
        for url in rep.charts:
            self.send_photo(url)
        # 「낼 주문이 없습니다」가 성공인지 실패인지 헷갈린다. 무슨 뜻인지 붙여 준다.
        if "이번에 낼 주문은 없습니다" in 본문:
            self.send("주문은 나가지 않았습니다. 고장이 아닙니다.\n"
                      "이미 목표에 가깝거나, 한 주 값이 남은 현금보다 크거나,\n"
                      "현금 최소선을 지키느라 건너뛴 것입니다. 위 각 줄에 사유가 있습니다.\n\n"
                      "더 맞추고 싶으면 /update_config 로 허용 오차를 좁히거나\n"
                      "현금 최소선을 낮춰 보세요.")
        else:
            self.send("주문이 끝났습니다. /status 로 지금 비중을 다시 보세요.")

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

        if data.startswith("go:"):
            self.call("answerCallbackQuery", {"callback_query_id": q["id"]})
        else:
            누름 = "승인" if data == "rb:ok" else "거절"
            self.call("answerCallbackQuery",
                      {"callback_query_id": q["id"], "text": f"{누름}했습니다"})
            self._replace_buttons(msg, f"눌림: {누름}")

        if data.startswith("go:"):
            이름 = data[3:]
            if 이름 == "review":
                self.send("무엇을 볼까요? 「/review 삼성전자 현대차」 처럼 보내 주세요.")
            elif 이름 == "journal":
                self.send("오늘 판단을 적어 주세요. 「/journal 오늘 안 팔았다」 처럼요.")
            elif 이름 == "rebalance":
                self.cmd_rebalance(confirmed=False)
            elif 이름 == "check":
                self.cmd_check()
            return
        if data == "rb:no":
            self.pending_rebalance = 0.0
            self.send("거절했습니다. 주문은 나가지 않았습니다.")
            return
        if not self.pending_rebalance or time.time() - self.pending_rebalance >= CONFIRM_WINDOW:
            self.pending_rebalance = 0.0
            self.send("승인 시간이 지났습니다. /rebalance 부터 다시 하세요.")
            return
        self.send("승인했습니다. 주문을 넣는 중입니다. 몇 초 걸립니다.")
        self.cmd_rebalance(confirmed=True)

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

    def dispatch(self, text: str) -> None:
        word = text.strip().lstrip("/").split("@")[0].split()[0] if text.strip() else ""
        name = word if word in dict(COMMANDS) else LEGACY.get(word) or ALIASES.get(word, "")

        if self.pending_rebalance:
            fresh = time.time() - self.pending_rebalance < CONFIRM_WINDOW
            if word in ("승인", "예", "네", "yes", "y"):
                if fresh:
                    self.send("승인했습니다. 주문을 넣는 중입니다. 몇 초 걸립니다.")
                    self.cmd_rebalance(confirmed=True)
                else:
                    self.pending_rebalance = 0.0
                    self.send("승인 시간이 지났습니다. /rebalance 부터 다시 하세요.")
                return
            if word in ("거절", "취소", "아니", "no", "n"):
                self.pending_rebalance = 0.0
                self.send("거절했습니다. 주문은 나가지 않았습니다.")
                return
            # 다른 명령은 그대로 받는다. 승인 전에 잔고를 확인하는 건 자연스럽다.
            # 대기는 시간이 지나거나 거절할 때만 풀린다.

        if not name:
            self.send("모르는 명령입니다. /help 를 보내 보세요.")
            return
        if name == "rebalance":
            self.cmd_rebalance(confirmed=False)
        elif name in ("review", "journal", "ask", "init"):
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
                    self.dispatch(text)
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

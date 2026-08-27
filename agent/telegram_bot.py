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
    # 순서가 곧 하루의 순서다. 설명은 무엇을 하는지와 무엇이 남는지만 적는다.
    ("check", "목표와 지금을 견주고 조정안을 보여준다. 주문은 나가지 않는다"),
    ("balance", "총자산과 종목별 비중을 목표와 함께 보여준다"),
    ("spec", "내가 정한 규칙 네 칸을 보여준다"),
    ("report", "종목을 분석한다. 뒤에 종목 이름과 궁금한 것을 적는다"),
    ("candidates", "시총 상위에서 내 규칙에 걸리지 않는 후보를 고른다"),
    ("news", "내 종목의 뉴스 제목을 모아 보여준다"),
    ("journal", "오늘 판단을 내-투자-판단.md 에 한 줄로 남긴다"),
    ("routines", "정해진 시각에 도는 루틴 목록을 보여준다"),
    ("ask", "스펙·루틴·예약을 고친다. 뒤에 시킬 말을 적는다"),
    ("rebalance", "목표 비중으로 되돌린다. 승인해야 주문이 나간다"),
    ("help", "명령 목록을 보여준다"),
]

# 슬래시를 모르는 사람을 위한 말 트리거. 같은 일을 한다.
ALIASES = {
    "점검": "check", "점검해줘": "check", "확인": "check",
    "잔고": "balance", "계좌": "balance",
    "후보": "candidates", "종목": "candidates",
    "뉴스": "news", "브리프": "news",
    "스펙": "spec", "내스펙": "spec",
    "루틴": "routines", "루틴목록": "routines",
    "분석": "report", "리포트": "report",
    "기록": "journal", "일지": "journal", "메모": "journal",
    "시켜": "ask", "물어봐": "ask", "고쳐": "ask",
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
        self.pending_rebalance = 0.0  # 확인 대기 시각

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

    def send_photo(self, url: str, caption: str = "") -> None:
        try:
            self.call("sendPhoto", {"chat_id": self.owner, "photo": url,
                                    "caption": caption[:1000]})
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError):
            self.send(f"차트: {url}")

    # ── 명령 ────────────────────────────────────────────────
    def cmd_help(self) -> None:
        lines = ["내 투자 시스템입니다. 위에서부터 하루 순서입니다.", ""]
        lines += [f"/{name}   {desc}" for name, desc in COMMANDS]
        lines += ["", "슬래시가 번거로우면 「점검」 「잔고」 「후보」 처럼 말로 보내도 됩니다."]
        self.send("\n".join(lines))

    def cmd_check(self) -> None:
        rep = build_report(execute=False)
        self.send(to_plain_text(rep))
        for url in rep.charts:
            self.send_photo(url)

    def cmd_balance(self) -> None:
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
        self.send("\n".join(lines))

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

    def cmd_spec(self) -> None:
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

    def cmd_report(self, arg: str = "") -> None:
        """종목 리포트. 뒤에 종목 이름과 하고 싶은 말을 자유롭게 붙인다.

        예) /report 삼성전자 현대차 반도체 쏠림이 걱정이야
        코드가 재료를 모으고, 판단은 AI가 한다. 주문은 나가지 않는다.
        """
        names, ask = _split_names(arg)
        if not names:
            names = [r["name"] for r in load_portfolio()]
        if not names:
            self.send("볼 종목이 없습니다. 예) /report 삼성전자 현대차")
            return

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
        self.send(to_plain_text(rep))

    # ── 루프 ────────────────────────────────────────────────
    def on_button(self, q: dict) -> None:
        """버튼을 눌렀을 때. 누가 눌렀는지 반드시 확인한다."""
        data = q.get("data", "")
        chat = str((q.get("message") or {}).get("chat", {}).get("id", ""))
        self.call("answerCallbackQuery", {"callback_query_id": q["id"]})
        if chat != self.owner:
            return                                   # 내 방이 아니면 무시한다
        if data == "rb:ok":
            if self.pending_rebalance and time.time() - self.pending_rebalance < CONFIRM_WINDOW:
                self.cmd_rebalance(confirmed=True)
            else:
                self.pending_rebalance = 0.0
                self.send("승인 시간이 지났습니다. /rebalance 부터 다시 하세요.")
        elif data == "rb:no":
            self.pending_rebalance = 0.0
            self.send("거절했습니다. 주문은 나가지 않았습니다.")

    def dispatch(self, text: str) -> None:
        word = text.strip().lstrip("/").split("@")[0].split()[0] if text.strip() else ""
        name = word if word in dict(COMMANDS) else ALIASES.get(word, "")

        if self.pending_rebalance:
            fresh = time.time() - self.pending_rebalance < CONFIRM_WINDOW
            if word in ("승인", "예", "네", "yes", "y"):
                if fresh:
                    self.cmd_rebalance(confirmed=True)
                else:
                    self.pending_rebalance = 0.0
                    self.send("승인 시간이 지났습니다. /rebalance 부터 다시 하세요.")
                return
            if word in ("거절", "취소", "아니", "no", "n"):
                self.pending_rebalance = 0.0
                self.send("거절했습니다. 주문은 나가지 않았습니다.")
                return
            self.pending_rebalance = 0.0  # 다른 말을 해도 취소한다

        if not name:
            self.send("모르는 명령입니다. /help 를 보내 보세요.")
            return
        if name == "rebalance":
            self.cmd_rebalance(confirmed=False)
        elif name in ("report", "journal", "ask"):
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

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
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent

from agent import build_report, load_forbidden, load_number, load_portfolio, load_schedule  # noqa: E402
from common.env import load_repo_env  # noqa: E402
from common.kis import KISClient  # noqa: E402
from common.report import to_plain_text  # noqa: E402

API = "https://api.telegram.org/bot{token}/{method}"
POLL_SECONDS = 50          # 긴 폴링. 이 시간 동안 서버가 답을 붙잡고 있다가 준다.
CONFIRM_WINDOW = 120       # 리밸런싱 확인을 기다리는 시간(초)

# 텔레그램 명령 메뉴. 이름은 소문자 영문만 된다 — 설명은 한글이어도 된다.
COMMANDS = [
    ("check", "포트폴리오 점검 (미리보기, 주문 없음)"),
    ("balance", "지금 잔고와 현금"),
    ("candidates", "정량 후보 — 시총 상위에서 걸러 본다"),
    ("news", "정성 브리프 — 내 종목 뉴스 제목"),
    ("spec", "내 스펙 네 칸"),
    ("routines", "루틴 목록 — 정해진 주기에 도는 것들"),
    ("rebalance", "리밸런싱 실행 (확인 한 번 더)"),
    ("help", "명령 목록"),
]

# 슬래시를 모르는 사람을 위한 말 트리거. 같은 일을 한다.
ALIASES = {
    "점검": "check", "점검해줘": "check", "확인": "check",
    "잔고": "balance", "계좌": "balance",
    "후보": "candidates", "종목": "candidates",
    "뉴스": "news", "브리프": "news",
    "스펙": "spec", "내스펙": "spec",
    "루틴": "routines", "루틴목록": "routines",
    "리밸런싱": "rebalance", "조정": "rebalance",
    "도움": "help", "도움말": "help", "명령": "help",
}


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

    def send(self, text: str) -> None:
        for i in range(0, len(text), 4000):
            self.call("sendMessage", {"chat_id": self.owner, "text": text[i:i + 4000]})

    def send_photo(self, url: str, caption: str = "") -> None:
        try:
            self.call("sendPhoto", {"chat_id": self.owner, "photo": url,
                                    "caption": caption[:1000]})
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError):
            self.send(f"차트: {url}")

    # ── 명령 ────────────────────────────────────────────────
    def cmd_help(self) -> None:
        lines = ["내 투자 시스템입니다. 아래 명령을 쓰세요.", ""]
        lines += [f"/{name} — {desc}" for name, desc in COMMANDS]
        lines += ["", "슬래시가 번거로우면 「점검」 「잔고」 「후보」 처럼 말로 보내도 됩니다."]
        self.send("\n".join(lines))

    def cmd_check(self) -> None:
        rep = build_report(execute=False)
        self.send(to_plain_text(rep))
        if rep.chart_url:
            self.send_photo(rep.chart_url, "목표 vs 현재")

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

    def cmd_rebalance(self, confirmed: bool) -> None:
        if not confirmed:
            self.pending_rebalance = time.time()
            self.send("[리밸런싱] 승인이 필요합니다.\n"
                      "실행하면 모의투자로 주문이 나갑니다.\n\n"
                      "승인하려면 2분 안에 「승인」 이라고 보내 주세요.\n"
                      "그만두려면 「거절」 이라고 보내면 됩니다.\n"
                      "가드레일을 어기는 주문은 승인해도 차단됩니다.")
            return
        self.pending_rebalance = 0.0
        rep = build_report(execute=True)
        self.send(to_plain_text(rep))

    # ── 루프 ────────────────────────────────────────────────
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

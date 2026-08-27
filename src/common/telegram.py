"""텔레그램 보고 헬퍼.

- 보고 본문은 항상 stdout 에 출력한다 (verify.py · 터미널).
- TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID 가 있으면 같은 내용을 텔레그램으로도 보낸다.
  변수 이름은 3~4회차 lecture-prism 과 같다 — 같은 봇·채널을 그대로 이어 쓸 수 있다.
- 안내 문구는 stderr 로 분리해서, verify.py 가 stdout 만 grep 해도 깨지지 않게 한다.

report() 는 agent.py 가 만든 문자열을 다시 파싱하지 않는다 — common/report.py 의
구조화된 Report 를 받는다. (렌더러는 서식만 입힌다.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from .env import load_repo_env
from .report import Report, to_plain_text, to_telegram_html

_TEXT_LIMIT = 4000  # Telegram sendMessage 한도(4096)에 여유


def _chunk(text: str) -> list[str]:
    return [text[i:i + _TEXT_LIMIT] for i in range(0, len(text), _TEXT_LIMIT)] or [text]


def _api(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "ai-trading-lab (telegram, 1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        raise RuntimeError(data.get("description", str(e))) from e
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "telegram api error"))
    return data


def _send_charts(token: str, chat_id: str, urls: list[str]) -> None:
    """그림은 한 묶음(앨범)으로 보낸다. 한 장씩 오면 화면이 그림으로 도배된다."""
    urls = [u for u in urls if u]
    if not urls:
        return
    try:
        if len(urls) == 1:
            _api(token, "sendPhoto", {"chat_id": chat_id, "photo": urls[0]})
        else:
            _api(token, "sendMediaGroup", {
                "chat_id": chat_id,
                "media": [{"type": "photo", "media": u} for u in urls[:10]],
            })
    except RuntimeError:
        _api(token, "sendMessage",
             {"chat_id": chat_id, "text": "\n".join(f"차트: {u}" for u in urls)})


def report(rep: Report) -> None:
    load_repo_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    text = to_plain_text(rep)

    print(text)  # stdout — verify.py grep · 터미널 확인. 텔레그램이 있어도 화면은 남긴다.

    if not token or not chat_id:
        # 텔레그램이 없으면 그림을 볼 길이 주소뿐이다. 길어도 그대로 찍는다.
        for i, url in enumerate(rep.charts, 1):
            print(f"\n차트 {i}: {url}")
        print("[텔레그램 미설정 → 화면만 출력]", file=sys.stderr)
        return
    if rep.charts:
        # 주소가 4천 자를 넘는다. 텔레그램으로 갈 것이면 터미널을 도배하지 않는다.
        print(f"\n(차트 {len(rep.charts)}장은 텔레그램으로 보냈습니다)")

    try:
        _, html = to_telegram_html(rep)
        if len(html) <= _TEXT_LIMIT:
            # 표가 표로 보이게 고정폭으로 보낸다. 길면 평문으로 잘라 보낸다.
            _api(token, "sendMessage", {"chat_id": chat_id, "text": html,
                                        "parse_mode": "HTML"})
        else:
            for part in _chunk(text):
                _api(token, "sendMessage", {"chat_id": chat_id, "text": part})
        _send_charts(token, chat_id, rep.charts)
        print("[텔레그램으로 보고 전송 완료]", file=sys.stderr)
    except RuntimeError as e:
        print(f"[텔레그램 전송 실패] {e}", file=sys.stderr)

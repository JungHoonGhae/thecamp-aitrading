"""디스코드 보고 헬퍼.

웹훅 URL(DISCORD_WEBHOOK 환경변수)이 있으면 디스코드로 보내고,
없으면 터미널에 그대로 출력한다. (강의 초반엔 웹훅 없이 화면으로 확인)
"""
from __future__ import annotations

import json
import os
import urllib.request


def report(text: str) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        print("\n[디스코드 미설정 → 화면 출력]\n" + text)
        return
    body = json.dumps({"content": text}).encode()
    req = urllib.request.Request(webhook, data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    print("[디스코드로 보고 전송 완료]")

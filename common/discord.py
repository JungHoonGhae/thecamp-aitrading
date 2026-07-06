"""디스코드 보고 헬퍼.

- DISCORD_WEBHOOK 이 있으면 디스코드로 직접 보낸다.
- 없으면 보고 본문을 그대로 stdout 에 출력한다. (안내 문구는 stderr 로 분리해서,
  hermes cron 의 no-agent 모드가 stdout 만 디스코드로 배달할 때 깔끔하게 나가게 한다.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def report(text: str) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        print("[디스코드 미설정 → 화면 출력]", file=sys.stderr)
        print(text)  # 본문은 stdout (hermes no-agent 가 이걸 디스코드로 배달)
        return
    body = json.dumps({"content": text}).encode()
    req = urllib.request.Request(webhook, data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10)
    print("[디스코드로 보고 전송 완료]", file=sys.stderr)

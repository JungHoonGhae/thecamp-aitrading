"""디스코드 보고 헬퍼.

- DISCORD_WEBHOOK 이 있으면 디스코드로 직접 보낸다 — Components v2 레이아웃
  (Container/TextDisplay/MediaGallery). 순수 incoming webhook(봇 아님)도
  URL 뒤에 ?with_components=true 만 붙이면 그대로 지원된다(2026-07-17 실측 확인).
  구식 content 필드(2000자 한도)보다 여유롭고(텍스트 블록당 ~4000자), 섹션별로 나뉘어 보인다.
  ⚠️ 링크 버튼(차트 URL 등)은 일부러 안 씀 — 버튼 url 필드는 Discord 에서
  훨씬 짧은 길이 제한이 있어, quickchart 같은 긴 쿼리스트링 URL을 넣으면
  전체 메시지가 400으로 거부된다(2026-07-17 실측 재현). Media Gallery 이미지는
  클릭하면 어차피 원본 크기로 열리므로 버튼 없이도 기능은 동일하다.
- 없으면 보고 본문을 그대로 stdout 에 출력한다. (안내 문구는 stderr 로 분리해서,
  hermes cron 의 no-agent 모드가 stdout 만 디스코드로 배달할 때 깔끔하게 나가게 한다.)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

_TEXT_LIMIT = 3900  # Discord Text Display 컴포넌트 한도(4000)에 여유를 둔 값

_CONTAINER, _TEXT, _MEDIA_GALLERY, _SEPARATOR = 17, 10, 12, 14

# agent.py 가 만드는 고정 문구 패턴 → 마크다운 스타일. 매칭 안 되는 줄은 그대로 둔다
# (agent.py 문구가 바뀌면 여기 패턴도 같이 손봐야 하지만, 안 맞아도 원문이 그대로
# 나가니 안전하게 깨진다 — 이쁘게 안 나올 뿐 내용이 사라지지 않는다).
_LINE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\[모의데이터\] (.+)$"), r"## 🧪 ai-trading-lab · \1"),
    (re.compile(r"^\[실계좌\] (.+)$"), r"## 🏦 ai-trading-lab · \1"),
    (re.compile(r"^총 자산: (.+?)원 \(현금 (.+?)원\)$"), r"**총 자산** \1원  ·  **현금** \2원"),
    (
        re.compile(r"^- (.+?)\((\d{6})\): 목표 (\d+)% / 현재 ([\d.]+)% → (매수|매도|유지) 약 (\d+)주\s*(.*)$"),
        r"> **\1** `\3%→\4%` — \5 약 \6주 \7",
    ),
    (re.compile(r"^리밸런싱 미리보기:$"), r"**🔄 리밸런싱 미리보기**"),
    (
        re.compile(r"^- (.+?): (매수|매도) (\d+)주 \(약 ([\d,]+)원\)$"),
        r"> **\1** \2 \3주 (약 \4원)",
    ),
    (re.compile(r"^리밸런싱할 주문이 없습니다(.*)$"), r"✅ 리밸런싱할 주문이 없습니다\1"),
    (re.compile(r"^⛔ 가드레일 위반 \(주문 차단\):$"), r"**⛔ 가드레일 위반 (주문 차단)**"),
    (re.compile(r"^가드레일 경고:$"), r"**⚠️ 가드레일 경고**"),
    (re.compile(r"^\[실행\] (.+)$"), r"**▶️ \1**"),
    (re.compile(r"^  (✅|❌) (.+)$"), r"> \1 \2"),
    (re.compile(r"^※ (.+)$"), r"-# \1"),
]


def _prettify(text: str) -> str:
    out_lines = []
    for line in text.split("\n"):
        for pat, repl in _LINE_RULES:
            m = pat.match(line)
            if m:
                line = pat.sub(repl, line)
                break
        out_lines.append(line)
    return "\n".join(out_lines)


def _split_blocks(text: str) -> list[str]:
    """문단(빈 줄) 단위로 묶어 _TEXT_LIMIT 이하 블록으로 나눈다."""
    paragraphs = text.split("\n\n")
    blocks: list[str] = []
    cur = ""
    for p in paragraphs:
        # 문단 하나가 한도를 넘는 예외적인 경우 강제로 자른다
        while len(p) > _TEXT_LIMIT:
            blocks.append(p[:_TEXT_LIMIT])
            p = p[_TEXT_LIMIT:]
        candidate = f"{cur}\n\n{p}" if cur else p
        if len(candidate) > _TEXT_LIMIT:
            if cur:
                blocks.append(cur)
            cur = p
        else:
            cur = candidate
    if cur:
        blocks.append(cur)
    return blocks


def build_payload(text: str, image_url: str | None = None) -> dict:
    """Components v2 페이로드를 만든다 — webhook 전송과 슬래시봇 팔로우업이 공유.

    (두 입구가 각자 컴포넌트를 짜면 오늘 슬래시봇에서처럼 차트가 텍스트로 새는
    버그가 또 생긴다. 빌더를 하나로 묶어 그 클래스의 실수를 원천 차단한다.)
    """
    inner: list[dict] = []
    blocks = _split_blocks(_prettify(text))
    for i, block in enumerate(blocks):
        if i:
            inner.append({"type": _SEPARATOR, "divider": True, "spacing": 1})
        inner.append({"type": _TEXT, "content": block})
    if image_url:
        inner.append({"type": _SEPARATOR, "divider": True, "spacing": 1})
        inner.append({"type": _MEDIA_GALLERY, "items": [{"media": {"url": image_url}}]})
    return {
        "flags": 1 << 15,  # IS_COMPONENTS_V2
        "components": [{"type": _CONTAINER, "accent_color": 0x35A46E, "components": inner}],
    }


def report(text: str, image_url: str | None = None) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        print("[디스코드 미설정 → 화면 출력]", file=sys.stderr)
        print(text)  # 본문은 stdout (hermes no-agent 가 이걸 디스코드로 배달)
        if image_url:
            # 디스코드는 이미지 URL 을 그대로 받아도 미리보기를 펼쳐준다
            # (hermes no-agent 경로에서도 차트가 보이도록 stdout 에 포함)
            print(f"\n차트: {image_url}")
        return

    body = json.dumps(build_payload(text, image_url)).encode()
    req = urllib.request.Request(
        f"{webhook}?with_components=true", data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "ai-trading-lab (webhook, 1.0)"},
    )
    urllib.request.urlopen(req, timeout=10)
    print("[디스코드로 보고 전송 완료]", file=sys.stderr)

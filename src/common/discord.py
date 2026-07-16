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

report()/build_payload() 는 agent.py 가 만든 문자열을 다시 파싱하지 않는다 — 둘 다
common/report.py 의 구조화된 Report 를 받는다. (2026-07-17 아키텍처 리뷰: 예전엔
agent.py 가 문자열로 뭉친 걸 이 파일이 regex 12개로 되짚어 파싱했고, 웹훅·슬래시봇
양쪽에서 각각 드리프트 버그가 났다 — Report 를 seam 으로 삼아 원천 차단.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from .report import Report, to_plain_text

_TEXT_LIMIT = 3900  # Discord Text Display 컴포넌트 한도(4000)에 여유를 둔 값

_CONTAINER, _TEXT, _MEDIA_GALLERY, _SEPARATOR = 17, 10, 12, 14


def _chunk(text: str) -> list[str]:
    """한 섹션이 예외적으로 _TEXT_LIMIT 을 넘으면(예: 종목 수가 아주 많은 스펙) 강제로 나눈다."""
    return [text[i:i + _TEXT_LIMIT] for i in range(0, len(text), _TEXT_LIMIT)] or [text]


def _section_blocks(r: Report) -> list[str]:
    """Report 의 각 섹션을 마크다운 텍스트 블록으로 렌더링한다. agent.py 문구를
    regex 로 되짚지 않고, 타입이 이미 갖고 있는 필드를 그대로 서식만 입힌다."""
    if r.mode_label is None:
        return ["\n".join(r.notes)]

    icon = "🧪" if r.mode_label == "모의데이터" else "🏦"
    blocks = [
        f"## {icon} ai-trading-lab · {r.title}\n"
        f"**총 자산** {r.total_won:,}원  ·  **현금** {r.cash_won:,}원"
    ]

    if r.comparison:
        rows = []
        for row in r.comparison:
            flag = " ⚠️" if row.needs_adjust else ""
            rows.append(f"> **{row.name}** `{row.target_pct:.0f}%→{row.current_pct:.1f}%` "
                        f"— {row.action} 약 {row.qty}주{flag}")
        blocks.append("\n".join(rows))

    for c in r.callouts:
        blocks.append(f"**{c.heading}**\n" + "\n".join(f"> {i}" for i in c.items))

    if r.preview:
        rows = [f"> **{p.name}** {p.verb} {p.qty}주 (약 {p.amount:,}원)" for p in r.preview]
        blocks.append("**🔄 리밸런싱 미리보기**\n" + "\n".join(rows))
    else:
        blocks.append("✅ 리밸런싱할 주문이 없습니다 (허용 오차 이내)")

    er = r.execute_result
    if er:
        if er.kind == "executed":
            rows = []
            for e in er.rows:
                mark = "✅" if e.ok else "❌"
                rows.append(f"> {mark} {e.name} {e.verb} {e.qty}주 — {e.msg}")
            blocks.append(f"**▶️ 가드레일 통과분 주문 전송 — {er.execution_kind}**\n" + "\n".join(rows))
        else:
            blocks.append("\n".join(er.lines))

    if r.notes:
        blocks.append("\n".join(f"-# {n}" for n in r.notes))

    return blocks


def build_payload(report: Report) -> dict:
    """Components v2 페이로드 — webhook 전송과 (개인 테스트용) 슬래시봇 팔로우업이 공유."""
    inner: list[dict] = []
    for i, block in enumerate(_section_blocks(report)):
        if i:
            inner.append({"type": _SEPARATOR, "divider": True, "spacing": 1})
        for j, chunk in enumerate(_chunk(block)):
            if j:
                inner.append({"type": _SEPARATOR, "divider": True, "spacing": 1})
            inner.append({"type": _TEXT, "content": chunk})
    if report.chart_url:
        inner.append({"type": _SEPARATOR, "divider": True, "spacing": 1})
        inner.append({"type": _MEDIA_GALLERY, "items": [{"media": {"url": report.chart_url}}]})
    return {
        "flags": 1 << 15,  # IS_COMPONENTS_V2
        "components": [{"type": _CONTAINER, "accent_color": 0x35A46E, "components": inner}],
    }


def report(rep: Report) -> None:
    webhook = os.getenv("DISCORD_WEBHOOK", "").strip()
    if not webhook:
        print("[디스코드 미설정 → 화면 출력]", file=sys.stderr)
        print(to_plain_text(rep))  # stdout (hermes no-agent 가 이걸 디스코드로 배달, verify.py 도 이걸 grep)
        if rep.chart_url:
            # 디스코드는 이미지 URL 을 그대로 받아도 미리보기를 펼쳐준다
            print(f"\n차트: {rep.chart_url}")
        return

    body = json.dumps(build_payload(rep)).encode()
    req = urllib.request.Request(
        f"{webhook}?with_components=true", data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "ai-trading-lab (webhook, 1.0)"},
    )
    urllib.request.urlopen(req, timeout=10)
    print("[디스코드로 보고 전송 완료]", file=sys.stderr)

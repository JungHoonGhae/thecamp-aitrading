"""포트폴리오 차트 URL 생성 — 표준 라이브러리만 사용.

이미지 파일을 로컬에서 그리지 않는다. 차트 설정(JSON)을 URL 에 담으면
QuickChart(quickchart.io)가 그 자리에서 PNG 로 렌더링해 준다.
텔레그램은 이미지 URL 을 받으면 채팅에 차트 이미지를 그대로 펼쳐 보여준다.
→ 설치 0개, OS 무관. (인터넷만 있으면 된다)

색은 수업 자료(덱)와 같은 팔레트를 쓴다. 보고가 강의 자료와 한 벌로 보이게 하려는 것이다.
"""
from __future__ import annotations

import json
import urllib.parse

# 수업 자료 팔레트. 덱의 Frame·Board 가 쓰는 값과 같다.
INK = "#171717"        # 본문 먹색
MUTED = "#737373"      # 축·보조
GRID = "#E5E5E5"       # 격자
CANVAS = "#FFFFFF"      # 판
TARGET = "#1B5E45"     # 목표 — 수업 초록
CURRENT = "#C2703D"    # 현재 — 벌어짐을 알리는 따뜻한 색
FONT = "'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"


def portfolio_chart_url(rows: list[dict], cash_weight: float) -> str:
    """목표 vs 현재 비중 막대 차트 URL.

    rows: [{"name": 종목명, "target": 목표비중%, "current": 현재비중%}]
    cash_weight: 현재 현금 비중(%)
    """
    labels = [r["name"] for r in rows] + ["현금"]
    target = [round(r["target"], 1) for r in rows] + [None]
    current = [round(r["current"], 1) for r in rows] + [round(cash_weight, 1)]
    # 눈금이 겹치지 않게 10 단위로 올린다. 46 같은 값이 되면 45 와 붙어 읽히지 않는다.
    peak = max([v for v in current + target if v is not None] + [20])
    ceiling = -(-int(peak * 1.2) // 10) * 10
    config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "목표 비중(%)", "data": target,
                 "backgroundColor": TARGET, "borderWidth": 0},
                {"label": "현재 비중(%)", "data": current,
                 "backgroundColor": CURRENT, "borderWidth": 0},
            ],
        },
        "options": {
            "title": {
                "display": True,
                "text": "포트폴리오 · 목표 vs 현재",
                "fontSize": 20, "fontStyle": "bold",
                "fontColor": INK, "fontFamily": FONT,
                "padding": 18,
            },
            "legend": {
                "position": "top", "align": "start",
                "labels": {"boxWidth": 14, "fontSize": 14,
                           "fontColor": MUTED, "fontFamily": FONT,
                           "usePointStyle": False, "padding": 16},
            },
            "layout": {"padding": {"left": 10, "right": 18, "top": 4, "bottom": 6}},
            "scales": {
                "yAxes": [{
                    "ticks": {"beginAtZero": True, "max": ceiling,
                              "fontColor": MUTED, "fontSize": 13, "fontFamily": FONT},
                    "gridLines": {"color": GRID, "zeroLineColor": GRID, "drawBorder": False},
                }],
                "xAxes": [{
                    "ticks": {"fontColor": INK, "fontSize": 14, "fontFamily": FONT},
                    "gridLines": {"display": False, "drawBorder": False},
                }],
            },
            "plugins": {"datalabels": {"display": False}},
        },
    }
    q = urllib.parse.urlencode({
        "c": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        "w": 620, "h": 340, "bkg": CANVAS,
    })
    return f"https://quickchart.io/chart?{q}"


def demo() -> None:
    """URL 이 만들어지고 실제로 PNG 가 내려오는지 본다.  python src/common/chart.py"""
    rows = [{"name": "삼성전자", "target": 20.0, "current": 36.9},
            {"name": "현대차", "target": 20.0, "current": 9.8}]
    url = portfolio_chart_url(rows, 19.6)
    assert url.startswith("https://quickchart.io/chart?"), url
    assert "%ED%8F%AC%ED%8A%B8%ED%8F%B4%EB%A6%AC%EC%98%A4" in url, "제목이 URL 에 없다"
    import urllib.request
    with urllib.request.urlopen(url, timeout=20) as r:
        head = r.read(8)
    assert head.startswith(b"\x89PNG"), f"PNG 가 아니다: {head!r}"
    print(f"OK — PNG 응답 확인. 길이 {len(url)}자")


if __name__ == "__main__":
    demo()

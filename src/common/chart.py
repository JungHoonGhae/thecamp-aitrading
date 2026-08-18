"""포트폴리오 차트 URL 생성 — 표준 라이브러리만 사용.

이미지 파일을 로컬에서 그리지 않는다. 차트 설정(JSON)을 URL 에 담으면
QuickChart(quickchart.io)가 그 자리에서 PNG 로 렌더링해 준다.
텔레그램은 이미지 URL 을 받으면 채팅에 차트 이미지를 그대로 펼쳐 보여준다.
→ 설치 0개, OS 무관. (인터넷만 있으면 된다)
"""
from __future__ import annotations

import json
import urllib.parse


def portfolio_chart_url(rows: list[dict], cash_weight: float) -> str:
    """목표 vs 현재 비중 막대 차트 URL.

    rows: [{"name": 종목명, "target": 목표비중%, "current": 현재비중%}]
    cash_weight: 현재 현금 비중(%)
    """
    labels = [r["name"] for r in rows] + ["현금"]
    target = [round(r["target"], 1) for r in rows] + [None]
    current = [round(r["current"], 1) for r in rows] + [round(cash_weight, 1)]
    config = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "목표 비중(%)", "data": target, "backgroundColor": "rgba(54,120,235,0.75)"},
                {"label": "현재 비중(%)", "data": current, "backgroundColor": "rgba(255,160,64,0.75)"},
            ],
        },
        "options": {
            "title": {"display": True, "text": "포트폴리오: 목표 vs 현재"},
            "scales": {"yAxes": [{"ticks": {"beginAtZero": True, "max": 50}}]},
            "plugins": {"datalabels": {"display": False}},
        },
    }
    q = urllib.parse.urlencode({
        "c": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        "w": 560, "h": 320, "bkg": "white",
    })
    return f"https://quickchart.io/chart?{q}"

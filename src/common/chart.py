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
from datetime import datetime

# 수업 자료 팔레트. 덱의 Frame·Board 가 쓰는 값과 같다.
INK = "#171717"        # 본문 먹색
MUTED = "#737373"      # 축·보조
GRID = "#E5E5E5"       # 격자
CANVAS = "#FFFFFF"      # 판
TARGET = "#1B5E45"     # 목표 — 수업 초록
CURRENT = "#C2703D"    # 현재 — 벌어짐을 알리는 따뜻한 색
FONT = "'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif"

# 수업 마크. 공개 저장소의 파일이라 학생 환경에서도 그대로 보인다.
MARK = ("https://raw.githubusercontent.com/JungHoonGhae/thecamp-aitrading"
        "/main/assets/logo-camp-ink.png")


def stamp() -> str:
    """언제 데이터인지. 그림만 저장해 두고 나중에 보면 알 수가 없다."""
    return datetime.now().strftime("%Y-%m-%d %H:%M 기준")


def branded(chart_url: str, ratio: float = 0.13, opacity: float = 0.5) -> str:
    """차트 위에 THE CAMP 마크를 얹는다.

    QuickChart 의 워터마크가 대신 합성해 준다. 로컬에 이미지 라이브러리가 없어도 된다.
    합성이 막히면 원래 차트 주소를 그대로 돌려준다 — 마크 때문에 그림을 잃지 않는다.
    """
    if not chart_url:
        return chart_url
    return "https://quickchart.io/watermark?" + urllib.parse.urlencode({
        "mainImageUrl": chart_url,
        "markImageUrl": MARK,
        "position": "bottomRight",
        "opacity": opacity,
        "markRatio": ratio,
        "margin": 12,
    })


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
                    "scaleLabel": {"display": True, "labelString": stamp(),
                                   "fontColor": MUTED, "fontSize": 12, "fontFamily": FONT},
                }],
            },
            # 막대 위에 값을 적는다. 눈금만 있으면 정확한 숫자를 읽으려고 눈이 왔다 갔다 한다.
            "plugins": {"datalabels": {
                "display": True, "anchor": "end", "align": "end", "offset": 2,
                "color": INK, "font": {"size": 12, "family": FONT, "weight": "bold"},
                "formatter": "(v) => v === null ? '' : v + '%'",
            }},
        },
    }
    q = urllib.parse.urlencode({
        "c": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        "w": 620, "h": 340, "bkg": CANVAS,
    })
    return branded(f"https://quickchart.io/chart?{q}")


def demo() -> None:
    """URL 이 만들어지고 실제로 PNG 가 내려오는지 본다.  python src/common/chart.py"""
    rows = [{"name": "삼성전자", "target": 20.0, "current": 36.9},
            {"name": "현대차", "target": 20.0, "current": 9.8}]
    url = portfolio_chart_url(rows, 19.6)
    assert url.startswith("https://quickchart.io/"), url
    assert "logo-camp-ink" in url, "마크가 안 붙었다"
    import urllib.request
    with urllib.request.urlopen(url, timeout=20) as r:
        head = r.read(8)
    assert head.startswith(b"\x89PNG"), f"PNG 가 아니다: {head!r}"
    print(f"OK — PNG 응답 확인. 길이 {len(url)}자")


if __name__ == "__main__":
    demo()


def weight_donut_url(rows: list[dict], cash_weight: float) -> str:
    """지금 무엇이 얼마나 들어 있나 — 구성 비율 도넛.

    막대는 「목표와 얼마나 벌어졌나」를 보여주고, 도넛은 「지금 무엇으로 차 있나」를
    보여준다. 폰에서는 도넛 쪽이 먼저 읽힌다.
    """
    # 초록에서 흙빛으로 도는 순환. 수업 팔레트 안에서만 고른다.
    WHEEL = ["#1B5E45", "#2D8A63", "#5BAE8A", "#C2703D", "#D99A6C", "#8A6A4F"]
    items = [(r["name"], round(r["current"], 1)) for r in rows if r["current"] > 0]
    if cash_weight > 0:
        items.append(("현금", round(cash_weight, 1)))
    config = {
        "type": "doughnut",
        "data": {
            "labels": [n for n, _ in items],
            "datasets": [{
                "data": [v for _, v in items],
                "backgroundColor": [WHEEL[i % len(WHEEL)] for i in range(len(items))],
                "borderColor": CANVAS, "borderWidth": 2,
            }],
        },
        "options": {
            "title": {"display": True,
                      "text": ["지금 무엇으로 차 있나 (%)", stamp()],
                      "fontSize": 17, "fontStyle": "bold",
                      "fontColor": INK, "fontFamily": FONT, "padding": 12},
            "legend": {"position": "right",
                       "labels": {"boxWidth": 13, "fontSize": 14,
                                  "fontColor": INK, "fontFamily": FONT, "padding": 11}},
            "cutoutPercentage": 56,
            # 조각마다 숫자를 적는다. 범례 색만 보고 비율을 가늠하게 두지 않는다.
            "plugins": {"datalabels": {
                "display": True, "color": "#FFFFFF", "backgroundColor": None,
                "font": {"size": 13, "family": FONT, "weight": "bold"},
                "formatter": "(v) => v >= 6 ? v + '%' : ''",
            }},
        },
    }
    q = urllib.parse.urlencode({
        "c": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        "w": 620, "h": 340, "bkg": CANVAS,
    })
    return branded(f"https://quickchart.io/chart?{q}")


def overview_chart_url(rows: list[dict], cash_weight: float) -> str:
    """한 장으로 다 보이게 — 지금 비중 · 목표 · 얼마나 엇나갔나.

    도넛(구성)과 막대(목표 대비)를 따로 보내면 두 장을 번갈아 봐야 한다.
    가로 막대 한 장에 셋을 다 담는다. 이름 옆의 `+16.9%p` 가 벌어진 폭이다.
    """
    items = [(r["name"], float(r["target"]), float(r["current"])) for r in rows]
    if cash_weight > 0:
        items.append(("현금", 0.0, round(cash_weight, 1)))

    labels, target, current, colors = [], [], [], []
    for name, tgt, cur in items:
        gap = cur - tgt
        if tgt == 0:
            labels.append(f"{name}   (목표 없음)")
        elif abs(gap) < 0.05:
            labels.append(f"{name}   목표와 같음")
        else:
            labels.append(f"{name}   {gap:+.1f}%p")
        target.append(round(tgt, 1) or None)
        current.append(round(cur, 1))
        # 벌어진 쪽을 색으로 가른다. 5%p 를 넘으면 눈에 띄게.
        colors.append(CURRENT if abs(gap) >= 5 and tgt else "#7BA894")

    config = {
        "type": "horizontalBar",
        "data": {
            "labels": labels,
            "datasets": [
                {"label": "목표 비중(%)", "data": target,
                 "backgroundColor": "#CBD9D1", "borderWidth": 0, "barPercentage": 0.9},
                {"label": "지금 비중(%)", "data": current,
                 "backgroundColor": colors, "borderWidth": 0, "barPercentage": 0.9},
            ],
        },
        "options": {
            "title": {"display": True,
                      "text": ["포트폴리오 · 지금과 목표", stamp()],
                      "fontSize": 17, "fontStyle": "bold",
                      "fontColor": INK, "fontFamily": FONT, "padding": 12},
            "legend": {"position": "top", "align": "start",
                       "labels": {"boxWidth": 13, "fontSize": 13, "fontColor": MUTED,
                                  "fontFamily": FONT, "padding": 12}},
            "layout": {"padding": {"left": 6, "right": 30, "top": 2, "bottom": 4}},
            "scales": {
                "xAxes": [{"ticks": {"beginAtZero": True,
                                     "fontColor": MUTED, "fontSize": 12, "fontFamily": FONT},
                           "gridLines": {"color": GRID, "drawBorder": False}}],
                "yAxes": [{"ticks": {"fontColor": INK, "fontSize": 13, "fontFamily": FONT},
                           "gridLines": {"display": False, "drawBorder": False}}],
            },
            "plugins": {"datalabels": {
                "display": True, "anchor": "end", "align": "right", "offset": 3,
                "color": INK, "font": {"size": 12, "family": FONT, "weight": "bold"},
            }},
        },
    }
    q = urllib.parse.urlencode({
        "c": json.dumps(config, ensure_ascii=False, separators=(",", ":")),
        "w": 660, "h": 40 * len(items) + 130, "bkg": CANVAS,
    })
    return branded(f"https://quickchart.io/chart?{q}", ratio=0.12)

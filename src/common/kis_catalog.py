"""KIS Trading MCP 166개 API를 AI 없이 빠르게 찾는 수업용 색인."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


CATALOG = Path(__file__).with_name("fixtures") / "kis_trading_catalog.json"
DOMAIN_LABELS = {
    "auth": "인증",
    "domestic_bond": "국내채권",
    "domestic_futureoption": "국내선물옵션",
    "domestic_stock": "국내주식",
    "elw": "ELW",
    "etfetn": "ETF·ETN",
    "overseas_futureoption": "해외선물옵션",
    "overseas_stock": "해외주식",
}
SYNONYMS = {
    "가격": ("가격", "현재가", "시세", "차트", "호가", "분봉", "일별"),
    "차트": ("차트", "분봉", "일별", "기간별", "시세"),
    "순위": ("순위", "시가총액", "거래량", "등락률", "체결강도"),
    "수급": ("수급", "외국인", "기관", "프로그램", "투자자", "순매수", "공매도", "대차"),
    "실적": ("실적", "투자의견", "추정", "재무", "배당", "기업"),
    "계좌": ("계좌", "잔고", "보유", "미체결", "체결내역", "매수가능", "손익"),
    "주문": ("주문", "정정", "취소", "매수", "매도"),
    "시장": ("시장", "지수", "업종", "순위"),
    "뉴스": ("뉴스", "공시"),
}


def load_catalog() -> dict:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    if int(payload.get("total", 0)) != 166 or len(payload.get("apis") or []) != 166:
        raise ValueError("KIS Trading MCP 카탈로그가 166개 정본과 맞지 않습니다.")
    return payload


def ingredient_counts() -> list[tuple[str, int]]:
    counts = Counter(row["ingredient"] for row in load_catalog()["apis"])
    order = (
        "가격·차트", "순위·스크리닝", "수급", "실적·기업", "지수·시장",
        "뉴스·공시", "계좌·잔고", "주문·정정·취소", "기타 조회", "인증",
    )
    return [(name, counts[name]) for name in order if counts[name]]


def search_catalog(query: str, *, limit: int = 10) -> list[dict[str, str]]:
    raw = query.strip().lower()
    if not raw:
        return []
    terms = {raw}
    for key, values in SYNONYMS.items():
        if raw == key or raw in values:
            terms.update(value.lower() for value in values)
    scored: list[tuple[int, dict[str, str]]] = []
    for row in load_catalog()["apis"]:
        fields = " ".join(str(value).lower() for value in row.values())
        score = sum(3 if term == raw else 1 for term in terms if term in fields)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1]["domain"], item[1]["api_name"]))
    return [row for _, row in scored[:limit]]


def render_catalog(query: str = "") -> str:
    value = query.strip()
    if not value:
        counts = " · ".join(f"{name} {count}" for name, count in ingredient_counts())
        domains = " · ".join(
            f"{DOMAIN_LABELS.get(name, name)} {count}"
            for name, count in load_catalog()["domains"].items()
        )
        return "\n".join([
            "[KIS Trading MCP · 전략 재료 지도]",
            "공식 호출 API 166개 · Hermes에서는 8개 분야 입구로 보입니다.",
            "",
            counts,
            "",
            domains,
            "",
            "찾아보기: /ts_tools 수급 · /ts_tools 실적 · /ts_tools 순위 · /ts_tools 주문",
            "전략은 이 재료 중 필요한 것만 골라 호출합니다. 166개를 한 번에 부르지 않습니다.",
        ])
    rows = search_catalog(value)
    if not rows:
        return "\n".join([
            f"[KIS Trading MCP 재료 검색 · {value}]",
            "맞는 API를 찾지 못했습니다.",
            "예: /ts_tools 수급 · /ts_tools 실적 · /ts_tools 계좌 · /ts_tools 주문",
        ])
    lines = [f"[KIS Trading MCP 재료 검색 · {value}]", f"166개 중 관련도가 높은 {len(rows)}개", ""]
    for row in rows:
        domain = DOMAIN_LABELS.get(row["domain"], row["domain"])
        lines.append(f"- {row['name']} · {domain} · {row['ingredient']}")
        lines.append(f"  api_name: {row['api_name']}")
    lines += [
        "",
        "Hermes에게 이 이름을 말하면 알맞은 분야 도구로 호출할 수 있습니다.",
        "조회는 가능하지만 주문·정정·취소는 모의계좌와 사람 승인을 다시 확인합니다.",
    ]
    return "\n".join(lines)

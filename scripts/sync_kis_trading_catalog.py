#!/usr/bin/env python3
"""KIS Trading MCP 공식 configs 166개를 수업용 검색 카탈로그로 고정한다."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CONFIG_FILES = (
    "auth.json",
    "domestic_bond.json",
    "domestic_futureoption.json",
    "domestic_stock.json",
    "elw.json",
    "etfetn.json",
    "overseas_futureoption.json",
    "overseas_stock.json",
)


def _ingredient(name: str, category: str, method: str) -> str:
    identity = f"{name} {method}".lower()
    text = f"{identity} {category}".lower()
    if any(word in identity for word in ("잔고", "미체결", "체결내역", "매수가능", "손익", "balance", "profit")):
        return "계좌·잔고"
    if any(word in identity for word in ("주문", "정정", "취소", "order", "modify", "cancel")):
        return "주문·정정·취소"
    rules = (
        ("수급", ("외국인", "기관", "프로그램", "투자자", "순매수", "공매도", "대차")),
        ("실적·기업", ("실적", "투자의견", "추정", "재무", "배당", "종목정보")),
        ("순위·스크리닝", ("순위", "시가총액", "거래량", "등락률", "체결강도", "상승", "하락")),
        ("가격·차트", ("현재가", "시세", "호가", "차트", "분봉", "일별", "기간별")),
        ("지수·시장", ("지수", "업종", "시장", "index", "sector")),
        ("뉴스·공시", ("뉴스", "공시")),
        ("인증", ("토큰", "auth")),
    )
    for label, words in rules:
        if any(word in text for word in words):
            return label
    return "기타 조회"


def build(source: Path) -> dict:
    rows: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    for filename in CONFIG_FILES:
        path = source / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        domain = path.stem
        apis = payload.get("apis") or {}
        counts[domain] = len(apis)
        for api_name, item in apis.items():
            name = str(item.get("name") or api_name)
            category = str(item.get("category") or "")
            method = str(item.get("method") or api_name)
            rows.append({
                "domain": domain,
                "api_name": str(api_name),
                "name": name,
                "category": category,
                "ingredient": _ingredient(name, category, method),
                "method": method,
                "api_path": str(item.get("api_path") or ""),
                "github_url": str(item.get("github_url") or ""),
            })
    rows.sort(key=lambda row: (row["domain"], row["category"], row["api_name"]))
    return {
        "source": "koreainvestment/open-trading-api · MCP/Kis Trading MCP/configs",
        "schema_version": 1,
        "total": len(rows),
        "domains": counts,
        "apis": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="공식 Trading MCP configs 폴더")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("src/common/fixtures/kis_trading_catalog.json"),
    )
    args = parser.parse_args()
    catalog = build(args.source)
    if catalog["total"] != 166:
        raise SystemExit(f"공식 카탈로그가 166개가 아닙니다: {catalog['total']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"KIS Trading MCP 카탈로그 {catalog['total']}개 저장")


if __name__ == "__main__":
    main()

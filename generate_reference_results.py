"""강사용: 비공식 월별 조정주가로 고정 참조 결과를 다시 만든다.

학생 수업은 이 명령을 실행하지 않고, 커밋된 결과와 작은 스냅샷을 사용한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from common.reference_data import fetch_adjusted_monthly_returns  # noqa: E402
from common.reference_momentum import (  # noqa: E402
    content_hash,
    materialize_market_manifest,
    run_reference_backtest,
)

FIXTURES = ROOT / "src" / "common" / "fixtures"
MANIFEST_PATH = FIXTURES / "reference_manifest.json"
RETRIEVED_AT = "2026-08-28"


def month_range(start: str, end: str) -> list[str]:
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    values = []
    while (year, month) <= (end_year, end_month):
        values.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return values


def save_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results: dict[str, dict] = {}
    snapshots: dict[str, dict] = {}

    for market in ("US", "KR"):
        contract = materialize_market_manifest(manifest, market)
        symbols = contract["symbols"]
        print(f"{market}: {len(symbols)}개 종목과 벤치마크를 가져옵니다.")
        stocks = {
            symbol: fetch_adjusted_monthly_returns(symbol)
            for symbol in symbols
        }
        benchmark_symbol = contract["benchmark"]["symbol"]
        benchmark_returns = fetch_adjusted_monthly_returns(benchmark_symbol)
        market_data = {
            "schema_version": 1,
            "market": market,
            "currency": contract["currency"],
            "adjustment": contract["adjustment"],
            "holding_months": month_range("2016-01", "2025-12"),
            "stocks": stocks,
            "benchmark": {
                **contract["benchmark"],
                "adjustment": contract["adjustment"],
                "returns": benchmark_returns,
            },
        }
        result = run_reference_backtest(contract, market_data)
        result.pop("result_hash")
        result["metadata"] = {
            "source": "Yahoo Finance chart endpoint (unofficial)",
            "retrieved_at": RETRIEVED_AT,
            "universe_method": contract["universe_method"],
            "period": "2015-01 through 2025-12; 2015 warm-up",
            "adjustment": contract["adjustment"],
            "cost_bps": contract["cost_bps"],
            "generation_command": "python3 generate_reference_results.py",
            "limitations": manifest["limitations"],
            "raw_history_committed": False,
        }
        result["result_hash"] = content_hash(result)
        results[market] = result
        save_json(FIXTURES / f"{market.lower()}_momentum_result.json", result)

        snapshot_months = month_range("2024-01", "2025-02")
        snapshot = {
            "schema_version": 1,
            "market": market,
            "currency": contract["currency"],
            "adjustment": contract["adjustment"],
            "holding_months": ["2025-01", "2025-02"],
            "stocks": {
                symbol: {
                    month: value
                    for month, value in returns.items()
                    if month in snapshot_months
                }
                for symbol, returns in stocks.items()
            },
            "benchmark": {
                **contract["benchmark"],
                "adjustment": contract["adjustment"],
                "returns": {
                    month: value
                    for month, value in benchmark_returns.items()
                    if month in snapshot_months
                },
            },
            "metadata": {
                "source": "Yahoo Finance chart endpoint에서 계산한 월별 조정수익률",
                "retrieved_at": RETRIEVED_AT,
                "redistribution": "원시 시세는 포함하지 않고 수업 검산용 파생 수익률만 포함",
                "limitations": manifest["limitations"],
            },
        }
        snapshot["input_hash"] = content_hash(snapshot)
        snapshots[market] = snapshot
        save_json(FIXTURES / f"{market.lower()}_momentum_snapshot.json", snapshot)

    us_excess = results["US"]["periods"]["later"]["net_excess_return"]
    kr_excess = results["KR"]["periods"]["later"]["net_excess_return"]
    reference_market = "US" if us_excess > kr_excess else "KR"
    selection = {
        "schema_version": 1,
        "manifest_hash": content_hash(manifest),
        "reference_market": reference_market,
        "selection_rule": "later-period net excess return; KR wins exact ties",
        "later_net_excess_return": {"US": us_excess, "KR": kr_excess},
        "result_hashes": {
            market: result["result_hash"] for market, result in results.items()
        },
    }
    selection["selection_hash"] = content_hash(selection)
    save_json(FIXTURES / "reference_selection.json", selection)
    print(
        f"참조 시장: {reference_market} "
        f"(US {us_excess:+.2%}, KR {kr_excess:+.2%})"
    )


if __name__ == "__main__":
    main()

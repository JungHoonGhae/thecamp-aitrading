"""월간 고정 결과와 짧은 스냅샷으로 리밸런싱 주기만 비교한다.

전체 기간 원시 시세는 저장소에 없다. 숙제는 커밋된 월간 결과와
검산용 스냅샷만 사용한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .reference_momentum import materialize_market_manifest, run_reference_backtest


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _period_row(period: dict) -> dict:
    return {
        "start": period["start"],
        "end": period["end"],
        "net_compounded_return": period["net_compounded_return"],
        "net_excess_return": period["net_excess_return"],
        "maximum_drawdown": period["maximum_drawdown"],
        "buy_turnover": period["buy_turnover"],
        "sell_turnover": period["sell_turnover"],
    }


def _snapshot_row(result: dict) -> dict:
    months = result["months"]
    return {
        "holding_months": [row["month"] for row in months],
        "rebalance_months": [row["month"] for row in months if row["is_rebalance_month"]],
        "held_months": [row["month"] for row in months if not row["is_rebalance_month"]],
        "buy_turnover": sum(row["buy_turnover"] for row in months),
        "sell_turnover": sum(row["sell_turnover"] for row in months),
        "scheduled_exits": {
            row["month"]: list(row["scheduled_exits"]) for row in months
        },
        "net_compounded_return": result["summary"]["net_compounded_return"],
    }


def compare_rebalance(fixtures: Path, rebalance_months: int = 3) -> dict:
    """고정 월간 결과와 스냅샷의 1개월·N개월 리밸런싱을 나란히 본다."""
    if rebalance_months < 2:
        raise ValueError("비교할 주기는 2개월 이상이어야 합니다.")
    manifest = _load(fixtures / "reference_manifest.json")
    markets = {}
    for market in ("US", "KR"):
        frozen = _load(fixtures / f"{market.lower()}_momentum_result.json")
        snapshot = _load(fixtures / f"{market.lower()}_momentum_snapshot.json")
        snapshot.pop("input_hash", None)
        monthly_contract = materialize_market_manifest(manifest, market)
        quarterly_manifest = dict(manifest)
        quarterly_manifest["rebalance_months"] = rebalance_months
        quarterly_contract = materialize_market_manifest(quarterly_manifest, market)
        markets[market] = {
            "frozen_monthly": {
                "earlier": _period_row(frozen["periods"]["earlier"]),
                "later": _period_row(frozen["periods"]["later"]),
            },
            "snapshot_monthly": _snapshot_row(
                run_reference_backtest(monthly_contract, snapshot)
            ),
            "snapshot_compare": _snapshot_row(
                run_reference_backtest(quarterly_contract, snapshot)
            ),
        }
    return {
        "schema_version": 1,
        "rule": "course-momentum-12-2-v1",
        "compare_rebalance_months": rebalance_months,
        "note": (
            "전체 기간 3개월 결과는 원시 시세가 없어 다시 계산하지 않습니다. "
            "나중 구간 숫자는 고정 월간 결과이고, 청산이 미뤄지는지는 "
            "짧은 스냅샷으로 확인합니다."
        ),
        "markets": markets,
    }

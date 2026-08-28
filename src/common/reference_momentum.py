"""수업용 12–2 모멘텀 참조 실험의 결정적 계산 코어."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class BacktestContractError(ValueError):
    """비교 가능한 백테스트를 만들 수 없을 때 발생한다."""


def canonical_json(value: Any) -> str:
    """해시와 저장에 공통으로 쓰는 정규 JSON."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def materialize_market_manifest(manifest: dict, market: str) -> dict:
    """한 개의 공통 manifest에서 시장별 실행 계약을 만든다."""
    markets = manifest.get("markets") or {}
    if market not in markets:
        raise BacktestContractError(f"manifest has no {market} market")
    selected = {key: value for key, value in manifest.items() if key != "markets"}
    selected.update(markets[market])
    selected["market"] = market
    selected["source_manifest_hash"] = content_hash(manifest)
    return selected


def _shift_month(month: str, offset: int) -> str:
    year_text, month_text = month.split("-", 1)
    index = int(year_text) * 12 + int(month_text) - 1 + offset
    year, zero_based_month = divmod(index, 12)
    return f"{year:04d}-{zero_based_month + 1:02d}"


def formation_months(holding_month: str) -> tuple[str, ...]:
    """보유월 H의 신호 구간 H-12..H-2를 돌려준다."""
    return tuple(_shift_month(holding_month, offset) for offset in range(-12, -1))


def formation_return(
    monthly_returns: dict[str, float],
    holding_month: str,
) -> float | None:
    """완전한 형성 구간만 복리 수익률로 계산한다."""
    months = formation_months(holding_month)
    if any(month not in monthly_returns for month in months):
        return None
    wealth = 1.0
    for month in months:
        wealth *= 1.0 + float(monthly_returns[month])
    return wealth - 1.0


def select_top_fraction(
    scores: dict[str, float],
    fraction: float,
) -> tuple[str, ...]:
    if not scores:
        return ()
    if not 0 < fraction <= 1:
        raise BacktestContractError("top_fraction must be greater than 0 and at most 1")
    count = max(1, math.ceil(len(scores) * fraction))
    ranked = sorted(scores, key=lambda ticker: (-scores[ticker], ticker))
    return tuple(ranked[:count])


def max_drawdown(returns: list[float]) -> float:
    wealth = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        wealth *= 1.0 + float(value)
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - 1.0)
    return worst


def loss_review_alerts(
    month_end_closes_since_entry: dict[str, list[float]],
    *,
    threshold: float = 0.10,
) -> tuple[str, ...]:
    """고점 대비 하락 경고만 만든다. 매도 주문에는 영향을 주지 않는다."""
    alerts = []
    for ticker, closes in month_end_closes_since_entry.items():
        if not closes:
            continue
        peak = max(float(value) for value in closes)
        latest = float(closes[-1])
        if peak > 0 and latest / peak - 1.0 <= -threshold + 1e-12:
            alerts.append(ticker)
    return tuple(sorted(alerts))


def _turnover(
    previous: dict[str, float],
    current: dict[str, float],
) -> tuple[float, float]:
    tickers = set(previous) | set(current)
    buy = sum(max(current.get(ticker, 0.0) - previous.get(ticker, 0.0), 0.0)
              for ticker in tickers)
    sell = sum(max(previous.get(ticker, 0.0) - current.get(ticker, 0.0), 0.0)
               for ticker in tickers)
    return buy, sell


def _validate_contract(manifest: dict, data: dict) -> None:
    if manifest.get("formation_months") != 11 or manifest.get("skip_months") != 1:
        raise BacktestContractError("reference strategy requires an 11-month formation and 1 skipped month")
    if manifest.get("market") != data.get("market"):
        raise BacktestContractError("manifest and data market do not match")
    if manifest.get("currency") != data.get("currency"):
        raise BacktestContractError("manifest and data currency do not match")
    adjustment = manifest.get("adjustment")
    benchmark_adjustment = (data.get("benchmark") or {}).get("adjustment")
    if adjustment != data.get("adjustment") or adjustment != benchmark_adjustment:
        raise BacktestContractError("strategy and benchmark adjustment conventions do not match")


def summarize_periods(rows: list[dict], periods: dict[str, list[str]]) -> dict:
    summaries = {}
    for label, bounds in periods.items():
        start, end = bounds
        selected = [row for row in rows if start <= row["month"] <= end]
        net_returns = [float(row["net_return"]) for row in selected]
        benchmark_returns = [float(row["benchmark_return"]) for row in selected]
        net_compounded = _compound(net_returns)
        benchmark_compounded = _compound(benchmark_returns)
        summaries[label] = {
            "start": start,
            "end": end,
            "months": len(selected),
            "net_compounded_return": net_compounded,
            "benchmark_compounded_return": benchmark_compounded,
            "net_excess_return": net_compounded - benchmark_compounded,
            "maximum_drawdown": max_drawdown(net_returns),
            "buy_turnover": sum(float(row["buy_turnover"]) for row in selected),
            "sell_turnover": sum(float(row["sell_turnover"]) for row in selected),
        }
    return summaries


def run_reference_backtest(manifest: dict, data: dict) -> dict:
    """한 시장의 월별 선택·비용·벤치마크를 동일 계약으로 계산한다."""
    _validate_contract(manifest, data)
    stocks = data.get("stocks") or {}
    benchmark = data.get("benchmark") or {}
    benchmark_returns = benchmark.get("returns") or {}
    top_fraction = float(manifest["top_fraction"])
    buy_rate = float(manifest["cost_bps"]["buy"]) / 10_000
    sell_rate = float(manifest["cost_bps"]["sell"]) / 10_000
    rebalance_months = int(manifest.get("rebalance_months", 1))
    if rebalance_months < 1:
        raise BacktestContractError("rebalance_months must be at least 1")

    previous_weights: dict[str, float] = {}
    previous_scores: dict[str, float] = {}
    rows = []
    for index, holding_month in enumerate(data.get("holding_months") or []):
        is_rebalance_month = index % rebalance_months == 0
        if is_rebalance_month:
            scores = {
                ticker: score
                for ticker, returns in stocks.items()
                if (score := formation_return(returns, holding_month)) is not None
            }
            selected = select_top_fraction(scores, top_fraction)
            if not selected:
                raise BacktestContractError(
                    f"{holding_month} has no eligible stocks with a complete formation window"
                )
            weight = 1.0 / len(selected)
            weights = {ticker: weight for ticker in selected}
        else:
            scores = previous_scores
            selected = tuple(previous_weights)
            weights = dict(previous_weights)
        holding_returns: list[float] = []
        for ticker in selected:
            if holding_month not in stocks[ticker]:
                raise BacktestContractError(
                    f"{ticker} {holding_month} holding return is missing"
                )
            holding_returns.append(float(stocks[ticker][holding_month]))
        if holding_month not in benchmark_returns:
            raise BacktestContractError(
                f"{benchmark.get('symbol', 'benchmark')} {holding_month} return is missing"
            )

        buy_turnover, sell_turnover = _turnover(previous_weights, weights)
        gross_return = sum(holding_returns) / len(holding_returns)
        cost = buy_turnover * buy_rate + sell_turnover * sell_rate
        rows.append({
            "month": holding_month,
            "selected": list(selected),
            "scores": {ticker: scores[ticker] for ticker in selected},
            "is_rebalance_month": is_rebalance_month,
            "scheduled_exits": sorted(set(previous_weights) - set(weights)),
            "gross_return": gross_return,
            "buy_turnover": buy_turnover,
            "sell_turnover": sell_turnover,
            "cost": cost,
            "net_return": gross_return - cost,
            "benchmark_return": float(benchmark_returns[holding_month]),
        })
        previous_weights = weights
        previous_scores = scores

    net_returns = [row["net_return"] for row in rows]
    benchmark_values = [row["benchmark_return"] for row in rows]
    result = {
        "schema_version": 1,
        "strategy_id": manifest["strategy_id"],
        "market": data["market"],
        "currency": data["currency"],
        "manifest_hash": manifest.get("source_manifest_hash") or content_hash(manifest),
        "input_hash": content_hash(data),
        "months": rows,
        "summary": {
            "net_compounded_return": _compound(net_returns),
            "benchmark_compounded_return": _compound(benchmark_values),
            "net_excess_return": _compound(net_returns) - _compound(benchmark_values),
            "maximum_drawdown": max_drawdown(net_returns),
            "buy_turnover": sum(row["buy_turnover"] for row in rows),
            "sell_turnover": sum(row["sell_turnover"] for row in rows),
        },
        "periods": summarize_periods(rows, manifest.get("periods") or {}),
    }
    result["result_hash"] = content_hash(result)
    return result


def _compound(returns: list[float]) -> float:
    wealth = 1.0
    for value in returns:
        wealth *= 1.0 + value
    return wealth - 1.0

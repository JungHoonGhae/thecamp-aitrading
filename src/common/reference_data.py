"""강사용 참조 데이터 취득과 Yahoo 월별 조정주가 정규화."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .reference_momentum import BacktestContractError

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = {"User-Agent": "Mozilla/5.0 (ai-trading-lab course research)"}


def adjusted_monthly_returns(payload: dict) -> dict[str, float]:
    """Yahoo chart 응답의 조정주가를 인접 월 수익률로 바꾼다."""
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        raise BacktestContractError("market data response has no chart result")
    result = results[0]
    timestamps = result.get("timestamp") or []
    adjusted = (
        (result.get("indicators") or {}).get("adjclose") or [{}]
    )[0].get("adjclose") or []
    if len(timestamps) != len(adjusted):
        raise BacktestContractError("market data timestamps and adjusted closes differ")

    observations = [
        (
            datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime("%Y-%m"),
            None if close is None else float(close),
        )
        for timestamp, close in zip(timestamps, adjusted)
    ]
    returns: dict[str, float] = {}
    for (previous_month, previous), (month, current) in zip(
        observations, observations[1:]
    ):
        if previous is None or current is None or previous <= 0:
            continue
        if previous_month == month:
            raise BacktestContractError(f"duplicate monthly observation for {month}")
        returns[month] = round(current / previous - 1.0, 12)
    return returns


def fetch_adjusted_monthly_returns(
    symbol: str,
    *,
    start: str = "2014-12-01",
    end: str = "2026-01-02",
) -> dict[str, float]:
    """비공식 Yahoo chart endpoint에서 월별 조정수익률을 가져온다."""
    period1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())
    params = urllib.parse.urlencode({
        "period1": period1,
        "period2": period2,
        "interval": "1mo",
        "events": "div,splits",
        "includeAdjustedClose": "true",
    })
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol)) + "?" + params
    with urllib.request.urlopen(
        urllib.request.Request(url, headers=USER_AGENT),
        timeout=30,
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return adjusted_monthly_returns(payload)

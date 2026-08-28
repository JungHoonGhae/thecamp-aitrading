from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common.reference_momentum import (  # noqa: E402
    BacktestContractError,
    formation_months,
    formation_return,
    loss_review_alerts,
    materialize_market_manifest,
    max_drawdown,
    run_reference_backtest,
    select_top_fraction,
    summarize_periods,
)


class ReferenceMomentumTests(unittest.TestCase):
    def test_formation_window_uses_h_minus_12_through_h_minus_2(self):
        months = formation_months("2024-02")

        self.assertEqual(months[0], "2023-02")
        self.assertEqual(months[-1], "2023-12")
        self.assertEqual(len(months), 11)
        self.assertNotIn("2024-01", months)

    def test_formation_return_ignores_the_skipped_month(self):
        returns = {month: 0.01 for month in formation_months("2024-02")}
        returns["2024-01"] = -0.99

        result = formation_return(returns, "2024-02")

        self.assertAlmostEqual(result, (1.01**11) - 1)

    def test_incomplete_formation_window_is_ineligible(self):
        returns = {month: 0.01 for month in formation_months("2024-02")}
        del returns["2023-08"]

        self.assertIsNone(formation_return(returns, "2024-02"))

    def test_top_twenty_percent_uses_ceiling_and_ticker_tie_break(self):
        scores = {
            "ZZZ": 0.10,
            "AAA": 0.10,
            "BBB": 0.05,
            "CCC": 0.04,
            "DDD": 0.03,
            "EEE": 0.02,
        }

        self.assertEqual(select_top_fraction(scores, 0.20), ("AAA", "ZZZ"))

    def test_missing_selected_holding_return_invalidates_result(self):
        data = _market_data(
            holding_months=("2024-02",),
            stock_returns={"AAA": {}, "BBB": {"2024-02": 0.01}},
        )

        with self.assertRaisesRegex(
            BacktestContractError, "AAA.*2024-02.*holding return"
        ):
            run_reference_backtest(_manifest(), data)

    def test_directional_costs_reconcile_with_turnover(self):
        data = _market_data(
            holding_months=("2024-02",),
            stock_returns={
                "AAA": {"2024-02": 0.02},
                "BBB": {"2024-02": 0.01},
            },
        )

        result = run_reference_backtest(_manifest(), data)
        row = result["months"][0]

        self.assertEqual(row["selected"], ["AAA"])
        self.assertAlmostEqual(row["buy_turnover"], 1.0)
        self.assertAlmostEqual(row["sell_turnover"], 0.0)
        self.assertAlmostEqual(row["gross_return"], 0.02)
        self.assertAlmostEqual(row["cost"], 0.001)
        self.assertAlmostEqual(row["net_return"], 0.019)

    def test_strategy_and_benchmark_conventions_must_match(self):
        data = _market_data(
            holding_months=("2024-02",),
            stock_returns={
                "AAA": {"2024-02": 0.02},
                "BBB": {"2024-02": 0.01},
            },
        )
        data["benchmark"]["adjustment"] = "price_return"

        with self.assertRaisesRegex(BacktestContractError, "adjustment"):
            run_reference_backtest(_manifest(), data)

    def test_max_drawdown_uses_compounded_wealth_path(self):
        self.assertAlmostEqual(max_drawdown([0.10, -0.20, 0.05]), -0.20)

    def test_combined_manifest_hash_survives_market_selection(self):
        combined = {
            "schema_version": 1,
            "strategy_id": "course-momentum-12-2-v1",
            "formation_months": 11,
            "skip_months": 1,
            "top_fraction": 0.2,
            "rebalance_months": 1,
            "adjustment": "total_return",
            "periods": _manifest()["periods"],
            "markets": {
                "US": {
                    "currency": "USD",
                    "cost_bps": {"buy": 10, "sell": 10},
                }
            },
        }

        selected = materialize_market_manifest(combined, "US")

        self.assertEqual(len(selected["source_manifest_hash"]), 64)
        self.assertEqual(selected["market"], "US")
        self.assertNotIn("markets", selected)

    def test_ten_percent_peak_loss_is_review_only(self):
        alerts = loss_review_alerts(
            {"AAA": [100.0, 110.0, 99.0], "BBB": [100.0, 105.0, 100.0]},
            threshold=0.10,
        )

        self.assertEqual(alerts, ("AAA",))

    def test_period_summary_reports_net_benchmark_drawdown_and_turnover(self):
        rows = [
            {
                "month": "2020-12",
                "net_return": 0.10,
                "benchmark_return": 0.05,
                "buy_turnover": 1.0,
                "sell_turnover": 0.0,
            },
            {
                "month": "2021-01",
                "net_return": -0.20,
                "benchmark_return": -0.10,
                "buy_turnover": 0.5,
                "sell_turnover": 0.5,
            },
        ]

        summary = summarize_periods(
            rows,
            {"earlier": ["2020-12", "2020-12"], "later": ["2021-01", "2021-01"]},
        )

        self.assertAlmostEqual(summary["earlier"]["net_compounded_return"], 0.10)
        self.assertAlmostEqual(summary["earlier"]["net_excess_return"], 0.05)
        self.assertAlmostEqual(summary["later"]["maximum_drawdown"], -0.20)
        self.assertAlmostEqual(summary["later"]["buy_turnover"], 0.5)

    def test_three_month_homework_keeps_names_until_next_review(self):
        months = ("2024-02", "2024-03", "2024-04")
        all_formation_months = {
            month
            for holding_month in months
            for month in formation_months(holding_month)
        }
        stocks = {
            "AAA": {month: 0.0 for month in all_formation_months},
            "BBB": {month: 0.0 for month in all_formation_months},
        }
        stocks["AAA"]["2023-02"] = 1.0
        stocks["BBB"]["2023-02"] = -0.5
        stocks["AAA"]["2024-01"] = -0.5
        stocks["BBB"]["2024-01"] = 1.0
        for ticker in stocks:
            stocks[ticker].update({month: 0.01 for month in months})
        data = {
            "schema_version": 1,
            "market": "US",
            "currency": "USD",
            "adjustment": "total_return",
            "holding_months": list(months),
            "stocks": stocks,
            "benchmark": {
                "symbol": "SP500TR",
                "adjustment": "total_return",
                "returns": {month: 0.0 for month in months},
            },
        }
        manifest = _manifest()
        manifest["rebalance_months"] = 3
        manifest["top_fraction"] = 0.5

        result = run_reference_backtest(manifest, data)

        self.assertEqual(
            [row["selected"] for row in result["months"]],
            [["AAA"], ["AAA"], ["AAA"]],
        )
        self.assertEqual(
            [row["is_rebalance_month"] for row in result["months"]],
            [True, False, False],
        )
        self.assertAlmostEqual(result["months"][1]["buy_turnover"], 0.0)


def _manifest() -> dict:
    return {
        "schema_version": 1,
        "strategy_id": "course-momentum-12-2-v1",
        "formation_months": 11,
        "skip_months": 1,
        "top_fraction": 0.20,
        "rebalance_months": 1,
        "adjustment": "total_return",
        "market": "US",
        "currency": "USD",
        "cost_bps": {"buy": 10, "sell": 10},
        "periods": {
            "earlier": ["2024-02", "2024-02"],
            "later": ["2024-03", "2024-03"],
        },
    }


def _market_data(
    *,
    holding_months: tuple[str, ...],
    stock_returns: dict[str, dict[str, float]],
) -> dict:
    formation = {
        "AAA": {month: 0.02 for month in formation_months("2024-02")},
        "BBB": {month: 0.01 for month in formation_months("2024-02")},
    }
    for ticker, rows in stock_returns.items():
        formation[ticker].update(rows)
    benchmark_returns = {month: 0.005 for month in holding_months}
    return {
        "schema_version": 1,
        "market": "US",
        "currency": "USD",
        "adjustment": "total_return",
        "holding_months": list(holding_months),
        "stocks": formation,
        "benchmark": {
            "symbol": "SP500TR",
            "adjustment": "total_return",
            "returns": benchmark_returns,
        },
    }


if __name__ == "__main__":
    unittest.main()

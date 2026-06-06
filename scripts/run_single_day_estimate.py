"""Run a single-day NAV estimate smoke test for the NAVigator MVP."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.estimator import NAVEstimator  # noqa: E402


def fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def main() -> None:
    holdings = pd.read_csv(
        PROJECT_ROOT / "data/manual/fund_holdings.csv",
        dtype={"fund_code": str},
    )
    fund_info = pd.read_csv(
        PROJECT_ROOT / "data/manual/fund_info.csv",
        dtype={"fund_code": str},
    )
    asset_returns = pd.read_csv(PROJECT_ROOT / "data/processed/asset_prices.csv")
    fx_rates = pd.read_csv(PROJECT_ROOT / "data/processed/fx_rates.csv")

    estimator = NAVEstimator()
    result = estimator.estimate_single_day(
        fund_code="001118",
        target_date="2026-06-02",
        holdings=holdings,
        fund_info=fund_info,
        asset_returns=asset_returns,
        fx_rates=fx_rates,
    )

    print("NAV estimate")
    print(f"Fund: {result.fund_name} ({result.fund_code})")
    print(f"Date: {result.date}")
    print(f"Estimated return: {fmt_pct(result.estimated_return)}")
    print()
    print("Contribution summary")
    print(f"Top holdings contribution: {fmt_pct(result.top_holdings_contribution)}")
    print(f"Uncovered contribution: {fmt_pct(result.uncovered_contribution)}")
    print(f"FX contribution: {fmt_pct(result.fx_contribution)}")
    print(f"Fee impact: {fmt_pct(result.fee_impact)}")
    print(f"Covered weight: {fmt_pct(result.covered_weight)}")
    print(f"Uncovered weight: {fmt_pct(result.uncovered_weight)}")
    print(
        "Benchmark: "
        f"{result.benchmark_ticker} ({fmt_pct(result.benchmark_return)})"
    )

    missing_tickers = result.diagnostics["missing_tickers"]
    if missing_tickers:
        print(f"Missing tickers: {', '.join(missing_tickers)}")
    else:
        print("Missing tickers: none")

    print()
    print("Contribution table")
    sorted_table = result.contribution_table.sort_values(
        "contribution",
        ascending=False,
    )
    print(sorted_table.to_string(index=False))

    output_dir = PROJECT_ROOT / "data/processed"
    result.contribution_table.to_csv(
        output_dir / "nav_contribution_table.csv",
        index=False,
    )

    summary = pd.DataFrame(
        [
            {
                "date": result.date,
                "fund_code": result.fund_code,
                "fund_name": result.fund_name,
                "estimated_return": result.estimated_return,
                "top_holdings_contribution": result.top_holdings_contribution,
                "uncovered_contribution": result.uncovered_contribution,
                "fx_contribution": result.fx_contribution,
                "fee_impact": result.fee_impact,
                "covered_weight": result.covered_weight,
                "uncovered_weight": result.uncovered_weight,
                "benchmark_ticker": result.benchmark_ticker,
                "benchmark_return": result.benchmark_return,
                "fx_pair": result.fx_pair,
                "fx_return": result.fx_return,
                "annual_fee_rate": result.annual_fee_rate,
                "daily_fee_rate": result.daily_fee_rate,
                "model_version": result.diagnostics["model_version"],
                "missing_tickers": ",".join(missing_tickers),
            }
        ]
    )
    summary.to_csv(output_dir / "nav_estimate_summary.csv", index=False)


if __name__ == "__main__":
    main()

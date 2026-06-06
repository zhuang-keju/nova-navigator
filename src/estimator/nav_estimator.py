"""Pure NAV estimation logic for the NAVigator MVP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

MODEL_VERSION = "top_holdings_plus_benchmark_v0"

CONTRIBUTION_COLUMNS = [
    "date",
    "fund_code",
    "component_type",
    "symbol",
    "name",
    "weight",
    "return",
    "contribution",
    "note",
]


@dataclass
class NAVEstimateResult:
    """
    Structured result for one fund's one-day NAV return estimation.

    All return and contribution values are decimal returns:
    0.0157 means +1.57%.
    """

    fund_code: str
    fund_name: str
    date: str

    estimated_return: float

    top_holdings_contribution: float
    uncovered_contribution: float
    fx_contribution: float
    fee_impact: float

    covered_weight: float
    uncovered_weight: float
    benchmark_ticker: str
    benchmark_return: float

    fx_pair: str
    fx_return: float

    annual_fee_rate: float
    daily_fee_rate: float

    contribution_table: pd.DataFrame
    diagnostics: dict[str, Any]


class NAVEstimator:
    """Estimate one-day fund NAV returns from already-prepared market DataFrames."""

    def estimate_single_day(
        self,
        fund_code: str,
        target_date: str,
        holdings: pd.DataFrame,
        fund_info: pd.DataFrame,
        asset_returns: pd.DataFrame,
        fx_rates: pd.DataFrame,
    ) -> NAVEstimateResult:
        """Estimate one fund's one-day NAV return.

        The estimator deliberately does not fetch data, call yfinance, or read CSV
        files. Keeping it as pure calculation logic makes the model deterministic
        and easy to test: callers are responsible for loading and validating the
        input DataFrames before asking for an estimate.
        """
        fund_holdings = holdings[holdings["fund_code"].astype(str) == str(fund_code)].copy()
        if fund_holdings.empty:
            raise ValueError(f"No holdings found for fund_code={fund_code}.")

        fund_rows = fund_info[fund_info["fund_code"].astype(str) == str(fund_code)]
        if fund_rows.empty:
            raise ValueError(f"No fund_info found for fund_code={fund_code}.")

        info = fund_rows.iloc[0]
        fund_name = str(info["fund_name"])
        benchmark_ticker = str(info["benchmark_ticker"])
        asset_currency = str(info["asset_currency"]).upper()
        base_currency = str(info["base_currency"]).upper()
        fx_pair = f"{asset_currency}/{base_currency}"

        target_date_str = str(pd.to_datetime(target_date).date())
        asset_on_date = self._rows_for_date(asset_returns, target_date_str)
        fx_on_date = self._rows_for_date(fx_rates, target_date_str)

        rows: list[dict[str, Any]] = []
        missing_tickers: list[str] = []
        top_holdings_contribution = 0.0
        covered_weight = 0.0

        for holding in fund_holdings.itertuples(index=False):
            ticker = str(holding.ticker)
            weight = float(holding.weight)
            ticker_return = self._lookup_return(
                asset_on_date,
                key_column="ticker",
                key_value=ticker,
                label=f"asset return for ticker={ticker}",
                required=False,
            )

            if ticker_return is None:
                # MVP behavior: missing disclosed holding returns are skipped so a
                # partial estimate can still be produced. The skipped tickers are
                # surfaced in diagnostics, and a later version can replace this
                # with stricter validation or a fallback return model.
                missing_tickers.append(ticker)
                continue

            contribution = weight * ticker_return
            top_holdings_contribution += contribution
            covered_weight += weight
            rows.append(
                {
                    "date": target_date_str,
                    "fund_code": str(fund_code),
                    "component_type": "holding",
                    "symbol": ticker,
                    "name": str(holding.name),
                    "weight": weight,
                    "return": ticker_return,
                    "contribution": contribution,
                    "note": "disclosed holding",
                }
            )

        # Only the disclosed top holdings are known in this MVP. The remaining
        # portfolio weight is assigned to the fund benchmark, giving undisclosed
        # holdings a transparent broad-market proxy instead of pretending the
        # disclosed names are the whole portfolio.
        uncovered_weight = 1.0 - covered_weight
        benchmark_return = self._lookup_return(
            asset_on_date,
            key_column="ticker",
            key_value=benchmark_ticker,
            label=f"benchmark return for ticker={benchmark_ticker}",
            required=True,
        )
        uncovered_contribution = uncovered_weight * benchmark_return
        rows.append(
            {
                "date": target_date_str,
                "fund_code": str(fund_code),
                "component_type": "benchmark_proxy",
                "symbol": benchmark_ticker,
                "name": "Uncovered holdings proxy",
                "weight": uncovered_weight,
                "return": benchmark_return,
                "contribution": uncovered_contribution,
                "note": "proxy for undisclosed holdings",
            }
        )

        fx_return = self._lookup_return(
            fx_on_date,
            key_column="pair",
            key_value=fx_pair,
            label=f"FX return for pair={fx_pair}",
            required=True,
        )

        usd_asset_return = top_holdings_contribution + uncovered_contribution
        # Currency conversion compounds with the asset move: a CNY investor's
        # return is affected by both the USD asset return and the USD/CNY FX move,
        # so the adjustment is multiplicative rather than a simple additive spread.
        fx_adjusted_return = (1.0 + usd_asset_return) * (1.0 + fx_return) - 1.0
        fx_contribution = fx_adjusted_return - usd_asset_return
        rows.append(
            {
                "date": target_date_str,
                "fund_code": str(fund_code),
                "component_type": "fx",
                "symbol": fx_pair,
                "name": "FX adjustment",
                "weight": 1.0,
                "return": fx_return,
                "contribution": fx_contribution,
                "note": "multiplicative currency conversion effect",
            }
        )

        annual_fee_rate = float(info["management_fee"]) + float(info["custody_fee"])
        trading_days_per_year = float(info["trading_days_per_year"])
        if trading_days_per_year <= 0:
            raise ValueError("trading_days_per_year must be greater than zero.")

        # Management and custody fees are annual rates, while this estimate is for
        # a single trading day. Dividing by trading days makes the daily drag
        # comparable to the one-day asset and FX returns.
        daily_fee_rate = annual_fee_rate / trading_days_per_year
        fee_impact = -daily_fee_rate
        rows.append(
            {
                "date": target_date_str,
                "fund_code": str(fund_code),
                "component_type": "fee",
                "symbol": "annual_fee",
                "name": "Daily fee impact",
                "weight": 1.0,
                "return": fee_impact,
                "contribution": fee_impact,
                "note": "annual management and custody fee divided by trading days",
            }
        )

        estimated_return = fx_adjusted_return + fee_impact
        # The contribution table stays separate from summary fields because it is
        # an explainability artifact: downstream scripts can print, sort, or save
        # the component rows without unpacking the scalar result fields.
        contribution_table = pd.DataFrame(rows, columns=CONTRIBUTION_COLUMNS)
        diagnostics = {
            "model_version": MODEL_VERSION,
            "num_holdings_input": int(len(fund_holdings)),
            "num_holdings_used": int(len(fund_holdings) - len(missing_tickers)),
            "num_holdings_missing_return": int(len(missing_tickers)),
            "missing_tickers": missing_tickers,
            "used_benchmark_proxy": True,
            "used_fx_adjustment": True,
            "used_fee_adjustment": True,
            "asset_currency": asset_currency,
            "base_currency": base_currency,
        }

        return NAVEstimateResult(
            fund_code=str(fund_code),
            fund_name=fund_name,
            date=target_date_str,
            estimated_return=estimated_return,
            top_holdings_contribution=top_holdings_contribution,
            uncovered_contribution=uncovered_contribution,
            fx_contribution=fx_contribution,
            fee_impact=fee_impact,
            covered_weight=covered_weight,
            uncovered_weight=uncovered_weight,
            benchmark_ticker=benchmark_ticker,
            benchmark_return=benchmark_return,
            fx_pair=fx_pair,
            fx_return=fx_return,
            annual_fee_rate=annual_fee_rate,
            daily_fee_rate=daily_fee_rate,
            contribution_table=contribution_table,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _rows_for_date(df: pd.DataFrame, target_date: str) -> pd.DataFrame:
        """Return rows whose date column matches target_date as YYYY-MM-DD."""
        dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return df[dates == target_date]

    @staticmethod
    def _lookup_return(
        df: pd.DataFrame,
        key_column: str,
        key_value: str,
        label: str,
        required: bool,
    ) -> float | None:
        """Look up a decimal return in a same-date DataFrame slice."""
        matched = df[df[key_column].astype(str) == str(key_value)]
        if matched.empty:
            if required:
                raise ValueError(f"Missing required {label}.")
            return None

        value = matched.iloc[0]["return"]
        if pd.isna(value):
            if required:
                raise ValueError(f"Missing required {label}.")
            return None

        return float(value)

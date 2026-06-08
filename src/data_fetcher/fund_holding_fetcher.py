"""Fetch disclosed fund holdings from AKShare."""

from __future__ import annotations

import re

import pandas as pd


HOLDING_COLUMNS = [
    "fund_code",
    "fund_name",
    "disclosure_date",
    "ticker",
    "name",
    "weight",
    "currency",
]

AK_TICKER_COLUMN = "股票代码"
AK_NAME_COLUMN = "股票名称"
AK_WEIGHT_COLUMN = "占净值比例"
AK_QUARTER_COLUMN = "季度"
AK_REQUIRED_COLUMNS = [
    AK_TICKER_COLUMN,
    AK_NAME_COLUMN,
    AK_WEIGHT_COLUMN,
    AK_QUARTER_COLUMN,
]


class FundHoldingFetcher:
    """Fetch and normalize fund portfolio holdings from AKShare."""

    def fetch_holdings(
        self,
        fund_code: str,
        fund_name: str,
        year: str,
        asset_currency: str = "USD",
        quarter: str | None = None,
    ) -> pd.DataFrame:
        """Fetch a fund's disclosed holdings and return NAVigator's holdings schema.

        AKShare is intentionally used only in this fetcher layer. NAVEstimator should
        stay focused on estimation math and receive already-normalized inputs, which
        keeps network/data-vendor details out of model logic.
        """
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError(
                "akshare is required to fetch fund holdings. Install requirements.txt."
            ) from exc

        raw = ak.fund_portfolio_hold_em(symbol=fund_code, date=year)
        if raw is None or raw.empty:
            raise RuntimeError(
                f"No fund holdings were fetched for fund_code={fund_code}, year={year}."
            )

        self._validate_required_columns(raw)

        available_quarters = raw[AK_QUARTER_COLUMN].dropna().astype(str).unique()
        if quarter is not None:
            if quarter not in available_quarters:
                raise ValueError(
                    f"Requested quarter {quarter!r} was not found for "
                    f"fund_code={fund_code}, year={year}."
                )
            selected_quarter = quarter
        else:
            # Holdings disclosures can include multiple quarters for the same year.
            # For the MVP, use the latest disclosed portfolio by default so downstream
            # estimates are based on the freshest available holdings snapshot.
            selected_quarter = self._select_latest_quarter(raw)

        filtered = raw[raw[AK_QUARTER_COLUMN].astype(str) == selected_quarter].copy()
        if filtered.empty:
            raise RuntimeError(
                f"No holdings remain after filtering to quarter {selected_quarter!r}."
            )

        return self._normalize_holdings(
            raw=filtered,
            fund_code=fund_code,
            fund_name=fund_name,
            asset_currency=asset_currency,
        )

    @staticmethod
    def _parse_quarter_label(label: str) -> tuple[int, int] | None:
        """Parse AKShare's quarter label into a sortable ``(year, quarter)`` tuple."""
        text = str(label)
        match = re.search(r"(\d{4})年.*?([1-4一二三四])\s*季度", text)
        if match is None:
            match = re.search(r"(\d{4}).*?([1-4一二三四]).*?季度", text)
        if match is None:
            return None

        quarter_text = match.group(2)
        quarter_map = {"一": 1, "二": 2, "三": 3, "四": 4}
        quarter = (
            quarter_map[quarter_text]
            if quarter_text in quarter_map
            else int(quarter_text)
        )
        return int(match.group(1)), quarter

    def _select_latest_quarter(self, raw: pd.DataFrame) -> str:
        """Select the latest disclosure quarter returned by AKShare."""
        quarter_labels = raw[AK_QUARTER_COLUMN].dropna().astype(str).unique()
        if len(quarter_labels) == 0:
            raise RuntimeError("AKShare returned no disclosure quarter values.")

        parsed_labels: list[tuple[tuple[int, int], str]] = []
        for label in quarter_labels:
            parsed = self._parse_quarter_label(label)
            if parsed is not None:
                parsed_labels.append((parsed, label))

        if parsed_labels:
            return max(parsed_labels, key=lambda item: item[0])[1]

        # If AKShare changes the label enough that regex parsing fails, preserve its
        # returned order and use the last unique label as the best MVP fallback
        # instead of guessing.
        return quarter_labels[-1]

    def _normalize_holdings(
        self,
        raw: pd.DataFrame,
        fund_code: str,
        fund_name: str,
        asset_currency: str,
    ) -> pd.DataFrame:
        """Convert AKShare's holdings shape to NAVigator's estimator input shape."""
        self._validate_required_columns(raw)

        normalized = pd.DataFrame(
            {
                "fund_code": str(fund_code),
                "fund_name": fund_name,
                "disclosure_date": raw[AK_QUARTER_COLUMN].astype(str),
                "ticker": raw[AK_TICKER_COLUMN].astype(str).str.strip(),
                "name": raw[AK_NAME_COLUMN],
                # AKShare reports this as a percentage number: 9.32 means 9.32%.
                # NAVEstimator expects decimal weights, so 9.32 becomes 0.0932.
                "weight": pd.to_numeric(raw[AK_WEIGHT_COLUMN], errors="coerce") / 100,
                "currency": asset_currency,
            }
        )

        normalized = normalized.replace({"ticker": {"": pd.NA}})
        normalized = normalized.dropna(subset=["ticker", "weight"])
        if normalized.empty:
            raise RuntimeError(
                "No fund holdings remain after dropping missing tickers or weights."
            )

        # This exact output schema matches NAVEstimator's expected holdings input, so
        # the estimator can consume fetched holdings without reading CSVs or knowing
        # anything about AKShare's original column names.
        normalized = normalized[HOLDING_COLUMNS]
        normalized = normalized.sort_values("weight", ascending=False).reset_index(
            drop=True
        )
        return normalized

    @staticmethod
    def _validate_required_columns(raw: pd.DataFrame) -> None:
        missing_columns = [
            column for column in AK_REQUIRED_COLUMNS if column not in raw.columns
        ]
        if missing_columns:
            raise ValueError(
                f"AKShare holdings data is missing required columns: {missing_columns}"
            )

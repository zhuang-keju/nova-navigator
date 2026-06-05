"""Fetch daily FX rates from Yahoo Finance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from src.data_fetcher.schemas import FX_COLUMNS, validate_columns


class CurrencyFetcher:
    """Fetch and normalize daily foreign-exchange rates."""

    TICKER_MAP = {
        ("USD", "CNY"): "CNY=X",
        ("USD", "HKD"): "HKD=X",
        ("USD", "JPY"): "JPY=X",
        ("EUR", "USD"): "EURUSD=X",
    }

    def __init__(self, auto_adjust: bool = True) -> None:
        """Initialize the fetcher.

        Args:
            auto_adjust: Whether Yahoo Finance should return adjusted rate data.
        """
        self.auto_adjust = auto_adjust

    def fetch_daily_fx(
        self,
        base_currency: str,
        quote_currency: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """Fetch daily FX rates and returns for a supported currency pair.

        Args:
            base_currency: Base currency code, such as "USD".
            quote_currency: Quote currency code, such as "CNY".
            start: Start date accepted by yfinance, such as "2026-05-01".
            end: End date accepted by yfinance, such as "2026-06-05".

        Returns:
            A long-format DataFrame with columns date, pair, rate, return.

        Raises:
            ValueError: If the requested pair is not in TICKER_MAP.
            RuntimeError: If yfinance returns no usable data.
        """
        base = base_currency.upper()
        quote = quote_currency.upper()
        pair_key = (base, quote)
        ticker = self.TICKER_MAP.get(pair_key)
        if ticker is None:
            pair = f"{base}/{quote}"
            raise ValueError(
                f"Unsupported FX pair {pair}. Add it to CurrencyFetcher.TICKER_MAP."
            )

        raw = yf.download(
            tickers=ticker,
            start=start,
            end=end,
            auto_adjust=self.auto_adjust,
            progress=False,
        )
        if raw.empty:
            raise RuntimeError(f"No FX data was fetched for {base}/{quote}.")

        rate = self._extract_close(raw, ticker)
        if rate is None or rate.dropna().empty:
            raise RuntimeError(f"No usable FX rate data was fetched for {base}/{quote}.")

        result = rate.rename("rate").reset_index()
        result.columns = ["date", "rate"]
        result["date"] = pd.to_datetime(result["date"]).dt.date
        result["pair"] = f"{base}/{quote}"
        result["rate"] = result["rate"].astype(float)
        result["return"] = result["rate"].pct_change()
        result = result[FX_COLUMNS].sort_values("date").reset_index(drop=True)
        validate_columns(result, FX_COLUMNS)
        return result

    @staticmethod
    def _extract_close(raw: pd.DataFrame, ticker: str) -> pd.Series | None:
        """Extract the close-rate series from yfinance's output shape."""
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.get_level_values(0):
                close_data = raw["Close"]
                if isinstance(close_data, pd.Series):
                    return close_data
                if ticker in close_data.columns:
                    return close_data[ticker]
                if len(close_data.columns) == 1:
                    return close_data.iloc[:, 0]

            if "Close" in raw.columns.get_level_values(-1):
                try:
                    return raw[(ticker, "Close")]
                except KeyError:
                    return None

            return None

        if "Close" in raw.columns:
            return raw["Close"]

        return None

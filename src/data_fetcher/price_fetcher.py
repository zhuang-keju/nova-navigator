"""Fetch daily asset prices from Yahoo Finance."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import yfinance as yf

from src.data_fetcher.schemas import PRICE_COLUMNS, validate_columns


class PriceFetcher:
    """Fetch and normalize daily close prices for Yahoo Finance tickers."""

    def __init__(self, auto_adjust: bool = True) -> None:
        """Initialize the fetcher.

        Args:
            auto_adjust: Whether Yahoo Finance should return adjusted price data.
        """
        self.auto_adjust = auto_adjust

    def fetch_daily_prices(
        self,
        tickers: Sequence[str],
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """Fetch daily close prices and returns for one or more tickers.

        Args:
            tickers: Yahoo Finance ticker symbols to fetch.
            start: Start date accepted by yfinance, such as "2026-05-01".
            end: End date accepted by yfinance, such as "2026-06-05".

        Returns:
            A long-format DataFrame with columns date, ticker, close, return.

        Raises:
            ValueError: If no tickers are provided.
            RuntimeError: If yfinance returns no usable data.
        """
        cleaned_tickers = [ticker.strip() for ticker in tickers if ticker.strip()]
        if not cleaned_tickers:
            raise ValueError("At least one ticker is required.")

        raw = yf.download(
            tickers=cleaned_tickers,
            start=start,
            end=end,
            auto_adjust=self.auto_adjust,
            progress=False,
        )
        if raw.empty:
            raise RuntimeError("No price data was fetched from Yahoo Finance.")

        frames: list[pd.DataFrame] = []
        for ticker in cleaned_tickers:
            close = self._extract_close(raw, ticker, len(cleaned_tickers) == 1)
            if close is None or close.dropna().empty:
                print(f"Warning: no price data returned for ticker {ticker}; skipping.")
                continue

            ticker_df = close.rename("close").reset_index()
            ticker_df.columns = ["date", "close"]
            ticker_df["date"] = pd.to_datetime(ticker_df["date"]).dt.date
            ticker_df["ticker"] = ticker
            ticker_df["close"] = ticker_df["close"].astype(float)
            ticker_df["return"] = ticker_df["close"].pct_change()
            frames.append(ticker_df[PRICE_COLUMNS])

        if not frames:
            raise RuntimeError("No usable price data was fetched from Yahoo Finance.")

        result = pd.concat(frames, ignore_index=True)
        result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
        validate_columns(result, PRICE_COLUMNS)
        return result

    @staticmethod
    def _extract_close(
        raw: pd.DataFrame,
        ticker: str,
        is_single_ticker: bool,
    ) -> pd.Series | None:
        """Extract the close-price series from yfinance's single or multi-ticker shape."""
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.get_level_values(0):
                close_by_ticker = raw["Close"]
                if isinstance(close_by_ticker, pd.Series):
                    return close_by_ticker
                if ticker in close_by_ticker.columns:
                    return close_by_ticker[ticker]

            if "Close" in raw.columns.get_level_values(-1):
                try:
                    return raw[(ticker, "Close")]
                except KeyError:
                    return None

            return None

        if is_single_ticker and "Close" in raw.columns:
            return raw["Close"]

        return None

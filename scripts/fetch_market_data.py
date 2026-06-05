"""Fetch sample market data for the NAVigator MVP."""

from pathlib import Path

import sys; sys.path.append(".")

from src.data_fetcher import CurrencyFetcher, PriceFetcher

def main() -> None:
    """Fetch asset prices and FX rates, then save them as processed CSV files."""
    start = "2026-05-01"
    end = "2026-06-05"
    tickers = [
        "NVDA",
        "MSFT",
        "AAPL",
        "TSM",
        "GOOGL",
        "AMZN",
        "META",
        "AVGO",
        "TSLA",
        "ASML",
        "QQQ",
    ]

    output_dir = Path("data/processed")
    output_dir.mkdir(parents=True, exist_ok=True)

    price_fetcher = PriceFetcher(auto_adjust=True)
    prices = price_fetcher.fetch_daily_prices(tickers=tickers, start=start, end=end)
    prices_path = output_dir / "asset_prices.csv"
    prices.to_csv(prices_path, index=False)

    currency_fetcher = CurrencyFetcher(auto_adjust=True)
    fx_rates = currency_fetcher.fetch_daily_fx(
        base_currency="USD",
        quote_currency="CNY",
        start=start,
        end=end,
    )
    fx_path = output_dir / "fx_rates.csv"
    fx_rates.to_csv(fx_path, index=False)

    print("Asset prices preview:")
    print(prices.head())
    print(f"Saved asset prices to {prices_path}")
    print()
    print("FX rates preview:")
    print(fx_rates.head())
    print(f"Saved FX rates to {fx_path}")


if __name__ == "__main__":
    main()

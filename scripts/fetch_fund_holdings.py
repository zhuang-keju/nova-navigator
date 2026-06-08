"""Fetch latest disclosed fund holdings for the NAVigator MVP."""

from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.data_fetcher import FundHoldingFetcher  # noqa: E402


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> None:
    fund_code = "017436"
    fund_name = "华宝纳斯达克精选股票发起式(QDII)A"
    year = "2026"
    asset_currency = "USD"

    fetcher = FundHoldingFetcher()
    holdings = fetcher.fetch_holdings(
        fund_code=fund_code,
        fund_name=fund_name,
        year=year,
        asset_currency=asset_currency,
    )

    output_dir = PROJECT_ROOT / "data/manual"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "fund_holdings.csv"
    holdings.to_csv(output_path, index=False, encoding="utf-8-sig")

    selected_quarter = holdings["disclosure_date"].iloc[0]
    covered_weight = float(holdings["weight"].sum())
    uncovered_weight = 1 - covered_weight

    print("Fetched fund holdings")
    print(f"Fund: {fund_name} ({fund_code})")
    print(f"Selected quarter: {selected_quarter}")
    print(f"Number of holdings: {len(holdings)}")
    print(f"Covered weight: {fmt_pct(covered_weight)}")
    print(f"Uncovered weight: {fmt_pct(uncovered_weight)}")
    print()
    print("Top holdings:")
    print(holdings.head(10).to_string(index=False))
    print(f"Saved to {output_path.relative_to(PROJECT_ROOT).as_posix()}")


if __name__ == "__main__":
    main()

"""Lightweight schema helpers for fetched market data."""

from collections.abc import Sequence

import pandas as pd

PRICE_COLUMNS = ["date", "ticker", "close", "return"]
FX_COLUMNS = ["date", "pair", "rate", "return"]


def validate_columns(df: pd.DataFrame, expected_columns: Sequence[str]) -> None:
    """Raise ValueError if a DataFrame does not have exactly the expected columns."""
    actual_columns = list(df.columns)
    expected = list(expected_columns)
    if actual_columns != expected:
        raise ValueError(f"Expected columns {expected}, got {actual_columns}")

"""
data_loader.py – Pandas-based CSV loader and join helpers.
Loads each CSV once per process (module-level cache).
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import pandas as pd

# Repo root is two levels up from src/tools/
_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = _REPO_ROOT / "data"


@functools.cache
def _load(filename: str) -> pd.DataFrame:
    """Load a CSV from data/ with dtype inference disabled for ID columns."""
    path = DATA_DIR / filename
    return pd.read_csv(path, low_memory=False)


def orders() -> pd.DataFrame:
    return _load("olist_orders_dataset.csv")


def order_items() -> pd.DataFrame:
    return _load("olist_order_items_dataset.csv")


def order_payments() -> pd.DataFrame:
    return _load("olist_order_payments_dataset.csv")


def sellers() -> pd.DataFrame:
    return _load("olist_sellers_dataset.csv")


def customers() -> pd.DataFrame:
    return _load("olist_customers_dataset.csv")


# ---------------------------------------------------------------------------
# Convenience query helpers
# ---------------------------------------------------------------------------


def get_order(order_id: str) -> dict[str, Any] | None:
    """Return a single order row as a dict, or None if not found."""
    df = orders()
    rows = df[df["order_id"] == order_id]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def get_order_items(order_id: str) -> list[dict[str, Any]]:
    """Return all item rows for an order."""
    df = order_items()
    rows = df[df["order_id"] == order_id]
    return rows.to_dict(orient="records")


def get_order_payments(order_id: str) -> list[dict[str, Any]]:
    """Return all payment rows for an order."""
    df = order_payments()
    rows = df[df["order_id"] == order_id]
    return rows.to_dict(orient="records")


def get_sellers_for_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return seller rows for the seller_ids in items."""
    if not items:
        return []
    seller_ids = list({item["seller_id"] for item in items})
    df = sellers()
    rows = df[df["seller_id"].isin(seller_ids)]
    return rows.to_dict(orient="records")


def compute_totals(
    items: list[dict[str, Any]], payments: list[dict[str, Any]]
) -> tuple[float, float, float]:
    """
    Returns (item_total, freight_total, payment_total) rounded to 2 dp.
    item_total = sum of price across all items
    freight_total = sum of freight_value across all items
    payment_total = sum of payment_value across all payment rows
    """
    item_total = round(sum(float(i.get("price", 0) or 0) for i in items), 2)
    freight_total = round(
        sum(float(i.get("freight_value", 0) or 0) for i in items), 2
    )
    payment_total = round(
        sum(float(p.get("payment_value", 0) or 0) for p in payments), 2
    )
    return item_total, freight_total, payment_total

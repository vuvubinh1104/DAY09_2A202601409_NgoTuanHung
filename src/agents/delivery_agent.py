"""
Delivery Agent – compares actual vs. estimated delivery timestamps and
determines whether the seller was responsible for a late handoff.

Timestamps are compared as raw strings from the CSV (ISO-like format)
without timezone conversion, per the README instruction.

Pure data pipeline — no LLM calls needed.
"""
from __future__ import annotations

import logging

from src.schemas import AgentState

logger = logging.getLogger(__name__)


def _str_gt(a: str | None, b: str | None) -> bool:
    """Return True if non-empty string a > b (lexicographic ISO date compare)."""
    if not a or not b or a in ("nan", "NaT") or b in ("nan", "NaT"):
        return False
    return a > b


def delivery_node(state: AgentState) -> AgentState:
    order_id = state["order_id"]
    logger.info("[Delivery] Checking delivery SLA for order %s", order_id)

    delivered = state.get("order_delivered_customer_date")
    estimated = state.get("order_estimated_delivery_date", "")
    carrier_received = state.get("order_delivered_carrier_date")

    # Is overall delivery late?
    is_late = _str_gt(delivered, estimated) if delivered else False
    state["is_late_delivery"] = is_late

    # Check per-item shipping_limit_date vs carrier received date
    items = state.get("items", [])
    late_seller_ids: list[str] = []
    seller_handoff_late = False

    if carrier_received:
        for item in items:
            limit = str(item.get("shipping_limit_date", "") or "")
            if limit and limit not in ("nan", "NaT"):
                if _str_gt(carrier_received, limit):
                    seller_id = str(item.get("seller_id", ""))
                    seller_handoff_late = True
                    if seller_id and seller_id not in late_seller_ids:
                        late_seller_ids.append(seller_id)

    state["is_seller_handoff_late"] = seller_handoff_late
    state["late_seller_ids"] = late_seller_ids

    logger.debug(
        "[Delivery] is_late=%s seller_handoff_late=%s late_sellers=%s",
        is_late,
        seller_handoff_late,
        late_seller_ids,
    )
    return state

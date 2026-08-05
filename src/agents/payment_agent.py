"""
Payment Agent – fetches payment rows and computes financial totals.
Pure data pipeline — no LLM calls needed.
"""
from __future__ import annotations

import logging

from src.schemas import AgentState
from src.tools.data_loader import compute_totals, get_order_payments

logger = logging.getLogger(__name__)


def payment_node(state: AgentState) -> AgentState:
    order_id = state["order_id"]
    logger.info("[Payment] Reconciling payments for order %s", order_id)

    payments = get_order_payments(order_id)
    state["payments"] = payments

    items = state.get("items", [])
    item_total, freight_total, payment_total = compute_totals(items, payments)

    state["item_total"] = item_total
    state["freight_total"] = freight_total
    state["payment_total"] = payment_total

    logger.debug(
        "[Payment] item_total=%.2f freight_total=%.2f payment_total=%.2f",
        item_total,
        freight_total,
        payment_total,
    )
    return state

"""
Order & Seller Agent – fetches order row, items, and seller info from CSVs.
Populates state: order_status, items, sellers, and delivery timestamps.
Pure data pipeline — no LLM calls needed.
"""
from __future__ import annotations

import logging
from typing import Any

from src.schemas import AgentState
from src.tools.data_loader import (
    get_order,
    get_order_items,
    get_sellers_for_items,
)

logger = logging.getLogger(__name__)


def order_seller_node(state: AgentState) -> AgentState:
    order_id = state["order_id"]
    logger.info("[OrderSeller] Fetching order data for %s", order_id)

    order = get_order(order_id)
    if order is None:
        logger.warning("[OrderSeller] Order %s not found in CSV", order_id)
        # Populate with safe defaults so downstream agents still run
        state["order_status"] = "not_found"
        state["order_purchase_timestamp"] = ""
        state["order_estimated_delivery_date"] = ""
        state["order_delivered_customer_date"] = None
        state["order_delivered_carrier_date"] = None
        state["items"] = []
        state["sellers"] = []
        return state

    state["order_status"] = str(order.get("order_status", ""))
    state["order_purchase_timestamp"] = str(
        order.get("order_purchase_timestamp", "") or ""
    )
    state["order_estimated_delivery_date"] = str(
        order.get("order_estimated_delivery_date", "") or ""
    )
    state["order_delivered_customer_date"] = (
        str(order["order_delivered_customer_date"])
        if order.get("order_delivered_customer_date")
        and str(order["order_delivered_customer_date"]) != "nan"
        else None
    )
    state["order_delivered_carrier_date"] = (
        str(order["order_delivered_carrier_date"])
        if order.get("order_delivered_carrier_date")
        and str(order["order_delivered_carrier_date"]) != "nan"
        else None
    )

    items = get_order_items(order_id)
    state["items"] = items
    state["sellers"] = get_sellers_for_items(items)

    logger.debug(
        "[OrderSeller] status=%s items=%d sellers=%d",
        state["order_status"],
        len(items),
        len(state["sellers"]),
    )
    return state

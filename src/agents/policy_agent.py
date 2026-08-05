"""
Policy Agent – applies EC_POLICY_V1 rules (pure Python via policy.py)
and writes the decision fields into state.
No LLM calls — all decisions are deterministic.
"""
from __future__ import annotations

import logging

from src.policy import apply_policy
from src.schemas import AgentState

logger = logging.getLogger(__name__)


def policy_node(state: AgentState) -> AgentState:
    order_id = state["order_id"]
    logger.info("[Policy] Applying EC_POLICY_V1 for order %s", order_id)

    decision = apply_policy(
        order_status=state.get("order_status", ""),
        payment_total=state.get("payment_total", 0.0),
        item_total=state.get("item_total", 0.0),
        freight_total=state.get("freight_total", 0.0),
        is_late_delivery=state.get("is_late_delivery", False),
        is_seller_handoff_late=state.get("is_seller_handoff_late", False),
        late_seller_ids=state.get("late_seller_ids", []),
        num_payment_rows=len(state.get("payments", [])),
    )

    state["primary_issue"] = decision.primary_issue
    state["responsible_party_type"] = decision.responsible_party_type
    state["responsible_party_id"] = decision.responsible_party_id
    state["root_cause_code"] = decision.root_cause_code
    state["recommended_refund"] = decision.recommended_refund
    state["resolution_action"] = decision.resolution_action
    state["confidence"] = decision.confidence

    logger.debug(
        "[Policy] issue=%s status=%s refund=%.2f",
        decision.primary_issue,
        decision.case_status,
        decision.recommended_refund,
    )
    return state

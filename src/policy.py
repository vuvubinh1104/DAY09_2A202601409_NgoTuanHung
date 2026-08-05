"""
EC_POLICY_V1 – Pure Python business logic.
No LLM calls here; all decisions are deterministic from data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TOLERANCE_BRL = 0.10  # acceptable rounding gap for split-payment reconciliation


# ---------------------------------------------------------------------------
# Root-cause codes
# ---------------------------------------------------------------------------
RC_SELLER_HANDOFF = "SELLER_HANDOFF_AFTER_LIMIT"
RC_CARRIER_LATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
RC_CANCELED = "ORDER_CANCELED_AFTER_PAYMENT"
RC_UNAVAILABLE = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
RC_MULTI_PAYMENT = "MULTIPLE_PAYMENTS_RECONCILED"
RC_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"


@dataclass
class PolicyDecision:
    primary_issue: str
    case_status: str           # action_required | no_action
    responsible_party_type: str  # platform | seller | logistics_provider | none
    responsible_party_id: str
    root_cause_code: str
    recommended_refund: float  # BRL, rounded to 2 dp
    resolution_action: str
    confidence: float


def apply_policy(
    order_status: str,
    payment_total: float,
    item_total: float,
    freight_total: float,
    is_late_delivery: bool,
    is_seller_handoff_late: bool,
    late_seller_ids: list[str],
    num_payment_rows: int,
) -> PolicyDecision:
    """
    Apply EC_POLICY_V1 rules in priority order and return a PolicyDecision.
    All monetary values rounded to 2 decimal places.
    """
    pt = round(payment_total, 2)
    it = round(item_total, 2)
    ft = round(freight_total, 2)

    # 1. canceled_order_paid
    if order_status == "canceled" and pt > 0:
        return PolicyDecision(
            primary_issue="canceled_order_paid",
            case_status="action_required",
            responsible_party_type="platform",
            responsible_party_id="OLIST_PLATFORM",
            root_cause_code=RC_CANCELED,
            recommended_refund=pt,
            resolution_action="issue_full_refund",
            confidence=0.98,
        )

    # 2. unavailable_order_paid
    if order_status == "unavailable" and pt > 0:
        return PolicyDecision(
            primary_issue="unavailable_order_paid",
            case_status="action_required",
            responsible_party_type="platform",
            responsible_party_id="OLIST_PLATFORM",
            root_cause_code=RC_UNAVAILABLE,
            recommended_refund=pt,
            resolution_action="issue_full_refund",
            confidence=0.98,
        )

    # 3 & 4. Late delivery (only when actually late)
    if is_late_delivery:
        if is_seller_handoff_late and late_seller_ids:
            seller_id = late_seller_ids[0]
            return PolicyDecision(
                primary_issue="late_delivery_seller",
                case_status="action_required",
                responsible_party_type="seller",
                responsible_party_id=seller_id,
                root_cause_code=RC_SELLER_HANDOFF,
                recommended_refund=ft,
                resolution_action="refund_freight",
                confidence=0.92,
            )
        else:
            return PolicyDecision(
                primary_issue="late_delivery_logistics",
                case_status="action_required",
                responsible_party_type="logistics_provider",
                responsible_party_id="LOGISTICS_PROVIDER",
                root_cause_code=RC_CARRIER_LATE,
                recommended_refund=ft,
                resolution_action="refund_freight",
                confidence=0.90,
            )

    # 5. valid_split_payment: ≥2 payment rows, total matches item+freight
    if num_payment_rows >= 2:
        expected = round(it + ft, 2)
        if abs(pt - expected) <= TOLERANCE_BRL:
            return PolicyDecision(
                primary_issue="valid_split_payment",
                case_status="no_action",
                responsible_party_type="none",
                responsible_party_id="",
                root_cause_code=RC_MULTI_PAYMENT,
                recommended_refund=0.0,
                resolution_action="explain_valid_split_payment",
                confidence=0.95,
            )

    # 6. unsupported_late_claim (fallback)
    return PolicyDecision(
        primary_issue="unsupported_late_claim",
        case_status="no_action",
        responsible_party_type="none",
        responsible_party_id="",
        root_cause_code=RC_WITHIN_ESTIMATE,
        recommended_refund=0.0,
        resolution_action="reject_late_refund",
        confidence=0.85,
    )

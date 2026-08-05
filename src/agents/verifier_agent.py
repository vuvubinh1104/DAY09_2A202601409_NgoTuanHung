"""
Verifier Agent – validates schema, evidence ID format, financial math,
and enforces all list-length limits before writing the final output dict.
Pure Python — no LLM calls.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.policy import RC_CANCELED, RC_UNAVAILABLE, RC_WITHIN_ESTIMATE
from src.schemas import (
    AffectedEntities,
    AgentState,
    Assessment,
    CaseOutput,
    FinancialResolution,
    RankedCause,
    ResponsibleParty,
    RootCauseAnalysis,
)

logger = logging.getLogger(__name__)

_EVIDENCE_PATTERN = re.compile(
    r"^(order:[a-f0-9]+|item:[a-f0-9]+:\d+|payment:[a-f0-9]+:\d+|seller:[a-f0-9]+|policy:[A-Z_]+)$"
)

_CASE_STATUS_MAP = {
    "canceled_order_paid": "action_required",
    "unavailable_order_paid": "action_required",
    "late_delivery_seller": "action_required",
    "late_delivery_logistics": "action_required",
    "valid_split_payment": "no_action",
    "unsupported_late_claim": "no_action",
}


def _build_evidence_ids(state: AgentState) -> list[str]:
    """Build evidence IDs from verified data in state."""
    order_id = state.get("order_id", "")
    items = state.get("items", [])
    payments = state.get("payments", [])
    root_cause_code = state.get("root_cause_code", "")

    evidence: list[str] = []

    # order evidence
    if order_id:
        evidence.append(f"order:{order_id}")

    # item evidence (max 3 to stay within 10 total)
    for item in items[:3]:
        item_seq = item.get("order_item_id", "")
        if item_seq:
            evidence.append(f"item:{order_id}:{item_seq}")

    # payment evidence (max 3)
    for pay in payments[:3]:
        pay_seq = pay.get("payment_sequential", "")
        if pay_seq:
            evidence.append(f"payment:{order_id}:{pay_seq}")

    # seller evidence
    responsible_id = state.get("responsible_party_id", "")
    responsible_type = state.get("responsible_party_type", "")
    if responsible_type == "seller" and responsible_id:
        evidence.append(f"seller:{responsible_id}")

    # policy evidence
    if root_cause_code:
        evidence.append(f"policy:{root_cause_code}")

    # Validate format and deduplicate, keep max 10
    valid = []
    for eid in evidence:
        if _EVIDENCE_PATTERN.match(eid) and eid not in valid:
            valid.append(eid)
    return valid[:10]


def verifier_node(state: AgentState) -> AgentState:
    order_id = state.get("order_id", "")
    case_id = state.get("case_id", "")
    logger.info("[Verifier] Validating output for case %s", case_id)

    errors: list[str] = []

    # Gather affected entity IDs (enforce max 5 each)
    items = state.get("items", [])
    payments = state.get("payments", [])

    item_ids = [
        f"{order_id}:{item['order_item_id']}"
        for item in items
        if item.get("order_item_id")
    ][:5]
    seller_ids = list({str(item["seller_id"]) for item in items if item.get("seller_id")})[:5]
    payment_ids = [
        f"{order_id}:{pay['payment_sequential']}"
        for pay in payments
        if pay.get("payment_sequential")
    ][:5]

    # Financial validation
    item_total = round(state.get("item_total", 0.0), 2)
    freight_total = round(state.get("freight_total", 0.0), 2)
    payment_total = round(state.get("payment_total", 0.0), 2)
    recommended_refund = round(state.get("recommended_refund", 0.0), 2)

    primary_issue = state.get("primary_issue", "unsupported_late_claim")
    case_status = _CASE_STATUS_MAP.get(primary_issue, "no_action")

    # Verify refund makes sense
    if case_status == "no_action" and recommended_refund > 0:
        errors.append("no_action case has non-zero refund; correcting to 0")
        recommended_refund = 0.0

    # Build responsible parties (max 3)
    responsible_parties: list[dict[str, Any]] = []
    r_type = state.get("responsible_party_type", "none")
    r_id = state.get("responsible_party_id", "")
    if r_type != "none" and r_id:
        responsible_parties.append({"party_type": r_type, "party_id": r_id})

    # Build evidence IDs
    evidence_ids = _build_evidence_ids(state)

    # Assemble root causes (max 3)
    root_cause_code = state.get("root_cause_code", RC_WITHIN_ESTIMATE)
    ranked_causes = [{"cause_code": root_cause_code, "rank": 1}]

    # Build the output dict
    output: dict[str, Any] = {
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": round(state.get("confidence", 0.85), 2),
        },
        "affected_entities": {
            "order_ids": [order_id] if order_id else [],
            "item_ids": item_ids,
            "seller_ids": seller_ids,
            "payment_ids": payment_ids,
        },
        "root_cause_analysis": {
            "ranked_causes": ranked_causes,
            "responsible_parties": responsible_parties,
        },
        "evidence_ids": evidence_ids,
        "financial_resolution": {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "payment_total_brl": payment_total,
            "recommended_refund_brl": recommended_refund,
        },
        "resolution_actions": [state.get("resolution_action", "reject_late_refund")],
    }

    # Final Pydantic validation
    try:
        CaseOutput(**{
            **output,
            "assessment": Assessment(**output["assessment"]),
            "affected_entities": AffectedEntities(**output["affected_entities"]),
            "root_cause_analysis": RootCauseAnalysis(
                ranked_causes=[RankedCause(**c) for c in output["root_cause_analysis"]["ranked_causes"]],
                responsible_parties=[ResponsibleParty(**p) for p in output["root_cause_analysis"]["responsible_parties"]],
            ),
            "financial_resolution": FinancialResolution(**output["financial_resolution"]),
        })
        verified = True
    except Exception as exc:
        errors.append(f"Schema validation failed: {exc}")
        verified = False
        logger.error("[Verifier] Schema error for %s: %s", case_id, exc)

    if errors:
        logger.warning("[Verifier] Warnings for %s: %s", case_id, errors)

    state["output"] = output
    state["verified"] = verified
    state["verification_errors"] = errors
    return state

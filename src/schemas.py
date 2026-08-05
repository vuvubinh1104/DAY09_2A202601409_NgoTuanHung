from __future__ import annotations

from typing import Annotated, Any, TypedDict

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Assessment(BaseModel):
    primary_issue: str = Field(
        ...,
        description=(
            "One of: canceled_order_paid, unavailable_order_paid, "
            "late_delivery_seller, late_delivery_logistics, "
            "valid_split_payment, unsupported_late_claim"
        ),
    )
    case_status: str = Field(..., description="action_required | no_action")
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("primary_issue")
    @classmethod
    def validate_primary_issue(cls, v: str) -> str:
        allowed = {
            "canceled_order_paid",
            "unavailable_order_paid",
            "late_delivery_seller",
            "late_delivery_logistics",
            "valid_split_payment",
            "unsupported_late_claim",
        }
        if v not in allowed:
            raise ValueError(f"primary_issue must be one of {allowed}, got {v!r}")
        return v

    @field_validator("case_status")
    @classmethod
    def validate_case_status(cls, v: str) -> str:
        allowed = {"action_required", "no_action"}
        if v not in allowed:
            raise ValueError(f"case_status must be one of {allowed}, got {v!r}")
        return v


class AffectedEntities(BaseModel):
    order_ids: list[str] = Field(default_factory=list, max_length=5)
    item_ids: list[str] = Field(default_factory=list, max_length=5)
    seller_ids: list[str] = Field(default_factory=list, max_length=5)
    payment_ids: list[str] = Field(default_factory=list, max_length=5)


class RankedCause(BaseModel):
    cause_code: str
    rank: int


class ResponsibleParty(BaseModel):
    party_type: str  # platform | seller | logistics_provider
    party_id: str


class RootCauseAnalysis(BaseModel):
    ranked_causes: list[RankedCause] = Field(default_factory=list, max_length=3)
    responsible_parties: list[ResponsibleParty] = Field(
        default_factory=list, max_length=3
    )


class FinancialResolution(BaseModel):
    currency: str = "BRL"
    item_total_brl: float = Field(..., ge=0.0)
    freight_total_brl: float = Field(..., ge=0.0)
    payment_total_brl: float = Field(..., ge=0.0)
    recommended_refund_brl: float = Field(..., ge=0.0)


# ---------------------------------------------------------------------------
# Root output schema
# ---------------------------------------------------------------------------


class CaseOutput(BaseModel):
    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    financial_resolution: FinancialResolution
    resolution_actions: list[str] = Field(default_factory=list, max_length=5)


# ---------------------------------------------------------------------------
# LangGraph shared state
# ---------------------------------------------------------------------------


class AgentState(TypedDict, total=False):
    # Input
    case_id: str
    order_id: str
    opened_at: str
    customer_message: str
    policy_version: str

    # Order & Seller layer
    order_status: str
    order_purchase_timestamp: str
    order_estimated_delivery_date: str
    order_delivered_customer_date: str | None
    order_delivered_carrier_date: str | None
    items: list[dict[str, Any]]  # raw order_items rows
    sellers: list[dict[str, Any]]  # joined seller rows

    # Payment layer
    payments: list[dict[str, Any]]  # raw payment rows
    payment_total: float
    item_total: float
    freight_total: float

    # Delivery layer
    is_late_delivery: bool
    is_seller_handoff_late: bool  # any item's carrier_date > shipping_limit_date
    late_seller_ids: list[str]

    # Policy layer
    primary_issue: str
    responsible_party_type: str
    responsible_party_id: str
    root_cause_code: str
    recommended_refund: float
    resolution_action: str
    confidence: float

    # Verifier layer
    verified: bool
    verification_errors: list[str]

    # Final output
    output: dict[str, Any]

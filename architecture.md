# Architecture: Multi-Agent E-commerce Dispute Resolution

## Agent Diagram

```
input/EC_xxx.json
        │
        ▼
┌──────────────────────────────────┐
│  Coordinator Agent               │
│  • Parses case input             │
│  • Optional LLM triage summary   │
│  • Initialises AgentState        │
└──────────────┬───────────────────┘
               │ handoff (AgentState dict)
               ▼
┌──────────────────────────────────┐
│  Order & Seller Agent            │
│  • Reads: olist_orders           │
│  • Reads: olist_order_items      │
│  • Reads: olist_sellers          │
│  • Populates: order_status,      │
│    timestamps, items, sellers    │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Payment Agent                   │
│  • Reads: olist_order_payments   │
│  • Computes: item_total,         │
│    freight_total, payment_total  │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Delivery Agent                  │
│  • Compares delivered vs         │
│    estimated_delivery_date       │
│  • Compares carrier_date vs      │
│    shipping_limit_date per item  │
│  • Flags: is_late_delivery,      │
│    is_seller_handoff_late,       │
│    late_seller_ids               │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Policy Agent                    │
│  • Applies EC_POLICY_V1          │
│    (pure Python, deterministic)  │
│  • Sets: primary_issue,          │
│    responsible_party,            │
│    root_cause_code,              │
│    recommended_refund,           │
│    resolution_action             │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│  Verifier Agent                  │
│  • Validates evidence ID format  │
│  • Enforces list-length limits   │
│  • Pydantic schema check         │
│  • Corrects financial anomalies  │
│  • Writes final output dict      │
└──────────────┬───────────────────┘
               │
               ▼
        output/EC_xxx.json
```

## Agent Roles & Data Access

| Agent | Role | Data Access |
|---|---|---|
| **Coordinator** | Parse input, optional LLM triage, initialise state | `input/*.json` |
| **Order & Seller** | Fetch order status, items, seller info, delivery timestamps | `olist_orders`, `olist_order_items`, `olist_sellers` |
| **Payment** | Sum item/freight/payment totals, reconcile rows | `olist_order_payments`, `olist_order_items` |
| **Delivery** | Compare timestamps; determine if delivery is late and who is at fault | `olist_orders`, `olist_order_items` |
| **Policy** | Apply EC_POLICY_V1 rules in priority order; output decision | State from upstream agents |
| **Verifier** | Validate schema, evidence IDs, financial limits; write output | State from all agents |

## Handoff Protocol

Each agent receives the full `AgentState` TypedDict and returns an updated copy.
No agent skips: the pipeline is always sequential to respect VRAM constraints.

```
Coordinator → OrderSeller → Payment → Delivery → Policy → Verifier → END
```

## LLM Usage

| Agent | LLM? | Reason |
|---|---|---|
| Coordinator | Optional (1 call) | Customer message triage classification |
| Order & Seller | No | Pure CSV lookup |
| Payment | No | Pure arithmetic |
| Delivery | No | String timestamp comparison |
| Policy | No | Deterministic rule engine |
| Verifier | No | Schema + regex validation |

**Model**: `qwen3:4b` via Ollama (Q4_K_M quantization, ~2.5 GB VRAM)  
**Temperature**: 0 (deterministic)  
**Max ~50 LLM calls total** for 50 cases (1 per case, coordinator only)

## EC_POLICY_V1 Priority Order

1. `canceled_order_paid` → full refund, platform responsible
2. `unavailable_order_paid` → full refund, platform responsible
3. `late_delivery_seller` → freight refund, seller responsible (carrier received after `shipping_limit_date`)
4. `late_delivery_logistics` → freight refund, logistics provider responsible
5. `valid_split_payment` → no refund, explain split payment
6. `unsupported_late_claim` → no refund, reject claim (fallback)

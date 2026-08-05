"""
main.py – Entrypoint for the Multi-Agent E-commerce Dispute Resolution system.

Usage:
    uv run python src/main.py --case EC_001        # single case
    uv run python src/main.py --all                # all 50 cases
    uv run python src/main.py --all --dry-run      # validate without writing
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from src.agents.coordinator import coordinator_node
from src.agents.delivery_agent import delivery_node
from src.agents.order_seller_agent import order_seller_node
from src.agents.payment_agent import payment_node
from src.agents.policy_agent import policy_node
from src.agents.verifier_agent import verifier_node
from src.schemas import AgentState

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = REPO_ROOT / "input"
OUTPUT_DIR = REPO_ROOT / "output"
TRACE_FILE = REPO_ROOT / "trace.jsonl"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Build LangGraph pipeline
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("coordinator", coordinator_node)
    graph.add_node("order_seller", order_seller_node)
    graph.add_node("payment", payment_node)
    graph.add_node("delivery", delivery_node)
    graph.add_node("policy", policy_node)
    graph.add_node("verifier", verifier_node)

    # Sequential pipeline
    graph.add_edge(START, "coordinator")
    graph.add_edge("coordinator", "order_seller")
    graph.add_edge("order_seller", "payment")
    graph.add_edge("payment", "delivery")
    graph.add_edge("delivery", "policy")
    graph.add_edge("policy", "verifier")
    graph.add_edge("verifier", END)

    return graph.compile()


_APP = None


def get_app():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


# ---------------------------------------------------------------------------
# Case processing
# ---------------------------------------------------------------------------

def load_case(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_case(case_data: dict, dry_run: bool = False) -> dict:
    """Process a single case and return the output dict."""
    case_id: str = case_data["case_id"]
    order_id: str = case_data["customer_request"]["claimed_order_id"]

    initial_state: AgentState = {
        "case_id": case_id,
        "order_id": order_id,
        "opened_at": case_data.get("opened_at", ""),
        "customer_message": case_data["customer_request"].get("message", ""),
        "policy_version": case_data.get("policy_version", "EC_POLICY_V1"),
    }

    app = get_app()
    t0 = time.perf_counter()
    final_state: AgentState = app.invoke(initial_state)
    elapsed = time.perf_counter() - t0

    output = final_state.get("output", {})

    # Write output file
    if not dry_run:
        OUTPUT_DIR.mkdir(exist_ok=True)
        out_path = OUTPUT_DIR / f"{case_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("[main] Written %s (%.2fs)", out_path.name, elapsed)

    # Return trace entry
    return {
        "case_id": case_id,
        "order_id": order_id,
        "elapsed_s": round(elapsed, 3),
        "primary_issue": output.get("assessment", {}).get("primary_issue"),
        "case_status": output.get("assessment", {}).get("case_status"),
        "confidence": output.get("assessment", {}).get("confidence"),
        "recommended_refund_brl": output.get("financial_resolution", {}).get(
            "recommended_refund_brl"
        ),
        "verified": final_state.get("verified", False),
        "verification_errors": final_state.get("verification_errors", []),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "output": output,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Agent E-commerce Dispute Resolution"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", metavar="EC_XXX", help="Run a single case by ID")
    group.add_argument("--all", action="store_true", help="Run all 50 cases")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process cases but do not write output files",
    )
    args = parser.parse_args()

    trace_entries: list[dict] = []

    if args.case:
        case_path = INPUT_DIR / f"{args.case}.json"
        if not case_path.exists():
            logger.error("Case file not found: %s", case_path)
            sys.exit(1)
        case_data = load_case(case_path)
        trace = run_case(case_data, dry_run=args.dry_run)
        trace_entries.append(trace)
        print(json.dumps(trace["output"], ensure_ascii=False, indent=2))

    elif args.all:
        case_files = sorted(INPUT_DIR.glob("EC_*.json"))
        if not case_files:
            logger.error("No case files found in %s", INPUT_DIR)
            sys.exit(1)

        logger.info("Processing %d cases…", len(case_files))
        errors = 0
        for i, path in enumerate(case_files, 1):
            try:
                case_data = load_case(path)
                trace = run_case(case_data, dry_run=args.dry_run)
                trace_entries.append(trace)
                status_icon = "✓" if trace["verified"] else "✗"
                logger.info(
                    "[%d/%d] %s %s → %s (refund: %.2f BRL)",
                    i,
                    len(case_files),
                    status_icon,
                    trace["case_id"],
                    trace["primary_issue"],
                    trace["recommended_refund_brl"] or 0,
                )
            except Exception as exc:
                logger.error("Failed to process %s: %s", path.name, exc)
                errors += 1

        logger.info(
            "Done. %d/%d cases processed, %d errors.",
            len(trace_entries),
            len(case_files),
            errors,
        )

    # Write trace.jsonl (overwrite, only latest run)
    if trace_entries and not args.dry_run:
        with open(TRACE_FILE, "w", encoding="utf-8") as f:
            for entry in trace_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Trace written to %s (%d entries)", TRACE_FILE, len(trace_entries))


if __name__ == "__main__":
    main()

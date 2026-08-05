"""
Coordinator Agent – receives the raw case input, dispatches to other agents
via the LangGraph state, and assembles the final CaseOutput.

The LLM call here is intentionally minimal: it only parses the
customer message language and provides a short classification rationale.
All business logic is in the specialized agents and policy.py.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage

from src.schemas import AgentState

logger = logging.getLogger(__name__)

# Local Ollama model (qwen3:4b chạy trên localhost:11434)
MODEL_NAME = "qwen3:4b"

_llm: ChatOllama | None = None


def _get_llm() -> ChatOllama:
    global _llm
    if _llm is None:
        # Đọc OLLAMA_HOST từ env (set bởi .env), fallback về localhost
        base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        _llm = ChatOllama(
            model=MODEL_NAME,
            base_url=base_url,
            temperature=0,
        )
    return _llm


def coordinator_node(state: AgentState) -> AgentState:
    """
    Entry point: validate the case, optionally enrich with LLM classification,
    return updated state.
    """
    case_id = state["case_id"]
    order_id = state["order_id"]
    logger.info("[Coordinator] Processing case %s for order %s", case_id, order_id)

    # Optionally use LLM to summarise the customer message (non-critical path)
    try:
        llm = _get_llm()
        system = SystemMessage(
            content=(
                "You are a dispute triage assistant. Classify the customer complaint "
                "in one sentence: what is the main claim? Reply in English only."
            )
        )
        user = HumanMessage(content=state.get("customer_message", ""))
        reply = llm.invoke([system, user])
        logger.debug("[Coordinator] LLM classification: %s", reply.content)
    except Exception as exc:  # pragma: no cover – Ollama may not be running yet
        logger.warning("[Coordinator] LLM unavailable: %s", exc)

    return state  # no state mutation needed at this stage

"""
LangGraph-orchestrated RAG pipeline for the Zepto support assistant.

Stages (see README for the full architecture write-up):
  classify_intent      -> routes each query (policy_question | general_question)
  retrieve_and_answer   -> real ChromaDB retrieval (always) + generation (MOCK_LLM-gated)
  direct_answer         -> generation only (MOCK_LLM-gated), no retrieval

MOCK_LLM env var:
  unset or "1" -> graded baseline: no LLM calls anywhere in the graph.
  "0"          -> optional extension: real LLM calls for classification/generation,
                  via Groq (or any free-tier-compatible OpenAI-style client).
"""
import os
import json
from typing import TypedDict, List, Optional, Literal

from langgraph.graph import StateGraph, END

from ingest import retrieve_top_k
from prompt_template import build_messages
from schemas import AskResponse

MOCK_LLM = os.environ.get("MOCK_LLM", "1") != "0"  # True = mock (default/graded)

POLICY_KEYWORDS = [
    "delivery", "return", "refund", "membership",
    "tracking", "cancel", "gift card", "support hours",
]

CANNED_GENERAL_ANSWER = "I can only answer questions about Zepto policies right now."


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    query: str
    intent: Literal["policy_question", "general_question"]
    retrieved_chunks: List[dict]
    answer: str
    sources: List[str]
    confidence: float


# ---------------------------------------------------------------------------
# Optional real-LLM client (only constructed when MOCK_LLM=0)
# ---------------------------------------------------------------------------
def _get_llm_client():
    """
    Lazily build an OpenAI-compatible client pointed at Groq's free-tier API.
    Only ever called from the MOCK_LLM=0 branches below.
    """
    from openai import OpenAI  # local import: not a required dependency in mock mode
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "MOCK_LLM=0 requires GROQ_API_KEY to be set (optional extension only; "
            "the graded baseline runs with MOCK_LLM left at its default and never "
            "reaches this code path)."
        )
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def _call_llm_for_json(messages, model="llama-3.1-8b-instant", max_retries=2):
    """
    Call the real LLM and validate its output against AskResponse, retrying up to
    `max_retries` additional times with a corrective instruction on validation
    failure. Only reached when MOCK_LLM=0. Never called in the graded baseline.
    """
    client = _get_llm_client()
    attempt_messages = list(messages)
    last_error = None

    for attempt in range(max_retries + 1):
        resp = client.chat.completions.create(
            model=model,
            messages=attempt_messages,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        try:
            data = json.loads(raw)
            validated = AskResponse(**data)
            return validated
        except Exception as e:  # JSON decode error or Pydantic ValidationError
            last_error = e
            attempt_messages = list(messages) + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "That response was not valid JSON matching the required schema "
                    f"(answer: str, sources: list[str], confidence: float 0-1). "
                    f"Validation error: {e}. Reply again with ONLY a corrected JSON "
                    "object and nothing else."
                )},
            ]

    # Exhausted retries: clearly-marked error response, not a silent failure.
    return AskResponse(
        answer=f"[ERROR] LLM failed to produce a schema-valid response after "
               f"{max_retries} retries. Last error: {last_error}",
        sources=[],
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# Node 1: classify_intent
# ---------------------------------------------------------------------------
def classify_intent(state: GraphState) -> GraphState:
    query = state["query"]

    if MOCK_LLM:
        # Mock mode (graded baseline): keyword heuristic, no LLM call.
        lowered = query.lower()
        intent = "policy_question" if any(kw in lowered for kw in POLICY_KEYWORDS) else "general_question"
    else:
        # Optional extension: ask the real LLM to classify.
        client = _get_llm_client()
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": (
                    "Classify the user's question as exactly one word: "
                    "'policy_question' if it concerns Zepto's delivery, returns, "
                    "membership, tracking, cancellation, damaged/missing items, gift "
                    "cards, or support hours policies, otherwise 'general_question'. "
                    "Reply with only that one word."
                )},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip().lower()
        intent = "policy_question" if "policy_question" in raw else "general_question"

    return {**state, "intent": intent}


# ---------------------------------------------------------------------------
# Node 2: retrieve_and_answer  (policy_question path)
# ---------------------------------------------------------------------------
def retrieve_and_answer(state: GraphState) -> GraphState:
    query = state["query"]

    # Retrieval always runs for real, in both modes (no API key/network needed).
    chunks = retrieve_top_k(query, k=3)
    top_chunk = chunks[0] if chunks else None

    if MOCK_LLM:
        # Mock mode (graded baseline): canned templated answer, no LLM call.
        if top_chunk:
            snippet = top_chunk["text"][:200]
            answer = f"Based on the retrieved context: {snippet}"
            sources = [c["chunk_id"] for c in chunks]
        else:
            answer = "Based on the retrieved context: no relevant policy information was found."
            sources = []
        confidence = 1.0
    else:
        # Optional extension: real LLM, grounded only in retrieved chunks.
        messages = build_messages(query, chunks)
        validated = _call_llm_for_json(messages)
        answer = validated.answer
        sources = validated.sources
        confidence = validated.confidence

    return {
        **state,
        "retrieved_chunks": chunks,
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Node 3: direct_answer  (general_question path, no retrieval)
# ---------------------------------------------------------------------------
def direct_answer(state: GraphState) -> GraphState:
    query = state["query"]

    if MOCK_LLM:
        # Mock mode (graded baseline): fixed canned string, no LLM call.
        answer = CANNED_GENERAL_ANSWER
        confidence = 1.0
    else:
        # Optional extension: prompt the LLM directly, no retrieval context.
        client = _get_llm_client()
        resp = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": (
                    "You are a general assistant. The user's question is unrelated to "
                    "Zepto policies. Answer briefly and helpfully in 1-2 sentences."
                )},
                {"role": "user", "content": query},
            ],
            temperature=0.3,
        )
        answer = resp.choices[0].message.content.strip()
        confidence = 0.7  # heuristic: no grounding/schema-validated confidence available here

    return {**state, "answer": answer, "sources": [], "confidence": confidence}


# ---------------------------------------------------------------------------
# Conditional routing (does not depend on MOCK_LLM)
# ---------------------------------------------------------------------------
def route_by_intent(state: GraphState) -> str:
    return "retrieve_and_answer" if state["intent"] == "policy_question" else "direct_answer"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------
def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("retrieve_and_answer", retrieve_and_answer)
    graph.add_node("direct_answer", direct_answer)

    graph.set_entry_point("classify_intent")
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "retrieve_and_answer": "retrieve_and_answer",
            "direct_answer": "direct_answer",
        },
    )
    graph.add_edge("retrieve_and_answer", END)
    graph.add_edge("direct_answer", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def ask(query: str) -> AskResponse:
    """Run the full graph for one query and return a validated AskResponse."""
    graph = get_graph()
    result = graph.invoke({"query": query})
    return AskResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        confidence=result["confidence"],
    )


if __name__ == "__main__":
    for q in ["How long do I have to return a spoiled item?", "What's the capital of France?"]:
        r = ask(q)
        print(q, "->", r.model_dump())

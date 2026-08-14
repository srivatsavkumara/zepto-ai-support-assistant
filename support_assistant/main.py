"""
FastAPI wrapper around the LangGraph Zepto policy-assistant pipeline.

Run locally:
    uvicorn main:app --host 0.0.0.0 --port 7860

MOCK_LLM defaults to mock mode (graded baseline) unless explicitly set to "0"
before the process starts.
"""
from fastapi import FastAPI, HTTPException

from schemas import AskRequest, AskResponse
from graph import ask as run_graph

app = FastAPI(
    title="Zepto Policy Support Assistant",
    description="RAG-backed support assistant over Zepto's delivery, returns, "
                 "membership, tracking, cancellation, gift card, and support policies.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(request: AskRequest) -> AskResponse:
    try:
        return run_graph(request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

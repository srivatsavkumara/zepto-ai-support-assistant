"""
Pydantic schemas for the /ask endpoint.

AskResponse is the JSON output schema enforced on every final answer:
  - answer: str
  - sources: list[str]   (chunk/doc ids used; empty for general_question)
  - confidence: float    (0.0-1.0)
"""
from typing import List
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The customer's question.")


class AskResponse(BaseModel):
    answer: str
    sources: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)

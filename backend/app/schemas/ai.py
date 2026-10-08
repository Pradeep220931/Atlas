from typing import Literal

from pydantic import BaseModel, Field, field_validator


class KnowledgeGapAIResult(BaseModel):
    potential_gap: bool
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    targeted_question: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class KnowledgeQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    rationale: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class KnowledgeQuestionsResult(BaseModel):
    questions: list[KnowledgeQuestion] = Field(min_length=1, max_length=5)


class KnowledgeCaptureResult(BaseModel):
    knowledge_type: Literal["decision_rationale", "operational_context", "implementation_detail", "other"]
    decision: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=3000)
    mitigation: str = Field(default="", max_length=2000)
    related_incident: str | None = Field(default=None, max_length=160)
    related_change: str | None = Field(default=None, max_length=200)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class KnowledgeCheck(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    expected_concepts: list[str] = Field(min_length=1, max_length=10)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class TransitionAssistanceResult(BaseModel):
    summary: str = Field(min_length=1, max_length=3000)
    topics: list[str] = Field(min_length=1, max_length=10)
    targeted_questions: list[KnowledgeQuestion] = Field(min_length=1, max_length=5)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class KnowledgeVerificationResult(BaseModel):
    status: Literal["verified", "needs_clarification"]
    knowledge_area: str = Field(min_length=1, max_length=200)
    assessment: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool
    evidence_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("needs_clarification")
    @classmethod
    def status_matches_clarification(cls, value: bool, info):
        status = info.data.get("status")
        if status == "needs_clarification" and not value:
            raise ValueError("needs_clarification status requires needs_clarification=true")
        if status == "verified" and value:
            raise ValueError("verified status requires needs_clarification=false")
        return value

from typing import Any

from app.models.entities import Evidence, KnowledgeGap, KnowledgeRecord, Service
from app.schemas.ai import (
    KnowledgeCaptureResult,
    KnowledgeGapAIResult,
    KnowledgeQuestionsResult,
    KnowledgeCheck,
    TransitionAssistanceResult,
    KnowledgeVerificationResult,
)
from app.services.agent_router import AgentRouter

MAX_EVIDENCE_ITEMS = 20
MAX_EVIDENCE_CHARS = 1500
MAX_CONTEXT_CHARS = 18000


class InvalidEvidenceReference(ValueError):
    pass


class MissingEvidence(ValueError):
    pass


def build_gap_context(
    gap: KnowledgeGap,
    service: Service,
    evidence: list[Evidence],
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not evidence:
        raise MissingEvidence("No persisted source evidence is linked to this knowledge gap")
    selected = evidence[:MAX_EVIDENCE_ITEMS]
    context: dict[str, Any] = {
        "gap": {"title": gap.title, "description": gap.description, "priority": gap.priority},
        "service": {"name": service.name, "description": service.description, "criticality": service.criticality},
        "evidence": [
            {
                "id": item.source_id,
                "source_type": item.source_type,
                "title": item.title[:300],
                "reference": item.reference[:500],
                "summary": item.summary[:MAX_EVIDENCE_CHARS],
            }
            for item in selected
        ],
    }
    if signals is not None:
        context["deterministic_signals"] = signals
    while len(str(context)) > MAX_CONTEXT_CHARS and context["evidence"]:
        context["evidence"].pop()
    if not context["evidence"]:
        raise MissingEvidence("Persisted evidence exceeds the safe AI context limit")
    return context


def validate_evidence_ids(returned_ids: list[str], supplied_context: dict[str, Any]) -> list[str]:
    allowed = {item["id"] for item in supplied_context["evidence"]}
    invalid = set(returned_ids) - allowed
    if invalid:
        raise InvalidEvidenceReference("AI response referenced evidence that was not supplied")
    if not returned_ids:
        raise InvalidEvidenceReference("AI response must cite supplied evidence")
    return returned_ids


def analyze_gap(
    gap: KnowledgeGap,
    service: Service,
    evidence: list[Evidence],
    signals: dict[str, Any] | None = None,
) -> KnowledgeGapAIResult:
    context = build_gap_context(gap, service, evidence, signals)
    result = AgentRouter().analyze_gap(context)
    result.evidence_ids = validate_evidence_ids(result.evidence_ids, context)
    return result


def generate_questions(gap: KnowledgeGap, service: Service, evidence: list[Evidence]) -> KnowledgeQuestionsResult:
    context = build_gap_context(gap, service, evidence)
    result = AgentRouter().generate_questions(context)
    for question in result.questions:
        question.evidence_ids = validate_evidence_ids(question.evidence_ids, context)
    return result


def structure_capture(
    gap: KnowledgeGap,
    service: Service,
    evidence: list[Evidence],
    question: str,
    answer: str,
) -> KnowledgeCaptureResult:
    context = build_gap_context(gap, service, evidence)
    context["question"] = question[:1000]
    context["human_answer"] = answer[:6000]
    result = AgentRouter().structure_capture(context)
    if result.evidence_ids:
        result.evidence_ids = validate_evidence_ids(result.evidence_ids, context)
    return result


def verify_answer(
    area_name: str,
    validated_knowledge: list[dict[str, str]],
    evidence: list[Evidence],
    answer: str,
) -> KnowledgeVerificationResult:
    if not validated_knowledge or not evidence:
        raise MissingEvidence("Verification requires validated knowledge and persisted source evidence")
    context = {
        "knowledge_area": area_name,
        "validated_knowledge": validated_knowledge[:10],
        "human_answer": answer[:6000],
        "evidence": [
            {
                "id": item.source_id,
                "source_type": item.source_type,
                "title": item.title[:300],
                "reference": item.reference[:500],
                "summary": item.summary[:MAX_EVIDENCE_CHARS],
            }
            for item in evidence[:MAX_EVIDENCE_ITEMS]
        ],
    }
    result = AgentRouter().verify_answer(context)
    result.evidence_ids = validate_evidence_ids(result.evidence_ids, context)
    return result


def _validated_knowledge_context(
    area_name: str,
    records: list[KnowledgeRecord],
    evidence: list[Evidence],
) -> dict[str, Any]:
    validated = [record for record in records if record.status == "validated"][:10]
    if not validated or not evidence:
        raise MissingEvidence("Transition assistance requires validated knowledge and persisted source evidence")
    return {
        "knowledge_area": area_name,
        "validated_knowledge": [
            {
                "decision": record.decision[:1500],
                "reason": record.reason[:2000],
                "affected_system": record.affected_system,
                "related_incident": record.related_incident,
            }
            for record in validated
        ],
        "evidence": [
            {
                "id": item.source_id,
                "source_type": item.source_type,
                "title": item.title[:300],
                "reference": item.reference[:500],
                "summary": item.summary[:MAX_EVIDENCE_CHARS],
            }
            for item in evidence[:MAX_EVIDENCE_ITEMS]
        ],
    }


def generate_transition_assistance(
    area_name: str,
    records: list[KnowledgeRecord],
    evidence: list[Evidence],
) -> TransitionAssistanceResult:
    context = _validated_knowledge_context(area_name, records, evidence)
    result = AgentRouter().generate_transition_assistance(context)
    result.evidence_ids = validate_evidence_ids(result.evidence_ids, context)
    for question in result.targeted_questions:
        question.evidence_ids = validate_evidence_ids(question.evidence_ids, context)
    return result


def generate_knowledge_check(
    area_name: str,
    records: list[KnowledgeRecord],
    evidence: list[Evidence],
) -> KnowledgeCheck:
    context = _validated_knowledge_context(area_name, records, evidence)
    result = AgentRouter().generate_knowledge_check(context)
    result.evidence_ids = validate_evidence_ids(result.evidence_ids, context)
    return result

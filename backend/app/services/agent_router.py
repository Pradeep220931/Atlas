from typing import Any

from app.config import settings
from app.schemas.ai import (
    KnowledgeCaptureResult,
    KnowledgeCheck,
    KnowledgeGapAIResult,
    KnowledgeQuestionsResult,
    KnowledgeVerificationResult,
    TransitionAssistanceResult,
)
from app.services.anthropic_client import AIConfigurationError, AnthropicService


class AgentRouter:
    """Selects the configured AI provider and routes ATLAS tasks to it."""

    def __init__(self, provider: Any | None = None):
        if provider is not None:
            self.provider = provider
            self.provider_name = "test"
            return
        if settings.ai_provider != "anthropic":
            raise AIConfigurationError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")
        self.provider = AnthropicService()
        self.provider_name = "anthropic"

    def test_connection(self) -> str:
        return self.provider.test_connection()

    def analyze_gap(self, context: dict[str, Any]) -> KnowledgeGapAIResult:
        return self.provider.analyze_gap(context)

    def generate_questions(self, context: dict[str, Any]) -> KnowledgeQuestionsResult:
        return self.provider.generate_questions(context)

    def structure_capture(self, context: dict[str, Any]) -> KnowledgeCaptureResult:
        return self.provider.structure_capture(context)

    def verify_answer(self, context: dict[str, Any]) -> KnowledgeVerificationResult:
        return self.provider.verify_answer(context)

    def generate_transition_assistance(self, context: dict[str, Any]) -> TransitionAssistanceResult:
        return self.provider.generate_transition_assistance(context)

    def generate_knowledge_check(self, context: dict[str, Any]) -> KnowledgeCheck:
        return self.provider.generate_knowledge_check(context)

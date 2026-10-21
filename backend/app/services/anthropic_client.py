import json
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.ai import (
    KnowledgeCaptureResult,
    KnowledgeCheck,
    KnowledgeGapAIResult,
    KnowledgeQuestionsResult,
    KnowledgeVerificationResult,
    TransitionAssistanceResult,
)
from app.services import ai_prompts

logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AIConfigurationError(RuntimeError):
    pass


class AIProviderError(RuntimeError):
    pass


class AIOutputError(RuntimeError):
    pass


class AnthropicService:
    def __init__(self, client: anthropic.Anthropic | None = None):
        if not settings.anthropic_model:
            raise AIConfigurationError("ANTHROPIC_MODEL is not configured")
        if not settings.anthropic_auth_token and not settings.anthropic_api_key:
            raise AIConfigurationError("ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY is not configured")
        self.model = settings.anthropic_model
        if client is None:
            client_options: dict[str, Any] = {
                "timeout": 30.0,
                "max_retries": 1,
            }
            if settings.anthropic_auth_token:
                client_options["auth_token"] = settings.anthropic_auth_token
            else:
                client_options["api_key"] = settings.anthropic_api_key
            if settings.anthropic_base_url:
                client_options["base_url"] = settings.anthropic_base_url
            client = anthropic.Anthropic(**client_options)
        self.client = client

    def _structured_request(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        tool_name: str,
        tool_description: str,
        max_tokens: int = 1200,
    ) -> SchemaT:
        request_prompt = prompt
        for attempt in range(2):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=ai_prompts.BASE_INSTRUCTIONS,
                    messages=[{"role": "user", "content": request_prompt}],
                    tools=[{
                        "name": tool_name,
                        "description": tool_description,
                        "input_schema": schema.model_json_schema(),
                    }],
                    tool_choice={"type": "tool", "name": tool_name},
                )
            except anthropic.APIStatusError as error:
                logger.warning("Anthropic request failed with status %s", error.status_code)
                if error.status_code in (401, 403):
                    raise AIConfigurationError("Anthropic rejected the configured API key") from error
                if error.status_code == 404:
                    raise AIConfigurationError("The configured Anthropic model is unavailable to this account") from error
                if error.status_code == 429:
                    raise AIProviderError("The AI service is rate limited; try again later") from error
                raise AIProviderError("The AI service rejected the request or is unavailable") from error
            except anthropic.APIConnectionError as error:
                logger.warning("Could not connect to Anthropic: %s", type(error).__name__)
                raise AIProviderError("The AI service could not be reached") from error
            except anthropic.APIError as error:
                logger.warning("Anthropic API error: %s", type(error).__name__)
                raise AIProviderError("The AI service is temporarily unavailable") from error

            for item in response.content:
                if getattr(item, "type", None) == "tool_use" and getattr(item, "name", None) == tool_name:
                    try:
                        return schema.model_validate(item.input)
                    except (ValidationError, TypeError, ValueError):
                        logger.warning("Anthropic returned invalid structured output for %s", tool_name)
                        break
            else:
                logger.warning("Anthropic response omitted expected structured tool result")

            if attempt == 0:
                request_prompt = f"{prompt}\n\nThe previous result was invalid. Return a corrected result that strictly satisfies the requested tool schema."

        raise AIOutputError("The AI returned an invalid structured response")

    def test_connection(self) -> str:
        result = self._structured_request(
            'Return the exact phrase "ATLAS AI connection successful." in the field message.',
            ConnectionTestResult,
            tool_name="connection_test",
            tool_description="A minimal health response for the configured model.",
            max_tokens=80,
        )
        if result.message != "ATLAS AI connection successful.":
            raise AIOutputError("The AI connection test returned an unexpected response")
        return result.message

    def analyze_gap(self, context: dict[str, Any]) -> KnowledgeGapAIResult:
        return self._structured_request(
            ai_prompts.GAP_ANALYSIS_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            KnowledgeGapAIResult,
            tool_name="knowledge_gap_analysis",
            tool_description="Evidence-bounded potential knowledge gap analysis.",
        )

    def generate_questions(self, context: dict[str, Any]) -> KnowledgeQuestionsResult:
        return self._structured_request(
            ai_prompts.QUESTION_GENERATION_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            KnowledgeQuestionsResult,
            tool_name="knowledge_questions",
            tool_description="A short list of targeted questions grounded in supplied evidence.",
            max_tokens=1000,
        )

    def structure_capture(self, context: dict[str, Any]) -> KnowledgeCaptureResult:
        return self._structured_request(
            ai_prompts.CAPTURE_STRUCTURING_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            KnowledgeCaptureResult,
            tool_name="knowledge_capture",
            tool_description="A draft structure for a human-provided knowledge answer.",
        )

    def verify_answer(self, context: dict[str, Any]) -> KnowledgeVerificationResult:
        return self._structured_request(
            ai_prompts.KNOWLEDGE_VERIFICATION_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            KnowledgeVerificationResult,
            tool_name="knowledge_verification",
            tool_description="An assessment limited to one selected validated knowledge area.",
        )

    def generate_transition_assistance(self, context: dict[str, Any]) -> TransitionAssistanceResult:
        return self._structured_request(
            ai_prompts.TRANSITION_ASSISTANCE_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            TransitionAssistanceResult,
            tool_name="transition_assistance",
            tool_description="A concise transition summary and evidence-grounded discussion topics.",
            max_tokens=1400,
        )

    def generate_knowledge_check(self, context: dict[str, Any]) -> KnowledgeCheck:
        return self._structured_request(
            ai_prompts.KNOWLEDGE_CHECK_PROMPT.format(context=json.dumps(context, ensure_ascii=True)),
            KnowledgeCheck,
            tool_name="knowledge_check",
            tool_description="One check question based on validated knowledge and supplied evidence.",
            max_tokens=800,
        )


class ConnectionTestResult(BaseModel):
    message: str

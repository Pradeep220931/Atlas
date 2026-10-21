from collections.abc import Generator
from dataclasses import replace
from types import SimpleNamespace
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app import main as main_module
from app.main import app
from app.models.entities import AuditLog, Evidence, KnowledgeGap, KnowledgeRecord, Organization, Service, User
from app.schemas.ai import KnowledgeCaptureResult, KnowledgeGapAIResult, KnowledgeQuestion, KnowledgeQuestionsResult
from app.security import hash_password
from app.services import anthropic_client, knowledge_ai
from app.services.anthropic_client import AIConfigurationError, AIOutputError, AnthropicService
from app.services.knowledge_ai import InvalidEvidenceReference, build_gap_context, validate_evidence_ids


@pytest.fixture
def ai_client(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with testing_session() as db:
        organization = Organization(name="AI Test Org")
        foreign_organization = Organization(name="AI Foreign Org")
        db.add_all([organization, foreign_organization])
        db.flush()
        manager = User(organization_id=organization.id, name="Manager", email="manager-ai@example.com", role="manager", password_hash=hash_password("test-password"))
        holder = User(organization_id=organization.id, name="Holder", email="holder-ai@example.com", role="holder", password_hash=hash_password("test-password"))
        admin = User(organization_id=organization.id, name="Admin", email="admin-ai@example.com", role="admin", password_hash=hash_password("test-password"))
        service = Service(organization_id=organization.id, name="Checkout", description="Payment processing", criticality="high")
        foreign_service = Service(organization_id=foreign_organization.id, name="Foreign", description="", criticality="low")
        db.add_all([manager, holder, admin, service, foreign_service])
        db.flush()
        gap = KnowledgeGap(service_id=service.id, title="Retry policy", description="Why did retries change?", priority="high")
        no_evidence_gap = KnowledgeGap(service_id=service.id, title="Unlinked context", description="No source records", priority="medium")
        foreign_gap = KnowledgeGap(service_id=foreign_service.id, title="Foreign gap", description="Private", priority="medium")
        db.add_all([gap, no_evidence_gap, foreign_gap])
        db.flush()
        db.add(Evidence(knowledge_gap_id=gap.id, source_type="github", source_id="pr-1823", title="Retry change", reference="PR #1823", summary="Retry limit changed after a timeout issue."))
        db.commit()

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    main_module._ai_connection_state.update(connection_status="offline", checked_at=None)
    with TestClient(app) as client:
        yield client, testing_session
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def bearer(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": "test-password"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_ai_status_is_admin_only_and_never_returns_key(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = ai_client
    monkeypatch.setattr("app.main.settings", replace(app_settings(), anthropic_api_key="test-secret-not-returned", anthropic_auth_token=None, anthropic_base_url=None, anthropic_model="test-model"))
    manager_headers = bearer(client, "manager-ai@example.com")
    admin_headers = bearer(client, "admin-ai@example.com")

    assert client.get("/api/ai/status").status_code == 401
    assert client.get("/api/ai/status", headers=manager_headers).status_code == 200
    result = client.get("/api/ai/status", headers=admin_headers)
    assert result.status_code == 200
    assert result.json() == {
        "provider": "anthropic",
        "configured": True,
        "credentials_configured": True,
        "model_configured": True,
        "model": "test-model",
        "base_url": None,
        "connection_status": "offline",
        "checked_at": None,
        "message": None,
    }
    assert "test-secret-not-returned" not in result.text


def app_settings():
    from app.config import settings
    return settings


def test_status_reports_missing_configuration_without_calling_provider(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = ai_client
    monkeypatch.setattr("app.main.settings", replace(app_settings(), anthropic_api_key=None, anthropic_auth_token=None, anthropic_base_url=None, anthropic_model=None))
    headers = bearer(client, "admin-ai@example.com")
    result = client.get("/api/ai/status", headers=headers)
    assert result.status_code == 200
    assert result.json()["configured"] is False
    assert result.json()["model_configured"] is False
    assert result.json()["model"] is None

    class MissingConfiguration:
        def __init__(self):
            raise AIConfigurationError("ANTHROPIC_API_KEY is not configured")

    monkeypatch.setattr("app.main.AgentRouter", MissingConfiguration)
    assert client.post("/api/ai/test", headers=headers).status_code == 503


def test_ai_test_endpoint_is_protected_and_returns_test_result(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = ai_client
    manager_headers = bearer(client, "manager-ai@example.com")
    admin_headers = bearer(client, "admin-ai@example.com")
    assert client.post("/api/ai/test", headers=manager_headers).status_code == 403

    class WorkingAI:
        def test_connection(self):
            return "ATLAS AI connection successful."

    monkeypatch.setattr("app.main.AgentRouter", WorkingAI)
    response = client.post("/api/ai/test", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["provider"] == "anthropic"
    assert response.json()["message"] == "ATLAS AI connection successful."
    assert response.json()["connection_status"] == "online"
    assert client.get("/api/ai/status", headers=manager_headers).json()["connection_status"] == "online"


def test_ai_analysis_requires_organization_evidence_and_persists_valid_result(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions = ai_client
    headers = bearer(client, "manager-ai@example.com")
    result_data = KnowledgeGapAIResult(
        potential_gap=True,
        title="Retry behavior rationale",
        summary="The change is visible, but the rationale is not in the supplied evidence.",
        targeted_question="What failure scenario led to reducing retries?",
        reason="The linked change summary does not explain the decision.",
        confidence=0.82,
        evidence_ids=["pr-1823"],
    )
    def fake_analyze(gap, service, evidence):
        build_gap_context(gap, service, evidence)
        return result_data

    monkeypatch.setattr("app.main.analyze_gap", fake_analyze)

    response = client.post("/api/knowledge-gaps/retry-policy/analyze", headers=headers)
    assert response.status_code == 200
    assert response.json()["persisted"] is True
    assert response.json()["analysis"]["evidence_ids"] == ["pr-1823"]
    with sessions() as db:
        gap = db.scalar(select(KnowledgeGap).where(KnowledgeGap.title == "Retry policy"))
        actions = db.scalars(select(AuditLog.action)).all()
        assert gap.ai_analysis["title"] == "Retry behavior rationale"
        assert actions == ["ai.knowledge_gap_analyzed"]

    no_evidence = client.post("/api/knowledge-gaps/unlinked-context/analyze", headers=headers)
    assert no_evidence.status_code == 422
    foreign_gap = client.post("/api/knowledge-gaps/foreign-gap/analyze", headers=headers)
    assert foreign_gap.status_code == 404


def test_unknown_evidence_citation_is_rejected() -> None:
    context = {"evidence": [{"id": "pr-1823"}]}
    with pytest.raises(InvalidEvidenceReference):
        validate_evidence_ids(["jira-invented-9"], context)


def test_question_endpoint_returns_only_validated_evidence_citations(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = ai_client
    headers = bearer(client, "holder-ai@example.com")
    questions = KnowledgeQuestionsResult(questions=[KnowledgeQuestion(
        question="What failure mode motivated the retry change?",
        rationale="The stored source summary records the change but not its rationale.",
        evidence_ids=["pr-1823"],
    )])
    monkeypatch.setattr("app.main.generate_questions", lambda *args: questions)
    response = client.post("/api/knowledge-gaps/retry-policy/questions", headers=headers)
    assert response.status_code == 200
    assert response.json()["questions"][0]["evidence_ids"] == ["pr-1823"]

    invented = KnowledgeQuestionsResult(questions=[KnowledgeQuestion(
        question="Was there an incident?",
        rationale="Not supported by the supplied sources.",
        evidence_ids=["jira-not-supplied"],
    )])
    monkeypatch.setattr("app.main.generate_questions", lambda *args: invented)
    rejected = client.post("/api/knowledge-gaps/retry-policy/questions", headers=headers)
    assert rejected.status_code == 502


def test_context_builder_limits_evidence_and_refuses_empty_context() -> None:
    gap = KnowledgeGap(title="Retries", description="Rationale", priority="high")
    service = Service(name="Checkout", description="", criticality="high")
    evidence = [Evidence(source_id="pr-1", source_type="github", title="Change", reference="", summary="A" * 10000)]
    context = build_gap_context(gap, service, evidence)
    assert len(context["evidence"]) == 1
    assert len(context["evidence"][0]["summary"]) == 1500
    with pytest.raises(knowledge_ai.MissingEvidence):
        build_gap_context(gap, service, [])


def test_structured_client_validates_tool_output_and_repairs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anthropic_client, "settings", replace(app_settings(), anthropic_api_key="test-key", anthropic_model="test-model"))
    valid = {
        "potential_gap": True,
        "title": "Retry rationale",
        "summary": "Rationale not present in supplied sources.",
        "targeted_question": "Why did the retry limit change?",
        "reason": "The change record lacks rationale.",
        "confidence": 0.8,
        "evidence_ids": ["pr-1823"],
    }
    bad_response = SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="gap", input={"confidence": 3})])
    good_response = SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="gap", input=valid)])
    calls = []

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return bad_response if len(calls) == 1 else good_response

    client = AnthropicService(client=SimpleNamespace(messages=FakeMessages()))
    result = client._structured_request("input", KnowledgeGapAIResult, tool_name="gap", tool_description="test")
    assert result.title == "Retry rationale"
    assert len(calls) == 2
    assert "previous result was invalid" in calls[1]["messages"][0]["content"]
    assert calls[0]["model"] == "test-model"


def test_structured_client_fails_cleanly_after_invalid_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anthropic_client, "settings", replace(app_settings(), anthropic_api_key="test-key", anthropic_model="test-model"))
    invalid_response = SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="gap", input={"confidence": 10})])

    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return invalid_response

    messages = FakeMessages()
    client = AnthropicService(client=SimpleNamespace(messages=messages))
    with pytest.raises(AIOutputError):
        client._structured_request("input", KnowledgeGapAIResult, tool_name="gap", tool_description="test")
    assert messages.calls == 2


def test_missing_anthropic_credentials_raise_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(anthropic_client, "settings", replace(app_settings(), anthropic_auth_token=None, anthropic_api_key=None, anthropic_model="model"))
    with pytest.raises(AIConfigurationError, match="ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY"):
        AnthropicService()


def test_agent_router_initializes_official_sdk_for_agentrouter_without_exposing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "test-agentrouter-token"
    monkeypatch.setattr(anthropic_client, "settings", replace(
        app_settings(),
        ai_provider="anthropic",
        anthropic_auth_token=token,
        anthropic_api_key=None,
        anthropic_base_url="https://agentrouter.org",
        anthropic_model="claude-opus-4-8",
    ))
    captured = {}

    class FakeSDKClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(anthropic_client.anthropic, "Anthropic", FakeSDKClient)
    provider = AnthropicService()
    assert provider.model == "claude-opus-4-8"
    assert captured["auth_token"] == token
    assert captured["base_url"] == "https://agentrouter.org"
    assert "api_key" not in captured
    assert token not in repr(provider)


def test_agent_router_rejects_unconfigured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.agent_router import AgentRouter

    monkeypatch.setattr("app.services.agent_router.settings", replace(app_settings(), ai_provider="unknown"))
    with pytest.raises(AIConfigurationError, match="Unsupported AI_PROVIDER"):
        AgentRouter()


def test_agent_router_dispatches_every_task_to_selected_provider() -> None:
    from app.services.agent_router import AgentRouter

    calls = []

    class Provider:
        def __getattr__(self, name):
            def record(*args):
                calls.append((name, args))
                return name
            return record

    router = AgentRouter(provider=Provider())
    operations = (
        router.test_connection(),
        router.analyze_gap({}),
        router.generate_questions({}),
        router.structure_capture({}),
        router.generate_transition_assistance({}),
        router.generate_knowledge_check({}),
        router.verify_answer({}),
    )
    assert operations == tuple(name for name, _ in calls)
    assert len(calls) == 7


def test_capture_structuring_persists_unvalidated_draft(ai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions = ai_client
    headers = bearer(client, "holder-ai@example.com")
    structured = KnowledgeCaptureResult(
        knowledge_type="decision_rationale",
        decision="Retries reduced",
        reason="Timeouts could create duplicate attempts.",
        mitigation="Idempotency handling",
        related_incident="PAY-421",
        related_change="PR #1823",
        confidence=0.91,
        evidence_ids=["pr-1823"],
    )
    monkeypatch.setattr("app.main.structure_capture", lambda *args: structured)
    response = client.post(
        "/api/knowledge-gaps/retry-policy/structure-answer",
        headers=headers,
        json={"question": "Why?", "answer": "Five retries caused duplicate attempts during timeout."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "proposed"
    with sessions() as db:
        record = db.scalar(select(KnowledgeRecord).where(KnowledgeRecord.id == response.json()["id"]))
        gap = db.scalar(select(KnowledgeGap).where(KnowledgeGap.title == "Retry policy"))
        assert record.status == "proposed"
        assert record.submitted_by is not None
        assert gap.status == "open"


@pytest.mark.skipif(os.getenv("RUN_AI_INTEGRATION_TESTS") != "true", reason="Set RUN_AI_INTEGRATION_TESTS=true to call Anthropic")
def test_optional_real_anthropic_integration() -> None:
    from app.services.agent_router import AgentRouter
    assert AgentRouter().test_connection() == "ATLAS AI connection successful."

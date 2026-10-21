from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditLog, Evidence, Integration, KnowledgeGap, Organization, Repository, Service, User
from app.schemas.ai import KnowledgeGapAIResult
from app.security import hash_password
from app.integrations.github.client import GitHubClient, GitHubNotConfiguredError
from app.services.github_evidence import calculate_continuity_signals, to_github_context


@pytest.fixture
def github_client() -> Generator[tuple[TestClient, sessionmaker[Session], int, int], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with testing_session() as db:
        org = Organization(name="GitHub Test Org")
        other = Organization(name="Other Org")
        db.add_all([org, other])
        db.flush()
        manager = User(organization_id=org.id, name="Manager", email="github-manager@example.com", role="manager", password_hash=hash_password("test-password"))
        incoming = User(organization_id=org.id, name="Incoming", email="github-incoming@example.com", role="incoming", password_hash=hash_password("test-password"))
        db.add_all([manager, incoming])
        db.flush()
        repo = Repository(organization_id=org.id, name="acme/payments", provider="github", external_id="repo-123")
        foreign_repo = Repository(organization_id=other.id, name="acme/private", provider="github", external_id="repo-456")
        db.add_all([repo, foreign_repo])
        db.commit()
        org_id, repo_id, foreign_repo_id = org.id, repo.id, foreign_repo.id

    def override_db() -> Generator[Session, None, None]:
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    main_module._ai_connection_state.update(connection_status="offline", checked_at=None)
    with TestClient(app) as client:
        yield client, testing_session, repo_id, foreign_repo_id
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def auth(client: TestClient, email: str) -> dict[str, str]:
    result = client.post("/api/auth/login", json={"email": email, "password": "test-password"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


class FakeGitHub:
    def __init__(self, **kwargs):
        pass

    def repositories(self):
        return [{"id": 123, "full_name": "acme/payments", "name": "payments", "description": "Payments", "language": "Python", "default_branch": "main", "html_url": "https://github.com/acme/payments", "updated_at": "2026-10-07T10:00:00Z", "private": True}]

    def pull_requests(self, repository):
        return [{"number": 17, "id": 1717, "title": "Reduce retry count", "body": "Provider timeout behavior changed.", "state": "closed", "merged_at": "2026-10-01T12:00:00Z", "user": {"login": "dev-a", "avatar_url": "https://avatars.example/dev-a"}, "html_url": "https://github.com/acme/payments/pull/17", "changed_files": 2, "commits": 1, "additions": 5, "deletions": 2}]

    def pull_request(self, repository, number):
        assert repository == "acme/payments"
        assert number == 17
        return self.pull_requests(repository)[0] | {"merged": True}

    def pull_request_files(self, repository, number):
        return [{"filename": "payments/retry.py", "status": "modified", "additions": 2, "deletions": 1, "changes": 3, "patch": "@@ -1 +1 @@\n-MAX_RETRIES = 5\n+MAX_RETRIES = 3", "blob_url": "https://github.com/acme/payments/blob/main/payments/retry.py"}]

    def pull_request_reviews(self, repository, number):
        return [{"user": {"login": "reviewer-a"}, "state": "APPROVED", "submitted_at": "2026-10-02T12:00:00Z", "body": "Looks good"}]

    def pull_request_commits(self, repository, number):
        return [{"sha": "abc123", "commit": {"message": "Reduce retry attempts", "author": {"name": "Dev A"}}, "author": {"login": "dev-a"}}]

    def contributors(self, repository):
        return [{"login": "dev-a"}, {"login": "dev-b"}, {"login": "dev-c"}]


def test_github_client_paginates_and_rejects_cross_namespace_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient(token="test-token", org="acme")
    calls = []

    class FakeResponse:
        def __init__(self, payload, links):
            self.payload = payload
            self.links = links

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_get(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return FakeResponse([{"id": 1}], {"next": {"url": "https://api.github.com/orgs/acme/repos?page=2"}})
        return FakeResponse([{"id": 2}], {})

    monkeypatch.setattr("app.integrations.github.client.httpx.get", fake_get)
    assert client._paginated("/orgs/acme/repos", {"per_page": 1}) == [{"id": 1}, {"id": 2}]
    assert len(calls) == 2
    with pytest.raises(ValueError, match="outside the configured GitHub organization"):
        client.pull_requests("other/private")


def test_owner_mode_exposes_only_repositories_returned_by_authenticated_account(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient(token="test-token", org="", owner="Pradeep220931")
    monkeypatch.setattr(client, "_request", lambda path, params=None: {"login": "Pradeep220931"})
    monkeypatch.setattr(client, "_paginated", lambda path, params=None: [
        {"full_name": "Pradeep220931/Atlas"},
        {"full_name": "kishorea-sudo/shared-project"},
    ])
    client.repositories()
    assert client._repository_path("kishorea-sudo/shared-project") == "/repos/kishorea-sudo/shared-project"
    with pytest.raises(ValueError, match="not accessible to the configured GitHub account"):
        client._repository_path("unknown/private")


def test_owner_mode_rejects_mismatched_github_token_user(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GitHubClient(token="test-token", org="", owner="Pradeep220931")
    monkeypatch.setattr(client, "_request", lambda path, params=None: {"login": "someone-else"})
    with pytest.raises(GitHubNotConfiguredError, match="does not match GITHUB_OWNER"):
        client.repositories()


def test_github_signals_are_deterministic_and_scoped() -> None:
    pull_requests = [{"user": {"login": "dominant"}} for _ in range(11)] + [{"user": {"login": "other"}} for _ in range(9)]
    signals = calculate_continuity_signals(
        pull_requests,
        [{"login": "a"}, {"login": "b"}, {"login": "c"}],
        [{"user": {"login": "reviewer"}, "state": "APPROVED"}, {"user": {"login": "reviewer"}, "state": "CHANGES_REQUESTED"}],
        [{"filename": "README.md"}, {"filename": "src/main.py"}],
    )
    assert signals["contribution_concentration"]["status"] == "MODERATE"
    assert signals["contributor_redundancy"]["distinct_github_accounts"] == 3
    assert signals["selected_pr_review_concentration"]["status"] == "HIGH"
    assert signals["documentation_change_coverage"]["share"] == 0.5
    assert signals["jira_decision_traceability"] == "NOT_CONNECTED"


def test_live_github_endpoints_are_tenant_scoped_and_return_provider_data(github_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions, repo_id, foreign_repo_id = github_client
    manager_headers = auth(client, "github-manager@example.com")
    incoming_headers = auth(client, "github-incoming@example.com")
    monkeypatch.setattr("app.main.GitHubClient", FakeGitHub)

    repositories = client.get("/api/github/repositories", headers=manager_headers)
    assert repositories.status_code == 200
    assert repositories.json()[0]["full_name"] == "acme/payments"
    with sessions() as db:
        assert db.scalar(select(Integration).where(Integration.provider == "github")).status == "connected"

    forbidden = client.get(f"/api/github/repositories/{repo_id}/pull-requests", headers=incoming_headers)
    assert forbidden.status_code == 403
    foreign = client.get(f"/api/github/repositories/{foreign_repo_id}/pull-requests", headers=manager_headers)
    assert foreign.status_code == 404

    pull_requests = client.get(f"/api/github/repositories/{repo_id}/pull-requests", headers=manager_headers)
    assert pull_requests.status_code == 200
    assert pull_requests.json()[0]["number"] == 17
    assert pull_requests.json()[0]["merged"] is True

    evidence = client.get(f"/api/github/repositories/{repo_id}/pull-requests/17/evidence", headers=manager_headers)
    assert evidence.status_code == 200
    assert evidence.json()["files"][0]["patch"].endswith("+MAX_RETRIES = 3")
    assert evidence.json()["reviews"][0]["user"] == "reviewer-a"
    assert evidence.json()["signals"]["jira_decision_traceability"] == "NOT_CONNECTED"
    assert evidence.json()["ai_context_ready"] is True
    assert evidence.json()["ai_context_record_count"] >= 1


def test_analyze_real_provider_payload_persists_gap_evidence_and_trace(github_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions, repo_id, _ = github_client
    headers = auth(client, "github-manager@example.com")
    monkeypatch.setattr("app.main.GitHubClient", FakeGitHub)
    monkeypatch.setattr("app.main.retrieve_pull_request_evidence", lambda gh, repo, number: __import__("app.services.github_evidence", fromlist=["retrieve_pull_request_evidence"]).retrieve_pull_request_evidence(FakeGitHub(), repo, number))
    result = KnowledgeGapAIResult(
        potential_gap=True,
        title="Retry strategy rationale",
        summary="A retry policy changed, but the supplied PR does not contain its rationale.",
        targeted_question="Which failure mode caused retry attempts to be reduced?",
        reason="The PR patch changes retries without documenting why.",
        confidence=0.88,
        evidence_ids=["github:pr:1717", "github:pr:1717:file:0"],
    )
    monkeypatch.setattr("app.main.analyze_gap", lambda gap, service, evidence, signals: result)

    response = client.post(f"/api/github/repositories/{repo_id}/pull-requests/17/analyze", headers=headers)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["persisted"] is True
    assert payload["analysis"]["targeted_question"].startswith("Which failure mode")
    assert payload["provider"] == "anthropic"
    assert payload["stages"][-1]["status"] == "complete"
    with sessions() as db:
        gap = db.scalar(select(KnowledgeGap).where(KnowledgeGap.title == "Retry strategy rationale"))
        assert gap is not None
        assert gap.ai_analysis["source_ref"] == "github:pr:1717"
        evidence_rows = db.scalars(select(Evidence).where(Evidence.knowledge_gap_id == gap.id)).all()
        assert any("MAX_RETRIES = 3" in item.summary for item in evidence_rows)
        assert db.scalars(select(AuditLog.action)).all() == ["ai.github_pull_request_analyzed"]

    response_again = client.post(f"/api/github/repositories/{repo_id}/pull-requests/17/analyze", headers=headers)
    assert response_again.status_code == 200
    with sessions() as db:
        assert len(db.scalars(select(KnowledgeGap)).all()) == 1
        saved_gap = db.scalar(select(KnowledgeGap))
        assert len(db.scalars(select(Evidence).where(Evidence.knowledge_gap_id == saved_gap.id)).all()) == 4


def test_negative_ai_result_does_not_persist_a_knowledge_gap(github_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, sessions, repo_id, _ = github_client
    headers = auth(client, "github-manager@example.com")
    monkeypatch.setattr("app.main.GitHubClient", FakeGitHub)
    monkeypatch.setattr("app.main.retrieve_pull_request_evidence", lambda gh, repo, number: __import__("app.services.github_evidence", fromlist=["retrieve_pull_request_evidence"]).retrieve_pull_request_evidence(FakeGitHub(), repo, number))
    result = KnowledgeGapAIResult(
        potential_gap=False,
        title="No supported gap",
        summary="The supplied records do not show missing technical context.",
        targeted_question="What additional source would clarify this change?",
        reason="The supplied evidence is sufficient for this change.",
        confidence=0.74,
        evidence_ids=["github:pr:1717"],
    )
    monkeypatch.setattr("app.main.analyze_gap", lambda *args: result)

    response = client.post(f"/api/github/repositories/{repo_id}/pull-requests/17/analyze", headers=headers)
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    assert response.json()["stages"][-1]["status"] == "skipped"
    with sessions() as db:
        assert db.scalars(select(KnowledgeGap)).all() == []

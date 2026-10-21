from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.entities import AuditLog, KnowledgeRecord, KnowledgeGap, Organization, Service, User
from app.security import hash_password


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with TestingSession() as db:
        organization = Organization(name="Test Org")
        db.add(organization)
        db.flush()
        manager = User(
            organization_id=organization.id,
            name="Test Manager",
            email="manager@example.com",
            role="manager",
            password_hash=hash_password("test-password"),
        )
        holder = User(
            organization_id=organization.id,
            name="Test Holder",
            email="holder@example.com",
            role="holder",
            password_hash=hash_password("test-password"),
        )
        incoming = User(
            organization_id=organization.id,
            name="Incoming Engineer",
            email="incoming@example.com",
            role="incoming",
            password_hash=hash_password("test-password"),
        )
        service = Service(organization_id=organization.id, name="Checkout", description="", criticality="high")
        db.add_all([manager, holder, incoming, service])
        db.flush()
        db.add(KnowledgeGap(service_id=service.id, title="Retry policy", description="Rationale needed"))
        db.commit()

    def override_get_db() -> Generator[Session, None, None]:
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def token_for(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": "test-password"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_knowledge_capture_requires_manager_review_and_persists_audit(client: TestClient) -> None:
    holder_token = token_for(client, "holder@example.com")
    manager_token = token_for(client, "manager@example.com")
    gap_id = "retry-policy"

    submitted = client.post(
        f"/api/knowledge-gaps/{gap_id}/capture",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"answer": "The retry limit avoids duplicate authorization attempts."},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "Open"

    records = client.get(
        f"/api/knowledge-gaps/{gap_id}/records",
        headers={"Authorization": f"Bearer {holder_token}"},
    )
    assert records.status_code == 200
    assert len(records.json()) == 1
    record = records.json()[0]
    assert record["reason"] == "The retry limit avoids duplicate authorization attempts."
    assert record["status"] == "proposed"
    assert record["submitted_by"] == "Test Holder"

    forbidden = client.post(
        f"/api/knowledge-gaps/{gap_id}/records/{record['id']}/validate",
        headers={"Authorization": f"Bearer {holder_token}"},
        json={"decision": "approve"},
    )
    assert forbidden.status_code == 403

    approved = client.post(
        f"/api/knowledge-gaps/{gap_id}/records/{record['id']}/validate",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"decision": "approve", "comment": "Reviewed with the service owner."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "validated"
    assert approved.json()["validated_by"] == "Test Manager"
    assert client.get(
        f"/api/knowledge-gaps/{gap_id}",
        headers={"Authorization": f"Bearer {manager_token}"},
    ).json()["status"] == "Validated"

    with next(app.dependency_overrides[get_db]()) as db:
        saved_record = db.scalar(select(KnowledgeRecord).where(KnowledgeRecord.id == record["id"]))
        audit_actions = db.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
        assert saved_record is not None
        assert saved_record.reason == "The retry limit avoids duplicate authorization attempts."
        assert audit_actions == ["knowledge.submitted", "knowledge.approve"]


def test_knowledge_record_review_is_organization_scoped(client: TestClient) -> None:
    manager_token = token_for(client, "manager@example.com")
    with next(app.dependency_overrides[get_db]()) as db:
        foreign_organization = Organization(name="Foreign Org")
        db.add(foreign_organization)
        db.flush()
        foreign_service = Service(organization_id=foreign_organization.id, name="Foreign Checkout", description="", criticality="high")
        db.add(foreign_service)
        db.flush()
        foreign_gap = KnowledgeGap(service_id=foreign_service.id, title="Retry policy", description="Foreign rationale")
        db.add(foreign_gap)
        db.flush()
        foreign_record = KnowledgeRecord(
            knowledge_gap_id=foreign_gap.id,
            decision=foreign_gap.title,
            reason="Foreign organization context",
            affected_system=foreign_service.name,
            status="proposed",
        )
        db.add(foreign_record)
        db.commit()
        foreign_record_id = foreign_record.id

    hidden = client.post(
        f"/api/knowledge-gaps/retry-policy/records/{foreign_record_id}/validate",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"decision": "approve"},
    )
    assert hidden.status_code == 404

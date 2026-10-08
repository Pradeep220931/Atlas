from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from httpx import HTTPError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased
from jwt import InvalidTokenError

from app.integrations.github.client import GitHubClient, GitHubNotConfiguredError
from app.integrations.jira.client import JiraClient, JiraNotConfiguredError
from app.config import settings
from app.database import get_db
from app.models.entities import AuditLog, Integration, KnowledgeGap, KnowledgeRecord, Service, User
from app.security import create_access_token, decode_access_token, verify_password

app = FastAPI(title="ATLAS API", version="0.1.0")
app.add_middleware(
	CORSMiddleware,
	allow_origins=list(settings.cors_origins),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

Role = Literal["manager", "holder", "incoming", "admin"]


class LoginRequest(BaseModel):
	email: EmailStr
	password: str


class DemoUser(BaseModel):
	name: str
	email: EmailStr
	role: Role


class Gap(BaseModel):
	id: str
	title: str
	description: str
	service: str
	ref: str
	status: Literal["Open", "Validated"]


class CaptureRequest(BaseModel):
	answer: str


class KnowledgeRecordResponse(BaseModel):
	id: int
	gap_id: str
	decision: str
	reason: str
	affected_system: str
	status: Literal["proposed", "validated", "rejected", "needs_clarification"]
	submitted_by: str | None
	validated_by: str | None
	validated_at: datetime | None
	created_at: datetime


class ValidationRequest(BaseModel):
	decision: Literal["approve", "reject", "request_clarification"]
	comment: str = ""


class IntegrationStatus(BaseModel):
	provider: str
	configured: bool
	status: str
	details: str


class UserResponse(BaseModel):
	name: str
	email: EmailStr
	role: Role


security = HTTPBearer(auto_error=False)


DEMO_USERS = {
	"manager@finpay.demo": DemoUser(name="Engineering Manager", email="manager@finpay.demo", role="manager"),
	"arun@finpay.demo": DemoUser(name="Arun Kumar", email="arun@finpay.demo", role="holder"),
	"priya@finpay.demo": DemoUser(name="Priya Sharma", email="priya@finpay.demo", role="incoming"),
	"admin@finpay.demo": DemoUser(name="Admin / CTO", email="admin@finpay.demo", role="admin"),
}
@app.get("/api/integrations", response_model=list[IntegrationStatus])
def integration_status() -> list[IntegrationStatus]:
	return [
		IntegrationStatus(
			provider="github",
			configured=bool(settings.github_token and (settings.github_org or settings.github_owner)),
			status="connected" if settings.github_token and (settings.github_org or settings.github_owner) else "not_configured",
			details="Repository and pull request activity" if settings.github_token and (settings.github_org or settings.github_owner) else "Set GITHUB_TOKEN and GITHUB_ORG or GITHUB_OWNER",
		),
		IntegrationStatus(
			provider="jira",
			configured=bool(settings.jira_base_url and settings.jira_email and settings.jira_api_token),
			status="connected" if settings.jira_base_url and settings.jira_email and settings.jira_api_token else "not_configured",
			details="Projects and issue context" if settings.jira_base_url and settings.jira_email and settings.jira_api_token else "Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN",
		),
	]


@app.get("/health")
def health() -> dict[str, str]:
	return {"status": "ok", "service": "atlas-api"}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, object]:
	user = db.scalar(select(User).where(User.email == str(payload.email).lower(), User.is_active.is_(True)))
	if user is None or not verify_password(payload.password, user.password_hash):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
	token = create_access_token(str(user.id), user.role, user.organization_id)
	return {"access_token": token, "token_type": "bearer", "user": UserResponse(name=user.name, email=user.email, role=user.role)}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(get_db)) -> User:
	if credentials is None:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
	try:
		claims = decode_access_token(credentials.credentials)
		user_id = int(claims["sub"])
	except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
	user = db.get(User, user_id)
	if user is None or not user.is_active or user.organization_id != claims.get("organization_id"):
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
	return user


def require_roles(*roles: Role):
	def dependency(user: User = Depends(current_user)) -> User:
		if user.role not in roles:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
		return user
	return dependency


@app.get("/api/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> UserResponse:
	return UserResponse(name=user.name, email=user.email, role=user.role)


@app.get("/api/workspace")
def workspace(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, object]:
	last_sync = "Not synced"
	integration = db.scalar(select(Integration).where(Integration.organization_id == user.organization_id, Integration.provider == "github"))
	if integration and integration.last_synced_at:
		last_sync = integration.last_synced_at.isoformat()
	return {
		"name": "FinPay / Engineering",
		"organization_id": user.organization_id,
		"demo": True,
		"engineers": 64,
		"teams": 5,
		"services": 18,
		"knowledge_gaps": 12,
		"high_risk_areas": 3,
		"active_transitions": 1,
		"last_synced": last_sync,
	}


def _gap_response(gap: KnowledgeGap, service: Service) -> Gap:
	slug = gap.title.lower().replace(" ", "-")
	return Gap(id=slug, title=gap.title, description=gap.description, service=service.name, ref="No source evidence linked", status="Validated" if gap.status == "validated" else "Open")


@app.get("/api/knowledge-gaps", response_model=list[Gap])
def list_knowledge_gaps(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[Gap]:
	rows = db.execute(select(KnowledgeGap, Service).join(Service, KnowledgeGap.service_id == Service.id).where(Service.organization_id == user.organization_id)).all()
	return [_gap_response(gap, service) for gap, service in rows]


@app.get("/api/knowledge-gaps/{gap_id}", response_model=Gap)
def get_knowledge_gap(gap_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Gap:
	rows = db.execute(select(KnowledgeGap, Service).join(Service, KnowledgeGap.service_id == Service.id).where(Service.organization_id == user.organization_id)).all()
	for gap, service in rows:
		if gap.title.lower().replace(" ", "-") == gap_id:
			return _gap_response(gap, service)
	raise HTTPException(status_code=404, detail="Knowledge gap not found")


@app.post("/api/knowledge-gaps/{gap_id}/capture", response_model=Gap)
def capture_knowledge(gap_id: str, payload: CaptureRequest, user: User = Depends(require_roles("manager", "holder")), db: Session = Depends(get_db)) -> Gap:
	if not payload.answer.strip():
		raise HTTPException(status_code=422, detail="An answer is required")
	rows = db.execute(select(KnowledgeGap, Service).join(Service, KnowledgeGap.service_id == Service.id).where(Service.organization_id == user.organization_id)).all()
	for gap, service in rows:
		if gap.title.lower().replace(" ", "-") == gap_id:
			record = KnowledgeRecord(
				knowledge_gap_id=gap.id,
				knowledge_area_id=gap.knowledge_area_id,
				decision=gap.title,
				reason=payload.answer.strip(),
				affected_system=service.name,
				status="proposed",
				submitted_by=user.id,
			)
			db.add(record)
			db.add(AuditLog(
				organization_id=user.organization_id,
				user_id=user.id,
				action="knowledge.submitted",
				resource_type="knowledge_gap",
				resource_id=str(gap.id),
				metadata_json={"record_title": gap.title},
			))
			db.commit()
			return _gap_response(gap, service)
	raise HTTPException(status_code=404, detail="Knowledge gap not found")


def _knowledge_record_response(record: KnowledgeRecord, submitter: User | None, validator: User | None, gap_id: str) -> KnowledgeRecordResponse:
	return KnowledgeRecordResponse(
		id=record.id,
		gap_id=gap_id,
		decision=record.decision,
		reason=record.reason,
		affected_system=record.affected_system,
		status=record.status,
		submitted_by=submitter.name if submitter else None,
		validated_by=validator.name if validator else None,
		validated_at=record.validated_at,
		created_at=record.created_at,
	)


@app.get("/api/knowledge-gaps/{gap_id}/records", response_model=list[KnowledgeRecordResponse])
def list_knowledge_records(gap_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[KnowledgeRecordResponse]:
	submitter = aliased(User)
	validator = aliased(User)
	rows = db.execute(
		select(KnowledgeRecord, KnowledgeGap, submitter, validator)
		.join(KnowledgeGap, KnowledgeRecord.knowledge_gap_id == KnowledgeGap.id)
		.join(Service, KnowledgeGap.service_id == Service.id)
		.outerjoin(submitter, KnowledgeRecord.submitted_by == submitter.id)
		.outerjoin(validator, KnowledgeRecord.validated_by == validator.id)
		.where(Service.organization_id == user.organization_id)
		.order_by(KnowledgeRecord.created_at.desc(), KnowledgeRecord.id.desc())
	).all()
	return [
		_knowledge_record_response(record, submitter_user, validator_user, gap.title.lower().replace(" ", "-"))
		for record, gap, submitter_user, validator_user in rows
		if gap.title.lower().replace(" ", "-") == gap_id
	]


@app.post("/api/knowledge-gaps/{gap_id}/records/{record_id}/validate", response_model=KnowledgeRecordResponse)
def validate_knowledge_record(
	gap_id: str,
	record_id: int,
	payload: ValidationRequest,
	user: User = Depends(require_roles("manager")),
	db: Session = Depends(get_db),
) -> KnowledgeRecordResponse:
	submitter = aliased(User)
	row = db.execute(
		select(KnowledgeRecord, KnowledgeGap, Service, submitter)
		.join(KnowledgeGap, KnowledgeRecord.knowledge_gap_id == KnowledgeGap.id)
		.join(Service, KnowledgeGap.service_id == Service.id)
		.outerjoin(submitter, KnowledgeRecord.submitted_by == submitter.id)
		.where(
			KnowledgeRecord.id == record_id,
			Service.organization_id == user.organization_id,
			func.lower(func.replace(KnowledgeGap.title, " ", "-")) == gap_id,
		)
	).first()
	if row is None:
		raise HTTPException(status_code=404, detail="Knowledge record not found")
	record, gap, service, submitter_user = row
	if record.status != "proposed":
		raise HTTPException(status_code=409, detail="Only proposed knowledge can be reviewed")
	statuses = {"approve": "validated", "reject": "rejected", "request_clarification": "needs_clarification"}
	record.status = statuses[payload.decision]
	if payload.decision == "approve":
		record.validated_by = user.id
		record.validated_at = datetime.now(timezone.utc)
		gap.status = "validated"
	db.add(AuditLog(
		organization_id=user.organization_id,
		user_id=user.id,
		action=f"knowledge.{payload.decision}",
		resource_type="knowledge_record",
		resource_id=str(record.id),
		metadata_json={"comment": payload.comment.strip()},
	))
	db.commit()
	db.refresh(record)
	return _knowledge_record_response(record, submitter_user, user if payload.decision == "approve" else None, gap.title.lower().replace(" ", "-"))


@app.post("/api/integrations/{provider}/sync")
def sync_integration(provider: str, user: User = Depends(require_roles("manager", "admin")), db: Session = Depends(get_db)) -> dict[str, object]:
	try:
		if provider.lower() == "github":
			result = GitHubClient().sync_summary()
		elif provider.lower() == "jira":
			result = JiraClient().sync_summary()
		else:
			raise HTTPException(status_code=404, detail="Integration not found")
	except (GitHubNotConfiguredError, JiraNotConfiguredError) as error:
		raise HTTPException(status_code=503, detail=str(error)) from error
	except HTTPError as error:
		raise HTTPException(status_code=502, detail="The integration provider could not be reached") from error
	completed_at = datetime.now(timezone.utc)
	integration = db.scalar(select(Integration).where(Integration.organization_id == user.organization_id, Integration.provider == provider.lower()))
	if integration is None:
		integration = Integration(organization_id=user.organization_id, provider=provider.lower())
		db.add(integration)
	integration.status = "connected"
	integration.last_synced_at = completed_at
	db.commit()
	return {"provider": provider.lower(), "completed_at": completed_at.isoformat(), **result}

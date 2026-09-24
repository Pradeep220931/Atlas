from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from httpx import HTTPError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from jwt import InvalidTokenError

from app.integrations.github.client import GitHubClient, GitHubNotConfiguredError
from app.integrations.jira.client import JiraClient, JiraNotConfiguredError
from app.config import settings
from app.database import get_db
from app.models.entities import Integration, KnowledgeGap, Service, User
from app.security import decode_supabase_token

app = FastAPI(title="ATLAS API", version="0.1.0")
app.add_middleware(
	CORSMiddleware,
	allow_origins=list(settings.cors_origins),
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

Role = Literal["manager", "holder", "incoming", "admin"]


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


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(get_db)) -> User:
	if credentials is None:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
	try:
		claims = decode_supabase_token(credentials.credentials)
		email = str(claims.get("email", "")).lower()
		if not email:
			raise InvalidTokenError("Supabase token has no email claim")
	except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
		raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from error
	user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
	if user is None:
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
	refs = {"Payment retry policy": "PR-1823 · PAY-421", "Gateway timeout behaviour": "PR-1774", "Refund reconciliation behaviour": "PAY-398"}
	slug = gap.title.lower().replace(" ", "-")
	return Gap(id=slug, title=gap.title, description=gap.description, service=service.name, ref=refs.get(gap.title, "Connected source evidence"), status="Validated" if gap.status == "validated" else "Open")


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
			gap.status = "validated"
			db.commit()
			return _gap_response(gap, service)
	raise HTTPException(status_code=404, detail="Knowledge gap not found")


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

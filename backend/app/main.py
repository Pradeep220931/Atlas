from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from httpx import HTTPError
from sqlalchemy import select
from sqlalchemy.orm import Session
from jwt import InvalidTokenError

from app.integrations.github.client import GitHubClient, GitHubNotConfiguredError
from app.integrations.jira.client import JiraClient, JiraNotConfiguredError
from app.config import settings
from app.database import get_db
from app.models.entities import User
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
GAPS = [
	Gap(id="payment-retry-policy", title="Payment retry policy", description="Decision exists, rationale not found", service="Payment Service", ref="PR-1823 · PAY-421", status="Open"),
	Gap(id="gateway-timeout", title="Gateway timeout behaviour", description="Implementation exists, context unclear", service="Payment Service", ref="PR-1774", status="Open"),
	Gap(id="refund-reconciliation", title="Refund reconciliation behaviour", description="Operational context unclear", service="Refund Engine", ref="PAY-398", status="Open"),
]


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
def workspace(user: User = Depends(current_user)) -> dict[str, object]:
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
		"last_synced": "8 min ago",
	}


@app.get("/api/knowledge-gaps", response_model=list[Gap])
def list_knowledge_gaps() -> list[Gap]:
	return GAPS


@app.get("/api/knowledge-gaps/{gap_id}", response_model=Gap)
def get_knowledge_gap(gap_id: str) -> Gap:
	for gap in GAPS:
		if gap.id == gap_id:
			return gap
	raise HTTPException(status_code=404, detail="Knowledge gap not found")


@app.post("/api/knowledge-gaps/{gap_id}/capture", response_model=Gap)
def capture_knowledge(gap_id: str, payload: CaptureRequest) -> Gap:
	if not payload.answer.strip():
		raise HTTPException(status_code=422, detail="An answer is required")
	gap = get_knowledge_gap(gap_id)
	gap.status = "Validated"
	return gap


@app.post("/api/integrations/{provider}/sync")
def sync_integration(provider: str) -> dict[str, object]:
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
	return {"provider": provider.lower(), "completed_at": datetime.now(timezone.utc).isoformat(), **result}

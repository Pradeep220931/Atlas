from datetime import datetime, timezone
import logging
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
from app.models.entities import AuditLog, Evidence, Integration, KnowledgeGap, KnowledgeRecord, Repository, Service, User
from app.security import create_access_token, decode_access_token, verify_password
from app.services.anthropic_client import AIConfigurationError, AIOutputError, AIProviderError
from app.services.agent_router import AgentRouter
from app.services.knowledge_ai import InvalidEvidenceReference, MissingEvidence, analyze_gap, generate_questions, structure_capture
from app.schemas.github import AITraceStage, GitHubAnalysisResponse, GitHubEvidenceResponse, GitHubFileEvidence, GitHubPullRequestResponse, GitHubRepositoryResponse
from app.services.github_evidence import MAX_AI_FILES, MAX_PATCH_CHARS, retrieve_pull_request_evidence, to_github_context

logger = logging.getLogger(__name__)
_ai_connection_state: dict[str, object] = {"connection_status": "offline", "checked_at": None}

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
	ai_analysis: dict[str, object] | None = None


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


class StructureCaptureRequest(BaseModel):
	question: str
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


def _github_error(error: Exception) -> HTTPException:
	if isinstance(error, GitHubNotConfiguredError):
		return HTTPException(status_code=503, detail=str(error))
	if isinstance(error, ValueError):
		return HTTPException(status_code=422, detail=str(error))
	if isinstance(error, HTTPError):
		status_code = getattr(getattr(error, "response", None), "status_code", None)
		if status_code == 403 and getattr(error.response, "headers", {}).get("X-RateLimit-Remaining") == "0":
			return HTTPException(status_code=429, detail="GitHub API rate limit reached. Try again after the reset time.")
		if status_code in (401, 403):
			return HTTPException(status_code=502, detail="GitHub rejected the configured credentials or repository access")
		if status_code == 404:
			return HTTPException(status_code=404, detail="GitHub repository or pull request was not found or is not accessible")
		logger.warning("GitHub request failed with status %s", status_code)
		return HTTPException(status_code=502, detail="GitHub could not complete the request")
	logger.exception("Unexpected GitHub evidence failure")
	return HTTPException(status_code=502, detail="GitHub evidence could not be retrieved")


def _repository_response(repository: Repository, raw: dict[str, object] | None = None) -> GitHubRepositoryResponse:
	metadata = raw or {}
	return GitHubRepositoryResponse(
		id=repository.id,
		full_name=repository.name,
		description=metadata.get("description") if isinstance(metadata.get("description"), str) else None,
		language=metadata.get("language") if isinstance(metadata.get("language"), str) else None,
		default_branch=str(metadata.get("default_branch") or ""),
		html_url=str(metadata.get("html_url") or f"https://github.com/{repository.name}"),
		updated_at=metadata.get("updated_at"),
		private=bool(metadata.get("private", False)),
	)


def _pr_response(raw: dict[str, object]) -> GitHubPullRequestResponse:
	user_data = raw.get("user") if isinstance(raw.get("user"), dict) else {}
	return GitHubPullRequestResponse(
		number=int(raw["number"]),
		title=str(raw.get("title") or "(untitled pull request)"),
		body=raw.get("body") if isinstance(raw.get("body"), str) else None,
		state=str(raw.get("state") or "unknown"),
		merged=bool(raw.get("merged", False) or raw.get("merged_at")),
		author=user_data.get("login") if isinstance(user_data, dict) else None,
		author_avatar_url=user_data.get("avatar_url") if isinstance(user_data, dict) else None,
		html_url=str(raw.get("html_url") or ""),
		created_at=raw.get("created_at"),
		updated_at=raw.get("updated_at"),
		merged_at=raw.get("merged_at"),
		changed_files=int(raw.get("changed_files") or 0),
		commits=int(raw.get("commits") or 0),
		additions=int(raw.get("additions") or 0),
		deletions=int(raw.get("deletions") or 0),
	)


def _tenant_repository(repository_id: int, organization_id: int, db: Session) -> Repository:
	repository = db.scalar(select(Repository).where(
		Repository.id == repository_id,
		Repository.organization_id == organization_id,
		Repository.provider == "github",
	))
	if repository is None:
		raise HTTPException(status_code=404, detail="GitHub repository not found in this workspace")
	return repository


@app.get("/api/github/repositories", response_model=list[GitHubRepositoryResponse])
def list_github_repositories(user: User = Depends(require_roles("manager", "admin")), db: Session = Depends(get_db)) -> list[GitHubRepositoryResponse]:
	try:
		remote_repositories = GitHubClient().repositories()
		responses = []
		for item in remote_repositories:
			full_name = item.get("full_name")
			external_id = item.get("id")
			if not isinstance(full_name, str) or not isinstance(external_id, (int, str)):
				continue
			repository = db.scalar(select(Repository).where(
				Repository.organization_id == user.organization_id,
				Repository.provider == "github",
				Repository.external_id == str(external_id),
			))
			if repository is None:
				repository = Repository(organization_id=user.organization_id, name=full_name, provider="github", external_id=str(external_id))
				db.add(repository)
			else:
				repository.name = full_name
			responses.append((repository, item))
		integration = db.scalar(select(Integration).where(Integration.organization_id == user.organization_id, Integration.provider == "github"))
		if integration is None:
			integration = Integration(organization_id=user.organization_id, provider="github")
			db.add(integration)
		integration.status = "connected"
		integration.last_synced_at = datetime.now(timezone.utc)
		db.commit()
		return [_repository_response(repository, item) for repository, item in responses]
	except (GitHubNotConfiguredError, HTTPError, ValueError) as error:
		db.rollback()
		raise _github_error(error) from error


@app.get("/api/github/repositories/{repository_id}/pull-requests", response_model=list[GitHubPullRequestResponse])
def list_github_pull_requests(repository_id: int, user: User = Depends(require_roles("manager", "admin")), db: Session = Depends(get_db)) -> list[GitHubPullRequestResponse]:
	repository = _tenant_repository(repository_id, user.organization_id, db)
	try:
		pull_requests = GitHubClient().pull_requests(repository.name)
	except (GitHubNotConfiguredError, HTTPError, ValueError) as error:
		raise _github_error(error) from error
	return [_pr_response(item) for item in pull_requests[:100]]


@app.get("/api/github/repositories/{repository_id}/pull-requests/{number}/evidence", response_model=GitHubEvidenceResponse)
def github_pull_request_evidence(repository_id: int, number: int, user: User = Depends(require_roles("manager", "admin")), db: Session = Depends(get_db)) -> GitHubEvidenceResponse:
	repository = _tenant_repository(repository_id, user.organization_id, db)
	try:
		client = GitHubClient()
		data = retrieve_pull_request_evidence(client, repository.name, number)
	except (GitHubNotConfiguredError, HTTPError, ValueError) as error:
		raise _github_error(error) from error
	bounded_context = to_github_context(repository.name, data)
	return GitHubEvidenceResponse(
		repository=_repository_response(repository),
		pull_request=_pr_response(data["pull_request"]),
		files=[GitHubFileEvidence(
			filename=str(item.get("filename") or "(filename unavailable)"),
			status=str(item.get("status") or "unknown"),
			additions=int(item.get("additions") or 0),
			deletions=int(item.get("deletions") or 0),
			changes=int(item.get("changes") or 0),
			patch=(item.get("patch") or "")[:6000] if isinstance(item.get("patch"), str) else None,
			patch_available=isinstance(item.get("patch"), str),
			patch_truncated=isinstance(item.get("patch"), str) and len(item["patch"]) > 6000,
			blob_url=item.get("blob_url") if isinstance(item.get("blob_url"), str) else None,
		) for item in data["files"]],
		reviews=[{"user": (item.get("user") or {}).get("login"), "state": item.get("state"), "submitted_at": item.get("submitted_at"), "body": (item.get("body") or "")[:1000]} for item in data["reviews"][:100]],
		commits=[{"sha": item.get("sha"), "message": ((item.get("commit") or {}).get("message") or "")[:1000], "author": ((item.get("author") or {}).get("login"))} for item in data["commits"][:100]],
		signals=data["signals"],
		ai_context_ready=bool(bounded_context["evidence"]),
		ai_context_record_count=len(bounded_context["evidence"]),
	)


def _persist_github_evidence(db: Session, gap: KnowledgeGap, context: dict[str, object]) -> list[str]:
	persisted_ids = []
	for item in context["evidence"]:
		source_id = item["id"]
		row = db.scalar(select(Evidence).where(Evidence.knowledge_gap_id == gap.id, Evidence.source_id == source_id))
		if row is None:
			row = Evidence(knowledge_gap_id=gap.id, source_id=source_id, source_type=item["source_type"], title=item["title"][:240], reference=item["reference"][:500], summary=item["summary"])
			db.add(row)
		else:
			row.source_type = item["source_type"]
			row.title = item["title"][:240]
			row.reference = item["reference"][:500]
			row.summary = item["summary"]
		persisted_ids.append(source_id)
	return persisted_ids


@app.post("/api/github/repositories/{repository_id}/pull-requests/{number}/analyze", response_model=GitHubAnalysisResponse)
def analyze_github_pull_request(
	repository_id: int,
	number: int,
	user: User = Depends(require_roles("manager", "admin")),
	db: Session = Depends(get_db),
) -> GitHubAnalysisResponse:
	repository = _tenant_repository(repository_id, user.organization_id, db)
	try:
		remote = retrieve_pull_request_evidence(GitHubClient(), repository.name, number)
	except (GitHubNotConfiguredError, HTTPError, ValueError) as error:
		raise _github_error(error) from error
	pull = remote["pull_request"]
	service = db.get(Service, repository.service_id) if repository.service_id else None
	if service is None:
		service = db.scalar(select(Service).where(Service.organization_id == user.organization_id, Service.name == repository.name))
	if service is None:
		service = Service(organization_id=user.organization_id, name=repository.name, description=f"GitHub repository {repository.name}", criticality="unknown")
	source_ref = f"github:pr:{pull.get('id', number)}"
	gap = None
	if service.id is not None:
		for candidate in db.scalars(select(KnowledgeGap).where(KnowledgeGap.service_id == service.id)).all():
			if (candidate.ai_analysis or {}).get("source_ref") == source_ref:
				gap = candidate
				break
	provisional_title = f"PR #{number}: {pull.get('title') or 'Engineering change'}"
	transient_evidence = [Evidence(
			knowledge_gap_id=gap.id if gap and gap.id else 0,
			source_id=item["id"],
			source_type=item["source_type"],
			title=item["title"][:240],
			reference=item["reference"][:500],
			summary=item["summary"],
		) for item in to_github_context(repository.name, remote)["evidence"]]
	context = to_github_context(repository.name, remote)
	try:
		analysis_gap = gap or KnowledgeGap(
			service_id=service.id or 0,
			title=provisional_title[:200],
			description=(pull.get("body") or "")[:3000] or "Potentially important engineering change; rationale requires review.",
			priority="medium",
			status="open",
			created_by=user.id,
		)
		analysis = analyze_gap(analysis_gap, service, transient_evidence, remote["signals"])
	except (AIConfigurationError, AIOutputError, AIProviderError, InvalidEvidenceReference, MissingEvidence) as error:
		db.rollback()
		raise _ai_http_error(error) from error
	if not {item.source_id for item in transient_evidence}.issuperset(analysis.evidence_ids):
		db.rollback()
		raise HTTPException(status_code=502, detail="Claude referenced evidence that was not supplied")
	persisted = False
	if analysis.potential_gap:
		if service.id is None:
			db.add(service)
			db.flush()
			repository.service_id = service.id
		if gap is None:
			gap = KnowledgeGap(service_id=service.id, title=provisional_title[:200], description=(pull.get("body") or "")[:3000] or "Potentially important engineering change; rationale requires review.", priority="medium", status="open", created_by=user.id)
			db.add(gap)
			db.flush()
		gap.title = analysis.title[:200]
		gap.description = analysis.summary[:3000]
		persisted_ids = _persist_github_evidence(db, gap, context)
		gap.ai_analysis = {
			**analysis.model_dump(mode="json"),
			"source_ref": source_ref,
			"provider": settings.ai_provider,
			"model": settings.anthropic_model,
			"task": "Knowledge Gap Detection",
			"signals": remote["signals"],
			"persisted_evidence_ids": persisted_ids,
		}
		persisted = True
	db.add(AuditLog(
		organization_id=user.organization_id,
		user_id=user.id,
		action="ai.github_pull_request_analyzed",
		resource_type="knowledge_gap" if persisted else "github_pull_request",
		resource_id=str(gap.id if persisted and gap is not None else pull.get("id", number)),
		metadata_json={"repository": repository.name, "pr_number": number, "evidence_count": len(context["evidence"]), "potential_gap": analysis.potential_gap},
	))
	db.commit()
	if persisted and gap is not None:
		db.refresh(gap)
	trace_stages = [
		AITraceStage(id="github", label="Retrieve GitHub evidence", status="complete", detail=f"PR #{number}; {len(remote['files'])} changed files; {len(remote['reviews'])} reviews; {len(remote['commits'])} commits"),
		AITraceStage(id="signals", label="Calculate deterministic signals", status="complete", detail=f"Recent PR window {remote['signals']['window']['recent_pull_requests']}; Jira/incidents explicitly unavailable"),
		AITraceStage(id="context", label="Build evidence context", status="complete", detail=f"{len(context['evidence'])} bounded records sent; no repository-wide source was sent"),
		AITraceStage(id="claude", label="Agent Router → Claude", status="complete", detail=f"{settings.ai_provider} / {settings.anthropic_model}; structured response received"),
		AITraceStage(id="validation", label="Validate Pydantic response and references", status="complete", detail=f"Schema valid; {len(analysis.evidence_ids)} citations matched supplied evidence"),
		AITraceStage(id="persistence", label="Persist potential knowledge gap", status="complete" if persisted else "skipped", detail="Saved to knowledge_gaps and evidence" if persisted else "No potential gap supported; no knowledge-gap row created"),
	]
	return GitHubAnalysisResponse(
		knowledge_gap_id=gap.title.lower().replace(" ", "-") if persisted and gap is not None else "",
		persisted=persisted,
		provider=settings.ai_provider,
		model=settings.anthropic_model or "",
		task="Knowledge Gap Detection",
		input_record_count=len(context["evidence"]),
		evidence_ids=analysis.evidence_ids,
		signals=remote["signals"],
		analysis=analysis.model_dump(mode="json"),
		stages=trace_stages,
	)


@app.get("/api/ai/status")
def ai_status(user: User = Depends(current_user)) -> dict[str, object]:
	credentials_configured = bool(settings.anthropic_auth_token or settings.anthropic_api_key)
	model_configured = bool(settings.anthropic_model)
	configured = settings.ai_provider == "anthropic" and credentials_configured and model_configured
	return {
		"provider": settings.ai_provider,
		"configured": configured,
		"credentials_configured": credentials_configured,
		"model_configured": model_configured,
		"model": settings.anthropic_model,
		"base_url": settings.anthropic_base_url,
		**_ai_connection_state,
		"message": None if configured else "Configure AI_PROVIDER, ANTHROPIC_AUTH_TOKEN (or ANTHROPIC_API_KEY), and ANTHROPIC_MODEL on the backend.",
	}


@app.post("/api/ai/test")
def test_ai_connection(user: User = Depends(require_roles("admin"))) -> dict[str, str]:
	checked_at = datetime.now(timezone.utc).isoformat()
	try:
		message = AgentRouter().test_connection()
	except AIConfigurationError as error:
		_ai_connection_state.update(connection_status="offline", checked_at=checked_at)
		raise HTTPException(status_code=503, detail=str(error)) from error
	except AIProviderError as error:
		_ai_connection_state.update(connection_status="offline", checked_at=checked_at)
		raise HTTPException(status_code=502, detail=str(error)) from error
	except AIOutputError as error:
		_ai_connection_state.update(connection_status="offline", checked_at=checked_at)
		raise HTTPException(status_code=502, detail=str(error)) from error
	_ai_connection_state.update(connection_status="online", checked_at=checked_at)
	return {"provider": settings.ai_provider, "message": message, "connection_status": "online", "checked_at": checked_at}


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
	analysis = gap.ai_analysis or {}
	source_ref = analysis.get("source_ref")
	ref = f"GitHub {source_ref}" if isinstance(source_ref, str) else "No source evidence linked"
	return Gap(id=slug, title=gap.title, description=gap.description, service=service.name, ref=ref, status="Validated" if gap.status == "validated" else "Open", ai_analysis=gap.ai_analysis)


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


def _get_authorized_gap(gap_id: str, organization_id: int, db: Session) -> tuple[KnowledgeGap, Service, list[Evidence]]:
	row = db.execute(
		select(KnowledgeGap, Service)
		.join(Service, KnowledgeGap.service_id == Service.id)
		.where(
			Service.organization_id == organization_id,
			func.lower(func.replace(KnowledgeGap.title, " ", "-")) == gap_id,
		)
	).first()
	if row is None:
		raise HTTPException(status_code=404, detail="Knowledge gap not found")
	gap, service = row
	evidence = db.scalars(
		select(Evidence)
		.where(Evidence.knowledge_gap_id == gap.id)
		.order_by(Evidence.id)
		.limit(20)
	).all()
	return gap, service, evidence


def _ai_http_error(error: Exception) -> HTTPException:
	if isinstance(error, MissingEvidence):
		return HTTPException(status_code=422, detail=str(error))
	if isinstance(error, InvalidEvidenceReference):
		logger.warning("Rejected AI output with untrusted evidence references")
		return HTTPException(status_code=502, detail="The AI response did not reference valid supplied evidence")
	if isinstance(error, AIConfigurationError):
		return HTTPException(status_code=503, detail=str(error))
	if isinstance(error, AIOutputError):
		return HTTPException(status_code=502, detail=str(error))
	if isinstance(error, AIProviderError):
		return HTTPException(status_code=502, detail=str(error))
	logger.exception("Unexpected AI workflow failure")
	return HTTPException(status_code=500, detail="The AI workflow could not be completed")


@app.post("/api/knowledge-gaps/{gap_id}/analyze")
def analyze_knowledge_gap(
	gap_id: str,
	user: User = Depends(require_roles("manager", "admin")),
	db: Session = Depends(get_db),
) -> dict[str, object]:
	gap, service, evidence = _get_authorized_gap(gap_id, user.organization_id, db)
	try:
		result = analyze_gap(gap, service, evidence)
	except (AIConfigurationError, AIOutputError, AIProviderError, InvalidEvidenceReference, MissingEvidence) as error:
		raise _ai_http_error(error) from error
	if not set(result.evidence_ids).issubset({item.source_id for item in evidence}):
		raise HTTPException(status_code=502, detail="The AI response did not reference valid supplied evidence")
	gap.ai_analysis = result.model_dump(mode="json")
	db.add(AuditLog(
		organization_id=user.organization_id,
		user_id=user.id,
		action="ai.knowledge_gap_analyzed",
		resource_type="knowledge_gap",
		resource_id=str(gap.id),
		metadata_json={"evidence_count": len(evidence), "potential_gap": result.potential_gap},
	))
	db.commit()
	db.refresh(gap)
	return {"analysis": gap.ai_analysis, "persisted": True}


@app.post("/api/knowledge-gaps/{gap_id}/questions")
def create_knowledge_questions(
	gap_id: str,
	user: User = Depends(require_roles("manager", "holder")),
	db: Session = Depends(get_db),
) -> dict[str, object]:
	gap, service, evidence = _get_authorized_gap(gap_id, user.organization_id, db)
	try:
		result = generate_questions(gap, service, evidence)
	except (AIConfigurationError, AIOutputError, AIProviderError, InvalidEvidenceReference, MissingEvidence) as error:
		raise _ai_http_error(error) from error
	allowed_evidence_ids = {item.source_id for item in evidence}
	if any(not set(question.evidence_ids).issubset(allowed_evidence_ids) for question in result.questions):
		logger.warning("Rejected AI questions with untrusted evidence references")
		raise HTTPException(status_code=502, detail="The AI response did not reference valid supplied evidence")
	return result.model_dump(mode="json")


@app.post("/api/knowledge-gaps/{gap_id}/structure-answer")
def structure_knowledge_answer(
	gap_id: str,
	payload: StructureCaptureRequest,
	user: User = Depends(require_roles("manager", "holder")),
	db: Session = Depends(get_db),
) -> KnowledgeRecordResponse:
	if not payload.question.strip() or not payload.answer.strip():
		raise HTTPException(status_code=422, detail="A question and answer are required")
	gap, service, evidence = _get_authorized_gap(gap_id, user.organization_id, db)
	try:
		result = structure_capture(gap, service, evidence, payload.question, payload.answer)
	except (AIConfigurationError, AIOutputError, AIProviderError, InvalidEvidenceReference, MissingEvidence) as error:
		raise _ai_http_error(error) from error
	record = KnowledgeRecord(
		knowledge_gap_id=gap.id,
		knowledge_area_id=gap.knowledge_area_id,
		decision=result.decision,
		reason="\n\n".join(
			part for part in (
				result.reason,
				f"Mitigation: {result.mitigation}" if result.mitigation else "",
				f"Related change: {result.related_change}" if result.related_change else "",
			) if part
		),
		affected_system=service.name,
		related_incident=result.related_incident,
		status="proposed",
		submitted_by=user.id,
	)
	db.add(record)
	db.flush()
	db.add(AuditLog(
		organization_id=user.organization_id,
		user_id=user.id,
		action="ai.knowledge_capture_structured",
		resource_type="knowledge_record",
		resource_id=str(record.id),
		metadata_json={"confidence": result.confidence, "evidence_ids": result.evidence_ids},
	))
	db.commit()
	db.refresh(record)
	return KnowledgeRecordResponse(
		id=record.id,
		gap_id=gap_id,
		decision=record.decision,
		reason=record.reason,
		affected_system=record.affected_system,
		status=record.status,
		submitted_by=user.name,
		validated_by=None,
		validated_at=None,
		created_at=record.created_at,
	)


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

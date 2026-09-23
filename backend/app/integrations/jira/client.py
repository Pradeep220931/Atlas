from typing import Any

import httpx

from app.config import settings


class JiraNotConfiguredError(RuntimeError):
	pass


class JiraClient:
	def __init__(self):
		if not settings.jira_base_url or not settings.jira_email or not settings.jira_api_token:
			raise JiraNotConfiguredError("JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN are required")
		self.base_url = settings.jira_base_url.rstrip("/")
		self.auth = (settings.jira_email, settings.jira_api_token)

	def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
		response = httpx.get(f"{self.base_url}{path}", auth=self.auth, params=params, timeout=20)
		response.raise_for_status()
		return response.json()

	def projects(self) -> list[dict[str, Any]]:
		return self._request("/rest/api/3/project")

	def issues(self, project_keys: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
		keys = project_keys or settings.jira_project_keys
		if not keys:
			return []
		jql = f"project in ({','.join(keys)}) ORDER BY updated DESC"
		return self._request("/rest/api/3/search", {"jql": jql, "maxResults": 100, "fields": "summary,status,assignee"}).get("issues", [])

	def sync_summary(self) -> dict[str, int | str]:
		return {"projects": len(self.projects()), "issues": len(self.issues()), "status": "completed"}

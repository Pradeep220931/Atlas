from typing import Any

import httpx

from app.config import settings


class GitHubNotConfiguredError(RuntimeError):
	pass


class GitHubClient:
	def __init__(self, token: str | None = None, org: str | None = None, owner: str | None = None):
		self.token = token or settings.github_token
		self.org = org or settings.github_org
		self.owner = owner or settings.github_owner
		if not self.token:
			raise GitHubNotConfiguredError("GITHUB_TOKEN is not configured")
		if not self.org and not self.owner:
			raise GitHubNotConfiguredError("Set GITHUB_ORG or GITHUB_OWNER")

	def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
		response = httpx.get(
			f"https://api.github.com{path}",
			headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"},
			params=params,
			timeout=20,
		)
		response.raise_for_status()
		return response.json()

	def repositories(self) -> list[dict[str, Any]]:
		path = f"/orgs/{self.org}/repos" if self.org else f"/users/{self.owner}/repos"
		return self._request(path, {"per_page": 100, "sort": "updated"})

	def pull_requests(self, repository: str) -> list[dict[str, Any]]:
		return self._request(f"/repos/{self._namespace()}/{repository}/pulls", {"state": "all", "per_page": 100})

	def contributors(self, repository: str) -> list[dict[str, Any]]:
		return self._request(f"/repos/{self._namespace()}/{repository}/contributors", {"per_page": 100})

	def _namespace(self) -> str:
		return self.org or self.owner or ""

	def sync_summary(self) -> dict[str, int | str]:
		repositories = self.repositories()
		pull_requests = sum(len(self.pull_requests(repository["name"])) for repository in repositories)
		contributors = {item.get("login") for repository in repositories for item in self.contributors(repository["name"]) if item.get("login")}
		return {"repositories": len(repositories), "pull_requests": pull_requests, "contributors": len(contributors), "status": "completed"}

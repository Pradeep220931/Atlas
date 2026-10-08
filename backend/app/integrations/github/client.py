from typing import Any
from urllib.parse import urlparse
import re

import httpx

from app.config import settings


class GitHubNotConfiguredError(RuntimeError):
	pass


class GitHubClient:
	API_ROOT = "https://api.github.com"
	MAX_PAGES = 10

	def __init__(self, token: str | None = None, org: str | None = None, owner: str | None = None):
		self.token = token or settings.github_token
		self.org = settings.github_org if org is None else org
		self.owner = settings.github_owner if owner is None else owner
		self._accessible_repository_names: set[str] | None = None
		if not self.token:
			raise GitHubNotConfiguredError("GITHUB_TOKEN is not configured")
		if not self.org and not self.owner:
			raise GitHubNotConfiguredError("Set GITHUB_ORG or GITHUB_OWNER")

	def _request(self, path: str, params: dict[str, Any] | None = None) -> Any:
		response = self._get(f"{self.API_ROOT}{path}", params=params)
		response.raise_for_status()
		return response.json()

	def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
		return httpx.get(
			url,
			headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
			params=params,
			timeout=20,
		)

	def _paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
		url = f"{self.API_ROOT}{path}"
		items: list[dict[str, Any]] = []
		for page in range(self.MAX_PAGES):
			response = self._get(url, params=params if page == 0 else None)
			response.raise_for_status()
			data = response.json()
			if not isinstance(data, list):
				raise ValueError("GitHub returned an unexpected paginated response")
			items.extend(data)
			next_url = response.links.get("next", {}).get("url")
			if not next_url:
				break
			parsed = urlparse(next_url)
			if parsed.scheme != "https" or parsed.netloc != "api.github.com":
				raise ValueError("GitHub returned an unexpected pagination URL")
			url = next_url
		return items

	def _repository_path(self, repository: str) -> str:
		parts = repository.split("/")
		if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
			raise ValueError("Invalid GitHub repository")
		if self.org:
			if parts[0].casefold() != self.org.casefold():
				raise ValueError("Repository is outside the configured GitHub organization")
		elif parts[0].casefold() != (self.owner or "").casefold():
			if self._accessible_repository_names is None:
				self.repositories()
			if repository.casefold() not in {name.casefold() for name in self._accessible_repository_names or set()}:
				raise ValueError("Repository is not accessible to the configured GitHub account")
		return f"/repos/{parts[0]}/{parts[1]}"

	def repositories(self) -> list[dict[str, Any]]:
		if self.org:
			repositories = self._paginated(f"/orgs/{self.org}/repos", {"per_page": 100, "sort": "updated", "type": "all"})
		else:
			user = self._request("/user")
			if str(user.get("login", "")).casefold() != (self.owner or "").casefold():
				raise GitHubNotConfiguredError("The GitHub token account does not match GITHUB_OWNER")
			repositories = self._paginated("/user/repos", {"per_page": 100, "sort": "updated"})
		self._accessible_repository_names = {
			str(item["full_name"]) for item in repositories if isinstance(item.get("full_name"), str)
		}
		return repositories

	def pull_requests(self, repository: str) -> list[dict[str, Any]]:
		return self._paginated(f"{self._repository_path(repository)}/pulls", {"state": "all", "per_page": 100, "sort": "updated", "direction": "desc"})

	def contributors(self, repository: str) -> list[dict[str, Any]]:
		return self._paginated(f"{self._repository_path(repository)}/contributors", {"per_page": 100})

	def pull_request(self, repository: str, number: int) -> dict[str, Any]:
		return self._request(f"{self._repository_path(repository)}/pulls/{number}")

	def pull_request_files(self, repository: str, number: int) -> list[dict[str, Any]]:
		return self._paginated(f"{self._repository_path(repository)}/pulls/{number}/files", {"per_page": 100})

	def pull_request_reviews(self, repository: str, number: int) -> list[dict[str, Any]]:
		return self._paginated(f"{self._repository_path(repository)}/pulls/{number}/reviews", {"per_page": 100})

	def pull_request_commits(self, repository: str, number: int) -> list[dict[str, Any]]:
		return self._paginated(f"{self._repository_path(repository)}/pulls/{number}/commits", {"per_page": 100})

	def _namespace(self) -> str:
		return self.org or self.owner or ""

	def sync_summary(self) -> dict[str, int | str]:
		repositories = self.repositories()
		pull_requests = sum(len(self.pull_requests(repository["name"])) for repository in repositories)
		contributors = {item.get("login") for repository in repositories for item in self.contributors(repository["name"]) if item.get("login")}
		return {"repositories": len(repositories), "pull_requests": pull_requests, "contributors": len(contributors), "status": "completed"}

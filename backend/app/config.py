import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()
    )
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_org: str | None = os.getenv("GITHUB_ORG")
    github_owner: str | None = os.getenv("GITHUB_OWNER")
    jira_base_url: str | None = os.getenv("JIRA_BASE_URL")
    jira_email: str | None = os.getenv("JIRA_EMAIL")
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN")
    jira_project_keys: tuple[str, ...] = tuple(
        key.strip() for key in os.getenv("JIRA_PROJECT_KEYS", "").split(",") if key.strip()
    )


settings = Settings()
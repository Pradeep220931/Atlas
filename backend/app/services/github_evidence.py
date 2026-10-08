from collections import Counter
from typing import Any

from app.integrations.github.client import GitHubClient

RECENT_PR_WINDOW = 20
MAX_AI_FILES = 16
MAX_PATCH_CHARS = 1200


def _level(percentage: float) -> str:
    if percentage >= 0.60:
        return "HIGH"
    if percentage >= 0.40:
        return "MODERATE"
    return "LOW"


def _github_user(value: Any) -> str | None:
    if isinstance(value, dict):
        login = value.get("login")
        return login if isinstance(login, str) and login else None
    return None


def calculate_continuity_signals(
    recent_pull_requests: list[dict[str, Any]],
    contributors: list[dict[str, Any]],
    selected_reviews: list[dict[str, Any]],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    recent = recent_pull_requests[:RECENT_PR_WINDOW]
    author_counts = Counter(author for pr in recent if (author := _github_user(pr.get("user"))))
    author_total = sum(author_counts.values())
    top_author, top_author_count = author_counts.most_common(1)[0] if author_counts else (None, 0)
    contribution_share = top_author_count / author_total if author_total else None

    review_counts = Counter(
        login
        for review in selected_reviews
        if review.get("state") not in {"PENDING", "COMMENTED"}
        and (login := _github_user(review.get("user")))
    )
    review_total = sum(review_counts.values())
    top_reviewer, top_reviewer_count = review_counts.most_common(1)[0] if review_counts else (None, 0)
    review_share = top_reviewer_count / review_total if review_total else None

    contributor_logins = {login for item in contributors if (login := _github_user(item))}
    doc_files = [
        item for item in files
        if str(item.get("filename", "")).lower().startswith(("docs/", "doc/"))
        or str(item.get("filename", "")).lower().endswith((".md", ".rst"))
    ]

    return {
        "window": {"recent_pull_requests": len(recent), "available_author_records": author_total},
        "contribution_concentration": {
            "status": _level(contribution_share) if contribution_share is not None else "UNAVAILABLE",
            "top_author": top_author,
            "top_author_pull_requests": top_author_count,
            "share": round(contribution_share, 4) if contribution_share is not None else None,
            "thresholds": {"high": ">=60%", "moderate": ">=40% and <60%"},
        },
        "contributor_redundancy": {
            "status": "UNAVAILABLE" if not contributors else "LOW" if len(contributor_logins) <= 1 else "MODERATE" if len(contributor_logins) == 2 else "HIGH",
            "distinct_github_accounts": len(contributor_logins),
            "source": "GitHub contributors endpoint; accounts, not individual knowledge or competence",
        },
        "selected_pr_review_concentration": {
            "status": _level(review_share) if review_share is not None else "UNAVAILABLE",
            "top_reviewer": top_reviewer,
            "review_events": review_total,
            "share": round(review_share, 4) if review_share is not None else None,
            "scope": "Selected pull request only",
            "thresholds": {"high": ">=60%", "moderate": ">=40% and <60%"},
        },
        "documentation_change_coverage": {
            "changed_files": len(files),
            "documentation_files": len(doc_files),
            "share": round(len(doc_files) / len(files), 4) if files else None,
            "scope": "Filename heuristic only; not a documentation quality assessment",
        },
        "jira_decision_traceability": "NOT_CONNECTED",
        "incident_history": "NOT_CONNECTED",
        "service_criticality": "NOT_MAPPED",
    }


def retrieve_pull_request_evidence(client: GitHubClient, repository: str, pull_number: int) -> dict[str, Any]:
    pull_request = client.pull_request(repository, pull_number)
    files = client.pull_request_files(repository, pull_number)
    reviews = client.pull_request_reviews(repository, pull_number)
    commits = client.pull_request_commits(repository, pull_number)
    recent_pull_requests = client.pull_requests(repository)[:RECENT_PR_WINDOW]
    contributors = client.contributors(repository)
    signals = calculate_continuity_signals(recent_pull_requests, contributors, reviews, files)
    return {
        "pull_request": pull_request,
        "files": files,
        "reviews": reviews,
        "commits": commits,
        "recent_pull_requests": recent_pull_requests,
        "contributors": contributors,
        "signals": signals,
    }


def to_github_context(repository: str, evidence: dict[str, Any]) -> dict[str, Any]:
    pull_request = evidence["pull_request"]
    pull_number = pull_request["number"]
    source_ref = f"github:pr:{pull_request.get('id', pull_number)}"
    file_context = []
    for index, file in enumerate(evidence["files"][:MAX_AI_FILES]):
        file_context.append({
            "id": f"{source_ref}:file:{index}",
            "filename": file.get("filename"),
            "status": file.get("status"),
            "additions": file.get("additions", 0),
            "deletions": file.get("deletions", 0),
            "patch": (file.get("patch") or "")[:MAX_PATCH_CHARS],
        })
    review_context = [
        {"user": _github_user(review.get("user")), "state": review.get("state"), "submitted_at": review.get("submitted_at")}
        for review in evidence["reviews"][:20]
    ]
    commit_context = [
        {"sha": commit.get("sha"), "message": ((commit.get("commit") or {}).get("message") or "")[:500], "author": _github_user((commit.get("author") or {}))}
        for commit in evidence["commits"][:20]
    ]
    context_evidence = [{"id": source_ref, "source_type": "github_pull_request", "title": pull_request.get("title", ""), "reference": pull_request.get("html_url", ""), "summary": (pull_request.get("body") or "")[:4000]}]
    context_evidence.extend({"id": item["id"], "source_type": "github_changed_file", "title": item["filename"] or "Changed file", "reference": item["filename"] or "", "summary": item["patch"] or f"{item['status']}; +{item['additions']} -{item['deletions']} lines"} for item in file_context)
    if review_context:
        context_evidence.append({"id": f"{source_ref}:reviews", "source_type": "github_reviews", "title": f"Reviews for PR #{pull_number}", "reference": pull_request.get("html_url", ""), "summary": str(review_context)[:1500]})
    if commit_context:
        context_evidence.append({"id": f"{source_ref}:commits", "source_type": "github_commits", "title": f"Commits for PR #{pull_number}", "reference": pull_request.get("html_url", ""), "summary": str(commit_context)[:1500]})
    return {
        "repository": repository,
        "pull_request": {
            "number": pull_number,
            "title": pull_request.get("title"),
            "body": (pull_request.get("body") or "")[:4000],
            "author": _github_user(pull_request.get("user")),
            "state": pull_request.get("state"),
            "merged": bool(pull_request.get("merged")),
            "changed_files": pull_request.get("changed_files"),
            "url": pull_request.get("html_url"),
        },
        "changed_files": file_context,
        "reviews": review_context,
        "commits": commit_context,
        "signals": evidence["signals"],
        "jira": "No Jira evidence supplied to this analysis.",
        "incidents": "No incident evidence supplied to this analysis.",
        "evidence": context_evidence,
    }

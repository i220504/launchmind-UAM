from __future__ import annotations

import base64
import re
from typing import Any

import requests

from config import settings
from utils.logger import get_logger
from utils.retry import retry_call


class GitHubClient:
    def __init__(self) -> None:
        self.logger = get_logger("github_client")
        self.base_url = f"https://api.github.com/repos/{settings.github_owner}/{settings.github_repo}"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        def _do() -> Any:
            response = self.session.request(method, f"{self.base_url}{path}", timeout=45, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"GitHub API error {response.status_code}: {response.text}")
            return response.json()

        return retry_call(_do, retry_on=(requests.RequestException, RuntimeError))

    def validate(self) -> None:
        if not settings.github_token or not settings.github_owner or not settings.github_repo:
            raise ValueError("GitHub environment variables are incomplete")
        self._request("GET", "")
        self.logger.info("GitHub client validated for %s/%s", settings.github_owner, settings.github_repo)

    def get_branch_sha(self, branch: str) -> str:
        data = self._request("GET", f"/git/ref/heads/{branch}")
        return data["object"]["sha"]

    def branch_exists(self, branch: str) -> bool:
        try:
            self.get_branch_sha(branch)
            return True
        except Exception:  # noqa: BLE001
            return False

    def create_issue(self, title: str, body: str) -> dict[str, Any]:
        return self._request("POST", "/issues", json={"title": title, "body": body})

    def create_branch(self, branch_name: str, source_branch: str | None = None) -> str:
        if self.branch_exists(branch_name):
            self.logger.info("GitHub branch %s already exists, reusing it", branch_name)
            return self.get_branch_sha(branch_name)
        base_branch = source_branch or settings.github_default_base_branch
        sha = self.get_branch_sha(base_branch)
        self._request("POST", "/git/refs", json={"ref": f"refs/heads/{branch_name}", "sha": sha})
        return sha

    def get_file_sha(self, path: str, branch: str) -> str | None:
        try:
            response = self._request("GET", f"/contents/{path}", params={"ref": branch})
            return response["sha"]
        except Exception:  # noqa: BLE001
            return None

    def commit_file(self, branch: str, path: str, content: str, message: str) -> dict[str, Any]:
        existing_sha = self.get_file_sha(path, branch)
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch": branch,
            "committer": {
                "name": settings.github_commit_author_name,
                "email": settings.github_commit_author_email,
            },
            "author": {
                "name": settings.github_commit_author_name,
                "email": settings.github_commit_author_email,
            },
        }
        if existing_sha:
            body["sha"] = existing_sha
        return self._request("PUT", f"/contents/{path}", json=body)

    def open_pull_request(self, title: str, body: str, head: str, base: str | None = None) -> dict[str, Any]:
        payload = {"title": title, "body": body, "head": head, "base": base or settings.github_default_base_branch}
        try:
            return self._request("POST", "/pulls", json=payload)
        except RuntimeError as exc:
            if "A pull request already exists" not in str(exc):
                raise
            existing = self.find_open_pull_request(head=head, base=payload["base"])
            if existing is None:
                raise
            self.logger.info("Open pull request for head=%s already exists, reusing PR #%s", head, existing["number"])
            return existing

    def find_open_pull_request(self, head: str, base: str | None = None) -> dict[str, Any] | None:
        owner_scoped_head = f"{settings.github_owner}:{head}"
        pulls = self._request(
            "GET",
            "/pulls",
            params={"state": "open", "head": owner_scoped_head, "base": base or settings.github_default_base_branch},
        )
        if isinstance(pulls, list) and pulls:
            return pulls[0]
        return None

    def list_pull_request_files(self, pr_number: int) -> list[dict[str, Any]]:
        files = self._request("GET", f"/pulls/{pr_number}/files")
        if not isinstance(files, list):
            raise RuntimeError(f"Unexpected PR files response type: {type(files).__name__}")
        return files

    def find_valid_review_lines(self, pr_number: int, path: str, desired_count: int = 2) -> list[int]:
        files = self.list_pull_request_files(pr_number)
        file_match = next((item for item in files if item.get("filename") == path), None)
        if not file_match:
            raise RuntimeError(f"Path {path} not found in PR #{pr_number} diff")

        patch = file_match.get("patch") or ""
        lines = self._extract_added_lines_from_patch(patch)
        if not lines:
            raise RuntimeError(f"No valid added diff lines found for {path} in PR #{pr_number}")
        return lines[:desired_count]

    def _extract_added_lines_from_patch(self, patch: str) -> list[int]:
        added_lines: list[int] = []
        current_new_line = 0

        for raw_line in patch.splitlines():
            if raw_line.startswith("@@"):
                match = re.search(r"\+(\d+)(?:,(\d+))?", raw_line)
                if not match:
                    continue
                current_new_line = int(match.group(1))
                continue
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                added_lines.append(current_new_line)
                current_new_line += 1
                continue
            if raw_line.startswith("-") and not raw_line.startswith("---"):
                continue
            current_new_line += 1

        return added_lines

    def post_inline_comment(self, pr_number: int, commit_id: str, path: str, line: int, body: str) -> dict[str, Any]:
        payload = {"body": body, "commit_id": commit_id, "path": path, "line": line, "side": "RIGHT"}
        return self._request("POST", f"/pulls/{pr_number}/comments", json=payload)

    def post_issue_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        return self._request("POST", f"/issues/{issue_number}/comments", json={"body": body})

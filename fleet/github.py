"""Read-only GitHub REST client used by fleet observation workflows."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class GitHubError(RuntimeError):
    """An actionable GitHub API failure."""


class GitHubClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        api_url: str = "https://api.github.com",
        api_timeout_seconds: int = 20,
        page_timeout_seconds: int = 20,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.api_timeout_seconds = api_timeout_seconds
        self.page_timeout_seconds = page_timeout_seconds

    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.api_url}/{path.lstrip('/')}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "opensidewalkmap-fleet-manager/1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.api_timeout_seconds) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GitHubError(f"GitHub API {error.code} for {method} {path}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise GitHubError(f"GitHub API request failed for {method} {path}: {error}") from error

    def get_json(self, path: str) -> Any:
        return self.request_json("GET", path)

    def get_content(self, repository: str, path: str, branch: str) -> dict[str, Any]:
        encoded_path = urllib.parse.quote(path, safe="/")
        encoded_ref = urllib.parse.quote(branch, safe="")
        payload = self.get_json(
            f"repos/{repository}/contents/{encoded_path}?ref={encoded_ref}"
        )
        if not isinstance(payload, dict):
            raise GitHubError(f"Unexpected contents response for {repository}:{path}")
        return payload

    def get_optional_content(
        self, repository: str, path: str, branch: str
    ) -> dict[str, Any] | None:
        try:
            return self.get_content(repository, path, branch)
        except GitHubError as error:
            if "GitHub API 404" in str(error):
                return None
            raise

    @staticmethod
    def content_text(payload: dict[str, Any]) -> str:
        content = payload.get("content")
        encoding = payload.get("encoding")
        if not isinstance(content, str):
            raise GitHubError("GitHub contents response did not include file content")
        if encoding == "base64":
            try:
                return base64.b64decode(content).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as error:
                raise GitHubError("GitHub returned invalid UTF-8/base64 content") from error
        if encoding in {None, "utf-8"}:
            return content
        raise GitHubError(f"Unsupported GitHub contents encoding: {encoding}")

    def node_snapshot(self, repository: str, branch: str, history: int) -> dict[str, Any]:
        workflows = self.get_json(f"repos/{repository}/actions/workflows?per_page=100")
        # GitHub's server-side `branch=` filter has intermittently returned stale
        # workflow-run history for otherwise current public repositories. Fetch the
        # recent repository history without that filter and apply the branch match
        # locally using each run's explicit head_branch instead.
        runs = self.get_json(
            f"repos/{repository}/actions/runs?per_page={history}"
        )
        raw_runs = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        branch_runs = [
            run
            for run in raw_runs
            if isinstance(run, dict) and run.get("head_branch") == branch
        ]
        config = self.get_content(repository, "config.py", branch)
        core = self.get_optional_content(repository, "oswm_codebase", branch)
        managed = self.get_optional_content(repository, ".oswm-managed-files.json", branch)
        build = self.get_optional_content(repository, "oswm-build.json", branch)
        return {
            "config_text": self.content_text(config),
            "core_sha": core.get("sha") if isinstance(core, dict) else None,
            "managed_text": self.content_text(managed) if isinstance(managed, dict) else None,
            "build_text": self.content_text(build) if isinstance(build, dict) else None,
            "workflows": workflows.get("workflows", []) if isinstance(workflows, dict) else [],
            "runs": branch_runs,
        }

    def probe_url(self, url: str) -> dict[str, Any]:
        started = time.monotonic()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "opensidewalkmap-fleet-manager/1"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.page_timeout_seconds) as response:
                response.read(1)
                return {
                    "ok": 200 <= response.status < 400,
                    "status": response.status,
                    "latency_ms": round((time.monotonic() - started) * 1000),
                    "url": response.geturl(),
                }
        except urllib.error.HTTPError as error:
            return {
                "ok": False,
                "status": error.code,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "url": url,
                "error": str(error),
            }
        except (urllib.error.URLError, TimeoutError) as error:
            return {
                "ok": False,
                "status": None,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "url": url,
                "error": str(error),
            }

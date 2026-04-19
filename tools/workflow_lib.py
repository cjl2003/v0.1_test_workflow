#!/usr/bin/env python3
"""Shared helpers for the phase-1 PR-driven workflow."""

from __future__ import annotations

import base64
import json
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv


PRIMARY_LABELS = (
    "wf:intake",
    "wf:needs-clarification",
    "wf:awaiting-plan-approval",
    "wf:codex-queued",
    "wf:codex-running",
    "wf:awaiting-gpt-review",
    "wf:rework-needed",
    "wf:frontend-passed",
    "wf:failed",
)

PRIMARY_LABEL_META = {
    "wf:intake": ("1D76DB", "Request submitted and waiting for planning."),
    "wf:needs-clarification": ("FBCA04", "Planner needs clarification before producing a plan."),
    "wf:awaiting-plan-approval": ("BFD4F2", "Plan is ready and waiting for /approve-plan."),
    "wf:codex-queued": ("C2E0C6", "Approved work is queued for local Codex execution."),
    "wf:codex-running": ("0E8A16", "Local Codex has claimed the PR and is running."),
    "wf:awaiting-gpt-review": ("5319E7", "Local run succeeded and is waiting for GPT review."),
    "wf:rework-needed": ("D93F0B", "GPT review requested a minimal rework round."),
    "wf:frontend-passed": ("006B75", "Frontend work passed GPT review."),
    "wf:failed": ("B60205", "Phase-1 flow failed and requires manual attention."),
}

TRUSTED_AUTHOR_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}

MARKER_PLAN = "<!-- wf:plan -->"
MARKER_CLARIFICATION = "<!-- wf:clarification -->"
MARKER_CODEX_RUN = "<!-- wf:codex-run -->"
MARKER_GPT_REVIEW = "<!-- wf:gpt-review -->"
MARKER_FORMAL_DIAGNOSE = "<!-- wf:formal-diagnose -->"
MARKER_FORMAL_REVIEW_PLAN = "<!-- wf:formal-review-plan -->"
MARKER_FORMAL_APPROVAL = "<!-- wf:formal-approval -->"

DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_GITHUB_API_VERSION = "2022-11-28"
DEFAULT_OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENAI_ENDPOINT_STYLE = "auto"
DEFAULT_OPENAI_REASONING_EFFORT = "medium"
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 1800
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 60


class WorkflowError(RuntimeError):
    """Raised when the workflow cannot continue safely."""


@dataclass(frozen=True)
class GitHubConfig:
    github_token: str
    github_repo: str
    github_api_base: str
    github_api_version: str


@dataclass(frozen=True)
class OpenAIConfig:
    openai_api_key: str
    openai_api_base: str
    openai_model: str
    openai_endpoint_style: str
    openai_reasoning_effort: str
    max_output_tokens: int


@dataclass(frozen=True)
class RenderedComment:
    marker: str
    target_state: str
    body: str


def get_env(name: str, default: str | None = None, required: bool = False) -> str:
    """Read an environment variable while treating blank strings as unset."""
    value = os.getenv(name)
    if value is not None:
        value = value.strip()
        if value:
            return value

    if required:
        raise WorkflowError(f"Missing required environment variable: {name}")

    return "" if default is None else default.strip()


def parse_positive_int(raw_value: str, env_name: str) -> int:
    """Validate integer-like configuration values early."""
    try:
        value = int(raw_value)
    except ValueError as error:
        raise WorkflowError(f"{env_name} must be an integer, got: {raw_value!r}") from error

    if value <= 0:
        raise WorkflowError(f"{env_name} must be greater than zero, got: {value}")

    return value


def parse_timestamp(raw_timestamp: str) -> datetime:
    """Parse an ISO8601 GitHub timestamp as UTC."""
    normalized = raw_timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def comment_timestamp(comment: dict[str, Any], prefer_updated: bool = True) -> datetime:
    """Pick the most relevant timestamp from a GitHub comment payload."""
    if prefer_updated and comment.get("updated_at"):
        return parse_timestamp(str(comment["updated_at"]))
    if comment.get("created_at"):
        return parse_timestamp(str(comment["created_at"]))
    raise WorkflowError("GitHub comment payload is missing created_at/updated_at.")


def build_primary_label_set(labels: Iterable[str], target_state: str) -> list[str]:
    """Replace the current primary workflow label while preserving all others."""
    if target_state not in PRIMARY_LABELS:
        raise WorkflowError(f"Unknown primary workflow label: {target_state}")

    preserved = [name for name in labels if name not in PRIMARY_LABELS]
    preserved.append(target_state)
    return sorted(dict.fromkeys(preserved))


def extract_primary_state(labels: Iterable[str]) -> str | None:
    """Return the single current primary state, if any."""
    current = [name for name in labels if name in PRIMARY_LABELS]
    if not current:
        return None
    return sorted(current)[0]


def is_trusted_author(author_association: str) -> bool:
    """Check whether a PR comment author is allowed to drive the workflow."""
    return author_association.strip().upper() in TRUSTED_AUTHOR_ASSOCIATIONS


def find_latest_marker_comment(
    comments: Iterable[dict[str, Any]], marker: str
) -> dict[str, Any] | None:
    """Find the newest machine-readable comment for a specific marker."""
    candidates = [
        comment
        for comment in comments
        if marker in str(comment.get("body", ""))
    ]
    if not candidates:
        return None
    return max(candidates, key=comment_timestamp)


def find_latest_command_comment(
    comments: Iterable[dict[str, Any]], command: str
) -> dict[str, Any] | None:
    """Find the newest PR comment that begins with a specific slash command."""
    command = command.strip()
    candidates = [
        comment
        for comment in comments
        if str(comment.get("body", "")).strip().startswith(command)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: comment_timestamp(item, prefer_updated=False))


def split_repo(full_repo: str) -> tuple[str, str]:
    """Split a GitHub owner/repo string."""
    if "/" not in full_repo:
        raise WorkflowError(f"GITHUB_REPO must look like 'owner/repo', got: {full_repo!r}")
    owner, repo = full_repo.split("/", 1)
    if not owner or not repo:
        raise WorkflowError(f"GITHUB_REPO must look like 'owner/repo', got: {full_repo!r}")
    return owner, repo


def raise_for_status(response: requests.Response, context: str) -> None:
    """Wrap HTTP failures with the body snippet for easier workflow debugging."""
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        body = response.text.strip()
        snippet = body[:1000] if body else "<empty response>"
        raise WorkflowError(
            f"{context} failed with HTTP {response.status_code}: {snippet}"
        ) from error


def github_get_json(session: requests.Session, url: str, context: str) -> Any:
    """Read JSON from the GitHub REST API."""
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    raise_for_status(response, context)
    return response.json()


def github_send_json(
    session: requests.Session,
    method: str,
    url: str,
    payload: dict[str, Any],
    context: str,
) -> Any:
    """Send JSON to the GitHub REST API."""
    response = session.request(
        method=method,
        url=url,
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, context)
    return response.json()


def load_github_config() -> GitHubConfig:
    """Load GitHub workflow configuration from the environment."""
    load_dotenv()
    return GitHubConfig(
        github_token=get_env("GITHUB_TOKEN", required=True),
        github_repo=get_env("GITHUB_REPO", required=True),
        github_api_base=get_env("GITHUB_API_BASE", DEFAULT_GITHUB_API_BASE).rstrip("/"),
        github_api_version=get_env("GITHUB_API_VERSION", DEFAULT_GITHUB_API_VERSION),
    )


def load_openai_config() -> OpenAIConfig:
    """Load OpenAI/GPT workflow configuration from the environment."""
    load_dotenv()
    return OpenAIConfig(
        openai_api_key=get_env("OPENAI_API_KEY", required=True),
        openai_api_base=get_env("OPENAI_API_BASE", DEFAULT_OPENAI_API_BASE).rstrip("/"),
        openai_model=get_env(
            "OPENAI_REVIEW_MODEL", get_env("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
        ),
        openai_endpoint_style=get_env(
            "OPENAI_ENDPOINT_STYLE", DEFAULT_OPENAI_ENDPOINT_STYLE
        ).lower(),
        openai_reasoning_effort=get_env(
            "OPENAI_REASONING_EFFORT", DEFAULT_OPENAI_REASONING_EFFORT
        ),
        max_output_tokens=parse_positive_int(
            get_env(
                "OPENAI_MAX_OUTPUT_TOKENS", str(DEFAULT_OPENAI_MAX_OUTPUT_TOKENS)
            ),
            "OPENAI_MAX_OUTPUT_TOKENS",
        ),
    )


class GitHubClient:
    """Small GitHub REST client for PR workflow orchestration."""

    def __init__(self, config: GitHubConfig):
        self.config = config
        self.owner, self.repo = split_repo(config.github_repo)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {config.github_token}",
                "User-Agent": "pr-driven-rtl-frontend-autoflow/1.0",
                "X-GitHub-Api-Version": config.github_api_version,
            }
        )

    def close(self) -> None:
        self.session.close()

    def _repo_url(self, suffix: str) -> str:
        return f"{self.config.github_api_base}/repos/{self.owner}/{self.repo}/{suffix}"

    def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        payload = github_get_json(
            self.session,
            self._repo_url(f"pulls/{pr_number}"),
            "Fetching pull request metadata",
        )
        if not isinstance(payload, dict):
            raise WorkflowError("Unexpected GitHub pull request payload format.")
        return payload

    def list_pull_request_files(self, pr_number: int) -> list[dict[str, Any]]:
        payload = github_get_json(
            self.session,
            self._repo_url(f"pulls/{pr_number}/files?per_page=100"),
            "Listing pull request files",
        )
        if not isinstance(payload, list):
            raise WorkflowError("Unexpected GitHub pull request files payload format.")
        return [item for item in payload if isinstance(item, dict)]

    def list_open_pull_requests(self) -> list[dict[str, Any]]:
        payload = github_get_json(
            self.session,
            self._repo_url("pulls?state=open&sort=created&direction=asc&per_page=100"),
            "Listing open pull requests",
        )
        if not isinstance(payload, list):
            raise WorkflowError("Unexpected GitHub open pull requests payload format.")
        return [item for item in payload if isinstance(item, dict)]

    def fetch_pull_request_diff(self, pr_number: int) -> str:
        response = self.session.get(
            self._repo_url(f"pulls/{pr_number}"),
            headers={"Accept": "application/vnd.github.diff"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        raise_for_status(response, "Fetching pull request diff")
        return response.text

    def fetch_pull_request_file_text(self, pr_number: int, path: str) -> str:
        """Read a text file from the PR head ref via the GitHub contents API."""
        pr = self.get_pull_request(pr_number)
        head = (pr.get("head") or {}) if isinstance(pr, dict) else {}
        ref = str(head.get("sha") or head.get("ref") or "").strip()
        if not ref:
            raise WorkflowError("Pull request payload is missing head sha/ref.")

        payload = github_get_json(
            self.session,
            self._repo_url(f"contents/{path}?ref={ref}"),
            f"Fetching PR file contents for {path}",
        )
        if not isinstance(payload, dict):
            raise WorkflowError(f"Unexpected GitHub contents payload for {path}.")

        encoded = str(payload.get("content", "")).strip()
        encoding = str(payload.get("encoding", "")).strip().lower()
        if not encoded or encoding != "base64":
            raise WorkflowError(f"GitHub contents payload for {path} is missing base64 content.")

        try:
            raw_bytes = base64.b64decode(encoded, validate=False)
        except ValueError as error:
            raise WorkflowError(f"Failed to decode GitHub contents for {path}.") from error
        return raw_bytes.decode("utf-8").strip()

    def list_issue_comments(self, pr_number: int) -> list[dict[str, Any]]:
        payload = github_get_json(
            self.session,
            self._repo_url(f"issues/{pr_number}/comments?per_page=100"),
            "Listing PR comments",
        )
        if not isinstance(payload, list):
            raise WorkflowError("Unexpected GitHub issue comments payload format.")
        return [item for item in payload if isinstance(item, dict)]

    def ensure_primary_labels_exist(self) -> None:
        for name, (color, description) in PRIMARY_LABEL_META.items():
            response = self.session.post(
                self._repo_url("labels"),
                json={
                    "name": name,
                    "color": color,
                    "description": description,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code in {201, 422}:
                continue
            raise_for_status(response, f"Ensuring label {name}")

    def set_primary_state(self, pr_number: int, target_state: str) -> list[str]:
        pr = self.get_pull_request(pr_number)
        current_labels = [
            str(label.get("name", "")).strip()
            for label in pr.get("labels", [])
            if isinstance(label, dict) and str(label.get("name", "")).strip()
        ]
        next_labels = build_primary_label_set(current_labels, target_state)
        github_send_json(
            self.session,
            "PUT",
            self._repo_url(f"issues/{pr_number}/labels"),
            {"labels": next_labels},
            f"Updating primary workflow label to {target_state}",
        )
        return next_labels

    def upsert_marker_comment(self, pr_number: int, marker: str, body: str) -> str:
        comments = self.list_issue_comments(pr_number)
        existing = find_latest_marker_comment(comments, marker)

        if existing:
            comment_id = existing.get("id")
            if not comment_id:
                raise WorkflowError("Existing machine-readable comment is missing an id.")
            result = github_send_json(
                self.session,
                "PATCH",
                self._repo_url(f"issues/comments/{comment_id}"),
                {"body": body},
                f"Updating comment for marker {marker}",
            )
        else:
            result = github_send_json(
                self.session,
                "POST",
                self._repo_url(f"issues/{pr_number}/comments"),
                {"body": body},
                f"Creating comment for marker {marker}",
            )

        return str(result.get("html_url", ""))

    def create_issue_comment(self, pr_number: int, body: str) -> str:
        result = github_send_json(
            self.session,
            "POST",
            self._repo_url(f"issues/{pr_number}/comments"),
            {"body": body},
            "Creating PR comment",
        )
        return str(result.get("html_url", ""))

    def create_pull_request(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> dict[str, Any]:
        payload = github_send_json(
            self.session,
            "POST",
            self._repo_url("pulls"),
            {
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
            "Creating pull request",
        )
        if not isinstance(payload, dict):
            raise WorkflowError("Unexpected GitHub pull request creation payload format.")
        return payload


def should_fallback_to_chat_completions(error_message: str) -> bool:
    """Detect endpoint-shape failures that merit a chat completions retry."""
    retry_markers = ("HTTP 400", "HTTP 404", "HTTP 405", "HTTP 415", "HTTP 422")
    unsupported_markers = (
        "unsupported",
        "not found",
        "not implemented",
        "unknown url",
        "no route",
        "does not exist",
        "convert_request_failed",
    )
    normalized = error_message.lower()
    return any(marker in error_message for marker in retry_markers) or any(
        marker in normalized for marker in unsupported_markers
    )


def normalize_anthropic_messages_url(base_url: str) -> str:
    """Normalize an Anthropic-compatible base URL to the messages endpoint."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/messages"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/messages"
    return f"{normalized}/v1/messages"


def extract_openai_text(response_json: dict[str, Any]) -> str:
    """Aggregate all Responses API output text chunks from the raw payload."""
    parts: list[str] = []

    for item in response_json.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") != "output_text":
                continue
            text = str(content.get("text", "")).strip()
            if text:
                parts.append(text)

    return "\n\n".join(parts).strip()


def extract_anthropic_text(response_json: dict[str, Any]) -> str:
    """Aggregate text blocks from an Anthropic messages payload."""
    parts: list[str] = []

    for item in response_json.get("content", []):
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text", "")).strip()
        if text:
            parts.append(text)

    text = "\n\n".join(parts).strip()
    if not text:
        raise WorkflowError("Anthropic messages API returned no text content.")
    return text


def extract_chat_completions_text(response_json: dict[str, Any]) -> str:
    """Extract assistant text from a chat completions-style payload."""
    choices = response_json.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    message = (choices[0] or {}).get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"text", "output_text"}:
                continue
            text = str(item.get("text", "")).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip()

    return ""


def call_openai_text(
    config: OpenAIConfig, instructions: str, user_input: str
) -> tuple[str, str]:
    """Call an OpenAI-compatible endpoint and return the response text."""
    style = config.openai_endpoint_style
    if style == "responses":
        return call_openai_responses_text(config, instructions, user_input)
    if style == "chat_completions":
        return call_openai_chat_completions_text(config, instructions, user_input)
    if style == "anthropic_messages":
        return call_anthropic_messages_text(config, instructions, user_input)
    if style != "auto":
        raise WorkflowError(
            "OPENAI_ENDPOINT_STYLE must be one of: auto, responses, chat_completions, anthropic_messages"
        )

    try:
        return call_openai_responses_text(config, instructions, user_input)
    except WorkflowError as error:
        if not should_fallback_to_chat_completions(str(error)):
            raise
        return call_openai_chat_completions_text(config, instructions, user_input)


def call_anthropic_messages_text(
    config: OpenAIConfig, instructions: str, user_input: str
) -> tuple[str, str]:
    """Call an Anthropic-compatible messages endpoint."""
    response = requests.post(
        normalize_anthropic_messages_url(config.openai_api_base),
        headers={
            "x-api-key": config.openai_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        },
        json={
            "model": config.openai_model,
            "system": instructions,
            "messages": [{"role": "user", "content": user_input}],
            "max_tokens": config.max_output_tokens,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Calling Anthropic-compatible messages API")

    data = response.json()
    if not isinstance(data, dict):
        raise WorkflowError("Unexpected Anthropic messages payload format.")

    return extract_anthropic_text(data), str(data.get("id", "unknown"))


def call_openai_responses_text(
    config: OpenAIConfig, instructions: str, user_input: str
) -> tuple[str, str]:
    """Call the OpenAI Responses API."""
    payload: dict[str, Any] = {
        "model": config.openai_model,
        "instructions": instructions,
        "input": user_input,
        "max_output_tokens": config.max_output_tokens,
        "metadata": {"tool": "pr-driven-rtl-frontend-autoflow"},
    }

    if config.openai_reasoning_effort:
        payload["reasoning"] = {"effort": config.openai_reasoning_effort}

    response = requests.post(
        f"{config.openai_api_base}/responses",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Calling OpenAI Responses API")

    data = response.json()
    if not isinstance(data, dict):
        raise WorkflowError("Unexpected OpenAI Responses payload format.")

    text = extract_openai_text(data)
    if not text:
        raise WorkflowError("OpenAI Responses API returned no output_text content.")
    return text, str(data.get("id", "unknown"))


def call_openai_chat_completions_text(
    config: OpenAIConfig, instructions: str, user_input: str
) -> tuple[str, str]:
    """Call an OpenAI-compatible chat completions endpoint."""
    payload: dict[str, Any] = {
        "model": config.openai_model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_input},
        ],
        "max_tokens": config.max_output_tokens,
    }

    response = requests.post(
        f"{config.openai_api_base}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.openai_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    raise_for_status(response, "Calling OpenAI-compatible chat completions API")

    data = response.json()
    if not isinstance(data, dict):
        raise WorkflowError("Unexpected chat completions payload format.")

    text = extract_chat_completions_text(data)
    if not text:
        raise WorkflowError("Chat completions API returned no text.")
    return text, str(data.get("id", "unknown"))


def strip_code_fences(text: str) -> str:
    """Remove a single surrounding Markdown code fence if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    match = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def call_openai_json(
    config: OpenAIConfig, instructions: str, user_input: str
) -> tuple[dict[str, Any], str]:
    """Call OpenAI and parse the returned JSON object."""
    raw_text, response_id = call_openai_text(config, instructions, user_input)
    stripped = strip_code_fences(raw_text)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise WorkflowError(
            "Model response was not valid JSON. "
            f"Response id: {response_id}. Raw text: {raw_text[:800]}"
        ) from error

    if not isinstance(payload, dict):
        raise WorkflowError(f"Model response must be a JSON object, got: {type(payload)!r}")
    return payload, response_id


def render_sections(sections: Iterable[tuple[str, list[str] | str]]) -> list[str]:
    """Render Markdown sections for machine-readable workflow comments."""
    lines: list[str] = []

    for heading, content in sections:
        lines.append(f"### {heading}")
        if isinstance(content, str):
            text = content.strip()
            lines.append(text if text else "_None_")
            continue

        items = list(content)
        if not items:
            lines.append("- None.")
            continue
        for item in items:
            lines.append(f"- {item}")

    return lines


def render_marked_comment(
    marker: str,
    title: str,
    metadata: Iterable[tuple[str, str]],
    sections: Iterable[tuple[str, list[str] | str]],
) -> str:
    """Render a machine-readable PR comment with consistent formatting."""
    lines = [marker, f"## {title}"]
    for key, value in metadata:
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.extend(render_sections(sections))
    return "\n".join(lines).strip()


def read_text_file(path: Path) -> str:
    """Read a UTF-8 text file and raise a workflow-specific error on failure."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise WorkflowError(f"Required file not found: {path}") from error


def find_request_document(pr_files: Iterable[dict[str, Any]]) -> Path | None:
    """Pick the request document touched by the PR, if there is one."""
    candidates: list[Path] = []
    for item in pr_files:
        filename = str(item.get("filename", "")).strip()
        if not filename.startswith("docs/requests/") or not filename.endswith(".md"):
            continue
        candidates.append(Path(filename))
    if not candidates:
        return None
    return sorted(candidates)[-1]


def truncate_text(text: str, max_chars: int) -> str:
    """Trim large blobs while keeping the head and tail context."""
    if len(text) <= max_chars:
        return text
    head = max_chars // 2
    tail = max_chars - head
    return (
        text[:head]
        + "\n\n... [truncated by workflow_lib.py to keep prompt size bounded] ...\n\n"
        + text[-tail:]
    )


def extract_comment_field(comment_body: str, field_name: str) -> str | None:
    """Extract a bullet field like '- Run Result Path: `docs/runs/...`' from a comment."""
    pattern = re.compile(
        rf"^- {re.escape(field_name)}:\s+`?(.+?)`?\s*$",
        re.MULTILINE,
    )
    match = pattern.search(comment_body)
    if not match:
        return None
    return match.group(1).strip()


def indent_block(title: str, text: str) -> str:
    """Render a titled prompt block with stable spacing."""
    body = text.strip() or "(empty)"
    return textwrap.dedent(
        f"""
        ## {title}
        {body}
        """
    ).strip()

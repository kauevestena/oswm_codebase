"""Load and validate the versioned OSWM fleet registry."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class FleetPolicy:
    schedule_grace_minutes: int = 180
    workflow_history: int = 100
    api_timeout_seconds: int = 20
    page_timeout_seconds: int = 20


@dataclass(frozen=True)
class FleetNode:
    id: str
    repository: str
    branch: str
    role: str
    enabled: bool
    rollout_wave: int
    pages_url: str

    @property
    def owner(self) -> str:
        return self.repository.split("/", 1)[0]


@dataclass(frozen=True)
class FleetRegistry:
    schema_version: int
    policy: FleetPolicy
    nodes: tuple[FleetNode, ...]


def _positive_integer(value: object, name: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def _node(entry: object, index: int) -> FleetNode:
    if not isinstance(entry, dict):
        raise ValueError(f"nodes[{index}] must be a table")

    required = {"id", "repository", "branch", "role", "enabled", "rollout_wave", "pages_url"}
    missing = sorted(required - set(entry))
    if missing:
        raise ValueError(f"nodes[{index}] is missing: {', '.join(missing)}")

    node_id = str(entry["id"]).strip()
    repository = str(entry["repository"]).strip()
    branch = str(entry["branch"]).strip()
    role = str(entry["role"]).strip()
    pages_url = str(entry["pages_url"]).strip()
    enabled = entry["enabled"]
    rollout_wave = entry["rollout_wave"]

    if not node_id or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node_id):
        raise ValueError(f"nodes[{index}].id must be a lowercase slug")
    if not REPOSITORY.fullmatch(repository):
        raise ValueError(f"nodes[{index}].repository must be owner/name")
    if not branch or any(character.isspace() for character in branch):
        raise ValueError(f"nodes[{index}].branch must be a nonempty git branch")
    if role not in {"reference", "pilot", "production"}:
        raise ValueError(f"nodes[{index}].role has an unsupported value")
    if not isinstance(enabled, bool):
        raise ValueError(f"nodes[{index}].enabled must be boolean")
    if isinstance(rollout_wave, bool) or not isinstance(rollout_wave, int) or rollout_wave < 0:
        raise ValueError(f"nodes[{index}].rollout_wave must be a nonnegative integer")
    parsed_url = urlparse(pages_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError(f"nodes[{index}].pages_url must be an HTTPS URL")

    return FleetNode(
        id=node_id,
        repository=repository,
        branch=branch,
        role=role,
        enabled=enabled,
        rollout_wave=rollout_wave,
        pages_url=pages_url,
    )


def load_registry(path: str | Path) -> FleetRegistry:
    registry_path = Path(path)
    data = tomllib.loads(registry_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("fleet registry schema_version must be 1")

    raw_policy = data.get("policy", {})
    if not isinstance(raw_policy, dict):
        raise ValueError("fleet registry policy must be a table")
    policy = FleetPolicy(
        schedule_grace_minutes=_positive_integer(
            raw_policy.get("schedule_grace_minutes", 180),
            "policy.schedule_grace_minutes",
        ),
        workflow_history=_positive_integer(
            raw_policy.get("workflow_history", 100),
            "policy.workflow_history",
            maximum=100,
        ),
        api_timeout_seconds=_positive_integer(
            raw_policy.get("api_timeout_seconds", 20),
            "policy.api_timeout_seconds",
        ),
        page_timeout_seconds=_positive_integer(
            raw_policy.get("page_timeout_seconds", 20),
            "policy.page_timeout_seconds",
        ),
    )

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("fleet registry must contain at least one node")
    nodes = tuple(_node(entry, index) for index, entry in enumerate(raw_nodes))
    ids = [node.id for node in nodes]
    repositories = [node.repository.lower() for node in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("fleet node ids must be unique")
    if len(repositories) != len(set(repositories)):
        raise ValueError("fleet node repositories must be unique")

    return FleetRegistry(schema_version=1, policy=policy, nodes=nodes)

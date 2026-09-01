"""Resolve and attest the small set of user-owned skills used by Yiming Lab.

The adapter intentionally does not vendor the ``-SKILL-`` repository.  A local
checkout is supplied at runtime, and generated run artifacts record the exact
file hash and source root instead.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Iterable


SKILL_SPECS: tuple[dict[str, str], ...] = (
    {
        "name": "openwiki",
        "role": "primary",
        "path": "tools/openwiki/SKILL.md",
        "root": "skill",
        "why": "maintain a local code/personal wiki from connected sources",
    },
    {
        "name": "DeepTutor",
        "role": "support",
        "path": "skills/community/DeepTutor/SKILL.md",
        "root": "skill",
        "why": "run learning, research, question, visualization, and memory capabilities",
    },
    {
        "name": "sun-chengze-perspective",
        "role": "support",
        "path": "skills/community/nuwa-distilled/sun-chengze-perspective/SKILL.md",
        "root": "perspective",
        "why": "calibrate decisions as a mirror, never impersonate the user",
    },
    {
        "name": "research-workflow-kit",
        "role": "support",
        "path": "bundles/research-workflow-kit/WORKFLOW.md",
        "root": "skill",
        "why": "force charter, evidence, claim mapping, review, and release gates",
    },
    {
        "name": "QUALITY_GATES",
        "role": "review",
        "path": "governance/QUALITY_GATES.md",
        "root": "skill",
        "why": "audit facts, interfaces, implementation evidence, privacy, and delivery",
    },
    {
        "name": "universal-skill-router",
        "role": "coordination",
        "path": "SKILL.md",
        "root": "skill",
        "why": "keep the active skill group minimal and explicit",
    },
)


@dataclass(frozen=True)
class ResolvedSkill:
    name: str
    role: str
    relative_path: str
    root_kind: str
    path: str | None
    status: str
    sha256: str | None
    bytes: int
    lines: int
    declared_name: str | None
    description: str | None
    why: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def candidate_roots(
    explicit_skill_root: str | Path | None = None,
    explicit_perspective_root: str | Path | None = None,
) -> dict[str, Path | None]:
    """Resolve roots without ever cloning or downloading anything implicitly."""

    skill_value = explicit_skill_root or os.environ.get("YIMING_SKILL_ROOT")
    perspective_value = explicit_perspective_root or os.environ.get(
        "YIMING_PERSPECTIVE_ROOT"
    )
    return {
        "skill": _resolve_optional_path(skill_value),
        "perspective": _resolve_optional_path(perspective_value or skill_value),
    }


def resolve_selected_skills(
    skill_root: str | Path | None = None,
    perspective_root: str | Path | None = None,
) -> list[ResolvedSkill]:
    roots = candidate_roots(skill_root, perspective_root)
    resolved: list[ResolvedSkill] = []
    for spec in SKILL_SPECS:
        root = roots[spec["root"]]
        relative = spec["path"]
        if root is None:
            resolved.append(
                ResolvedSkill(
                    name=spec["name"],
                    role=spec["role"],
                    relative_path=relative,
                    root_kind=spec["root"],
                    path=None,
                    status="root_missing",
                    sha256=None,
                    bytes=0,
                    lines=0,
                    declared_name=None,
                    description=None,
                    why=spec["why"],
                )
            )
            continue

        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            resolved.append(_missing_skill(spec, path, "unsafe_path"))
            continue
        if not path.is_file():
            resolved.append(_missing_skill(spec, path, "file_missing"))
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            resolved.append(_missing_skill(spec, path, "unreadable"))
            continue
        resolved.append(
            ResolvedSkill(
                name=spec["name"],
                role=spec["role"],
                relative_path=relative,
                root_kind=spec["root"],
                path=str(path),
                status="loaded",
                sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                bytes=len(text.encode("utf-8")),
                lines=len(text.splitlines()),
                declared_name=_frontmatter_value(text, "name"),
                description=_frontmatter_value(text, "description"),
                why=spec["why"],
            )
        )
    return resolved


def read_skill(skill: ResolvedSkill, max_chars: int | None = None) -> str:
    if skill.status != "loaded" or skill.path is None:
        raise FileNotFoundError(f"Skill is not loaded: {skill.name} ({skill.status})")
    text = Path(skill.path).read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n[skill excerpt truncated by adapter]\n"
    return text


def skill_status_summary(skills: Iterable[ResolvedSkill]) -> dict[str, Any]:
    items = list(skills)
    return {
        "selected": len(items),
        "loaded": sum(item.status == "loaded" for item in items),
        "missing": [item.name for item in items if item.status != "loaded"],
        "items": [item.to_dict() for item in items],
    }


def _resolve_optional_path(value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return Path(value).expanduser().resolve()


def _missing_skill(spec: dict[str, str], path: Path, status: str) -> ResolvedSkill:
    return ResolvedSkill(
        name=spec["name"],
        role=spec["role"],
        relative_path=spec["path"],
        root_kind=spec["root"],
        path=str(path),
        status=status,
        sha256=None,
        bytes=0,
        lines=0,
        declared_name=None,
        description=None,
        why=spec["why"],
    )


def _frontmatter_value(text: str, key: str) -> str | None:
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None
    raw = "\n".join(lines[1:end])
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+)$", raw)
    if not match:
        return None
    value = match.group(1).strip().strip('"\'')
    return value or None

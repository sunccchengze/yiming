"""Roster discovery and run metadata for the Yiming Council.

The council treats each user-owned distilled book/person skill as a *lens*, not
as an autonomous authority. Discovery is local and read-only: no source tree is
copied into this repository and no skill script is executed by the roster.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


DISTILLED_PREFIXES = (
    "skills/community/nuwa-distilled/",
    "skills/community/nuwa-skill/examples/",
)


@dataclass(frozen=True)
class Seat:
    seat_id: str
    display_name: str
    kind: str
    relative_path: str
    source_root: str
    source_path: str
    sha256: str
    bytes: int
    lines: int
    declared_name: str | None
    description: str | None
    # These fields make a roster row explainable and reproducible even when
    # two checkouts contain the same logical skill path.
    source_branch: str = "unknown"
    source_commit: str = "unknown"
    source_dirty: bool | None = None
    lens_policy: str = "analytical_lens"
    stable_id_basis: str = "kind + relative_path + file_sha256"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def discover_roster(
    roots: Iterable[str | Path],
    mode: str = "people-books",
    limit: int = 0,
) -> list[Seat]:
    """Discover a deterministic roster from one or more local skill checkouts.

    ``people-books`` is the safe default for a large roundtable. ``distilled``
    adds the other Nuwa-distilled methods, and ``all`` scans every SKILL.md in
    the supplied checkout. A zero limit means all matching seats.
    """

    if mode not in {"people-books", "distilled", "all"}:
        raise ValueError(f"unknown roster mode: {mode}")
    candidates: dict[str, tuple[Path, Path]] = {}
    for root_value in roots:
        root = Path(root_value).expanduser().resolve()
        if not root.is_dir():
            continue
        for path in root.rglob("SKILL.md"):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if not _matches(relative, mode):
                continue
            # If two pinned checkouts contain the same logical path, the first
            # explicitly supplied root wins. The hash still exposes drift.
            candidates.setdefault(relative, (root, path))

    seats: list[Seat] = []
    used_ids: set[str] = set()
    provenance_by_root = {root: _git_provenance(root) for root, _ in candidates.values()}
    for relative, (root, path) in sorted(candidates.items()):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        parent = path.parent.name
        kind = _classify(relative, parent)
        declared_name = _frontmatter_value(text, "name")
        display_name = declared_name or _humanize(parent)
        # Include the logical path in the deterministic identity so adding a
        # second similarly named lens cannot renumber existing seats.
        identity = hashlib.sha256(
            f"{kind}\0{relative}\0{digest}".encode("utf-8")
        ).hexdigest()[:12]
        seat_id = f"{kind}-{_slug(display_name)}-{identity}"
        used_ids.add(seat_id)
        seats.append(
            Seat(
                seat_id=seat_id,
                display_name=display_name,
                kind=kind,
                relative_path=relative,
                source_root=str(root),
                source_path=str(path),
                sha256=digest,
                bytes=len(text.encode("utf-8")),
                lines=len(text.splitlines()),
                declared_name=declared_name,
                description=_frontmatter_value(text, "description"),
                source_branch=provenance_by_root[root]["branch"],
                source_commit=provenance_by_root[root]["commit"],
                source_dirty=provenance_by_root[root]["dirty"],
                lens_policy=(
                    "analytical_person_lens_not_person_statement"
                    if kind == "person"
                    else "distilled_book_or_method_lens"
                ),
            )
        )

    if limit > 0:
        return seats[:limit]
    return seats


def roster_summary(seats: Iterable[Seat], mode: str) -> dict[str, Any]:
    items = list(seats)
    return {
        "mode": mode,
        "count": len(items),
        "books": sum(seat.kind == "book" for seat in items),
        "people": sum(seat.kind == "person" for seat in items),
        "methods": sum(seat.kind == "method" for seat in items),
        "provenance": {
            "git_rows": sum(seat.source_commit not in {"", "unknown", "not-a-git-repo"} for seat in items),
            "dirty_rows": sum(seat.source_dirty is True for seat in items),
            "unknown_rows": sum(seat.source_commit in {"", "unknown", "not-a-git-repo"} for seat in items),
        },
        "seats": [seat.to_dict() for seat in items],
    }


def load_roster(path: str | Path) -> list[Seat]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("seats", payload if isinstance(payload, list) else [])
    if not isinstance(rows, list):
        raise ValueError("roster JSON must contain a seats list")
    return [Seat(**row) for row in rows]


def read_seat_text(seat: Seat, max_chars: int | None = None) -> str:
    text = Path(seat.source_path).read_text(encoding="utf-8")
    if max_chars is not None and len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n[seat brief truncated by adapter]\n"
    return text


def _matches(relative: str, mode: str) -> bool:
    if mode == "all":
        return True
    normalized = relative.lower()
    if mode == "distilled":
        return normalized.startswith(DISTILLED_PREFIXES)
    parent = Path(relative).parent.name.lower()
    return parent.startswith("book-") or "perspective" in parent


def _classify(relative: str, parent: str) -> str:
    lower_parent = parent.lower()
    lower_relative = relative.lower()
    if lower_parent.startswith("book-") or "/book-" in lower_relative:
        return "book"
    if "perspective" in lower_parent or "perspective" in lower_relative:
        return "person"
    return "method"


def _humanize(value: str) -> str:
    value = re.sub(r"[-_]+", " ", value).strip()
    return value.title() if value else "Unnamed seat"


def _slug(value: str) -> str:
    value = value.lower().replace("_", "-")
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value[:60] or "seat"


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


def _git_provenance(root: Path) -> dict[str, Any]:
    """Read branch, tip commit, and dirty state without mutating the checkout."""

    branch = _git_value(root, ["branch", "--show-current"])
    commit = _git_value(root, ["rev-parse", "HEAD"])
    if not commit:
        return {"branch": "not-a-git-repo", "commit": "not-a-git-repo", "dirty": None}
    return {
        "branch": branch or "detached",
        "commit": commit,
        "dirty": bool(_git_value(root, ["status", "--porcelain", "--untracked-files=all"])),
    }


def _git_value(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None

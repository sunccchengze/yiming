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
        base = f"{kind}-{_slug(display_name)}-{digest[:8]}"
        seat_id = base
        suffix = 2
        while seat_id in used_ids:
            seat_id = f"{base}-{suffix}"
            suffix += 1
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

"""Structured records and quality checks for a Yiming Council run.

The model output remains the source transcript.  This module only extracts an
optional, auditable structure from it; it never fills a missing recommendation
or score with a guess.  A missing field is represented as ``None`` and is
reported as a quality-gate warning.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

# Matches any CJK (Chinese/Japanese/Korean) character. Used to decide whether a
# section alias can safely act as a prefix for headings, since CJK text has no
# spaces/word boundaries.
_HAS_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


BALLOT_WEIGHTS: dict[str, float] = {
    "evidence": 0.35,
    "expected_value": 0.20,
    "reversibility": 0.20,
    "actionability": 0.25,
}

BALLOT_SCORE_FIELDS: tuple[str, ...] = tuple(BALLOT_WEIGHTS)

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "position": ("Position", "立场"),
    "best_argument": ("Best argument", "最强论点"),
    "strongest_objection": ("Strongest objection", "最强反对意见"),
    "evidence_needed": ("Evidence needed", "需要的证据"),
    "next_experiment": ("Small reversible next experiment", "Reversible next experiment", "可逆的下一步实验", "下一步实验", "最小可逆实验", "小步可逆实验"),
    "stop_condition": ("Stop condition",),
    "confidence": ("Confidence and why", "置信度及原因", "置信度"),
    "decision_frame": ("Decision frame and what is actually known", "决策框架与已知事实", "决策框架"),
    "options": ("Options and trade-offs", "选项与权衡"),
    "recommendation": ("Recommendation, if one is justified", "建议（如果证据足够）", "Recommendation", "建议"),
    "consensus": ("Consensus and convergence", "共识与收敛", "共识与趋同"),
    "strongest_dissent": ("Strongest dissent and why it might be right", "最强少数意见及其可能正确的原因", "Strongest dissent", "最强少数意见", "最强异议"),
    "evidence_gaps": ("Evidence gaps and claims that must not be repeated as facts", "证据缺口及不可当作事实的主张", "Evidence gaps", "证据缺口"),
    "stop_conditions": ("Stop conditions / human approval points", "停止条件／人工批准点", "Stop conditions", "停止条件"),
    "chair_confidence": ("Confidence and what would change your mind", "置信度及什么会改变判断", "Confidence"),
    "seat_map": ("Seat map", "席位映射"),
}

REQUIRED_CHAIR_SECTIONS: tuple[str, ...] = (
    "decision_frame",
    "options",
    "recommendation",
    "consensus",
    "strongest_dissent",
    "evidence_gaps",
    "next_experiment",
    "stop_conditions",
    "chair_confidence",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str | None:
    file_path = Path(path)
    if not file_path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def extract_model_text(raw: str) -> str:
    """Return the most useful text from common CLI JSON envelopes.

    DeepTutor versions and provider adapters use different JSON keys.  We keep
    the original raw output when no known text field is found so an operator can
    still inspect the exact transcript.
    """

    if not raw.strip():
        return ""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    candidate = _find_text(value)
    if candidate:
        return candidate
    return raw


def extract_sections(raw: str) -> dict[str, str]:
    """Extract sections by the exact headings requested in the prompts."""

    text = extract_model_text(raw)
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        canonical = _canonical_heading(line)
        if canonical:
            hits.append((index, canonical))
    sections: dict[str, str] = {}
    for hit_index, (line_index, canonical) in enumerate(hits):
        end = hits[hit_index + 1][0] if hit_index + 1 < len(hits) else len(lines)
        body = "\n".join(lines[line_index + 1 : end]).strip()
        if body and canonical not in sections:
            sections[canonical] = body
    return sections


def parse_ballot(raw: str, *, entity_id: str | None = None) -> dict[str, Any]:
    """Parse the optional ``<ballot>`` JSON block from a model response.

    Scores are normalized to the documented 0..5 range.  The weighted score is
    emitted only when every criterion is present and numeric; it is a heuristic
    prioritization aid, never a vote-counting truth claim.
    """

    text = extract_model_text(raw)
    candidate, source = _find_ballot_object(raw)
    if candidate is None:
        candidate, source = _find_ballot_object(text)
    candidate = candidate or {}
    stance = _normalize_stance(candidate.get("stance"))
    preferred = _as_optional_text(candidate.get("preferred_option"))
    confidence = _number(candidate.get("confidence"), minimum=0.0, maximum=1.0)

    raw_scores = candidate.get("scores")
    if not isinstance(raw_scores, dict):
        raw_scores = candidate
    scores = {
        field: _number(raw_scores.get(field), minimum=0.0, maximum=5.0)
        for field in BALLOT_SCORE_FIELDS
    }
    weighted_score = None
    if all(scores[field] is not None for field in BALLOT_SCORE_FIELDS):
        weighted_score = round(
            sum(float(scores[field]) / 5.0 * BALLOT_WEIGHTS[field] for field in BALLOT_SCORE_FIELDS),
            4,
        )

    missing = []
    if stance == "unclear":
        missing.append("stance")
    if confidence is None:
        missing.append("confidence")
    missing.extend(field for field, value in scores.items() if value is None)
    if preferred is None:
        missing.append("preferred_option")
    return {
        "entity_id": entity_id,
        "parse_status": "parsed" if source else "missing",
        "parse_source": source,
        "stance": stance,
        "preferred_option": preferred,
        "confidence": confidence,
        "scores": scores,
        "weighted_score": weighted_score,
        "weighting": dict(BALLOT_WEIGHTS),
        "missing_fields": sorted(set(missing)),
        "key_claims": _as_string_list(candidate.get("key_claims")),
        "disconfirming_evidence": _as_optional_text(candidate.get("disconfirming_evidence")),
    }


def build_proposal_ballots(blind: dict[str, Any]) -> list[dict[str, Any]]:
    ballots = []
    for proposal in blind.get("proposals", []):
        ballots.append(
            parse_ballot(
                str(proposal.get("response", "")),
                entity_id=str(proposal.get("anonymous_id")),
            )
        )
    return ballots


def build_reviewer_ballots(reviewers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ballots = []
    for reviewer in reviewers:
        path = Path(str(reviewer.get("stdout_path", "")))
        raw = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        ballots.append(
            parse_ballot(raw, entity_id=str(reviewer.get("reviewer_id")))
            | {
                "role": reviewer.get("role"),
                "status": reviewer.get("status"),
            }
        )
    return ballots


def build_decision_record(
    *,
    task: str,
    chair: dict[str, Any],
    blind: dict[str, Any],
    reviewers: Iterable[dict[str, Any]],
    ballots: Iterable[dict[str, Any]],
    reviewer_ballots: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    chair_path = Path(str(chair.get("stdout_path", "")))
    raw = chair_path.read_text(encoding="utf-8", errors="replace") if chair_path.is_file() else ""
    text = extract_model_text(raw)
    sections = extract_sections(raw)
    field_map = {
        "decision_frame": "decision_frame",
        "options": "options",
        "recommendation": "recommendation",
        "consensus": "consensus",
        "strongest_dissent": "strongest_dissent",
        "evidence_gaps": "evidence_gaps",
        "next_experiment": "next_experiment",
        "stop_conditions": "stop_conditions",
        "chair_confidence": "chair_confidence",
    }
    fields = {
        key: _compact(sections.get(section, ""), 8_000) or None
        for key, section in field_map.items()
    }
    missing = [key for key in REQUIRED_CHAIR_SECTIONS if not fields.get(key)]
    reviewer_items = list(reviewers)
    return {
        "schema_version": "yiming-decision-record-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": task,
        "chair_status": chair.get("status"),
        "chair_text_sha256": sha256_text(text),
        "chair_text_chars": len(text),
        "sections": fields,
        "missing_sections": missing,
        "independent_opinions": {
            "count": len(blind.get("proposals", [])),
            "artifact": "blind-packet.json",
        },
        "anonymous_review": {
            "count": len(reviewer_items),
            "artifact": "reviewer-results.json",
        },
        "ballots": list(ballots),
        "reviewer_ballots": list(reviewer_ballots),
        "interpretation": {
            "weighted_score_is_heuristic": True,
            "missing_fields_are_not_imputed": True,
            "person_lenses_are_not_person_statements": True,
        },
    }


def build_quality_report(
    *,
    output: Path,
    run: dict[str, Any],
    seats: list[Any],
    seat_results: Iterable[dict[str, Any]],
    blind: dict[str, Any],
    reviewers: Iterable[dict[str, Any]],
    chair: dict[str, Any],
    decision_record: dict[str, Any],
) -> dict[str, Any]:
    results = list(seat_results)
    reviewer_items = list(reviewers)
    checks: list[dict[str, Any]] = []

    provenance_ok = all(
        bool(getattr(seat, "source_branch", "")) and bool(getattr(seat, "source_commit", ""))
        for seat in seats
    )
    checks.append(
        _check(
            "roster-provenance",
            "pass" if provenance_ok else "warn",
            "Every seat records source branch and commit; unknown values remain explicit."
            if provenance_ok
            else "At least one seat has unavailable Git provenance (common for a non-Git fixture).",
        )
    )

    prompt_failures: list[str] = []
    raw_outputs = {
        str(item.get("seat_id")): _read_path(item.get("stdout_path"))
        for item in results
    }
    for seat in seats:
        prompt_path = output / "seats" / seat.seat_id / "prompt.md"
        prompt = _read_path(prompt_path)
        if not prompt:
            prompt_failures.append(f"{seat.seat_id}: missing prompt")
            continue
        if "Do not claim to be the historical person or author" not in prompt:
            prompt_failures.append(f"{seat.seat_id}: missing lens identity boundary")
        for other_id, other_output in raw_outputs.items():
            if other_id != seat.seat_id and len(other_output.strip()) >= 32 and other_output.strip() in prompt:
                prompt_failures.append(f"{seat.seat_id}: contains {other_id} output")
    checks.append(
        _check(
            "first-round-isolation",
            "pass" if not prompt_failures else "fail",
            "Seat prompts contain no peer output and include the analytical-lens disclaimer."
            if not prompt_failures
            else "; ".join(prompt_failures),
        )
    )

    forbidden = {"seat_id", "display_name", "source_path", "source_root", "relative_path"}
    leaked_names = sorted(
        key for key in forbidden if any(key in proposal for proposal in blind.get("proposals", []))
    )
    response_leaks: list[str] = []
    proposals = blind.get("proposals", [])
    for index, seat in enumerate(seats):
        if index >= len(proposals):
            continue
        response = str(proposals[index].get("response", "")).casefold()
        for identifier in (
            getattr(seat, "display_name", ""),
            getattr(seat, "declared_name", "") or "",
            getattr(seat, "relative_path", ""),
        ):
            if len(identifier) >= 3 and identifier.casefold() in response:
                response_leaks.append(f"P{index + 1:03d}:{identifier}")
    if response_leaks:
        leaked_names.append("response_identity")
    checks.append(
        _check(
            "anonymous-packet",
            "pass" if not leaked_names else "fail",
            "Blind packet contains anonymous IDs only; private roster mapping is separate."
            if not leaked_names
            else f"Blind packet leaks private fields or identity text: {', '.join(leaked_names + response_leaks)}",
        )
    )

    expected_reviewers = int(run.get("protocol", {}).get("reviewer_count", 0))
    reviewer_ok = len(reviewer_items) == expected_reviewers
    checks.append(
        _check(
            "reviewer-completeness",
            "pass" if reviewer_ok else "fail",
            f"Expected {expected_reviewers} reviewer records and found {len(reviewer_items)}."
            if reviewer_ok
            else f"Expected {expected_reviewers} reviewer records and found {len(reviewer_items)}.",
        )
    )

    missing_sections = decision_record.get("missing_sections", [])
    checks.append(
        _check(
            "decision-memo-structure",
            "pass" if not missing_sections and chair.get("status") == "completed" else "warn",
            "Chair memo contains all required decision-support sections."
            if not missing_sections and chair.get("status") == "completed"
            else "Chair output is incomplete or not parseable; inspect chair/final.md before acting.",
        )
    )
    if any(item.get("status") != "completed" for item in results):
        checks.append(
            _check(
                "seat-completeness",
                "warn",
                "Some seats failed or timed out; their absence must not be treated as agreement.",
            )
        )
    else:
        checks.append(_check("seat-completeness", "pass", "All selected seats returned successfully."))

    status = "fail" if any(item["status"] == "fail" for item in checks) else (
        "warn" if any(item["status"] == "warn" for item in checks) else "pass"
    )
    return {
        "schema_version": "yiming-quality-gates-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": checks,
        "manual_review_required": True,
        "note": "A passing gate does not make the recommendation true; it only confirms protocol and artifact checks.",
    }


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _find_text(value: Any) -> str:
    preferred = ("content", "text", "response", "answer", "output", "final", "message")
    if isinstance(value, dict):
        for key in preferred:
            child = value.get(key)
            if isinstance(child, str) and child.strip():
                return child
        for child in value.values():
            found = _find_text(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_text(child)
            if found:
                return found
    return ""


def _find_ballot_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    candidate = _walk_ballot(parsed)
    if candidate is not None:
        return candidate, "json"
    marker = re.search(r"<ballot>\s*(\{.*?\})\s*</ballot>", raw, flags=re.IGNORECASE | re.DOTALL)
    if marker:
        try:
            value = json.loads(marker.group(1))
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return value, "ballot-tag"
    for match in re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and _looks_like_ballot(value):
            return value, "json-fence"
    return None, None


def _walk_ballot(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if _looks_like_ballot(value):
            return value
        for child in value.values():
            found = _walk_ballot(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _walk_ballot(child)
            if found is not None:
                return found
    return None


def _looks_like_ballot(value: dict[str, Any]) -> bool:
    return "scores" in value or ("stance" in value and "confidence" in value)


def _normalize_stance(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {
        "support": "support",
        "支持": "support",
        "oppose": "oppose",
        "against": "oppose",
        "反对": "oppose",
        "conditional": "conditional",
        "有条件支持": "conditional",
        "条件支持": "conditional",
        "unclear": "unclear",
        "unknown": "unclear",
        "不确定": "unclear",
    }
    return mapping.get(normalized, "unclear")


def _number(value: Any, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < minimum or number > maximum:
        return None
    return round(number, 4)


def _canonical_heading(line: str) -> str | None:
    normalized = re.sub(r"^\s*#{0,6}\s*", "", line).strip()
    normalized = re.sub(r"^\s*\d+\s*[.)、:]\s*", "", normalized).strip()
    normalized = normalized.rstrip("：:").strip()
    if not normalized:
        return None
    for canonical, aliases in SECTION_ALIASES.items():
        for alias in aliases:
            if normalized == alias:
                return canonical
            # A single-word alias like "Confidence" is ambiguous: a body line that
            # merely begins with the same word ("Confidence low for ...") must not be
            # mistaken for a heading. Only allow a heading prefix when the alias is a
            # multi-word phrase, so a short terse heading such as "Confidence" still
            # matches exactly without swallowing long body sentences.
            if " " in alias and normalized.startswith(alias + " "):
                return canonical
            # CJK aliases have no word boundaries/spaces, so a heading such as
            # "共识与收敛（及分歧）" or "最强异议与对策" begins with the alias but
            # not with "alias + space". Allow a prefix match only when the alias
            # contains CJK characters AND is long enough to be unambiguous (>=4
            # chars), so a terse 2-3 char alias like "置信度" or "建议" never
            # swallows longer headings belonging to another section.
            if _HAS_CJK.match(alias) and len(alias) >= 4 and normalized.startswith(alias):
                return canonical
    return None


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _read_path(value: Any) -> str:
    if not value:
        return ""
    path = Path(str(value))
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        return ""


def _compact(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker = "\n\n[section compacted by adapter]\n\n"
    budget = max(2, limit - len(marker))
    left = max(1, budget // 2)
    right = max(1, budget - left)
    return value[:left].rstrip() + marker + value[-right:].lstrip()

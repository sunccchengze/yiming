"""Command line interface for the Yiming Lab / Council adapter."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .council import discover_roster, roster_summary
from .council_protocol import CouncilError, load_council, prepare_council, run_council
from .pipeline import (
    DEFAULT_TASK,
    PreparationError,
    apply_openwiki_config,
    prepare_run,
)
from .routing import route_task
from .skills import resolve_selected_skills, skill_status_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m lab",
        description="Local, privacy-first adapter for OpenWiki, DeepTutor, and a blind skill council.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="build a private source pack and execution plan")
    prepare.add_argument("--inventory", default="minillm/artifacts/account_inventory.json")
    prepare.add_argument("--out", required=True, help="private output directory, outside this Git checkout")
    prepare.add_argument("--corpus", help="optional existing JSONL corpus")
    prepare.add_argument("--include-corpus", action="store_true", help="explicitly copy safe corpus records into the local pack")
    prepare.add_argument("--repo", action="append", default=[], metavar="ID=PATH", help="local repo for OpenWiki, repeatable")
    prepare.add_argument("--skill-root", help="local -SKILL- checkout for router/OpenWiki/DeepTutor/workflow skills")
    prepare.add_argument("--perspective-root", help="optional -SKILL- checkout containing sun-chengze-perspective")
    prepare.add_argument("--no-skill-docs", action="store_true", help="record skill hashes but do not copy selected SKILL.md files into the private pack")
    prepare.add_argument("--task", default=DEFAULT_TASK)
    prepare.add_argument("--kb-name", default="yiming-lab")
    prepare.add_argument("--max-corpus-files", type=int, default=2000)
    prepare.add_argument("--max-corpus-record-chars", type=int, default=400_000)
    prepare.add_argument("--run-id")
    prepare.add_argument("--allow-repo-output", action="store_true")
    prepare.set_defaults(handler=_handle_prepare)

    route = sub.add_parser("route", help="show the minimal selected capability and skill group")
    route.add_argument("task")
    route.add_argument("--format", choices=("json", "text"), default="text")
    route.set_defaults(handler=_handle_route)

    doctor = sub.add_parser("doctor", help="check local prerequisites without printing credentials")
    doctor.add_argument("--inventory", default="minillm/artifacts/account_inventory.json")
    doctor.add_argument("--skill-root", action="append", default=[])
    doctor.add_argument("--perspective-root")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    doctor.add_argument("--strict", action="store_true")
    doctor.set_defaults(handler=_handle_doctor)

    apply = sub.add_parser("apply-openwiki-config", help="explicitly install local-git paths into OpenWiki")
    apply.add_argument("--run", required=True)
    apply.add_argument("--openwiki-home")
    apply.add_argument("--yes", action="store_true")
    apply.add_argument("--force", action="store_true")
    apply.set_defaults(handler=_handle_apply)

    council = sub.add_parser("council", help="discover seats, prepare prompts, or run the blind council")
    council_sub = council.add_subparsers(dest="council_command", required=True)

    roster = council_sub.add_parser("roster", help="list distilled people/books available as seats")
    roster.add_argument("--skill-root", action="append", default=[])
    roster.add_argument("--roster-mode", choices=("people-books", "distilled", "all"), default="people-books")
    roster.add_argument("--limit", type=int, default=0, help="0 means all matching seats")
    roster.add_argument("--json", action="store_true", dest="as_json")
    roster.set_defaults(handler=_handle_roster)

    council_prepare = council_sub.add_parser("prepare", help="create isolated seat prompts; never calls a model")
    council_prepare.add_argument("--out", required=True)
    council_prepare.add_argument("--skill-root", action="append", default=[])
    council_prepare.add_argument("--roster-mode", choices=("people-books", "distilled", "all"), default="people-books")
    council_prepare.add_argument("--max-seats", type=int, default=12, help="0 means all matching seats")
    council_prepare.add_argument("--reviewer-count", type=int, default=3, help="0 disables blind reviewer calls; max 3")
    council_prepare.add_argument("--source-pack")
    council_prepare.add_argument("--seat-excerpt-chars", type=int, default=12_000)
    council_prepare.add_argument("--task", default=DEFAULT_TASK)
    council_prepare.add_argument("--run-id")
    council_prepare.add_argument("--allow-repo-output", action="store_true")
    council_prepare.set_defaults(handler=_handle_council_prepare)

    council_run = council_sub.add_parser("run", help="dry-run or execute isolated seat calls followed by one chair")
    council_run.add_argument("--run", required=True)
    council_run.add_argument("--execute", action="store_true", help="actually invoke DeepTutor; otherwise print the plan")
    council_run.add_argument("--workers", type=int, default=8)
    council_run.add_argument("--max-seats", type=int, default=None)
    council_run.add_argument("--timeout-seconds", type=int, default=900)
    council_run.add_argument("--resume", action="store_true", help="reuse completed seat outputs and rerun only missing/failed seats")
    council_run.add_argument("--deeptutor-bin", default="deeptutor")
    council_run.set_defaults(handler=_handle_council_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (PreparationError, CouncilError, ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return int(result or 0)


def _handle_prepare(args: argparse.Namespace) -> int:
    local_repositories = [_parse_repo(value) for value in args.repo]
    manifest = prepare_run(
        args.inventory,
        args.out,
        corpus_path=args.corpus,
        include_corpus=args.include_corpus,
        local_repositories=local_repositories,
        skill_root=args.skill_root,
        perspective_root=args.perspective_root,
        include_skill_docs=not args.no_skill_docs,
        task=args.task,
        kb_name=args.kb_name,
        max_corpus_files=args.max_corpus_files,
        max_corpus_record_chars=args.max_corpus_record_chars,
        allow_repo_output=args.allow_repo_output,
        run_id=args.run_id,
    )
    print(json.dumps(_public_manifest_summary(manifest), ensure_ascii=False, indent=2))
    return 0


def _handle_route(args: argparse.Namespace) -> int:
    route = route_task(args.task)
    if args.format == "json":
        print(json.dumps(route, ensure_ascii=False, indent=2))
    else:
        print(f"能力: {route['capability']}")
        print(f"决策任务: {'是' if route['decision_task'] else '否'}")
        print(f"证据门禁: {'是' if route['evidence_required'] else '否'}")
        print(f"技能组: {'、'.join(route['selected_skills'])}")
        print(f"DeepTutor tools: {', '.join(route['deeptutor_tools']) or 'none'}")
        print(route["independence_rule"])
    return 0


def _handle_doctor(args: argparse.Namespace) -> int:
    roots = args.skill_root or []
    perspective_root = args.perspective_root
    inventory = Path(args.inventory).expanduser().resolve()
    commands = {name: shutil.which(name) for name in ("git", "gh", "node", "openwiki", "deeptutor")}
    versions = {name: _version(path) for name, path in commands.items() if path}
    skills = resolve_selected_skills(
        roots[0] if roots else None,
        perspective_root,
    )
    model_keys = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
        "DASHSCOPE_API_KEY",
    )
    payload: dict[str, Any] = {
        "python": sys.version.split()[0],
        "python_ok": sys.version_info >= (3, 11),
        "commands": commands,
        "versions": versions,
        "inventory": {"path": str(inventory), "exists": inventory.is_file()},
        "skill_root_count": len(roots),
        "skills": skill_status_summary(skills),
        "model_credentials_present": {key: bool(os.environ.get(key)) for key in model_keys},
        "note": "Absent model credentials are not a preparation failure; use dry-run or configure a provider before --execute.",
    }
    required_ok = (
        payload["python_ok"]
        and payload["inventory"]["exists"]
        and bool(commands["git"])
        and payload["skills"]["loaded"] >= 1
    )
    payload["strict_ok"] = required_ok
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Python {payload['python']} — {'ok' if payload['python_ok'] else 'need 3.11+'}")
        for name, path in commands.items():
            print(f"{name}: {path or 'missing'}")
        print(f"inventory: {'ok' if payload['inventory']['exists'] else 'missing'} ({inventory})")
        print(f"selected skill files loaded: {payload['skills']['loaded']}/{payload['skills']['selected']}")
        print("model credentials: " + ", ".join(key for key, present in payload["model_credentials_present"].items() if present) + ("" if any(payload["model_credentials_present"].values()) else "none"))
        print("strict: " + ("ok" if required_ok else "not ready"))
    return 0 if (required_ok or not args.strict) else 1


def _handle_apply(args: argparse.Namespace) -> int:
    target = apply_openwiki_config(
        args.run,
        openwiki_home=args.openwiki_home,
        yes=args.yes,
        force=args.force,
    )
    print(f"wrote OpenWiki local-git config: {target}")
    return 0


def _handle_roster(args: argparse.Namespace) -> int:
    if not args.skill_root:
        raise CouncilError("pass at least one --skill-root to a local -SKILL- checkout")
    seats = discover_roster(args.skill_root, mode=args.roster_mode, limit=args.limit)
    payload = roster_summary(seats, args.roster_mode)
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"模式: {args.roster_mode}; seats: {payload['count']} (books={payload['books']}, people={payload['people']}, methods={payload['methods']})")
        for index, seat in enumerate(seats, start=1):
            print(f"P{index:03d} [{seat.kind}] {seat.display_name} — {seat.relative_path} — {seat.sha256[:12]}")
    return 0


def _handle_council_prepare(args: argparse.Namespace) -> int:
    manifest = prepare_council(
        args.out,
        task=args.task,
        skill_roots=args.skill_root,
        roster_mode=args.roster_mode,
        max_seats=args.max_seats,
        reviewer_count=args.reviewer_count,
        source_pack=args.source_pack,
        seat_excerpt_chars=args.seat_excerpt_chars,
        allow_repo_output=args.allow_repo_output,
        run_id=args.run_id,
    )
    print(json.dumps(_public_council_summary(manifest), ensure_ascii=False, indent=2))
    return 0


def _handle_council_run(args: argparse.Namespace) -> int:
    result = run_council(
        args.run,
        execute=args.execute,
        workers=args.workers,
        max_seats=args.max_seats,
        timeout_seconds=args.timeout_seconds,
        deeptutor_bin=args.deeptutor_bin,
        resume=args.resume,
    )
    print(json.dumps(_public_run_summary(result), ensure_ascii=False, indent=2))
    return 0


def _parse_repo(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise PreparationError(f"--repo must be ID=PATH, got {value!r}")
    repo_id, path = value.split("=", 1)
    if not repo_id.strip() or not path.strip():
        raise PreparationError(f"--repo must be ID=PATH, got {value!r}")
    return repo_id.strip(), path.strip()


def _version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (result.stdout or result.stderr).strip().splitlines()
    return line[0] if line else None


def _public_manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "prepared",
        "run_id": manifest["run_id"],
        "output": manifest["artifacts"]["source_pack"].rsplit("/source-pack", 1)[0],
        "inventory_stats": manifest["inventory_stats"],
        "route": manifest["route"],
        "skills": manifest["skills"],
        "corpus": manifest["corpus"],
        "next": "review RUN_PLAN.md; preparation did not call a model",
    }


def _public_council_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "prepared",
        "run_id": manifest["run_id"],
        "output": manifest["artifacts"]["roster"].rsplit("/roster.json", 1)[0],
        "protocol": manifest["protocol"],
        "roster": {
            "mode": manifest["roster"]["mode"],
            "count": manifest["roster"]["count"],
            "books": manifest["roster"]["books"],
            "people": manifest["roster"]["people"],
            "methods": manifest["roster"]["methods"],
        },
        "execution": manifest["execution"],
        "next": "run `python -m lab council run --run <output>` for dry-run; add --execute only after configuring DeepTutor",
    }


def _public_run_summary(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "dry-run":
        return {
            "status": "dry-run",
            "run": result["run"],
            "seat_count": result["seat_count"],
            "reviewer_count": result.get("reviewer_count", 0),
            "expected_calls": result.get("expected_calls"),
            "seat_commands": len(result["commands"]),
            "chair_command_present": bool(result.get("chair_command")),
            "next": "add --execute after installing/configuring DeepTutor",
        }
    return {
        "status": result.get("status"),
        "seat_results": [
            {key: value for key, value in item.items() if key not in {"command"}}
            for item in result.get("seat_results", [])
        ],
        "reviewer_results": [
            {key: value for key, value in item.items() if key != "command"}
            for item in result.get("reviewer_results", [])
        ],
        "chair": {key: value for key, value in result.get("chair", {}).items() if key != "command"},
        "next": "inspect blind-packet.json, chair/final.md, dissent, and quality gates before acting",
    }

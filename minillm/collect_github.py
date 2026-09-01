from __future__ import annotations

"""Collect a bounded, safety-filtered corpus from a GitHub inventory.

The inventory is produced by the account/branch discovery step.  This module
uses shallow partial clones so it can inspect all branch tips without copying a
full Git object database or putting raw source under version control.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


TEXT_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".csv", ".go", ".h", ".hh", ".hpp",
    ".html", ".ini", ".ipynb", ".java", ".js", ".jsx", ".json", ".kt", ".less",
    ".md", ".mjs", ".php", ".py", ".r", ".rb", ".rs", ".sass", ".scala",
    ".scss", ".sh", ".sql", ".svg", ".swift", ".tex", ".toml", ".ts", ".tsx",
    ".txt", ".vue", ".xml", ".yaml", ".yml", ".zsh",
}
TEXT_FILENAMES = {
    "dockerfile", "license", "makefile", "readme", "readme.md", "readme.txt",
    "changelog", "contributing", "authors", "notice", "procfile",
}
SKIP_DIRS = {
    ".git", ".idea", ".next", ".nuxt", ".parcel-cache", ".pytest_cache",
    ".svelte-kit", ".tox", ".venv", ".vite", "__pycache__", "build", "coverage",
    "dist", "node_modules", "out", "public", "target", "vendor", "web_modules",
}
SKIP_FILENAMES = {
    ".ds_store", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "composer.lock",
    "poetry.lock", "cargo.lock",
}
SECRET_PATH_PARTS = {
    ".env", "credentials", "credential", "secrets", "secret", "private_key",
    "private-key", "id_rsa", "id_ed25519",
}
SECRET_CONTENT_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret)"
        r"\s*[:=]\s*[\"'][^\"']{12,}[\"']"
    ),
]


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def is_text_path(path: str) -> bool:
    path_obj = Path(path)
    name = path_obj.name.lower()
    if name in SKIP_FILENAMES:
        return False
    if name in TEXT_FILENAMES or name.startswith("readme"):
        return True
    return path_obj.suffix.lower() in TEXT_EXTENSIONS


def should_skip_path(path: str) -> str | None:
    parts = [part.lower() for part in Path(path).parts]
    if any(part in SKIP_DIRS for part in parts):
        return "generated_or_dependency_directory"
    if any(part in SECRET_PATH_PARTS for part in parts):
        return "sensitive_path"
    if not is_text_path(path):
        return "non_text_extension"
    if path.lower().endswith((".min.js", ".min.css", ".map")):
        return "generated_minified_file"
    return None


def has_secret_pattern(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_CONTENT_PATTERNS)


def path_priority(path: str) -> tuple[int, int, str]:
    lower = path.lower()
    name = Path(path).name.lower()
    if name.startswith("readme") or name in {"license", "changelog", "contributing"}:
        priority = 0
    elif "/docs/" in f"/{lower}/" or lower.startswith("docs/"):
        priority = 1
    elif Path(path).suffix.lower() in {".md", ".txt", ".rst"}:
        priority = 2
    elif Path(path).suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"}:
        priority = 3
    else:
        priority = 4
    return priority, len(path), path


def parse_tree(raw: bytes) -> list[tuple[str, str, int, str]]:
    entries: list[tuple[str, str, int, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        fields = metadata.decode("ascii").split()
        if len(fields) < 4:
            continue
        mode, object_type, sha, raw_size = fields[:4]
        if object_type != "blob":
            continue
        try:
            size = int(raw_size)
        except ValueError:
            continue
        entries.append((mode, sha, size, raw_path.decode("utf-8", errors="replace")))
    return entries


def ensure_branch_commit(repo_dir: Path, branch: dict[str, Any]) -> str | None:
    expected_sha = branch.get("sha")
    if not expected_sha:
        return None
    try:
        run(["git", "cat-file", "-e", f"{expected_sha}^{{commit}}"], cwd=repo_dir)
        return expected_sha
    except subprocess.CalledProcessError:
        try:
            run(["git", "fetch", "--depth=1", "origin", branch["name"]], cwd=repo_dir)
            run(["git", "cat-file", "-e", f"{expected_sha}^{{commit}}"], cwd=repo_dir)
            return expected_sha
        except subprocess.CalledProcessError:
            return None


def git_commit_stat(repo_dir: Path, sha: str) -> str:
    try:
        result = run(
            ["git", "show", "--stat", "--format=", "--no-renames", sha], cwd=repo_dir
        )
    except subprocess.CalledProcessError:
        return ""
    return result.stdout.decode("utf-8", errors="replace").strip()


def clone_repo(full_name: str, destination: Path) -> tuple[Path | None, str | None]:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{full_name}.git"
    command = [
        "git", "clone", "--filter=blob:none", "--no-checkout", "--no-tags",
        "--no-single-branch", "--depth=1", url, str(destination),
    ]
    try:
        run(command)
        return destination, None
    except subprocess.CalledProcessError as error:
        details = error.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return None, details[-1] if details else "git clone failed"


def file_record(
    repo: str,
    branch: str,
    commit_sha: str,
    path: str,
    text: str,
    byte_size: int,
    digest: str,
    aliases: list[dict[str, str]],
) -> dict[str, Any]:
    source_line = f"项目仓库：{repo}\n分支：{branch}\n最新提交：{commit_sha}\n文件路径：{path}"
    if aliases:
        source_line += "\n相同内容的其他来源：" + ", ".join(
            f"{item['branch']}:{item['path']}" for item in aliases[:20]
        )
    return {
        "kind": "repository_file",
        "repo": repo,
        "branch": branch,
        "commit": commit_sha,
        "path": path,
        "sha256": digest,
        "bytes": byte_size,
        "text": f"{source_line}\n文件内容：\n{text}",
    }


def commit_record(repo: str, branch: dict[str, Any], commit: dict[str, Any], stat: str) -> dict[str, Any]:
    message = str(commit.get("message") or "").strip()
    date = str(commit.get("date") or "未知时间")
    sha = str(commit.get("sha") or "")
    text = (
        f"项目仓库：{repo}\n分支：{branch['name']}\n提交时间：{date}\n"
        f"提交 SHA：{sha}\n提交说明：{message}"
    )
    if stat:
        text += f"\n文件改动统计：\n{stat}"
    return {
        "kind": "commit_summary",
        "repo": repo,
        "branch": branch["name"],
        "commit": sha,
        "text": text,
    }


def collect(
    inventory_path: Path,
    output_path: Path,
    work_dir: Path,
    max_file_bytes: int,
    max_files_per_branch: int,
    max_commits_per_branch: int,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    digest_sources: dict[str, list[dict[str, str]]] = {}
    stats: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    repo_summaries: list[dict[str, Any]] = []

    repositories = inventory.get("repositories", [])
    for repo_index, repository in enumerate(repositories, start=1):
        full_name = str(repository["nameWithOwner"])
        repo_dir, clone_error = clone_repo(full_name, work_dir / full_name.split("/", 1)[1])
        if repo_dir is None:
            failures.append({"repo": full_name, "stage": "clone", "error": clone_error or "unknown"})
            print(f"[{repo_index}/{len(repositories)}] {full_name}: clone failed: {clone_error}", file=sys.stderr)
            continue

        branch_summaries: list[dict[str, Any]] = []
        branches = repository.get("branches", [])
        for branch_index, branch in enumerate(branches, start=1):
            sha = ensure_branch_commit(repo_dir, branch)
            if sha is None:
                failures.append({
                    "repo": full_name,
                    "branch": str(branch.get("name")),
                    "stage": "branch",
                    "error": "tip commit was not available after fetch",
                })
                continue

            branch_counts: Counter[str] = Counter()
            branch_file_records: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
            try:
                tree = parse_tree(run(["git", "ls-tree", "-r", "-l", "-z", sha], cwd=repo_dir).stdout)
            except subprocess.CalledProcessError as error:
                failures.append({
                    "repo": full_name,
                    "branch": str(branch["name"]),
                    "stage": "tree",
                    "error": error.stderr.decode("utf-8", errors="replace")[-500:],
                })
                continue

            candidates: list[tuple[tuple[int, int, str], str, str, int, str]] = []
            for mode, blob_sha, size, path in tree:
                reason = should_skip_path(path)
                if reason:
                    branch_counts[reason] += 1
                    continue
                if size < 0 or size > max_file_bytes:
                    branch_counts["file_too_large"] += 1
                    continue
                candidates.append((path_priority(path), mode, blob_sha, size, path))
            candidates.sort(key=lambda item: item[0])

            for _, mode, blob_sha, size, path in candidates[:max_files_per_branch]:
                if mode.startswith("12"):
                    branch_counts["symlink"] += 1
                    continue
                try:
                    raw = run(["git", "show", f"{sha}:{path}"], cwd=repo_dir).stdout
                except subprocess.CalledProcessError:
                    branch_counts["blob_read_error"] += 1
                    continue
                if b"\0" in raw:
                    branch_counts["binary_content"] += 1
                    continue
                text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
                if has_secret_pattern(text):
                    branch_counts["secret_pattern"] += 1
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                source = {"repo": full_name, "branch": branch["name"], "path": path}
                if digest in digest_sources:
                    digest_sources[digest].append(source)
                    branch_counts["duplicate_file"] += 1
                    continue
                digest_sources[digest] = [source]
                record = file_record(
                    full_name,
                    branch["name"],
                    sha,
                    path,
                    text,
                    size,
                    digest,
                    [],
                )
                branch_file_records.append((path_priority(path), record))
                branch_counts["file_record"] += 1

            records.extend(record for _, record in branch_file_records)
            commits = branch.get("recent_commits", [])[:max_commits_per_branch]
            stat = git_commit_stat(repo_dir, sha)
            for commit in commits:
                if commit.get("sha") and commit.get("message"):
                    records.append(commit_record(full_name, branch, commit, stat if commit["sha"] == sha else ""))
                    branch_counts["commit_record"] += 1
            stats.update(branch_counts)
            branch_summaries.append({
                "name": branch["name"],
                "sha": sha,
                "records": dict(branch_counts),
            })
            print(
                f"[{repo_index}/{len(repositories)}] {full_name} "
                f"branch {branch_index}/{len(branches)} {branch['name']}: "
                f"{branch_counts['file_record']} files, {branch_counts['commit_record']} commits",
                flush=True,
            )
        repo_summaries.append({
            "repo": full_name,
            "branches": len(branch_summaries),
            "branch_summaries": branch_summaries,
        })
        shutil.rmtree(repo_dir, ignore_errors=True)

    # Fill duplicate-source metadata after all branches have been inspected.
    for record in records:
        if record["kind"] != "repository_file":
            continue
        sources = digest_sources.get(record["sha256"], [])
        record["sources"] = sources
        if len(sources) > 1:
            content = record["text"].split("文件内容：\n", 1)[-1]
            source_line = (
                f"项目仓库：{record['repo']}\n分支：{record['branch']}\n"
                f"最新提交：{record['commit']}\n文件路径：{record['path']}\n"
                "相同内容的其他来源："
                + ", ".join(f"{item['repo']}:{item['branch']}:{item['path']}" for item in sources[1:20])
                + "\n文件内容：\n"
                + content
            )
            record["text"] = source_line

    with open(output_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest = {
        "source_inventory": str(inventory_path),
        "output": str(output_path),
        "max_file_bytes": max_file_bytes,
        "max_files_per_branch": max_files_per_branch,
        "max_commits_per_branch": max_commits_per_branch,
        "records": len(records),
        "file_records": sum(record["kind"] == "repository_file" for record in records),
        "commit_records": sum(record["kind"] == "commit_summary" for record in records),
        "unique_file_contents": len(digest_sources),
        "stats": dict(stats),
        "failures": failures,
        "repositories": repo_summaries,
    }
    manifest_path = output_path.with_name("collection_manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corpus written to {output_path}")
    print(f"collection manifest written to {manifest_path}")
    print(json.dumps({key: manifest[key] for key in ("records", "file_records", "commit_records", "unique_file_contents")}, ensure_ascii=False))
    if failures:
        print(f"failures={len(failures)}; see {manifest_path}", file=sys.stderr)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect safe text snapshots from GitHub branches")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work-dir", default="/tmp/minillm-github")
    parser.add_argument("--max-file-bytes", type=int, default=120_000)
    parser.add_argument("--max-files-per-branch", type=int, default=250)
    parser.add_argument("--max-commits-per-branch", type=int, default=200)
    args = parser.parse_args()
    collect(
        Path(args.inventory),
        Path(args.out),
        Path(args.work_dir),
        args.max_file_bytes,
        args.max_files_per_branch,
        args.max_commits_per_branch,
    )


if __name__ == "__main__":
    main()

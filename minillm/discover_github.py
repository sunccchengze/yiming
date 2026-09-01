from __future__ import annotations

"""Build a repository/branch/commit inventory using the local GitHub CLI."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode


REPO_FIELDS = "nameWithOwner,isPrivate,defaultBranchRef,updatedAt,pushedAt,description"
VISIBILITIES = ("public", "private", "internal")


def run_json(command: list[str]) -> object:
    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise RuntimeError("找不到 gh，请先安装 GitHub CLI 并完成 gh auth login") from error
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "").strip()
        raise RuntimeError(f"命令失败：{' '.join(command)}\n{details}") from error
    return json.loads(result.stdout)


def repo_list(owner: str, visibility: str) -> list[dict]:
    return list(
        run_json(
            [
                "gh",
                "repo",
                "list",
                owner,
                "--limit",
                "1000",
                "--visibility",
                visibility,
                "--json",
                REPO_FIELDS,
            ]
        )
    )


def api_page(endpoint: str) -> list[dict]:
    value = run_json(["gh", "api", endpoint])
    if not isinstance(value, list):
        raise RuntimeError(f"GitHub API 返回的不是列表：{endpoint}")
    return value


def api_all(endpoint_base: str, params: dict[str, str]) -> list[dict]:
    items: list[dict] = []
    for page in range(1, 101):
        query = urlencode({**params, "per_page": "100", "page": str(page)})
        current = api_page(f"{endpoint_base}?{query}")
        items.extend(current)
        if len(current) < 100:
            break
    return items


def discover(owner: str, since: str, output: Path) -> dict:
    repos_by_name: dict[str, dict] = {}
    visibility_counts: dict[str, int] = {}
    for visibility in VISIBILITIES:
        repos = repo_list(owner, visibility)
        visibility_counts[visibility] = len(repos)
        for repo in repos:
            repos_by_name[repo["nameWithOwner"]] = repo

    repos = sorted(repos_by_name.values(), key=lambda item: item["nameWithOwner"].lower())
    inventory = {
        "owner": owner,
        "since": since,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "visibility_queries": visibility_counts,
        "repositories": [],
    }
    print(f"发现 {len(repos)} 个仓库，visibility 查询结果：{visibility_counts}")

    for repo_index, repo in enumerate(repos, start=1):
        full_name = repo["nameWithOwner"]
        branches = api_all(f"repos/{full_name}/branches", {})
        branch_records: list[dict] = []
        for branch_index, branch in enumerate(branches, start=1):
            branch_name = branch["name"]
            commit_records = api_all(
                f"repos/{full_name}/commits",
                {"sha": branch_name, "since": since},
            )
            tip_sha = branch.get("commit", {}).get("sha")
            branch_records.append(
                {
                    "name": branch_name,
                    "sha": tip_sha,
                    "commit_url": (
                        f"https://github.com/{full_name}/commit/{tip_sha}"
                        if tip_sha
                        else None
                    ),
                    "recent_commits": [
                        {
                            "sha": commit.get("sha"),
                            "date": commit.get("commit", {})
                            .get("author", {})
                            .get("date"),
                            "message": commit.get("commit", {})
                            .get("message", "")
                            .splitlines()[0],
                            "url": commit.get("html_url"),
                            "author": (
                                commit.get("author", {}).get("login")
                                if commit.get("author")
                                else None
                            ),
                        }
                        for commit in commit_records
                    ],
                }
            )
            print(
                f"[{repo_index}/{len(repos)}] {full_name} "
                f"branch {branch_index}/{len(branches)} {branch_name}: "
                f"{len(commit_records)} recent commit(s)",
                flush=True,
            )
        inventory["repositories"].append({**repo, "branches": branch_records})

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    total_branches = sum(len(repo["branches"]) for repo in inventory["repositories"])
    total_commits = sum(
        len(branch["recent_commits"])
        for repo in inventory["repositories"]
        for branch in repo["branches"]
    )
    print(f"清单已写入：{output}")
    print(f"repositories={len(repos)} branches={total_branches} recent_commits={total_commits}")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description="用本地 gh 盘点 GitHub 仓库和分支")
    parser.add_argument("--owner", default="sunccchengze")
    parser.add_argument("--since", default="2026-08-01T00:00:00Z")
    parser.add_argument("--out", default="minillm/artifacts/account_inventory.json")
    args = parser.parse_args()
    discover(args.owner, args.since, Path(args.out))


if __name__ == "__main__":
    main()

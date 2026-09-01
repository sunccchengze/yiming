from __future__ import annotations

"""Build the privacy-aware JSON consumed by the static Yiming Atlas UI."""

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any


CATEGORY_DEFINITIONS = {
    "learning": {
        "name": "学习系统",
        "eyebrow": "THE LAB OF LEARNING",
        "description": "把知识、考试和长期成长做成可以反复进入的系统。",
        "color": "#f5c96a",
        "accent": "rgba(245, 201, 106, .18)",
        "keywords": {
            "zixue2026", "sectiona-cet6", "ielts20260423scz", "physics-exam-1",
            "physics-exam-2", "gaoshu-6.1", "dawu-6.1", "rzyz-2026-gaokaojiayou",
            "ryh20260510", "liangji", "20260524",
        },
    },
    "engineering": {
        "name": "工程现场",
        "eyebrow": "THE ENGINEERING FRONTIER",
        "description": "把真实世界的复杂问题变成模型、界面和可操作的决策。",
        "color": "#73d9ff",
        "accent": "rgba(115, 217, 255, .16)",
        "keywords": {"turbine-blade-ai-platform", "wind_farm_viz", "fengdian001", "0530-planck"},
    },
    "agent": {
        "name": "AI 与工作流",
        "eyebrow": "THE INTELLIGENCE WORKSHOP",
        "description": "研究如何让模型、技能、记忆和交接真正变成可复用的工作方式。",
        "color": "#c5a4ff",
        "accent": "rgba(197, 164, 255, .16)",
        "keywords": {
            "-skill-", "0824-2026", "sucheng", "wendang11", "123", "06112cosmosagentmode",
            "202606060606ai", "ai", "claude-cpt",
        },
    },
    "personal": {
        "name": "重要的人",
        "eyebrow": "THE HUMAN CONSTELLATION",
        "description": "把情绪、关系、纪念和在乎的人，做成可以被抵达的体验。",
        "color": "#ff9dbb",
        "accent": "rgba(255, 157, 187, .15)",
        "keywords": {
            "-", "-0517", "yimingshengri", "yiming", "yiming-wish", "wode",
            "goooodbye_s-g", "hogwarts-sorting-hat-quiz",
        },
    },
}

MERGE_RE = re.compile(r"^merge (?:pull request|branch)\b", re.I)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def repo_key(full_name: str) -> str:
    return full_name.split("/", 1)[-1].lower()


def classify(repo: dict[str, Any]) -> list[str]:
    key = repo_key(repo["nameWithOwner"])
    categories = [
        category_id
        for category_id, definition in CATEGORY_DEFINITIONS.items()
        if key in definition["keywords"]
    ]
    if categories:
        return categories
    haystack = " ".join(
        [key, str(repo.get("description") or "")]
        + [commit.get("message", "") for branch in repo.get("branches", []) for commit in branch.get("recent_commits", [])[:10]]
    ).lower()
    if any(word in haystack for word in ("ai", "agent", "skill", "model", "claude")):
        return ["agent"]
    if any(word in haystack for word in ("physics", "english", "ielts", "cet", "probability", "study")):
        return ["learning"]
    if any(word in haystack for word in ("wind", "turbine", "blade", "optimization")):
        return ["engineering"]
    return ["personal"]


def display_name(repo: dict[str, Any]) -> str:
    key = repo_key(repo["nameWithOwner"])
    overrides = {
        "-": "英仔爱心社",
        "-skill-": "Skill 宇宙",
        "0824-2026": "八月二十四日实验场",
        "zixue2026": "自学 2026",
        "turbine-blade-ai-platform": "叶轮机械 AI 平台",
        "wind_farm_viz": "风电场偏航优化",
        "yimingshengri": "星际生日任务",
        "goooodbye_s-g": "Goodbye, S.G.",
    }
    return overrides.get(key, repo["nameWithOwner"].split("/", 1)[-1])


def clean_message(message: str) -> str:
    return " ".join(str(message).strip().split())


def load_document_excerpts(corpus_path: str | Path | None) -> dict[str, str]:
    """Return short README/docs excerpts without embedding full source files."""
    if not corpus_path:
        return {}
    excerpts: dict[str, str] = {}
    path = Path(corpus_path)
    if not path.exists():
        raise FileNotFoundError(f"corpus file not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("kind") != "repository_file":
                continue
            file_path = str(record.get("path", ""))
            lower_path = file_path.lower()
            if not (lower_path.startswith("readme") or "/readme" in lower_path or "/docs/" in f"/{lower_path}/"):
                continue
            repo = str(record.get("repo", ""))
            if not repo or repo in excerpts:
                continue
            raw_text = str(record.get("text", ""))
            excerpt = raw_text.split("文件内容：\n", 1)[-1].strip()
            if excerpt:
                excerpts[repo] = excerpt[:1600].rstrip() + ("\n……" if len(excerpt) > 1600 else "")
    return excerpts


def build(inventory: dict[str, Any], document_excerpts: dict[str, str] | None = None) -> dict[str, Any]:
    document_excerpts = document_excerpts or {}
    repositories: list[dict[str, Any]] = []
    all_commits: list[dict[str, Any]] = []
    activity_by_day: Counter[str] = Counter()
    meaningful_by_day: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    branch_count = 0

    for raw_repo in inventory.get("repositories", []):
        full_name = raw_repo["nameWithOwner"]
        categories = classify(raw_repo)
        category_counts.update(categories)
        branches: list[dict[str, Any]] = []
        repo_commits: list[dict[str, Any]] = []
        for raw_branch in raw_repo.get("branches", []):
            branch_count += 1
            branch_commits = []
            for raw_commit in raw_branch.get("recent_commits", []):
                message = clean_message(raw_commit.get("message", ""))
                commit = {
                    "sha": raw_commit.get("sha"),
                    "date": raw_commit.get("date"),
                    "message": message,
                    "url": raw_commit.get("url"),
                    "author": raw_commit.get("author"),
                    "isMerge": bool(MERGE_RE.match(message)),
                    "repo": full_name,
                    "branch": raw_branch["name"],
                }
                branch_commits.append(commit)
                repo_commits.append(commit)
                all_commits.append(commit)
                parsed = parse_date(commit["date"])
                if parsed:
                    day = parsed.date().isoformat()
                    activity_by_day[day] += 1
                    if not commit["isMerge"]:
                        meaningful_by_day[day] += 1
            branch_recent_latest = max(
                branch_commits,
                key=lambda commit: commit.get("date") or "",
                default=None,
            )
            branches.append(
                {
                    "name": raw_branch["name"],
                    "sha": raw_branch.get("sha"),
                    "commitUrl": raw_branch.get("commit_url"),
                    "recentCommitCount": len(branch_commits),
                    "latestCommit": branch_recent_latest,
                    "recentCommits": branch_commits[:50],
                }
            )
        latest = max(repo_commits, key=lambda commit: commit.get("date") or "", default=None)
        meaningful = [commit for commit in repo_commits if not commit["isMerge"]]
        activity_score = len(meaningful) + len(branches) * 0.5
        repositories.append(
            {
                "id": full_name,
                "name": display_name(raw_repo),
                "fullName": full_name,
                "description": raw_repo.get("description") or "还没有写下简介，但项目本身已经留下了轨迹。",
                "sourceExcerpt": document_excerpts.get(full_name),
                "private": bool(raw_repo.get("isPrivate")),
                "defaultBranch": (raw_repo.get("defaultBranchRef") or {}).get("name"),
                "updatedAt": raw_repo.get("updatedAt"),
                "pushedAt": raw_repo.get("pushedAt"),
                "categories": categories,
                "branchCount": len(branches),
                "recentCommitCount": len(repo_commits),
                "meaningfulCommitCount": len(meaningful),
                "activityScore": round(activity_score, 2),
                "latestCommit": latest,
                "branches": branches,
            }
        )

    all_commits.sort(key=lambda commit: commit.get("date") or "", reverse=True)
    meaningful_commits = [commit for commit in all_commits if not commit["isMerge"]]
    active_repositories = [repo for repo in repositories if repo["recentCommitCount"] > 0]
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    timeline = []
    for offset in range(31):
        current = start_date + timedelta(days=offset)
        key = current.isoformat()
        timeline.append(
            {
                "date": key,
                "label": current.strftime("%m/%d"),
                "count": activity_by_day[key],
                "meaningfulCount": meaningful_by_day[key],
            }
        )

    # A few intentionally human-readable interpretations. They are marked as
    # interpretation in the UI rather than being presented as objective facts.
    narrative = [
        {
            "kicker": "01 / THE PATTERN",
            "title": "你不是在维护项目，你在不断发明入口。",
            "body": "学习、工程、AI 和关系，在你的账号里都不是静态文件夹，而是会被做成网页、工具、流程和体验的入口。",
            "categories": ["learning", "engineering", "agent", "personal"],
        },
        {
            "kicker": "02 / THE RECENT MONTH",
            "title": "最近的你，尤其擅长把混乱变成下一步。",
            "body": "提交记录里反复出现修复、审计、交接、技能和研究。你在写代码，也在给未来的自己铺路。",
            "categories": ["agent", "engineering", "learning"],
        },
        {
            "kicker": "03 / THE HUMAN CORE",
            "title": "技术不是你的终点，抵达别人或抵达自己才是。",
            "body": "最硬核的叶片优化和最柔软的生日任务，使用的是同一种冲动：把想法做成别人可以真正感受到的东西。",
            "categories": ["engineering", "personal"],
        },
    ]

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "owner": inventory.get("owner", "sunccchengze"),
        "since": inventory.get("since"),
        "privacy": {
            "description": "数据由本地 GitHub inventory 生成；private 仓库不会离开生成它的电脑。",
            "sourceTypes": ["repository metadata", "branch tips", "recent commit summaries"],
        },
        "stats": {
            "repositories": len(repositories),
            "branches": branch_count,
            "recentCommits": len(all_commits),
            "meaningfulCommits": len(meaningful_commits),
            "activeRepositories": len(active_repositories),
            "categories": len(CATEGORY_DEFINITIONS),
        },
        "categories": [
            {
                "id": category_id,
                "name": definition["name"],
                "eyebrow": definition["eyebrow"],
                "description": definition["description"],
                "color": definition["color"],
                "accent": definition["accent"],
                "repoCount": category_counts[category_id],
            }
            for category_id, definition in CATEGORY_DEFINITIONS.items()
        ],
        "repositories": sorted(repositories, key=lambda repo: repo["activityScore"], reverse=True),
        "timeline": timeline,
        "commits": all_commits[:500],
        "highlights": meaningful_commits[:48],
        "narrative": narrative,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Yiming Atlas data from an account inventory")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--corpus", default=None, help="optional cleaned JSONL for README/docs excerpts")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    inventory_path = Path(args.inventory)
    output_path = Path(args.out)
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    data = build(inventory, load_document_excerpts(args.corpus))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"atlas data written to {output_path}")
    print(json.dumps(data["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()

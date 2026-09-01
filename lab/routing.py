"""Small, inspectable task router for the Yiming Lab adapter.

This is deliberately a policy layer, not a second LLM. The user's
``universal-skill-router`` remains the source of routing guidance; this module
only turns common intents into a reproducible DeepTutor command plan.
"""

from __future__ import annotations

import re
from typing import Any


CAPABILITIES = {
    "chat",
    "deep_solve",
    "deep_question",
    "deep_research",
    "visualize",
    "math_animator",
    "mastery_path",
}


_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "deep_question",
        ("quiz", "测验", "测试我", "考考", "题目", "flashcard", "自测"),
    ),
    (
        "visualize",
        ("visualize", "visualise", "可视化", "画图", "图示", "动画", "diagram"),
    ),
    (
        "mastery_path",
        ("学习路径", "学习计划", "mastery", "怎么学", "学会", "入门路线"),
    ),
    (
        "deep_solve",
        ("solve", "debug", "排错", "为什么", "推导", "证明", "解决", "怎么修"),
    ),
    (
        "deep_research",
        (
            "research",
            "调研",
            "研究",
            "综述",
            "论文",
            "证据",
            "引用",
            "比较",
            "竞品",
            "survey",
        ),
    ),
)

_DECISION_WORDS = (
    "要不要",
    "是否",
    "选择",
    "选哪个",
    "下一步",
    "决策",
    "方案",
    "should",
    "which",
    "trade-off",
    "优先级",
)


class RouteError(ValueError):
    """Raised when a task cannot be represented by the adapter."""


def route_task(task: str) -> dict[str, Any]:
    if not task or not task.strip():
        raise RouteError("task cannot be empty")
    normalized = task.strip().lower()
    capability = "chat"
    matched: list[str] = []
    for candidate, keywords in _PATTERNS:
        hits = [keyword for keyword in keywords if keyword in normalized]
        if hits:
            capability = candidate
            matched.extend(hits)
            break

    decision = any(word in normalized for word in _DECISION_WORDS)
    if decision and capability == "chat":
        # A decision question needs evidence and counterexamples even when it
        # does not literally contain "research" or "compare".
        capability = "deep_research"
        matched.append("decision")
    research = capability == "deep_research" or decision
    tools: list[str] = []
    configs: list[str] = []
    if capability == "deep_solve":
        tools = ["reason", "rag"]
    elif capability == "deep_research":
        tools = ["paper_search", "web_search", "rag"]
        configs = ["mode=report", "depth=standard"]
    elif capability == "deep_question":
        tools = ["rag"]
        configs = ["num_questions=5"]
    elif capability == "mastery_path":
        tools = ["rag"]
    elif capability == "visualize":
        tools = ["rag"]

    skills = ["universal-skill-router", "DeepTutor"]
    if decision:
        skills.append("sun-chengze-perspective")
    if research:
        skills.append("research-workflow-kit")
    # Every council output is still subject to an explicit quality review. This
    # is a reportable selection, not an attempt to execute every matching skill.
    skills.append("QUALITY_GATES")

    return {
        "task": task.strip(),
        "capability": capability,
        "matched_keywords": matched,
        "decision_task": decision,
        "evidence_required": research,
        "selected_skills": skills,
        "deeptutor_tools": tools,
        "deeptutor_config": configs,
        "openwiki_context": True,
        "independence_rule": (
            "Council seats receive only the task, shared factual context, and their own seat brief; "
            "peer answers are withheld until the blind review stage."
        ),
    }


def build_deeptutor_argv(
    route: dict[str, Any],
    kb: str | None = None,
    output_format: str = "json",
) -> list[str]:
    capability = str(route["capability"])
    if capability not in CAPABILITIES:
        raise RouteError(f"unsupported DeepTutor capability: {capability}")
    argv = ["deeptutor", "run", capability, str(route["task"])]
    for tool in route.get("deeptutor_tools", []):
        argv.extend(["--tool", str(tool)])
    if kb:
        argv.extend(["--kb", kb])
    argv.extend(["--language", "zh", "--format", output_format])
    for config in route.get("deeptutor_config", []):
        argv.extend(["--config", config])
    return argv

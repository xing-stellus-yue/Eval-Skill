"""Prompt constants actually used by the cleaned EvalSkill entry points."""

from __future__ import annotations

from types import ModuleType


PROMPT_MODULES: dict[str, str] = {
    "best_of_n": ".best_of_n",
    "evaluation": ".evaluation",
    "evaluation_msg": ".evaluation_msg",
    "explanation": ".explanation",
    "healthbench": ".healthbench",
    "skill": ".skill",
    "skill_msg": ".skill_msg",
}


USED_PROMPT_CONSTANTS: dict[str, tuple[str, ...]] = {
    "best_of_n": ("FINAL_COMPARISON_PROMPT",),
    "evaluation": (
        # Vanilla method inference.
        "RUBRIC_GENERATION_PROMPT",
        "VANILLA_LISTWISE_JUDGE_PROMPT",
        "VANILLA_PAIRWISE_JUDGE_PROMPT",
        # Rubric-based method inference.
        "RUBRIC_LISTWISE_JUDGE_PROMPT",
        "RUBRIC_PAIRWISE_JUDGE_PROMPT",
        # Eval-skill public entry points.
        "SKILL_LISTWISE_JUDGE_PROMPT",
        "SKILL_PAIRWISE_JUDGE_PROMPT",
    ),
    "evaluation_msg": (
        "VANILLA_LISTWISE_JUDGE_PROMPT",
        "VANILLA_PAIRWISE_JUDGE_PROMPT",
        "RUBRIC_LISTWISE_JUDGE_PROMPT",
        "RUBRIC_PAIRWISE_JUDGE_PROMPT",
        "SKILL_LISTWISE_JUDGE_PROMPT",
        "SKILL_PAIRWISE_JUDGE_PROMPT",
    ),
    "explanation": (
        "EXPLANATION_EXTRACTION_PROMPT",
        "HEALTHBENCH_EXPLANATION_EXTRACTION_PROMPT",
    ),
    "healthbench": ("HEALTHBENCH_GRADER_PROMPT",),
    "skill": (
        "WORKFLOW_ONLY_SKILL_TEMPLATE",
        "FULL_SKILL_TEMPLATE",
        "SKILL_INITIALIZATION_PROMPT",
        "SKILL_IMPROVE_PROMPT_STEP1A",
        "SKILL_IMPROVE_PROMPT_STEP1B",
        "SKILL_MERGE_PROMPT",
        "PATCH_INITIALIZATION_PROMPT",
        "PATCH_MERGE_PROMPT",
        "PATCH_APPLICATION_PROMPT",
        "SKILL_CLUSTERING_PROMPT",
        "TOP_SKILL_MERGE_PROMPT",
    ),
    "skill_msg": (
        "WORKFLOW_ONLY_SKILL_TEMPLATE",
        "FULL_SKILL_TEMPLATE",
        "SKILL_INITIALIZATION_PROMPT",
        "SKILL_IMPROVE_PROMPT_STEP1A",
        "SKILL_IMPROVE_PROMPT_STEP1B",
        "SKILL_MERGE_PROMPT",
        "PATCH_INITIALIZATION_PROMPT",
        "PATCH_MERGE_PROMPT",
        "PATCH_APPLICATION_PROMPT",
        "SKILL_CLUSTERING_PROMPT",
        "TOP_SKILL_MERGE_PROMPT",
    ),
}


def load_prompt_module(name: str) -> ModuleType:
    try:
        module_name = PROMPT_MODULES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(PROMPT_MODULES))
        raise ValueError(f"Unknown prompt module {name!r}. Choices: {choices}") from exc
    package_name = __package__ or "eval_skill.prompts"
    if module_name.startswith("."):
        module_name = package_name + module_name
    return __import__(module_name, fromlist=["*"])

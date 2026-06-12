"""Small shared helpers for the public eval-skill runtime."""

from __future__ import annotations

from dataclasses import dataclass
import glob
import hashlib
import json
import os
import random
from typing import Any


@dataclass
class LLMResponse:
    content: str
    reasoning_content: str | None = None


def is_set(var: str, default: bool = False) -> bool:
    value = os.getenv(var, "").lower()
    return value == "true" if value in {"true", "false"} else default


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: _normalize(value) for key, value in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_normalize(value) for value in obj]
    return obj


def get_rng(*args: Any) -> random.Random:
    key = json.dumps(_normalize(args), sort_keys=True, ensure_ascii=False)
    seed = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return random.Random(seed)


def load_best_skill(
    benchmark_name: str,
    subset_name: str,
    method: str = "adaptive",
    result_base: str = "",
) -> dict[str, Any]:
    """Load the skill selected by the public skill pipeline."""

    if method not in {"adaptive", "workflow_only", "full"}:
        raise ValueError(f"Unsupported method: {method}")

    output_dir_subset = os.path.join(result_base, benchmark_name, subset_name)

    full_score = 0.0
    full_skill = ""
    full_source = ""
    if method in {"adaptive", "full"}:
        pattern = os.path.join(
            output_dir_subset, "test_best_full_skill_*", "final_full_result.json"
        )
        full_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if not full_files and method == "full":
            raise FileNotFoundError(f"No full result file found: {pattern}")
        if len(full_files) > 1:
            raise AssertionError(f"Multiple full result files found: {full_files}")
        if full_files:
            full_source = full_files[0]
            with open(full_source, "r", encoding="utf-8") as f:
                full_result = json.load(f)
            full_score = full_result["summary"]["evol_acc"]
            full_skill = full_result["summary"]["final_skill"]

    workflow_score = 0.0
    workflow_skill = ""
    workflow_source = ""
    if method in {"adaptive", "workflow_only"}:
        dir_pattern = os.path.join(output_dir_subset, "test_best_workflow_only_skill_b*")
        workflow_dirs = sorted(glob.glob(dir_pattern), key=os.path.getmtime, reverse=True)
        if not workflow_dirs and method == "workflow_only":
            raise FileNotFoundError(
                f"No workflow-only result directory found: {dir_pattern}"
            )
        if len(workflow_dirs) > 1:
            raise AssertionError(
                f"Multiple workflow-only result directories found: {workflow_dirs}"
            )
        if workflow_dirs:
            branch_id = workflow_dirs[0].split("test_best_workflow_only_skill_b")[-1]
            workflow_source = os.path.join(
                output_dir_subset, "step1a_workflow_gen", "top_k_sel_skills.json"
            )
            with open(workflow_source, "r", encoding="utf-8") as f:
                candidates = json.load(f)
            selected = [
                item for item in candidates if str(item["branch_id"]) == str(branch_id)
            ][0]
            workflow_score = selected["evo_acc"]
            workflow_skill = selected["skill"]

    if method == "workflow_only":
        selected = "workflow_only"
        score = workflow_score
        skill = workflow_skill
        source = workflow_source
    elif method == "full":
        selected = "full"
        score = full_score
        skill = full_skill
        source = full_source
    elif workflow_score >= full_score:
        selected = "workflow_only"
        score = workflow_score
        skill = workflow_skill
        source = workflow_source
    else:
        selected = "full"
        score = full_score
        skill = full_skill
        source = full_source

    if not skill or score <= 0:
        raise ValueError(
            f"No valid skill found for benchmark={benchmark_name}, "
            f"subset={subset_name}, method={method}."
        )

    return {
        "benchmark": benchmark_name,
        "subset": subset_name,
        "method": method,
        "result_base": result_base,
        "selected": selected,
        "score": score,
        "skill": skill,
        "source": source,
    }

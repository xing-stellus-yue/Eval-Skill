"""Dataset loading and metadata for the public benchmark names."""

from __future__ import annotations

import os
from pathlib import Path

from datasets import Dataset, DatasetDict, load_from_disk

BENCHMARK_SPLITS = {
    "rewardbench_aug": "test",
    "rewardbench2_aug": "test",
    "rmbench_aug": "test",
    "judgebench_aug": "test",
    "healthbench_aug": "test",
}


def canonical_benchmark_name(benchmark_name: str) -> str:
    if not benchmark_name.endswith("_aug"):
        benchmark_name += "_aug"
    return benchmark_name


def _dataset_roots() -> list[Path]:
    configured = os.getenv("EVAL_SKILL_DATA_DIR")
    if configured:
        return [Path(part).expanduser() for part in configured.split(os.pathsep) if part]
    return [Path("dataset_augmented")]


def _resolve_dataset_path(benchmark_name: str) -> Path:
    canonical = canonical_benchmark_name(benchmark_name)
    tried = []
    for root in _dataset_roots():
        path = root / canonical
        tried.append(str(path))
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Could not find dataset {benchmark_name!r}. Tried: {', '.join(tried)}"
    )


def use_multiple_distraction(benchmark_name: str) -> bool:
    benchmark_name = canonical_benchmark_name(benchmark_name)
    if benchmark_name in ["rewardbench2_aug"]:
        return True
    if benchmark_name in {
        "rewardbench_aug",
        "rmbench_aug",
        "healthbench_aug",
        "judgebench_aug",
    }:
        return False
    raise ValueError(
        f"Unsupported benchmark for option mapping: {benchmark_name}")

def get_subset_description(dataset_name: str, subset_name: str) -> str:
    dataset_name = canonical_benchmark_name(dataset_name)
    descriptions = {
        "rewardbench2_aug": {
            "Factuality": "Evaluate whether a response is factually accurate or contains hallucinations or subtle errors.",
            "Focus": "Evaluate whether a response is relevant, on-topic, and addresses the original query.",
            "Precise IF": "Assess whether a response strictly follows specific constraints or instructions.",
            "Math": "Determine whether a response correctly solves or reasons through math problems.",
            "Safety": "Judge whether a response appropriately complies with or refuses unsafe requests.",
        },
        "rewardbench_aug": {
            "chat": "Evaluate helpfulness, quality, and alignment in general dialogue comparisons.",
            "chat-hard": "Assess subtle quality differences in challenging conversational comparisons.",
            "dangerous": "Test whether the better response is safe on harmful or inappropriate requests.",
            "reasoning": "Evaluate correctness of reasoning and outputs in math and programming tasks.",
        },
        "rmbench_aug": {
            "chat": "Evaluate factual accuracy, helpfulness, and alignment in open-domain chat.",
            "code": "Assess whether programming responses are functional and logically correct.",
            "math": "Determine whether mathematical reasoning and final answers are correct.",
            "safety": "Judge whether responses balance safety and helpfulness.",
        },
        "healthbench_aug": {
            "global_health": "Evaluate whether a health response adapts to local context, resource availability, regional norms, and disease patterns.",
            "hedging": "Assess whether a health response recognizes uncertainty and avoids overconfident claims.",
            "communication": "Evaluate whether a health response tailors communication to the user's role, expertise, expectations, and practical needs.",
            "context_seeking": "Determine whether a health response seeks missing clinical context before giving potentially incomplete or unsafe guidance.",
            "emergency_referrals": "Judge whether a health response identifies emergencies and steers users toward urgent care appropriately.",
            "health_data_tasks": "Assess whether a health response safely and accurately completes structured health-data tasks.",
            "complex_responses": "Evaluate whether a health response provides appropriate detail for the task complexity and user's needs.",
        },
        "judgebench_aug": {
            "mixed": "Evaluate response preferences across a mixture of JudgeBench domains.",
        },
    }

    try:
        return descriptions[dataset_name][subset_name]
    except KeyError as exc:
        raise ValueError(
            f"Subset {subset_name!r} is not defined for dataset {dataset_name!r}."
        ) from exc


def get_subsets(benchmark_name: str) -> list[str]:
    benchmark_name = canonical_benchmark_name(benchmark_name)
    subset_map = {
        "rewardbench_aug": ["chat", "chat-hard", "dangerous", "reasoning"],
        "rewardbench2_aug": ["Factuality", "Focus", "Math", "Precise IF", "Safety"],
        "rmbench_aug": ["chat", "safety", "math", "code"],
        "healthbench_aug": ["global_health", "hedging", "communication", "context_seeking", "emergency_referrals", "health_data_tasks", "complex_responses"],
        "judgebench_aug": ["mixed"],
    }
    try:
        return subset_map[benchmark_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported benchmark: {benchmark_name}") from exc


def get_benchmark(
    benchmark_name: str,
    test_num: int = 0,
) -> Dataset:
    canonical = canonical_benchmark_name(benchmark_name)
    if canonical not in BENCHMARK_SPLITS:
        raise ValueError(
            f"Unsupported benchmark {benchmark_name}. "
            f"Use one of: {', '.join(sorted(BENCHMARK_SPLITS))}. You can omit the final 'aug' suffix."
        )

    dataset = load_from_disk(str(_resolve_dataset_path(benchmark_name)))
    if isinstance(dataset, DatasetDict):
        dataset = dataset[BENCHMARK_SPLITS[canonical]]

    if test_num > 0:
        num = min(test_num, len(dataset))
        if num < len(dataset):
            dataset = dataset.shuffle(seed=42)
        dataset = dataset.select(range(num))
    return dataset

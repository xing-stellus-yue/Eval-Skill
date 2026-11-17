"""Evaluate a saved skill on held-out benchmark examples.

Run from the repository root: python -m examples.evaluate_demo_skill --help
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.eval_skill.config import load_env_files, repo_root, require_env
from src.eval_skill.data import get_benchmark, use_multiple_distraction
from src.eval_skill.eval_process import process_item
from src.eval_skill.managers.eval_manager import EvalManager


DEMO_SUBSETS = {
    "rewardbench2": ["Factuality", "Focus", "Math", "Precise IF", "Safety"],
    "rewardbench": ["chat", "chat-hard", "dangerous", "reasoning"],
    "judgebench": ["mixed"],
    "rmbench": ["chat", "safety", "math", "code"],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=DEMO_SUBSETS, default="rewardbench2")
    parser.add_argument("--subset", help="Domain to evaluate; defaults to the benchmark's first domain")
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--result-base", type=Path, default=Path("results/demo_skills"))
    parser.add_argument("--env-file", action="append", default=["eval_skill.env"])
    args = parser.parse_args(argv)
    if args.samples < 1:
        parser.error("--samples must be at least 1")
    subsets = DEMO_SUBSETS[args.benchmark]
    if args.subset is None:
        args.subset = subsets[0]
    if args.subset not in subsets:
        parser.error(f"--subset for {args.benchmark} must be one of: {', '.join(subsets)}")
    benchmark = args.benchmark + "_aug"

    load_env_files(args.env_file)
    require_env(["JUDGE_MODEL_NAME", "JUDGE_API_BASE", "JUDGE_API_KEY"])
    skill_path = repo_root() / "src/eval_skill/demo_skills" / args.benchmark / f"{args.subset.replace(' ', '_')}.md"
    skill = skill_path.read_text(encoding="utf-8")
    dataset = get_benchmark(benchmark)
    dataset = dataset.filter(
        lambda row: row["subset"] == args.subset and row["use"] == "test",
        keep_in_memory=True,
    )
    if not len(dataset):
        raise ValueError(f"No held-out examples for {args.subset}")
    dataset = dataset.shuffle(seed=args.seed, keep_in_memory=True).select(range(min(args.samples, len(dataset))))
    manager = EvalManager(dataset_name=benchmark)
    output_dir = args.result_base / args.benchmark / args.subset
    results = [
        process_item(
            benchmark, dict(row), 0, use_multiple_distraction(benchmark), output_dir / "rollouts",
            manager, "eval_skill", skill_content=skill,
        )
        for row in dataset
    ]
    summary = {
        "benchmark": benchmark,
        "subset": args.subset,
        "skill_file": str(skill_path.relative_to(repo_root())),
        "total_cases": len(results),
        "correct": sum(row["status"] == "Correct" for row in results),
        "incorrect": sum(row["status"] == "Incorrect" for row in results),
        "unexpected": sum(row["status"] not in {"Correct", "Incorrect"} for row in results),
        "case_ids": [row["id"] for row in results],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 1 if summary["unexpected"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

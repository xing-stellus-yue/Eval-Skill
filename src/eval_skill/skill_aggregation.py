"""Aggregate adaptive skill pipeline results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


MODE_FILES = {
    "workflow_only": "workflow_only_analysis_result.json",
    "full": "full_analysis_result.json",
}


def selection_sort_key(item: dict[str, Any]) -> str:
    if "branch_id" in item:
        return str(item["branch_id"])
    if "branch_id" in item:
        return str(item["branch_id"])
    return ""


def selected_branch(path: Path) -> dict[str, Any] | None:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    candidates = [item for item in data if "test_acc" in item]
    if not candidates:
        return None

    chosen = sorted(candidates, key=selection_sort_key)[0]
    return {
        "evo_acc": chosen.get("evo_acc"),
        "test_acc": chosen.get("test_acc"),
        "branch_id": chosen.get("branch_id"),
        "branch_id": chosen.get("branch_id"),
    }


def clean_option(option: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in option.items() if value is not None}


def percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_result(result: dict[str, Any]) -> dict[str, Any]:
    display_order = {"workflow_only": 0, "full": 1}
    formatted = {
        **result,
        "options": [
            {
                **option,
                "evo_acc": percent(option["evo_acc"]),
                "test_acc": percent(option["test_acc"]),
            }
            for option in sorted(
                result["options"],
                key=lambda item: display_order.get(item["source"], 99),
            )
        ],
    }
    if "best_test_acc" in formatted:
        formatted["best_test_acc"] = percent(formatted["best_test_acc"])
    return formatted


def build_subset_result(subset_dir: Path) -> dict[str, Any]:
    options = []
    missing_modes = []

    for mode, filename in MODE_FILES.items():
        path = subset_dir / filename
        if not path.exists():
            missing_modes.append(mode)
            continue

        selected = selected_branch(path)
        if selected is None or selected["evo_acc"] is None or selected["test_acc"] is None:
            continue

        options.append(
            clean_option(
                {
                    "source": mode,
                    "evo_acc": selected["evo_acc"],
                    "test_acc": selected["test_acc"],
                    "priority": 2 if mode == "workflow_only" else 1,
                    "branch_id": selected["branch_id"],
                    "branch_id": selected["branch_id"],
                }
            )
        )

    result = {
        "missing_modes": missing_modes,
        "options": sorted(
            options,
            key=lambda item: (item["evo_acc"], item["priority"]),
            reverse=True,
        ),
    }

    if result["options"]:
        winner = result["options"][0]
        result = {
            "best_test_acc": winner["test_acc"],
            "winner_source": winner["source"],
            **result,
        }

    return format_result(result)


def option_test_acc(result: dict[str, Any], source: str) -> str:
    for option in result["options"]:
        if option["source"] == source:
            return option["test_acc"]
    return ""


def write_test_acc_table(path: Path, subsets: dict[str, dict[str, Any]]) -> None:
    subset_names = sorted(subsets)
    rows = [
        ["method", *subset_names],
        [
            "workflow_only",
            *[
                option_test_acc(subsets[subset], "workflow_only")
                for subset in subset_names
            ],
        ],
        [
            "full",
            *[option_test_acc(subsets[subset], "full") for subset in subset_names],
        ],
        [
            "selected",
            *[subsets[subset].get("best_test_acc", "") for subset in subset_names],
        ],
    ]

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write("\t".join(row))
            f.write("\n")


def aggregate_skill_results(
    benchmark_dir: str | Path,
    subset_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    benchmark_path = Path(benchmark_dir)
    subset_filter = set(subset_names or [])
    subsets = {}
    written_subset_files = 0

    for subset_dir in sorted(benchmark_path.iterdir()):
        if not subset_dir.is_dir():
            continue
        if subset_filter and subset_dir.name not in subset_filter:
            continue
        has_any_mode_file = any(
            (subset_dir / filename).exists() for filename in MODE_FILES.values()
        )
        if not has_any_mode_file:
            continue

        result = build_subset_result(subset_dir)
        if not result["options"] and not result["missing_modes"]:
            continue

        out_file = subset_dir / "adaptive_selection.json"
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
            f.write("\n")
        written_subset_files += 1
        subsets[subset_dir.name] = result

    aggregate_file = None
    table_file = None
    if subsets:
        aggregate_file = benchmark_path / "aggregated_adaptive_selection.json"
        with aggregate_file.open("w", encoding="utf-8") as f:
            json.dump(dict(sorted(subsets.items())), f, indent=4, ensure_ascii=False)
            f.write("\n")

        table_file = benchmark_path / "adaptive_test_acc.tsv"
        write_test_acc_table(table_file, subsets)

    return {
        "benchmark_dir": str(benchmark_path),
        "subset_count": len(subsets),
        "written_subset_files": written_subset_files,
        "aggregate_file": None if aggregate_file is None else str(aggregate_file),
        "table_file": None if table_file is None else str(table_file),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-dir",
        required=True,
        help="Directory containing subset result folders, e.g. results/skill_runs/rewardbench_aug_100.",
    )
    parser.add_argument("--subset", nargs="+", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = aggregate_skill_results(args.benchmark_dir, subset_names=args.subset)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

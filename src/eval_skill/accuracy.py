"""Split/subset accuracy summaries for eval-skill outputs."""

from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
from typing import Any

from .data import get_benchmark


def _empty_counts() -> dict[str, int]:
    return {"total": 0, "correct": 0, "incorrect": 0, "unexpected": 0}


def _add_status(counts: dict[str, int], status: str | None) -> None:
    counts["total"] += 1
    if status == "Correct":
        counts["correct"] += 1
    elif status == "Incorrect":
        counts["incorrect"] += 1
    else:
        counts["unexpected"] += 1


def _merge_counts(items: list[dict[str, int]]) -> dict[str, int]:
    merged = _empty_counts()
    for item in items:
        for key in merged:
            merged[key] += item.get(key, 0)
    return merged


def _metrics(counts: dict[str, int]) -> dict[str, Any]:
    correct = counts["correct"]
    incorrect = counts["incorrect"]
    total = counts["total"]
    valid = correct + incorrect
    return {
        **counts,
        "valid": valid,
        "accuracy": correct / total if total else None,
        "accuracy_cal": correct / valid if valid else None,
    }


def _avg(values: list[float | None]) -> float | None:
    actual = [value for value in values if value is not None]
    return sum(actual) / len(actual) if actual else None


def _split_sort_key(split: str) -> tuple[int, str]:
    order = {"train": 0, "test": 1, "train_unused": 2, "test_unused": 3}
    return (order.get(split, 99), split)


def _rollout_files(benchmark_dir: Path) -> tuple[Path, list[Path]]:
    rollout_dir = benchmark_dir / "rollouts"
    rollout_files = sorted(rollout_dir.glob("*_trial_*.json"))
    if rollout_files:
        return rollout_dir, rollout_files
    return benchmark_dir, sorted(benchmark_dir.glob("*_trial_*.json"))


def _dataset_split_metadata(benchmark_name: str) -> dict[str, dict[str, str]]:
    dataset = get_benchmark(benchmark_name)
    metadata: dict[str, dict[str, str]] = {}

    if "use" not in dataset.column_names:
        raise ValueError(
            f"{benchmark_name} does not include a 'use' column. Accuracy summaries "
            "need materialized train/test assignments in the augmented dataset."
        )
    for item in dataset:
        split = item.get("use") or "unknown"
        metadata[str(item["id"])] = {
            "split": split,
            "subset": item.get("subset") or "default",
        }
    return metadata


def _load_rollouts(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as f:
                rows.append(json.load(f))
        except Exception as exc:
            rows.append(
                {
                    "id": path.stem,
                    "subset": "read_error",
                    "status": f"read_error: {exc}",
                }
            )
    return rows


def _summarize_nested(
    raw: dict[str, dict[str, dict[str, int]]]
) -> dict[str, dict[str, Any]]:
    summary = {}
    for split in sorted(raw, key=_split_sort_key):
        subset_metrics = {
            subset: _metrics(counts)
            for subset, counts in sorted(raw[split].items())
        }
        overall = _metrics(_merge_counts(list(raw[split].values())))
        summary[split] = {
            "subsets": subset_metrics,
            "overall": overall,
            "unweighted_average": {
                "accuracy": _avg(
                    [item["accuracy"] for item in subset_metrics.values()]
                ),
                "accuracy_cal": _avg(
                    [item["accuracy_cal"] for item in subset_metrics.values()]
                ),
                "subset_count": len(subset_metrics),
            },
        }
    return summary


def build_split_accuracy_summary(
    benchmark_name: str,
    benchmark_dir: str | Path,
) -> dict[str, Any]:
    benchmark_path = Path(benchmark_dir)
    rollout_dir, rollout_paths = _rollout_files(benchmark_path)
    rows = _load_rollouts(rollout_paths)
    metadata = _dataset_split_metadata(benchmark_name)

    raw: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(_empty_counts)
    )
    for row in rows:
        item_id = str(row.get("id"))
        meta = metadata.get(item_id, {})
        split = row.get("split") or meta.get("split") or "unknown"
        subset = row.get("subset") or meta.get("subset") or "default"
        _add_status(raw[split][subset], row.get("status"))

    by_split = _summarize_nested(raw)
    combined_raw: dict[str, dict[str, int]] = defaultdict(_empty_counts)
    for split_map in raw.values():
        for subset, counts in split_map.items():
            for key in combined_raw[subset]:
                combined_raw[subset][key] += counts[key]

    combined_subset_metrics = {
        subset: _metrics(counts) for subset, counts in sorted(combined_raw.items())
    }
    combined = {
        "subsets": combined_subset_metrics,
        "overall": _metrics(_merge_counts(list(combined_raw.values()))),
        "unweighted_average": {
            "accuracy": _avg(
                [item["accuracy"] for item in combined_subset_metrics.values()]
            ),
            "accuracy_cal": _avg(
                [item["accuracy_cal"] for item in combined_subset_metrics.values()]
            ),
            "subset_count": len(combined_subset_metrics),
        },
    }

    return {
        "benchmark": benchmark_name,
        "rollout_count": len(rollout_paths),
        "by_split": by_split,
        "combined": combined,
    }


def _fmt_pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _format_metric_line(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"{name:<28} "
        f"acc={_fmt_pct(metrics['accuracy']):>8} "
        f"acc_cal={_fmt_pct(metrics['accuracy_cal']):>8} "
        f"correct={metrics['correct']:>6} "
        f"incorrect={metrics['incorrect']:>6} "
        f"unexpected={metrics['unexpected']:>4} "
        f"total={metrics['total']:>6}"
    )


def format_split_accuracy_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Split accuracy for {summary['benchmark']}",
        f"Rollout files: {summary['rollout_count']}",
        "",
    ]

    for split, split_summary in summary["by_split"].items():
        lines.append(f"==== {split.upper()} ====")
        for subset, metrics in split_summary["subsets"].items():
            lines.append(_format_metric_line(f"[{subset}]", metrics))
        avg = split_summary["unweighted_average"]
        lines.append(
            f"{'[Unweighted Avg]':<28} "
            f"acc={_fmt_pct(avg['accuracy']):>8} "
            f"acc_cal={_fmt_pct(avg['accuracy_cal']):>8} "
            f"subsets={avg['subset_count']:>4}"
        )
        lines.append(_format_metric_line(f"[Overall {split}]", split_summary["overall"]))
        lines.append("")

    lines.append("==== COMBINED ====")
    for subset, metrics in summary["combined"]["subsets"].items():
        lines.append(_format_metric_line(f"[Combined - {subset}]", metrics))
    avg = summary["combined"]["unweighted_average"]
    lines.append(
        f"{'[Combined Unweighted Avg]':<28} "
        f"acc={_fmt_pct(avg['accuracy']):>8} "
        f"acc_cal={_fmt_pct(avg['accuracy_cal']):>8} "
        f"subsets={avg['subset_count']:>4}"
    )
    lines.append(_format_metric_line("[Combined Overall]", summary["combined"]["overall"]))
    return "\n".join(lines) + "\n"


def write_split_accuracy_result(
    benchmark_name: str,
    result_base: str
) -> Path:
    setting_name = os.environ["SETTING_NAME"]
    benchmark_dir = Path(result_base) / setting_name / benchmark_name
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    summary = build_split_accuracy_summary(benchmark_name, benchmark_dir)
    json_path = benchmark_dir / "summary_by_split.json"
    txt_path = benchmark_dir / "summary_by_split.txt"
    json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    txt_path.write_text(format_split_accuracy_summary(summary), encoding="utf-8")
    print(f"Split accuracy summary written to {txt_path}")
    return txt_path

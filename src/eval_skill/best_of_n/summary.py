"""Summaries for Best-of-N rollouts."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


COMPARE_RE = re.compile(r"compare_(\d+)_trial_(\d+)\.json$")
DISPLAY_ORDER = ("skill", "vanilla", "tie", "same_idx")


def pct(num: int, den: int) -> str:
    if den == 0:
        return "N/A"
    return f"{num / den * 100:.2f}%"


def ordered_count_items(counter: Counter):
    seen = set()
    for key in DISPLAY_ORDER:
        if counter.get(key, 0) > 0:
            seen.add(key)
            yield key, counter[key]
    for key, count in counter.items():
        if key not in seen:
            yield key, count


def summarize_directory(directory: Path) -> str:
    files = sorted(
        path
        for path in directory.rglob("compare_*_trial_*.json")
        if COMPARE_RE.match(path.name)
    )

    counts = Counter()
    separated_counts = Counter()
    excluding_same_idx_counts = Counter()
    bad_json_cnt = 0
    missing_cnt = 0
    same_idx_cnt = 0
    parsed_cnt = 0

    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            bad_json_cnt += 1
            continue

        parsed_cnt += 1
        winner = data.get("final_compare", {}).get("winner_runner")
        if winner is None:
            missing_cnt += 1
            winner = "None"
        counts[str(winner)] += 1

        skill_idx = data.get("skill_runner", {}).get("best_idx")
        vanilla_idx = data.get("vanilla_runner", {}).get("best_idx")
        same_idx = skill_idx is not None and skill_idx == vanilla_idx
        if same_idx:
            same_idx_cnt += 1
            separated_counts["same_idx"] += 1
        else:
            separated_counts[str(winner)] += 1
            excluding_same_idx_counts[str(winner)] += 1

    total_cnt = len(files)
    excluding_same_idx_cnt = parsed_cnt - same_idx_cnt
    lines = [
        f"directory: {directory}",
        f"total cnt: {total_cnt}",
        f"parsed cnt: {parsed_cnt}",
        f"bad json cnt: {bad_json_cnt}",
        f"missing/None cnt: {missing_cnt}",
        f"same idx cnt: {same_idx_cnt} ({pct(same_idx_cnt, parsed_cnt)})",
        "raw winner_runner counts:",
    ]
    for key, count in ordered_count_items(counts):
        lines.append(f"  {key}: {count} ({pct(count, parsed_cnt)})")

    lines.append("winner_runner counts with same_idx separated:")
    for key, count in ordered_count_items(separated_counts):
        lines.append(f"  {key}: {count} ({pct(count, parsed_cnt)})")

    lines.append("winner_runner counts excluding same_idx:")
    for key, count in ordered_count_items(excluding_same_idx_counts):
        lines.append(f"  {key}: {count} ({pct(count, excluding_same_idx_cnt)})")
    lines.append(f"  denominator: {excluding_same_idx_cnt}")
    return "\n".join(lines) + "\n"


def write_summary_file(directory: Path, output_file: Path) -> str:
    summary_text = summarize_directory(directory)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(summary_text, encoding="utf-8")
    return summary_text

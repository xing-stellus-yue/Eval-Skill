"""Download benchmarks, construct HealthBench pairs, and add explanations."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from datasets import Dataset, DatasetDict, load_dataset

from .config import (
    load_env_files,
    require_env,
)


HF_SOURCES: dict[str, str] = {
    "rewardbench": "allenai/reward-bench",
    "rewardbench2": "allenai/reward-bench-2",
    "rmbench": "THU-KEG/RM-Bench",
    "healthbench": "openai/healthbench",
    "judgebench": "ScalerLab/JudgeBench",
}

THEME_PREFIX = "theme:"
HEALTHBENCH_DATA_FILE = "2025-05-07-06-14-12_oss_eval.jsonl"
HEALTHBENCH_REQUIRED_COLUMNS = (
    "example_tags",
    "prompt",
    "rubrics",
)
HEALTHBENCH_PAIR_COLUMNS = (
    "response_a",
    "response_b",
    "score_a",
    "score_b",
    "score_diff",
    "orig_score",
    "metadata",
)
REWARDBENCH_SUBSET_MAP = {
    "alpacaeval-easy": "chat",
    "alpacaeval-length": "chat",
    "alpacaeval-hard": "chat",
    "mt-bench-easy": "chat",
    "mt-bench-med": "chat",
    "mt-bench-medium": "chat",
    "mt-bench-hard": "chat-hard",
    "llmbar-natural": "chat-hard",
    "llmbar-adver-neighbor": "chat-hard",
    "llmbar-adver-GPTInst": "chat-hard",
    "llmbar-adver-GPTOut": "chat-hard",
    "llmbar-adver-manual": "chat-hard",
    "refusals-dangerous": "dangerous",
    "refusals-offensive": "dangerous",
    "xstest-should-refuse": "dangerous",
    "xstest-should-respond": "dangerous",
    "donotanswer": "dangerous",
    "do not answer": "dangerous",
    "math-prm": "reasoning",
    "hep-cpp": "reasoning",
    "hep-go": "reasoning",
    "hep-java": "reasoning",
    "hep-js": "reasoning",
    "hep-python": "reasoning",
    "hep-rust": "reasoning",
}


def _safe_dataset_id(prefix: str, idx: int) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_")
    return f"{normalized}_{idx + 1:06d}"


def _first_split(dataset_or_dict: Any, preferred: tuple[str, ...]) -> Dataset:
    if not hasattr(dataset_or_dict, "keys"):
        return dataset_or_dict
    for split in preferred:
        if split in dataset_or_dict:
            return dataset_or_dict[split]
    return dataset_or_dict[list(dataset_or_dict.keys())[0]]


def _tag_value(tags: list[str], prefix: str) -> str:
    values = [
        tag.split(":", 1)[1]
        for tag in tags
        if isinstance(tag, str) and tag.startswith(prefix)
    ]
    if len(values) != 1:
        raise ValueError(f"Expected exactly one {prefix!r} tag, got {values}")
    return values[0]


def _require_columns(dataset: Dataset, required: tuple[str, ...], name: str) -> None:
    missing = [column for column in required if column not in dataset.column_names]
    if missing:
        raise ValueError(
            f"{name} is missing required column(s): {', '.join(missing)}. "
            f"Available columns: {', '.join(dataset.column_names)}"
        )


def _assign_healthbench_splits(rows: list[dict[str, Any]], seed: int) -> None:
    rng = random.Random(seed)
    theme_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        theme_to_indices[row["subset"]].append(idx)

    for _, indices in sorted(theme_to_indices.items()):
        sample_size = min(100, len(indices))
        sampled = set(rng.sample(indices, sample_size))
        for idx in indices:
            rows[idx]["use"] = "train" if idx in sampled else "test"


def _with_new_ids(rows: list[dict[str, Any]], dst_name: str, id_prefix: str) -> list[dict[str, Any]]:
    final_rows = []
    prefix = id_prefix or "id"
    for idx, row in enumerate(rows):
        new_row = dict(row)
        if "id" in new_row and "old_id" not in new_row:
            new_row["old_id"] = new_row["id"]
        new_row["id"] = _safe_dataset_id(prefix, idx)
        final_rows.append(new_row)
    return final_rows


def _assign_train_split_by_subset(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    train_per_subset: int = 100,
    subset_key: str = "subset",
) -> None:
    rng = random.Random(seed)
    subset_to_indices: dict[str, list[int]] = defaultdict(list)
    for idx, row in enumerate(rows):
        subset_to_indices[str(row.get(subset_key, "default"))].append(idx)

    for indices in subset_to_indices.values():
        train_count = min(train_per_subset, len(indices))
        train_indices = set(rng.sample(indices, train_count))
        for idx in indices:
            rows[idx]["use"] = "train" if idx in train_indices else "test"


def adapt_rewardbench(raw: Any, dst_name: str, id_prefix: str, seed: int) -> Dataset:
    dataset = _first_split(raw, ("test", "filtered", "raw", "train"))
    rows = []
    seen_source_ids = set()
    for row in dataset:
        source_id = row.get("id")
        if source_id is not None:
            if source_id in seen_source_ids:
                continue
            seen_source_ids.add(source_id)
        new_row = dict(row)
        new_row["response_a"] = row.get("response_a", row.get("chosen"))
        new_row["response_b"] = row.get("response_b", row.get("rejected"))
        subset = row.get("subset", "default")
        new_row["old_subset"] = subset
        new_row["subset"] = REWARDBENCH_SUBSET_MAP.get(subset, subset)
        rows.append(new_row)
    _assign_train_split_by_subset(rows, seed=seed)
    return Dataset.from_list(_with_new_ids(rows, dst_name, id_prefix))


def adapt_rewardbench2(
    raw: Any,
    dst_name: str,
    id_prefix: str,
    include_ties: bool,
    seed: int,
) -> Dataset:
    dataset = _first_split(raw, ("test", "train"))
    rows = []
    for row in dataset:
        if not include_ties and row.get("subset") == "Ties":
            continue
        new_row = dict(row)
        new_row["response_a"] = row.get("response_a", row.get("chosen"))
        new_row["response_b"] = row.get("response_b", row.get("rejected"))
        rows.append(new_row)
    _assign_train_split_by_subset(rows, seed=seed)
    return Dataset.from_list(_with_new_ids(rows, dst_name, id_prefix))


def adapt_rmbench(raw: Any, dst_name: str, id_prefix: str, seed: int) -> Dataset:
    rng = random.Random(seed)
    dataset = _first_split(raw, ("train", "test", "validation"))
    expanded_rows = []
    for row in dataset:
        chosen_list = row.get("chosen", [])
        rejected_list = row.get("rejected", [])
        if not isinstance(chosen_list, list):
            chosen_list = [chosen_list]
        if not isinstance(rejected_list, list):
            rejected_list = [rejected_list]
        for c_idx, chosen in enumerate(chosen_list):
            for r_idx, rejected in enumerate(rejected_list):
                new_row = dict(row)
                new_row["old_id"] = row.get("id")
                new_row["subset"] = row.get("domain", row.get("subset", "default"))
                new_row["subset"] = new_row["subset"].replace(
                    "safety-refuse", "safety"
                ).replace("safety-response", "safety")
                new_row["response_a"] = chosen
                new_row["response_b"] = rejected
                if c_idx < r_idx:
                    new_row["difficulty"] = "hard"
                elif c_idx > r_idx:
                    new_row["difficulty"] = "easy"
                else:
                    new_row["difficulty"] = "normal"
                new_row["use"] = "test"
                new_row.pop("chosen", None)
                new_row.pop("rejected", None)
                expanded_rows.append(new_row)

    subset_counts = {"math": 100, "safety": 100, "code": 100, "chat": 50}
    for subset_name, requested in subset_counts.items():
        candidate_old_ids = sorted(
            {
                row.get("old_id")
                for row in expanded_rows
                if row.get("subset") == subset_name and row.get("old_id") is not None
            }
        )
        selected = set(rng.sample(candidate_old_ids, min(requested, len(candidate_old_ids))))
        for old_id in selected:
            indices = [
                idx
                for idx, row in enumerate(expanded_rows)
                if row.get("subset") == subset_name and row.get("old_id") == old_id
            ]
            if not indices:
                continue
            train_idx = rng.choice(indices)
            for idx in indices:
                expanded_rows[idx]["use"] = "train" if idx == train_idx else "train_unused"

    return Dataset.from_list(_with_new_ids(expanded_rows, dst_name, id_prefix))


def adapt_healthbench(raw: Any, dst_name: str, id_prefix: str, seed: int) -> Dataset:
    dataset = _first_split(raw, ("test", "train"))
    _require_columns(dataset, HEALTHBENCH_REQUIRED_COLUMNS, "HealthBench")
    rows = []
    for idx, row in enumerate(dataset):
        new_row = dict(row)
        new_row["subset"] = _tag_value(new_row.get("example_tags", []), THEME_PREFIX)
        for column in HEALTHBENCH_PAIR_COLUMNS:
            new_row.setdefault(column, None)
        rows.append(new_row)
    _assign_healthbench_splits(rows, seed)
    return Dataset.from_list(_with_new_ids(rows, dst_name, id_prefix))


def adapt_judgebench(raw: Any, dst_name: str, id_prefix: str, seed: int) -> Dataset:
    rng = random.Random(seed)
    rows = []
    splits = raw.keys() if hasattr(raw, "keys") else ["test"]
    for split in splits:
        dataset = raw[split] if hasattr(raw, "keys") else raw
        for row in dataset:
            label = str(row.get("label", "")).strip()
            if label == "A>B":
                response_a = row.get("response_A")
                response_b = row.get("response_B")
            else:
                response_a = row.get("response_B")
                response_b = row.get("response_A")
            new_row = dict(row)
            new_row["prompt"] = row.get("prompt", row.get("question"))
            new_row["response_a"] = response_a
            new_row["response_b"] = response_b
            new_row["subset"] = "mixed"
            rows.append(new_row)

    prompt_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        prompt_counts[row["prompt"]] += 1
    prompts = list(prompt_counts)
    rng.shuffle(prompts)
    train_prompts = set()
    train_count = 0
    for prompt in prompts:
        if train_count + prompt_counts[prompt] <= 100:
            train_prompts.add(prompt)
            train_count += prompt_counts[prompt]
        if train_count == 100:
            break
    for row in rows:
        row["use"] = "train" if row["prompt"] in train_prompts else "test"
    return Dataset.from_list(_with_new_ids(rows, dst_name, id_prefix))


def _load_benchmark_source(args: argparse.Namespace) -> Any:
    repo_id = args.source or HF_SOURCES[args.benchmark]
    load_kwargs = {
        "split": args.split,
        "cache_dir": args.hf_cache_dir,
    }
    if args.benchmark == "healthbench":
        load_kwargs["data_files"] = {"test": HEALTHBENCH_DATA_FILE}

    return load_dataset(repo_id, **load_kwargs)


def download_and_adapt(args: argparse.Namespace) -> Dataset:
    raw = _load_benchmark_source(args)

    dst_name = args.dst_name or f"{args.benchmark}_aug"
    if args.benchmark == "rewardbench":
        dataset = adapt_rewardbench(raw, dst_name, args.id_prefix, args.seed)
    elif args.benchmark == "rewardbench2":
        dataset = adapt_rewardbench2(
            raw, dst_name, args.id_prefix, args.include_ties, args.seed
        )
    elif args.benchmark == "rmbench":
        dataset = adapt_rmbench(raw, dst_name, args.id_prefix, args.seed)
    elif args.benchmark == "healthbench":
        dataset = adapt_healthbench(raw, dst_name, args.id_prefix, args.seed)
    elif args.benchmark == "judgebench":
        dataset = adapt_judgebench(raw, dst_name, args.id_prefix, args.seed)
    else:
        raise ValueError(f"Unsupported benchmark: {args.benchmark}")

    if args.limit > 0:
        dataset = dataset.select(range(min(args.limit, len(dataset))))
    return dataset


def _save_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _healthbench_pair_meets_threshold(
    row: dict[str, Any], min_diff: float
) -> bool:
    if any(row.get(column) is None for column in HEALTHBENCH_PAIR_COLUMNS):
        return False
    return float(row["score_diff"]) >= min_diff


def _load_healthbench_pair_cache(
    cache_path: Path, min_diff: float
) -> dict[str, Any] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if _healthbench_pair_meets_threshold(payload, min_diff):
        return payload
    return None


def _healthbench_generation_indices(
    rows: list[dict[str, Any]], args: argparse.Namespace
) -> list[int]:
    cache_dir = Path(args.healthbench_pair_cache_dir)
    indices = []
    for idx, row in enumerate(rows):
        if row.get("use") not in {"train", "test"}:
            continue
        if not args.force_healthbench_pairs and _healthbench_pair_meets_threshold(
            row, args.min_healthbench_score_diff
        ):
            continue
        cache_path = cache_dir / f"{row['id']}.json"
        if not args.force_healthbench_pairs and _load_healthbench_pair_cache(
            cache_path, args.min_healthbench_score_diff
        ):
            continue
        indices.append(idx)
    return indices


def confirm_healthbench_pair_generation(
    rows: list[dict[str, Any]],
    generation_indices: list[int],
    args: argparse.Namespace,
) -> bool:
    if not generation_indices or args.yes:
        return True

    minimum_generation_calls = 2 * len(generation_indices)
    maximum_generation_calls = (args.healthbench_max_regens + 2) * len(
        generation_indices
    )
    minimum_judge_calls = 2 * sum(
        len(rows[idx].get("rubrics") or []) for idx in generation_indices
    )
    print(
        "can be costly."
    )
    print(
        f"generation calls: {minimum_generation_calls}-"
        f"{maximum_generation_calls}; minimum final-judge calls: "
        f"{minimum_judge_calls}."
    )
    print(
        f"final judge: {os.getenv('FJ_MODEL_NAME', '<unset>')}."
    )
    try:
        answer = input("Continue with HealthBench pair generation? [y/N] ")
    except EOFError:
        print(
            "approve the model calls, or --skip-healthbench-pairs to omit them."
        )
        return False
    return answer.strip().lower() in {"y", "yes"}


def add_healthbench_pairs(dataset: Dataset, args: argparse.Namespace) -> Dataset:
    from .managers.healthbench_pair_manager import HealthBenchPairManager

    rows = [dict(row) for row in dataset]
    cache_dir = Path(args.healthbench_pair_cache_dir)
    target_indices = [
        idx for idx, row in enumerate(rows) if row.get("use") in {"train", "test"}
    ]
    generation_indices = set(_healthbench_generation_indices(rows, args))
    print(
        f"{len(generation_indices)} require model calls"
    )

    pair_manager = HealthBenchPairManager() if generation_indices else None

    def one(idx: int) -> tuple[int, dict[str, Any], str]:
        row = rows[idx]
        cache_path = cache_dir / f"{row['id']}.json"
        if not args.force_healthbench_pairs and _healthbench_pair_meets_threshold(
            row, args.min_healthbench_score_diff
        ):
            return idx, {column: row[column] for column in HEALTHBENCH_PAIR_COLUMNS}, "already_done"

        if idx not in generation_indices:
            cached = _load_healthbench_pair_cache(
                cache_path, args.min_healthbench_score_diff
            )
            if cached is None:
                raise RuntimeError(f"Expected valid HealthBench cache at {cache_path}")
            return idx, cached, "cache"

        if pair_manager is None:
            raise RuntimeError("HealthBench pair manager was not initialized.")
        result = pair_manager.generate_and_score(
            row,
            min_diff=args.min_healthbench_score_diff,
            max_regens=args.healthbench_max_regens,
        )
        _save_json_atomic(cache_path, result)
        return idx, result, "generated"

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, args.healthbench_pair_workers)
    ) as executor:
        futures = {executor.submit(one, idx): idx for idx in target_indices}
        for done, future in enumerate(
            concurrent.futures.as_completed(futures), start=1
        ):
            idx, result, status = future.result()
            rows[idx].update(result)
            if done % 10 == 0 or done == len(futures):
                print(
                    f"last id={rows[idx]['id']} status={status} "
                    f"diff={float(rows[idx]['score_diff']):.4f}"
                )

    return Dataset.from_list(rows)


def add_explanations(dataset: Dataset, args: argparse.Namespace) -> Dataset:
    from .managers.extraction_manager import ExtractionManager

    dst_name = args.dst_name or f"{args.benchmark}_aug"
    cache_dir = Path(args.cache_dir) / dst_name
    extraction_manager = ExtractionManager()
    has_use_field = "use" in dataset.column_names
    rows = [dict(row) for row in dataset]

    target_indices = [
        idx
        for idx, row in enumerate(rows)
        if (not has_use_field or row.get("use") == "train")
        and (
            not args.skip_existing_explanations
            or not row.get("explanation")
            or not row.get("confidence_score")
        )
    ]

    def one(idx: int) -> tuple[int, str | None, int]:
        row = rows[idx]
        cache_path = cache_dir / f"{idx}.json"
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                explanation = payload.get("explanation")
                confidence = int(payload.get("confidence_score") or 0)
                if explanation:
                    return idx, explanation, confidence
            except Exception:
                pass

        try:
            if args.benchmark == "healthbench":
                if not row.get("response_a") or not row.get("response_b"):
                    return idx, None, 0
                explanation, confidence = extraction_manager.extract_explanation_healthbench(
                    row,
                    dst_name,
                    min_diff=args.min_healthbench_score_diff,
                )
            else:
                explanation, confidence = extraction_manager.extract_explanation(row, dst_name)
        except Exception as exc:
            explanation, confidence = "", 0

        _save_json_atomic(
            cache_path,
            {
                "id": row.get("id", idx),
                "old_id": row.get("old_id"),
                "explanation": explanation,
                "confidence_score": confidence,
            },
        )
        return idx, explanation, int(confidence or 0)

    failed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {executor.submit(one, idx): idx for idx in target_indices}
        for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
            idx, explanation, confidence = future.result()
            rows[idx]["explanation"] = explanation
            rows[idx]["confidence_score"] = confidence
            if not explanation:
                failed += 1
            if done % 10 == 0 or done == len(futures):
                print(f"[augment] Processed {done}/{len(futures)} rows; failed={failed}")

    for row in rows:
        row.setdefault("explanation", None)
        row.setdefault("confidence_score", None)
    return Dataset.from_list(rows)


def save_dataset(dataset: Dataset, output_dir: str | Path, dst_name: str) -> Path:
    output_path = Path(output_dir) / dst_name
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    if tmp_path.exists():
        shutil.rmtree(tmp_path)
    DatasetDict({"test": dataset}).save_to_disk(str(tmp_path))
    if output_path.exists():
        shutil.rmtree(output_path)
    os.replace(tmp_path, output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=sorted(HF_SOURCES), required=True)
    parser.add_argument(
        "--source",
        default="",
        help="Override the default Hugging Face dataset repository id.",
    )
    parser.add_argument("--split", default=None, help="Optional Hugging Face split.")
    parser.add_argument("--hf-cache-dir", default=None)
    parser.add_argument("--dst-name", default="")
    parser.add_argument("--output-dir", default="dataset_augmented")
    parser.add_argument("--id-prefix", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-ties", action="store_true")
    parser.add_argument("--skip-explanations", action="store_true")
    parser.add_argument("--skip-existing-explanations", action="store_true")
    parser.add_argument("--cache-dir", default="caches/explanation")
    parser.add_argument("--max-workers", type=int, default=16)
    parser.add_argument("--min-healthbench-score-diff", type=float, default=0.1)
    parser.add_argument("--healthbench-max-regens", type=int, default=10)
    parser.add_argument("--healthbench-pair-workers", type=int, default=16)
    parser.add_argument(
        "--healthbench-pair-cache-dir", default="caches/healthbench_pairs"
    )
    parser.add_argument("--force-healthbench-pairs", action="store_true")
    parser.add_argument("--skip-healthbench-pairs", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Approve costly HealthBench generation and final-judge calls.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=["eval_skill.env"],
        help="Env file for extraction, generation, and judge models.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env_files(args.env_file, missing_ok=True)

    dataset = download_and_adapt(args)
    dst_name = args.dst_name or f"{args.benchmark}_aug"
    if args.benchmark == "healthbench" and not args.skip_healthbench_pairs:
        rows = [dict(row) for row in dataset]
        generation_indices = _healthbench_generation_indices(rows, args)
        if not confirm_healthbench_pair_generation(
            rows, generation_indices, args
        ):
            return 0
        if generation_indices:
            require_env(
                [
                    "GENERATION_MODEL_NAME",
                    "GENERATION_API_BASE",
                    "GENERATION_API_KEY",
                    "FJ_MODEL_NAME",
                    "FJ_API_BASE",
                    "FJ_API_KEY",
                ]
            )
        dataset = add_healthbench_pairs(dataset, args)
    if not args.skip_explanations:
        require_env(["EXTRACTION_MODEL_NAME", "EXTRACTION_API_BASE", "EXTRACTION_API_KEY"])
        dataset = add_explanations(dataset, args)
    save_dataset(dataset, args.output_dir, dst_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

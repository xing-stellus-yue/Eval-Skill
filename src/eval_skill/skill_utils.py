"""Helper functions for skill initialization, refinement, and rollout."""

from __future__ import annotations

from collections import defaultdict
import concurrent.futures
import json
import os
from pathlib import Path
import random

from .data import use_multiple_distraction
from .eval_process import process_item
from .shared_manager import get_eval_manager, get_extraction_manager


def select_results_for_refinement(results: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for result in results:
        grouped.setdefault(result["id"], []).append(result)

    selected = []
    for trials in grouped.values():
        incorrect = [trial for trial in trials if trial["status"] != "Correct"]
        selected.append(incorrect[0] if incorrect else trials[0])
    return selected


def select_failed_results(results: list[dict], max_per_case: int = 2) -> list[dict]:
    grouped = defaultdict(list)
    for result in results:
        if result["status"] == "Correct":
            continue
        if len(grouped[result["id"]]) < max_per_case:
            grouped[result["id"]].append(result)
    return [item for branch in grouped.values() for item in branch]


def do_quit(correct_cnt_history: list[int], total_cnt: int, patience: int = 2) -> bool:
    if patience < 1:
        raise ValueError(f"Invalid patience={patience}")
    last_correct_cnt = correct_cnt_history[-1]
    best_correct_cnt = max(correct_cnt_history)
    idx_best = correct_cnt_history.index(best_correct_cnt)
    if last_correct_cnt == total_cnt:
        return True
    if len(correct_cnt_history) <= min(patience, 1):
        return False
    return idx_best < len(correct_cnt_history) - patience


def get_dataset_split_map(dataset) -> dict:
    if "use" not in dataset.column_names:
        raise ValueError(
            "Augmented benchmarks must include a 'use' column with train/test "
            "assignments. Regenerate the dataset with `eval_skill augment` or "
            "patch the split into the dataset before running skill methods."
        )
    split_map = {}
    for idx, item in enumerate(dataset):
        subset_name = item["subset"]
        # Added during augmentation, functioning as split
        use = item["use"]
        entry = split_map.setdefault(
            subset_name, {"evo_indices": [], "test_indices": []}
        )
        if use == "train":
            entry["evo_indices"].append(idx)
        elif use == "test":
            entry["test_indices"].append(idx)
        elif use in {"train_unused", "test_unused", "test_dq"}:
            continue
        else:
            raise ValueError(f"Unexpected use={use!r} at index {idx}.")

    for subset_name, item in split_map.items():
        print(
            f"[{subset_name}] {len(item['evo_indices'])} evolving samples, "
            f"{len(item['test_indices'])} test samples."
        )
    return split_map


def init_skill_from_batch(
    dataset,
    trial_num: int,
    batch: list[int],
    max_init_round: int,
    batch_idx: int,
    batch_output_dir: str,
    subset_name: str,
    dataset_name: str,
    early_quit: bool = True,
    patience: int = 2,
    step1_flag: str = "default",
    init_skill: str = "",
    failed_only: bool = False,
    pre_refine_shuffle: bool = False,
    first_round_supervision: bool = False,
) -> dict:
    if init_skill is None or not isinstance(init_skill, str):
        raise TypeError("init_skill must be a string.")
    extraction_manager = get_extraction_manager(dataset_name=dataset_name)

    correct_cnt_history = []
    skill_history = []
    skill_length_history = []
    used_rollouts = {}
    final_total_cnt = len(batch) * trial_num
    skill = init_skill
    reasoning = None

    rnd = 1
    while rnd <= max_init_round:
        print(
            f"[{subset_name}] Generating/refining skill round {rnd} for batch {batch_idx}")
        result_output_dir = Path(batch_output_dir) / f"round{rnd}" / "rollouts"
        result_output_dir.mkdir(parents=True, exist_ok=True)
        skill_history.append(skill)
        skill_length_history.append(len(skill))

        if skill:
            round_dir = Path(batch_output_dir) / f"round{rnd}"
            round_dir.mkdir(parents=True, exist_ok=True)
            (round_dir / "curr_skill.md").write_text(skill, encoding="utf-8")
            if reasoning:
                (round_dir / "reasoning.txt").write_text(reasoning, encoding="utf-8")

        use_supervision = first_round_supervision and rnd == 1
        actual_trial_num = 1 if use_supervision else trial_num
        total_cnt = len(batch) * actual_trial_num
        results, _ = get_results(
            dataset,
            actual_trial_num,
            skill,
            batch,
            str(result_output_dir),
            dataset_name,
            use_supervision=use_supervision,
        )
        correct_cnt = sum(
            1 for result in results if result["status"] == "Correct")
        correct_cnt_history.append(correct_cnt)
        print(
            f"[{subset_name}] batch {batch_idx}, round {rnd}: "
            f"{correct_cnt}/{total_cnt} correct."
        )

        if (not use_supervision) and early_quit and do_quit(
            correct_cnt_history, total_cnt=total_cnt, patience=patience
        ):
            break

        new_skill = skill
        new_reasoning = reasoning
        if rnd < max_init_round:
            if pre_refine_shuffle:
                results = random.sample(results, len(results))
            results_for_refinement = (
                select_failed_results(results, max_per_case=2)
                if failed_only
                else select_results_for_refinement(results)
                if actual_trial_num > 1
                else results
            )
            used_rollouts[f"round{rnd}"] = results_for_refinement
            next_round_dir = Path(batch_output_dir) / f"round{rnd + 1}"
            next_skill_file = next_round_dir / "curr_skill.md"
            next_reasoning_file = next_round_dir / "reasoning.txt"
            if next_skill_file.exists():
                new_skill = next_skill_file.read_text(encoding="utf-8")
                new_reasoning = (
                    next_reasoning_file.read_text(encoding="utf-8")
                    if next_reasoning_file.exists()
                    else None
                )
            elif skill:
                new_skill, new_reasoning = extraction_manager.new_improve_skill(
                    skill, results_for_refinement, step1_flag=step1_flag
                )
            else:
                new_skill, new_reasoning = extraction_manager.new_init_skill(
                    results_for_refinement, step1_flag=step1_flag
                )
            print(
                f"[{subset_name}] New skill length after {step1_flag}: "
                f"{len(new_skill)}."
            )

        rnd += 1
        skill = new_skill
        reasoning = new_reasoning

    if first_round_supervision:
        best_correct_cnt = max(correct_cnt_history[1:])
        best_idx = correct_cnt_history[1:].index(best_correct_cnt) + 1
    else:
        best_correct_cnt = max(correct_cnt_history)
        best_idx = correct_cnt_history.index(best_correct_cnt)

    batch_result = {
        "batch_idx": batch_idx,
        "max_round": max_init_round,
        "correct_cnt_history": correct_cnt_history,
        "skill_length_history": skill_length_history,
        "best_idx": best_idx,
        "best_correct_cnt": best_correct_cnt,
        "best_acc": best_correct_cnt / final_total_cnt if final_total_cnt else 0.0,
        "best_skill": skill_history[best_idx],
        "skill_history": skill_history,
    }
    Path(batch_output_dir).mkdir(parents=True, exist_ok=True)
    with open(f"{batch_output_dir}/batch_result.json", "w", encoding="utf-8") as f:
        json.dump(batch_result, f, indent=4)
    with open(f"{batch_output_dir}/used_rollouts.json", "w", encoding="utf-8") as f:
        json.dump(used_rollouts, f, indent=4)
    return batch_result


def merge_skill(skill_batch: list[str], batch_idx: int, output_file: str, dataset_name: str) -> dict:
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    extraction_manager = get_extraction_manager(dataset_name=dataset_name)
    if len(skill_batch) > 1:
        merged_skill, reasoning = extraction_manager.new_merge_skill(
            skill_batch)
    else:
        merged_skill = skill_batch[0]
        reasoning = "No reasoning needed for merging 1 skill."
    result = {
        "batch_idx": batch_idx,
        "merged_skill": merged_skill,
        "reasoning": reasoning,
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
    return result


def init_patch_from_batch(
    result_batch: list[dict],
    skill: str,
    batch_idx: int,
    batch_output_dir: str,
    subset_name: str,
    dataset_name: str
) -> dict:
    result_file = Path(batch_output_dir) / "result.json"
    if result_file.exists():
        try:
            with result_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    extraction_manager = get_extraction_manager(dataset_name)
    print(f"[{subset_name}] Generating patch from {len(result_batch)} results.")
    patch, reasoning = extraction_manager.new_init_patch(skill, result_batch)
    result = {
        "batch_idx": batch_idx,
        "status_list": [item["status"] for item in result_batch],
        "correct_cnt": sum(1 for item in result_batch if item["status"] == "Correct"),
        "patch": patch,
        "reasoning": reasoning,
        "used_rollouts": result_batch,
    }
    Path(batch_output_dir).mkdir(parents=True, exist_ok=True)
    with result_file.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=4)
    if reasoning:
        (Path(batch_output_dir) / "reasoning.txt").write_text(reasoning, encoding="utf-8")
    return result


def merge_patch(
    patch_batch: list[str],
    skill: str,
    batch_idx: int,
    output_file: str | None = None,
    dataset_name: str = ""
) -> dict:
    if output_file and os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    extraction_manager = get_extraction_manager(dataset_name=dataset_name)
    if len(patch_batch) == 1:
        merged_patch = patch_batch[0]
        reasoning = "No reasoning needed for merging 1 patch."
    else:
        merged_patch, reasoning = extraction_manager.new_merge_patch(
            patch_batch, skill
        )
    result = {"batch_idx": batch_idx,
              "merged_patch": merged_patch, "reasoning": reasoning}
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)
    return result


def final_skill_refine(skill: str, patch: str, dataset_name: str) -> tuple[str, str | None]:
    return get_extraction_manager(dataset_name=dataset_name).refine_skill_with_patch(skill, patch)


def step3_step(
    skill: str,
    results: list[dict],
    subset_name: str,
    curr_rnd: int,
    rnd_output_dir: str,
    init_patch_bs: int,
    merge_bs: int,
    dataset_name,
) -> tuple[str, list[dict], str | None]:
    next_rnd_output_dir = rnd_output_dir.rstrip(
        str(curr_rnd)) + str(curr_rnd + 1)
    reasoning_file = Path(rnd_output_dir) / "final_refine_reasoning.txt"
    next_skill_file = Path(next_rnd_output_dir) / "curr_skill.md"
    if next_skill_file.exists():
        new_skill = next_skill_file.read_text(encoding="utf-8")
        reasoning = reasoning_file.read_text(
            encoding="utf-8") if reasoning_file.exists() else None
        round_summary_file = Path(rnd_output_dir) / "round_summary.json"
        histories = []
        if round_summary_file.exists():
            with round_summary_file.open("r", encoding="utf-8") as f:
                histories = json.load(f).get("merge_patch_histories", [])
        return new_skill, histories, reasoning

    result_batches = [
        results[i: i + init_patch_bs] for i in range(0, len(results), init_patch_bs)
    ]
    initial_patches = [None] * len(result_batches)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(16, len(result_batches)))
    ) as executor:
        futures = []
        for batch_idx, result_batch in enumerate(result_batches):
            batch_output_dir = Path(rnd_output_dir) / f"batch{batch_idx}"
            futures.append(
                executor.submit(
                    init_patch_from_batch,
                    result_batch,
                    skill,
                    batch_idx,
                    str(batch_output_dir),
                    subset_name,
                    dataset_name
                )
            )
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            initial_patches[result["batch_idx"]] = result["patch"]

    curr_patches = [patch for patch in initial_patches if patch]
    if not curr_patches:
        return skill, [], "No failed rollouts produced patches."

    histories = [
        {
            "level": 0,
            "patch_num": len(curr_patches),
            "patch_length": [len(patch) for patch in curr_patches],
            "patches": curr_patches,
        }
    ]
    with open(f"{rnd_output_dir}/level0_merge_patch_history.json", "w", encoding="utf-8") as f:
        json.dump(histories[0], f, indent=4)

    level = 1
    while len(curr_patches) > 1:
        patch_batches = [
            curr_patches[i: i + merge_bs] for i in range(0, len(curr_patches), merge_bs)
        ]
        next_patches = [None] * len(patch_batches)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(16, len(patch_batches)))
        ) as executor:
            futures = [
                executor.submit(
                    merge_patch,
                    patch_batch,
                    skill,
                    batch_idx,
                    f"{rnd_output_dir}/level{level}_batch{batch_idx}.json",
                    dataset_name
                )
                for batch_idx, patch_batch in enumerate(patch_batches)
            ]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                next_patches[result["batch_idx"]] = result
        curr_patches = [item["merged_patch"] for item in next_patches if item]
        history = {
            "level": level,
            "patch_num": len(curr_patches),
            "patch_length": [len(patch) for patch in curr_patches],
            "patches": curr_patches,
            "reasonings": [item.get("reasoning") for item in next_patches if item],
        }
        with open(f"{rnd_output_dir}/level{level}_merge_patch_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4)
        histories.append(history)
        level += 1

    new_skill, reasoning = final_skill_refine(
        skill, curr_patches[0], dataset_name)
    if reasoning:
        reasoning_file.write_text(reasoning, encoding="utf-8")
    return new_skill, histories, reasoning


def get_results(
    dataset,
    trial_num: int,
    skill: str,
    indices: list[int],
    output_dir: str,
    dataset_name: str,
    raise_on_error: bool = True,
    use_supervision: bool = False,
) -> tuple[list[dict], int]:
    results = []
    failed_trials_cnt = 0
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    def get_one_result(item, trial_cnt: int) -> dict:
        item_id = item["id"]
        output_filepath = Path(output_dir) / \
            f"{item_id}_trial_{trial_cnt}.json"
        if output_filepath.exists():
            try:
                with output_filepath.open("r", encoding="utf-8") as f:
                    result = json.load(f)
                if "status" in result and result.get("skill") == skill:
                    return result
                if "status" in result and not skill and "skill" not in result:
                    return result
            except Exception:
                pass

        return process_item(
            dataset_name,
            item,
            trial_cnt,
            use_multiple_distraction(dataset_name),
            output_dir,
            get_eval_manager(dataset_name=dataset_name),
            eval_mode="eval_skill",
            use_supervision=use_supervision,
            skill_content=skill
        )

    max_workers = max(1, min(256, len(indices) * max(1, trial_num)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures_map = {}
        for idx in indices:
            item = dataset[idx]
            for trial_cnt in range(trial_num):
                futures_map[executor.submit(get_one_result, item, trial_cnt)] = (
                    idx,
                    trial_cnt,
                )
        for future in concurrent.futures.as_completed(futures_map):
            idx, trial_cnt = futures_map[future]
            try:
                results.append((idx, trial_cnt, future.result()))
            except Exception as exc:
                print(f"Error in trial {trial_cnt} for idx {idx}: {exc}")
                if raise_on_error:
                    raise
                failed_trials_cnt += 1

    idx_order = {idx: order for order, idx in enumerate(indices)}
    results.sort(key=lambda item: (
        idx_order.get(item[0], float("inf")), item[1]))
    return [item[2] for item in results], failed_trials_cnt

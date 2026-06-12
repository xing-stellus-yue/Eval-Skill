"""Step orchestration for the public supervised eval-skill pipeline."""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path

from .skill_utils import (
    do_quit,
    get_results,
    init_skill_from_batch,
    merge_skill,
    select_failed_results,
    step3_step,
)


def run_step1(
    dataset,
    evo_indices: list[int],
    output_dir_step1: str,
    max_init_round: int,
    trial_num_step1: int,
    init_skill_bs: int,
    subset_name: str,
    dataset_name: str,
    early_quit: bool = True,
    patience: int = 2,
    skip_rewrite_result: bool = False,
    step1_flag: str = "default",
    init_skill: str = "",
    exclude_init: bool = False,
    failed_only: bool = False,
    pre_refine_shuffle: bool = False,
    first_round_supervision: bool = False,
) -> tuple[list[str], dict]:
    idx_batches = [
        evo_indices[i : i + init_skill_bs]
        for i in range(0, len(evo_indices), init_skill_bs)
    ]
    best_idx_list = [None] * len(idx_batches)
    skills = [None] * len(idx_batches)
    batch_results = [None] * len(idx_batches)
    total_best_correct_cnt = 0
    initial_correct_cnt = 0
    total_cnt = len(evo_indices) * trial_num_step1

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(1, min(16, len(idx_batches)))
    ) as executor:
        futures = []
        for batch_idx, idx_batch in enumerate(idx_batches):
            batch_output_dir = Path(output_dir_step1) / f"batch{batch_idx}"
            batch_output_dir.mkdir(parents=True, exist_ok=True)
            futures.append(
                executor.submit(
                    init_skill_from_batch,
                    dataset,
                    trial_num_step1,
                    idx_batch,
                    max_init_round,
                    batch_idx,
                    str(batch_output_dir),
                    subset_name,
                    dataset_name,
                    early_quit=early_quit,
                    patience=patience,
                    step1_flag=step1_flag,
                    init_skill=init_skill,
                    failed_only=failed_only,
                    pre_refine_shuffle=pre_refine_shuffle,
                    first_round_supervision=first_round_supervision,
                )
            )
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            batch_idx = result["batch_idx"]
            best_idx_list[batch_idx] = result["best_idx"]
            total_best_correct_cnt += result["best_correct_cnt"]
            initial_correct_cnt += result["correct_cnt_history"][0]
            skills[batch_idx] = result["best_skill"]
            batch_results[batch_idx] = result

    curr_acc = total_best_correct_cnt / total_cnt if total_cnt else 0.0
    initial_total = len(evo_indices) if first_round_supervision else total_cnt
    initial_acc = initial_correct_cnt / initial_total if initial_total else 0.0
    print(
        f"[{subset_name}] step1 {step1_flag}: best={curr_acc:.2%}, "
        f"initial={initial_acc:.2%}."
    )
    step1_result = {
        "best_idx_list": best_idx_list,
        "best_correct_cnt": total_best_correct_cnt,
        "initial_correct_cnt": initial_correct_cnt,
        "total_cnt": total_cnt,
        "best_accuracy": curr_acc,
        "initial_accuracy": initial_acc,
        "batch_results": batch_results,
    }
    final_result_file = Path(output_dir_step1) / "final_result.json"
    if not (final_result_file.exists() and skip_rewrite_result):
        final_result_file.write_text(
            json.dumps(step1_result, indent=4), encoding="utf-8"
        )
    if exclude_init:
        skills = [
            skill
            for idx, skill in enumerate(skills)
            if best_idx_list[idx] != 0
        ]
    return skills, step1_result


def run_step1a(*args, **kwargs):
    return run_step1(*args, **kwargs, step1_flag="step1a")


def run_step1b(*args, **kwargs):
    return run_step1(*args, **kwargs, step1_flag="step1b")


def run_step2(
    skills: list[str],
    output_dir_step2: str,
    merge_batch_size: int,
    dataset_name="",
) -> tuple[str, dict]:
    output_dir = Path(output_dir_step2)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_result_file = output_dir / "final_result.json"
    if final_result_file.exists():
        with final_result_file.open("r", encoding="utf-8") as f:
            result = json.load(f)
        return result["final_skill"], result

    level = 0
    curr_skills = [skill for skill in skills if skill]
    histories = [
        {
            "level": level,
            "skill_num": len(curr_skills),
            "skill_length": [len(item) for item in curr_skills],
            "skills": curr_skills,
        }
    ]
    with (output_dir / f"level{level}_merge_skill_history.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(histories[0], f, indent=4)

    level = 1
    while len(curr_skills) > 1:
        batches = [
            curr_skills[i : i + merge_batch_size]
            for i in range(0, len(curr_skills), merge_batch_size)
        ]
        next_skills = [None] * len(batches)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, min(16, len(batches)))
        ) as executor:
            futures = [
                executor.submit(
                    merge_skill,
                    batch,
                    batch_idx,
                    str(output_dir / f"level{level}_batch{batch_idx}.json"),
                    dataset_name=dataset_name
                )
                for batch_idx, batch in enumerate(batches)
            ]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                next_skills[result["batch_idx"]] = result

        curr_skills = [
            item["merged_skill"] for item in next_skills if item is not None
        ]
        history = {
            "level": level,
            "skill_num": len(curr_skills),
            "skill_length": [len(item) for item in curr_skills],
            "skills": curr_skills,
            "reasonings": [
                item.get("reasoning") for item in next_skills if item is not None
            ],
        }
        with (output_dir / f"level{level}_merge_skill_history.json").open(
            "w", encoding="utf-8"
        ) as f:
            json.dump(history, f, indent=4)
        histories.append(history)
        level += 1

    merged_skill = curr_skills[0] if curr_skills else ""
    result = {"final_skill": merged_skill, "merge_skill_histories": histories}
    final_result_file.write_text(json.dumps(result, indent=4), encoding="utf-8")
    return merged_skill, result


def run_step3(
    dataset,
    evo_indices: list[int],
    skill: str,
    output_dir_step3: str,
    max_refine_round: int,
    trial_num_step3: int,
    init_patch_bs: int,
    merge_bs: int,
    subset_name: str,
    dataset_name: str,
    extra_list: list[str] | None = None,
    early_quit: bool = True,
    patience: int = 3,
    skip_rewrite_result: bool = False,
) -> tuple[str, dict]:
    extra_list = extra_list or []
    correct_cnt_history = []
    skill_history = []
    skill_length_history = []
    round_results_history = []
    best_correct_cnt = 0
    total_cnt = len(evo_indices) * trial_num_step3

    rnd = 1
    quit_next = False
    while rnd <= max_refine_round:
        rnd_output_dir = Path(output_dir_step3) / f"round{rnd}"
        result_output_dir = rnd_output_dir / "rollouts"
        result_output_dir.mkdir(parents=True, exist_ok=True)
        skill_history.append(skill)
        skill_length_history.append(len(skill))
        (rnd_output_dir / "curr_skill.md").write_text(skill, encoding="utf-8")

        results, _ = get_results(
            dataset,
            trial_num_step3,
            skill,
            evo_indices,
            str(result_output_dir),
            dataset_name,
        )
        correct_cnt = sum(1 for result in results if result["status"] == "Correct")
        round_results_history.append(results)
        best_correct_cnt = max(correct_cnt, best_correct_cnt)
        correct_cnt_history.append(correct_cnt)
        print(f"[{subset_name}] step3 round {rnd}: {correct_cnt}/{total_cnt} correct.")

        if not skill:
            quit_next = True
        if early_quit and do_quit(correct_cnt_history, total_cnt, patience=patience):
            quit_next = True

        new_skill = None
        merge_patch_histories = None
        if rnd < max_refine_round and not quit_next:
            failed_results = select_failed_results(results, max_per_case=2)
            new_skill, merge_patch_histories, _ = step3_step(
                skill,
                failed_results,
                subset_name,
                rnd,
                str(rnd_output_dir),
                init_patch_bs,
                merge_bs,
                dataset_name
            )

        round_summary = {
            "round": rnd,
            "correct_cnt": correct_cnt,
            "total_cnt": total_cnt,
            "accuracy": correct_cnt / total_cnt if total_cnt else 0.0,
            "curr_skill": skill,
            "new_skill": new_skill,
            "merge_patch_histories": merge_patch_histories,
        }
        (rnd_output_dir / "round_summary.json").write_text(
            json.dumps(round_summary, indent=4), encoding="utf-8"
        )
        if quit_next:
            break
        rnd += 1
        skill = new_skill

    best_idx = correct_cnt_history.index(best_correct_cnt)
    best_skill = skill_history[best_idx]
    result = {
        "final round": rnd,
        "max_round": max_refine_round,
        "correct_cnt_history": correct_cnt_history,
        "skill_length_history": skill_length_history,
        "best_idx": best_idx,
        "best_correct_cnt": best_correct_cnt,
        "evol_total_cnt": total_cnt,
        "best_acc": best_correct_cnt / total_cnt if total_cnt else 0.0,
        "best_skill_length": len(best_skill),
        "best_skill": best_skill,
        "skill_history": skill_history,
        "extra": (
            {"round_results_history": round_results_history}
            if "round_results_history" in extra_list
            else {}
        ),
    }
    final_result_file = Path(output_dir_step3) / "final_result.json"
    if not (final_result_file.exists() and skip_rewrite_result):
        final_result_file.write_text(json.dumps(result, indent=4), encoding="utf-8")
    return best_skill, result


def run_test(
    dataset,
    test_indices: list[int],
    best_skill: str,
    result_output_dir: str,
    trial_num: int,
    dataset_name: str,
    extra_list: list[str] | None = None,
) -> dict:
    extra_list = extra_list or []
    results, failed_trials_cnt = get_results(
        dataset,
        trial_num,
        best_skill,
        test_indices,
        result_output_dir,
        dataset_name,
        raise_on_error=False,
    )
    correct_cnt = sum(1 for result in results if result["status"] == "Correct")
    incorrect_cnt = sum(1 for result in results if result["status"] == "Incorrect")
    total_cnt = len(test_indices) * trial_num
    valid_cnt = correct_cnt + incorrect_cnt
    return {
        "test_correct_cnt": correct_cnt,
        "test_total_cnt": total_cnt,
        "test_failed_cnt": failed_trials_cnt,
        "test_acc": correct_cnt / total_cnt if total_cnt else 0.0,
        "test_acc_cal": correct_cnt / valid_cnt if valid_cnt else 0.0,
        "test_bug_cnt": total_cnt - correct_cnt - incorrect_cnt,
        "extra": {"test_results": results} if "test_results" in extra_list else None,
    }


def summarize_all(
    d1: dict,
    d2: dict,
    d3: dict,
    d4: dict,
    output_file: str,
    subset_name: str,
    evo_set_size: int,
    skip_rewrite_result: bool = False,
) -> dict:
    def remove_extra(payload: dict) -> dict:
        return {key: value for key, value in payload.items() if key != "extra"}

    result = {
        "summary": {
            "subset": subset_name,
            "evo_set_size": evo_set_size,
            "evol_initial_correct_cnt": d1.get("initial_correct_cnt"),
            "evol_correct_cnt": d3.get("best_correct_cnt"),
            "evol_total_cnt": d3.get("evol_total_cnt"),
            "evol_initial_acc": d1.get("initial_accuracy"),
            "evol_acc": d3.get("best_acc"),
            "test_correct_cnt": d4.get("test_correct_cnt"),
            "test_total_cnt": d4.get("test_total_cnt"),
            "test_failed_cnt": d4.get("test_failed_cnt"),
            "test_acc": d4.get("test_acc"),
            "test_acc_cal": d4.get("test_acc_cal"),
            "test_bug_cnt": d4.get("test_bug_cnt"),
            "final_skill_length": d3.get("best_skill_length"),
            "final_skill": d3.get("best_skill"),
        },
        "details": {
            "step 1": remove_extra(d1),
            "step 2": remove_extra(d2),
            "step 3": remove_extra(d3),
            "step 4": remove_extra(d4),
        },
    }
    print(json.dumps(result["summary"], indent=4))
    if not (os.path.exists(output_file) and skip_rewrite_result):
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4)
    return result

"""Evaluation loop used by the public eval-skill entry points."""

from __future__ import annotations

from collections import defaultdict
import concurrent.futures
import json
import os
from pathlib import Path
import threading

from tqdm import tqdm

from .data import get_benchmark, use_multiple_distraction
from .managers.eval_manager import EvalManager
from .shared_manager import get_eval_manager
from .util import get_rng, is_set



def split_think_output(content: str, kind: str) -> tuple[str, str]:
    close_count = content.count("</think>")
    if close_count == 1:
        reasoning, visible = content.rsplit("</think>", 1)
        return visible.strip(), reasoning.replace("<think>", "", 1).strip()
    if close_count > 1:
        tqdm.write(
            f"[think parser] {kind} contains {close_count} '</think>' tags; using the last tag as the split point.",
        )
        reasoning, visible = content.rsplit("</think>", 1)
        return visible.strip(), reasoning.replace("<think>", "", 1).strip()
    tqdm.write(
        f"[think parser] {kind} thinking is enabled, but no '</think>' tag was returned; using the full response as visible content.",
    )
    return content.strip(), ""


def get_setting_name(mode: str = "vanilla") -> str:
    judge_infix = (
        "_think"
        if os.getenv("JUDGE_THINK", "").lower() == "true" else ""
    )
    judge_part = f"{os.environ['JUDGE_MODEL_NAME'].lower()}{judge_infix}_judge"

    if mode == "eval_skill":
        first_part = "eval_skill"
    elif mode == "rubric_based":
        rubric_infix = (
            "_think"
            if os.getenv("RUBRIC_THINK", "").lower() == "true"
            else ""
        )
        first_part = f"rubric_based_{os.environ['RUBRIC_MODEL_NAME'].lower()}{rubric_infix}_rubric"
    elif mode == "vanilla":
        first_part = "vanilla"
    else:
        raise ValueError(
            "mode must be 'vanilla', 'rubric_based', or 'eval_skill'."
        )
    return f"{first_part}_{judge_part}".replace("-", "_")

# compatible with pairwise or listwise judging, where response_a is the preferred one, and response_b the distractor(s).
def shuffle_options(item: dict, multiple_distraction: bool = False) -> tuple[list[str], int]:
    response_a = item["response_a"]
    response_b = item["response_b"]
    # We want the rng to be deterministic based on the item content, so that repeated runs will have the same shuffled order and thus the same evaluation results.
    rng = get_rng(response_a, response_b)

    if isinstance(response_a, list):
        response_a = rng.choice(response_a)
    if isinstance(response_b, list):
        if multiple_distraction:
            if len(response_b) < 3:
                raise ValueError(f"Expected at least 3 distractors, got {len(response_b)}")
            negative = response_b[:3]
        else:
            negative = rng.choice(response_b)
    else:
        negative = response_b

    options = [response_a] + negative if isinstance(negative, list) else [response_a, negative]
    rng.shuffle(options)
    return options, options.index(response_a)


def _parse_prediction(evaluation: str) -> str:
    pred = (
        evaluation.rsplit("Final Decision", 1)[-1]
        .rsplit("Final Judgment", 1)[-1]
        .split("Winner", 1)[-1]
        .split("Response", 1)[-1]
        .split("Candidate", 1)[-1]
    )
    pred = pred.replace("*", "").replace(":", "").replace(".", "").replace(" ", "").strip()
    return pred[0] if len(pred) > 1 else pred


def process_item(
    benchmark_name: str,
    item: dict,
    trial_cnt: int,
    multiple_distraction: bool,
    output_dir: str | Path,
    eval_manager: EvalManager,
    eval_mode: str,
    use_supervision: bool = False,
    skill_content=None
) -> dict:
    item_id = item["id"]
    output_dir = Path(output_dir)

    super_cache_filepath = None
    if use_supervision:
        super_model = os.environ["SUPER_JUDGE_MODEL_NAME"]
        super_cache_filepath = (
            Path("caches/super_judge_rollout")
            / super_model
            / f"{item_id}_{trial_cnt}.json"
        )
        if super_cache_filepath.exists():
            with super_cache_filepath.open("r", encoding="utf-8") as f:
                result = json.load(f)
            if "status" in result:
                output_dir.mkdir(parents=True, exist_ok=True)
                with (output_dir / f"{item_id}_trial_{trial_cnt}.json").open(
                    "w", encoding="utf-8"
                ) as f:
                    json.dump(result, f, indent=4, ensure_ascii=False)
                return result

    prompt = item["prompt"]
    subset = item["subset"]
    options, correct_idx = shuffle_options(item, multiple_distraction)
    expected_pred = chr(ord("A") + correct_idx)
    valid_preds = [chr(ord("A") + idx) for idx in range(len(options))]

    rubric = None
    rubric_reasoning = ""
    evaluation = ""
    evaluation_reasoning = ""
    pred = ""
    result_status = ""

    if eval_mode == "rubric_based":
        rubric = eval_manager.generate_rubric(prompt)
        if is_set("RUBRIC_THINK") and rubric is not None:
            rubric, rubric_reasoning = split_think_output(rubric, "rubric")

        if rubric is None or len(rubric) < 10:
            evaluation = ""
            pred = ""
            result_status = "Rubric Generation Failed"
            tqdm.write(
                f"case {item_id}... (trial {trial_cnt}): rubric generation failed."
            )
        else:
            evaluation = eval_manager.evaluate_response(
                prompt,
                options,
                mode=eval_mode,
                augmentation=rubric,
                use_supervision=use_supervision,
            )
    elif eval_mode == "eval_skill":
        evaluation = eval_manager.evaluate_response(
            prompt,
            options,
            mode=eval_mode,
            augmentation=skill_content,
            use_supervision=use_supervision,
        )
    elif eval_mode == "vanilla":
        evaluation = eval_manager.evaluate_response(
            prompt,
            options,
            mode=eval_mode,
            augmentation="",
            use_supervision=use_supervision,
        )
    else:
        raise ValueError(f"Invalid evaluation mode: {eval_mode}")

    if result_status != "Rubric Generation Failed":
        if is_set("JUDGE_THINK"):
            evaluation, evaluation_reasoning = split_think_output(
                evaluation, "evaluation"
            )

        pred = _parse_prediction(evaluation)
        if pred == expected_pred:
            result_status = "Correct"
        elif pred in valid_preds:
            result_status = "Incorrect"
        else:
            result_status = "Unexpected format"
            tqdm.write(
                f"\n=====\nWeird prediction format:\n{evaluation}\n"
                f"Extracted pred: '{pred}'.\n=====\n"
            )

    result = {
        "benchmark": benchmark_name,
        "id": item_id,
        "subset": subset,
        "trial": trial_cnt,
        "prompt": prompt,
        "options": options,
        "expected_pred": expected_pred,
        "rubric": rubric,
        "evaluation": evaluation,
        "prediction": pred,
        "dataset_metadata": item.get("dataset_metadata"),
        "status": result_status,
    }
    if "healthbench_aug" in benchmark_name:
        for key in ["score_a", "score_b", "score_diff"]:
            result[key] = item.get(key)
    for key in ["explanation", "confidence_score"]:
        if item.get(key) is not None:
            result[key] = item[key]
    if eval_mode == "eval_skill":
        result["skill"] = skill_content
    if is_set("RUBRIC_THINK"):
        result["rubric_reasoning"] = rubric_reasoning
    if is_set("JUDGE_THINK"):
        result["evaluation_reasoning"] = evaluation_reasoning

    if use_supervision and super_cache_filepath and not super_cache_filepath.exists():
        super_cache_filepath.parent.mkdir(parents=True, exist_ok=True)
        with super_cache_filepath.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"{item_id}_trial_{trial_cnt}.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(result, f, indent=4, ensure_ascii=False)
    return result


def process_multiple(
    benchmark_name: str,
    benchmark_data,
    trial_num: int,
    output_dir: str | Path,
    eval_mode:str= "vanilla",
    raise_on_error: bool = True,
    rollout_subdir: str | None = None,
) -> int:
    fail_cnt = 0
    eval_manager = get_eval_manager(dataset_name=benchmark_name)
    output_dir = Path(output_dir)
    rollout_dir = output_dir / rollout_subdir if rollout_subdir else output_dir
    rollout_dir.mkdir(parents=True, exist_ok=True)

    results = []
    correct_cnt = incorrect_cnt = bug_cnt = skip_cnt = 0
    to_process = []
    for item in benchmark_data:
        item_id = item["id"]
        for trial_cnt in range(trial_num):
            output_filepath = rollout_dir / f"{item_id}_trial_{trial_cnt}.json"
            legacy_output_filepath = output_dir / f"{item_id}_trial_{trial_cnt}.json"
            existing_filepath = (
                output_filepath
                if output_filepath.exists()
                else legacy_output_filepath
                if rollout_subdir and legacy_output_filepath.exists()
                else None
            )
            if existing_filepath is not None:
                with existing_filepath.open("r", encoding="utf-8") as f:
                    result = json.load(f)
                if rollout_subdir and existing_filepath != output_filepath:
                    with output_filepath.open("w", encoding="utf-8") as f:
                        json.dump(result, f, indent=4, ensure_ascii=False)
                results.append(result)
                rubric = result.get("rubric", "")
                if eval_mode=="rubric_based" and (
                    rubric is None or len(rubric) < 10
                ):
                    to_process.append((item, trial_cnt))
                    continue
                if result.get("status") == "Correct":
                    correct_cnt += 1
                elif result.get("status") == "Incorrect":
                    incorrect_cnt += 1
                else:
                    bug_cnt += 1
            else:
                to_process.append((item, trial_cnt))

    multiple_distraction = use_multiple_distraction(benchmark_name)
    total_trial_count = len(benchmark_data) * trial_num
    completed_trial_count = total_trial_count - len(to_process)
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        futures = [
            executor.submit(
                process_item,
                benchmark_name,
                item,
                trial_cnt,
                multiple_distraction,
                rollout_dir,
                eval_manager,
                eval_mode,
            )
            for item, trial_cnt in to_process
        ]
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=total_trial_count,
            initial=completed_trial_count,
            desc=f"{benchmark_name} trials",
            unit="trial",
        ):
            try:
                result = future.result()
                results.append(result)
                if result.get("status") == "Rubric Generation Failed":
                    skip_cnt += 1
                elif result["status"] == "Correct":
                    correct_cnt += 1
                elif result["status"] == "Incorrect":
                    incorrect_cnt += 1
                else:
                    bug_cnt += 1
                total_valid = correct_cnt + incorrect_cnt
                total = total_valid + bug_cnt + skip_cnt
                if total % 50 == 0 and total_valid > 0:
                    tqdm.write(
                        f"Running accuracy: {correct_cnt / total_valid:.2%} "
                        f"({correct_cnt}/{total_valid}); processed={total}; "
                        f"skipped={skip_cnt}; unexpected={bug_cnt}"
                    )
            except Exception as exc:
                tqdm.write(f"Generated an exception: {exc}")
                if raise_on_error:
                    raise
                fail_cnt += 1

    case_results = defaultdict(list)
    for result in results:
        case_results[result["id"]].append(result["status"])

    maj_correct = maj_incorrect = 0
    for statuses in case_results.values():
        if statuses.count("Correct") > statuses.count("Incorrect"):
            maj_correct += 1
        else:
            maj_incorrect += 1

    with (output_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "total_trials": len(results),
                "total_cases": len(case_results),
                "average_accuracy": (
                    correct_cnt / (correct_cnt + incorrect_cnt)
                    if correct_cnt + incorrect_cnt > 0
                    else None
                ),
                "majority_vote_accuracy": (
                    maj_correct / (maj_correct + maj_incorrect)
                    if maj_correct + maj_incorrect > 0
                    else None
                ),
                "correct_count": correct_cnt,
                "incorrect_count": incorrect_cnt,
                "unexpected_count": bug_cnt,
                "skipped_due_to_rubric_failure": skip_cnt,
                "skipped_due_to_llm_call_failure": fail_cnt,
            },
            f,
            indent=4,
            ensure_ascii=False,
        )
    return fail_cnt


def process_batch(
    benchmark_name: str,
    test_num: int = 0,
    trial_num: int = 3,
    raise_on_error: bool = False,
    rollout_subdir: str | None = None,
    mode: str = "vanilla",
    split_mode: str ="test"
) -> int:
    if mode not in {"vanilla", "rubric_based"}:
        raise ValueError("mode must be 'vanilla' or 'rubric_based'.")
    benchmark_data = get_benchmark(benchmark_name, test_num=test_num)

    if split_mode != "all":
        if split_mode not in {"train", "test"}:
            raise ValueError("split_mode must be one of 'all', 'train', 'test'.")
        if "use" not in benchmark_data.column_names:
            raise ValueError(
                f"{benchmark_name} does not include a 'use' column. Inference "
                "split filtering needs materialized train/test assignments in "
                "the augmented dataset."
            )
        benchmark_data = benchmark_data.filter(
            lambda item: item.get("use") == split_mode
        )
        print(
            f"[process_batch] Using split use == {split_mode}: "
            f"{len(benchmark_data)} rows"
        )

    output_dir = Path(os.environ["RESULT_BASE"]) / os.environ["SETTING_NAME"] / benchmark_name
    return process_multiple(
        benchmark_name,
        benchmark_data,
        trial_num=trial_num,
        output_dir=output_dir,
        eval_mode= mode,
        raise_on_error=raise_on_error,
        rollout_subdir=rollout_subdir,
    )

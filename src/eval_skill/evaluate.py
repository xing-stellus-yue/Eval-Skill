"""Run vanilla or rubric-based evaluation from one clean entry point."""

from __future__ import annotations

import argparse
import os
import time

from .config import (
    load_env_files,
    require_env,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["vanilla", "rubric_based"],
        required=True,
        help="Evaluation mode: plain vanilla judging (one step) or online rubric-based judging (two step).",
    )
    parser.add_argument("--benchmark", "-b", default="rewardbench_aug")
    parser.add_argument("--trial-num", "-t", type=int, default=3)
    parser.add_argument(
        "--test-num",
        type=int,
        default=0,
        help="0 means use the full selected split.",
    )
    parser.add_argument("--result-base", default="results")
    parser.add_argument("--setting-name", default="")
    parser.add_argument(
        "--split",
        choices=["train", "test", "all"],
        default="test",
        help="Dataset split to evaluate. Defaults to the test split.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=["eval_skill.env"],
        help="Env file to load before applying the selected preset.",
    )
    parser.add_argument(
        "--raise-on-error",
        action="store_true",
        help="Propagate the first failed LLM/evaluation call.",
    )
    parser.add_argument(
        "--skip-split-accuracy",
        action="store_true",
        help="Do not write the split-accuracy summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    load_env_files(args.env_file, missing_ok=True)

    required = ["JUDGE_MODEL_NAME", "JUDGE_API_BASE"]
    if args.mode == "rubric_based":
        required.extend(["RUBRIC_MODEL_NAME", "RUBRIC_API_BASE"])
    require_env(required)

    from .accuracy import write_split_accuracy_result
    from .eval_process import get_setting_name, process_batch

    os.environ["SETTING_NAME"] = args.setting_name or get_setting_name(args.mode)
    os.environ["RESULT_BASE"] = args.result_base
    start = time.perf_counter()
    rollout_subdir = "rollouts"
    failed = process_batch(
        args.benchmark,
        test_num=args.test_num,
        trial_num=args.trial_num,
        raise_on_error=args.raise_on_error,
        rollout_subdir=rollout_subdir,
        mode=args.mode,
        split_mode=args.split
    )
    if not args.skip_split_accuracy:
        write_split_accuracy_result(args.benchmark, result_base=args.result_base)

    duration = time.perf_counter() - start
    print(
        f"[evaluate] mode={args.mode} benchmark={args.benchmark} "
        f"setting={os.environ['SETTING_NAME']} failed_trials={failed} "
        f"duration_sec={duration:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the supervised skill_based pipeline with a clean env-driven interface."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .config import (
    load_env_files,
    require_env,
)
from .data import get_benchmark, get_subsets
from .shared_manager import get_eval_manager, get_extraction_manager
from .skill_utils import get_dataset_split_map
from .eval_process import get_setting_name
from .util import load_best_skill


BEST_OF_2_MODES = (
    ("workflow_only", "best_branch", "branch_id", 2),
    ("full", "best_sample", "sample_id", 1),
)


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def build_final_summary(
    subset_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    options = []
    missing_modes = []

    for source, selected_key, output_id_key, priority in BEST_OF_2_MODES:
        mode_result = subset_results.get(source)
        if mode_result is None:
            missing_modes.append(source)
            continue
        if mode_result.get("evo_acc") is None or mode_result.get("test_acc") is None:
            continue

        option = {
            "source": source,
            "evo_acc": mode_result["evo_acc"],
            "test_acc": mode_result["test_acc"],
            "priority": priority,
        }
        selected_id = mode_result.get(selected_key)
        if selected_id is not None:
            option[output_id_key] = selected_id
        options.append(option)

    ranked_options = sorted(
        options,
        key=lambda item: (item["evo_acc"], item["priority"]),
        reverse=True,
    )
    result: dict[str, Any] = {
        "missing_modes": missing_modes,
        "options": [
            {
                **option,
                "evo_acc": _percent(option["evo_acc"]),
                "test_acc": _percent(option["test_acc"]),
            }
            for option in options
        ],
    }
    if ranked_options:
        winner = ranked_options[0]
        result = {
            "best_test_acc": _percent(winner["test_acc"]),
            "winner_source": winner["source"],
            **result,
        }
    return result


def write_final_summary(
    output_dir_subset: Path,
    subset_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summary = build_final_summary(subset_results)
    summary_path = output_dir_subset / "final_adaptive_result.json"
    summary_path.write_text(
        json.dumps(summary, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {**summary, "result_file": str(summary_path)}


def write_final_skill(
    output_dir_subset: Path,
    benchmark_name: str,
    subset_name: str,
    result_base: Path,
    final_summary: dict[str, Any],
) -> dict[str, Any]:
    selected = final_summary["winner_source"]
    skill_meta = load_best_skill(
        benchmark_name,
        subset_name,
        method=selected,
        result_base=str(result_base),
    )
    skill_path = output_dir_subset / "final_adaptive_skill.md"
    skill_path.write_text(
        skill_meta["skill"],
        encoding="utf-8",
    )
    return {
        **skill_meta,
        "method": "adaptive",
        "selected": selected,
        "result_file": str(skill_path),
    }


def _option_test_acc(summary: dict[str, Any], source: str) -> str:
    for option in summary["options"]:
        if option["source"] == source:
            return option["test_acc"]
    return ""


def write_benchmark_final_summary(
    output_dir: Path,
    subset_results: dict[str, dict[str, Any]],
) -> dict[str, str]:
    summaries = {
        subset_name: {
            key: value
            for key, value in result["adaptive"].items()
            if key != "result_file"
        }
        for subset_name, result in sorted(subset_results.items())
    }

    aggregate_path = output_dir / "aggregated_final_adaptive_result.json"
    aggregate_path.write_text(
        json.dumps(summaries, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    subset_names = list(summaries)
    rows = [
        ["method", *subset_names],
        [
            "workflow_only",
            *[
                _option_test_acc(summaries[subset], "workflow_only")
                for subset in subset_names
            ],
        ],
        [
            "full",
            *[_option_test_acc(summaries[subset], "full") for subset in subset_names],
        ],
        [
            "final",
            *[summaries[subset].get("best_test_acc", "") for subset in subset_names],
        ],
    ]
    table_path = output_dir / "final_adaptive_test_acc.tsv"
    table_path.write_text(
        "".join("\t".join(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return {
        "aggregate_file": str(aggregate_path),
        "table_file": str(table_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", "-b", required=True)
    parser.add_argument("--subset", "-s", nargs="+", default=[])
    parser.add_argument(
        "--method",
        "-m",
        choices=["adaptive", "workflow_only", "full"],
        default="adaptive",
        help="Skill search mode to run.",
    )
    parser.add_argument("--evo-set-size", "-e", type=int, default=100)
    parser.add_argument("--result-base", default="results")
    parser.add_argument("--setting-name", default="")
    parser.add_argument("--env-file", action="append", default=["eval_skill.env"])
    parser.add_argument("--min-confidence", type=int, default=8)
    parser.add_argument("--debug", action="store_true")

    parser.add_argument("--init-skill-bs", type=int, default=4)
    parser.add_argument("--init-patch-bs", type=int, default=4)
    parser.add_argument("--merge-bs", type=int, default=4)
    parser.add_argument("--step1a-trials", type=int, default=5)
    parser.add_argument("--step1a-max-round", type=int, default=3)
    parser.add_argument("--step1a-branch-trials", type=int, default=5)
    parser.add_argument("--k-gen", type=int, default=5)
    parser.add_argument("--k-sel", type=int, default=3)
    parser.add_argument("--step1b-trials", type=int, default=5)
    parser.add_argument("--step1b-max-round", type=int, default=3)
    parser.add_argument("--k-smp", type=int, default=5)
    parser.add_argument("--step3-trials", type=int, default=5)
    parser.add_argument("--step3-max-round", type=int, default=1)
    parser.add_argument("--test-trials", type=int, default=3)
    parser.add_argument("--max-subset-workers", type=int, default=5)
    parser.add_argument(
        "--skip-aggregation",
        default=True,
        action="store_true",
        help="Do not write adaptive-selection aggregation files after the pipeline finishes.",
    )
    parser.add_argument(
        "--run-aggregation",
        dest="skip_aggregation",
        action="store_false",
        help="Write adaptive-selection aggregation files after the pipeline finishes.",
    )
    return parser


class SkillPipeline:
    def __init__(self, args: argparse.Namespace):
        self.args = args

        self.dataset_name = args.benchmark
        self.result_base = args.result_base
        os.environ["SETTING_NAME"] = args.setting_name or get_setting_name("eval_skill")
        os.environ["RESULT_BASE"] = args.result_base

        get_eval_manager(dataset_name=self.dataset_name)
        self.dataset = get_benchmark(self.dataset_name)
        self.extraction_manager = get_extraction_manager(
            dataset=self.dataset,
            dataset_name=self.dataset_name,
            return_think=True,
        )

        self.dataset_split_map = get_dataset_split_map(self.dataset)
        self.subset_names = args.subset or get_subsets(self.dataset_name)
        self._validate_train_annotations(self.subset_names)
        self.total_failed_trials = 0
        self.failed_trials_lock = threading.Lock()

        if args.debug:
            args.step1a_trials = 1
            args.step1a_max_round = 2
            args.step1a_branch_trials = 1
            args.k_gen=3
            args.k_sel=3
            args.step1b_trials = 1
            args.step1b_max_round = 2
            args.k_smp=2
            args.step3_trials = 1
            args.step3_max_round = 1
            args.test_trials = 1

    def add_failed_trials(self, count: int) -> None:
        with self.failed_trials_lock:
            self.total_failed_trials += count

    def _validate_train_annotations(self,subset_names) -> None:
        missing_columns = [
            column
            for column in ("explanation", "confidence_score")
            if column not in self.dataset.column_names
        ]
        if missing_columns:
            raise ValueError(
                "Train split annotations are incomplete. Missing dataset column(s): "
                f"{', '.join(missing_columns)}."
            )

        missing_explanation = []
        missing_confidence = []
        train_indices = [
            idx
            for split_map in self.dataset_split_map.values()
            for idx in split_map["evo_indices"]
        ]
        for idx in train_indices:
            item = self.dataset[idx]
            subset=item["subset"]
            if subset not in subset_names:
                continue
            
            item_id = item.get("id", idx)
            explanation = item.get("explanation")
            confidence_score = item.get("confidence_score")
            if not isinstance(explanation, str) or not explanation.strip():
                missing_explanation.append(item_id)
            if (
                confidence_score is None
                or confidence_score == ""
                or confidence_score != confidence_score
            ):
                missing_confidence.append(item_id)

        if missing_explanation or missing_confidence:
            parts = []
            if missing_explanation:
                parts.append(
                    f"{len(missing_explanation)} missing explanation "
                    f"(examples: {missing_explanation[:10]})"
                )
            if missing_confidence:
                parts.append(
                    f"{len(missing_confidence)} missing confidence_score "
                    f"(examples: {missing_confidence[:10]})"
                )
            raise ValueError(
                "Train split annotations are incomplete: " + "; ".join(parts)
            )

    def _filter_evo_indices(self, subset_name: str, evo_indices: list[int]) -> list[int]:
        if "confidence_score" not in self.dataset.column_names:
            return evo_indices
        before = len(evo_indices)
        filtered = [
            idx
            for idx in evo_indices
            if (self.dataset[idx].get("confidence_score") or 0) >= self.args.min_confidence
        ]
        print(
            f"[{subset_name}] Filtered evolving set by confidence_score >= "
            f"{self.args.min_confidence}: {before} -> {len(filtered)}"
        )
        return filtered

    def run(self) -> dict[str, Any]:
        start = time.perf_counter()
        results: dict[str, Any] = {}
        worker_count = min(self.args.max_subset_workers, max(1, len(self.subset_names)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(self.run_on_subset, subset_name): subset_name
                for subset_name in self.subset_names
            }
            for future in concurrent.futures.as_completed(futures):
                subset_name = futures[future]
                results[subset_name] = future.result()

        output_dir = (
            Path(os.environ["RESULT_BASE"])
            / os.environ["SETTING_NAME"]
            / self.dataset_name
        )
        benchmark_final_summary = write_benchmark_final_summary(output_dir, results)
        print(
            "[skill] Benchmark adaptive summary saved to "
            f"{benchmark_final_summary['aggregate_file']} and "
            f"{benchmark_final_summary['table_file']}"
        )

        duration = time.perf_counter() - start
        summary = {
            "benchmark": self.dataset_name,
            "subsets": self.subset_names,
            "method": self.args.method,
            "failed_trials": self.total_failed_trials,
            "duration_sec": duration,
            "subset_results": results,
            "benchmark_final_summary": benchmark_final_summary,
        }
        if self.args.method == "adaptive" and not self.args.skip_aggregation:
            from .skill_aggregation import aggregate_skill_results

            benchmark_dir = Path(self.result_base) / os.environ["SETTING_NAME"] / self.dataset_name
            aggregation = aggregate_skill_results(
                benchmark_dir,
                subset_names=self.subset_names,
            )
            summary["aggregation"] = aggregation
            print(
                "[skill] Aggregation saved: "
                f"{aggregation.get('aggregate_file')} and {aggregation.get('table_file')}"
            )
        summary_path = Path(self.result_base) / os.environ["SETTING_NAME"] / self.dataset_name / "pipeline_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[skill] Summary saved to {summary_path}")
        return summary

    def run_on_subset(self, subset_name: str) -> dict[str, Any]:
        from .skill_steps import (
            run_step1a,
            run_step1b,
            run_step2,
            run_step3,
            run_test,
            summarize_all,
        )

        split_map = self.dataset_split_map[subset_name]
        evo_indices = self._filter_evo_indices(
            subset_name, split_map["evo_indices"]
        )
        test_indices = split_map["test_indices"]
        actual_evo_set_size = len(split_map["evo_indices"])
        if not evo_indices:
            raise ValueError(f"[{subset_name}] No evolving examples after filtering.")

        output_dir = Path(os.environ["RESULT_BASE"]) / os.environ["SETTING_NAME"] / self.dataset_name
        output_dir_subset = output_dir / subset_name
        output_dir_subset.mkdir(parents=True, exist_ok=True)

        output_dir_step1a = output_dir_subset / "step1a_workflow_gen"
        output_dir_step1a.mkdir(parents=True, exist_ok=True)
        local_skills, data_step1a = run_step1a(
            self.dataset,
            evo_indices,
            str(output_dir_step1a),
            self.args.step1a_max_round,
            self.args.step1a_trials,
            self.args.init_skill_bs,
            subset_name,
            self.dataset_name,
            pre_refine_shuffle=True,
            exclude_init=True,
            first_round_supervision=True,
        )

        if len(local_skills) < self.args.k_gen:
            raise ValueError(
                f"[{subset_name}] Only {len(local_skills)} non-empty initial "
                f"skills, fewer than branches={self.args.k_gen}."
            )
        clustered_skills = self.extraction_manager.cluster_skills(
            local_skills, subset_name, self.args.k_gen, str(output_dir_step1a)
        )

        output_step1a_file = output_dir_step1a / "skill_selection_merge.json"
        use_crossover = self.args.k_sel > 2
        if output_step1a_file.exists():
            payload = json.loads(output_step1a_file.read_text(encoding="utf-8"))
            branch_results = payload.get(
                "all_branch_results", payload["top_k_branches"]
            )
            branch_results.sort(key=lambda item: item["acc"], reverse=True)
        else:
            branch_results = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.args.k_gen
            ) as executor:
                futures = {
                    executor.submit(
                        run_test,
                        self.dataset,
                        evo_indices,
                        cwf["skill"],
                        str(output_dir_step1a / f"branch_{i}_evo_rollouts"),
                        self.args.step1a_branch_trials,
                        self.dataset_name,
                    ): i
                    for i, cwf in enumerate(clustered_skills)
                }
                for future in concurrent.futures.as_completed(futures):
                    i = futures[future]
                    try:
                        test_results = future.result()
                        acc = test_results["test_acc"]
                    except Exception as exc:
                        print(f"[{subset_name}] branch {i} evo test failed: {exc}")
                        acc = 0.0
                    branch_results.append(
                        {
                            "branch_id": i,
                            "skill": clustered_skills[i]["skill"],
                            "acc": acc,
                        }
                    )

            branch_results.sort(key=lambda item: item["acc"], reverse=True)

        if use_crossover:
            top_k_branches = branch_results[: self.args.k_sel - 1]
            print(
                f"[{subset_name}] Merging top {self.args.k_sel - 1} "
                "to create an optimal variant..."
            )
            cached_branch_ids = (
                [
                    branch["branch_id"]
                    for branch in payload.get("top_k_branches", [])
                ]
                if output_step1a_file.exists()
                else []
            )
            selected_branch_ids = [
                branch["branch_id"] for branch in top_k_branches
            ]
            if (
                output_step1a_file.exists()
                and payload.get("merged_skill")
                and cached_branch_ids == selected_branch_ids
            ):
                skill_merge = payload["merged_skill"]
                reasoning = payload.get("reasoning")
            else:
                skill_merge, reasoning = self.extraction_manager.merge_top_k_skills(
                    top_k_branches
                )
            selected_branches = top_k_branches + [
                {"branch_id": "x", "skill": skill_merge, "acc": 0.0}
            ]
        else:
            top_k_branches = branch_results[: self.args.k_sel]
            skill_merge = None
            reasoning = None
            selected_branches = top_k_branches
            print(
                f"[{subset_name}] k_sel={self.args.k_sel}; skipping skill crossover."
            )

        output_step1a_file.write_text(
            json.dumps(
                {
                    "k_sel": self.args.k_sel,
                    "crossover_enabled": use_crossover,
                    "top_k_branches": top_k_branches,
                    "merged_skill": skill_merge,
                    "reasoning": reasoning,
                    "all_branch_results": branch_results,
                },
                indent=4,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        subset_summary: dict[str, Any] = {}
        if self.args.method in {"workflow_only", "adaptive"}:
            subset_summary["workflow_only"] = self.run_workflow_only_method(
                subset_name,
                output_dir_subset,
                output_dir_step1a,
                evo_indices,
                test_indices,
                selected_branches,
                skill_merge,
                data_step1a,
                actual_evo_set_size,
                run_test,
                summarize_all,
            )
        if self.args.method in {"full", "adaptive"}:
            subset_summary["full"] = self.run_full_method(
                subset_name,
                output_dir_subset,
                evo_indices,
                test_indices,
                selected_branches,
                data_step1a,
                actual_evo_set_size,
                run_step1b,
                run_step2,
                run_step3,
                run_test,
                summarize_all,
            )
        subset_summary["adaptive"] = write_final_summary(
            output_dir_subset,
            subset_summary,
        )
        final_skill = write_final_skill(
            output_dir_subset,
            self.dataset_name,
            subset_name,
            output_dir.parent,
            subset_summary["adaptive"],
        )
        subset_summary["adaptive_skill"] = {
            "selected": final_skill["selected"],
            "score": final_skill["score"],
            "result_file": final_skill["result_file"],
        }
        print(
            f"[{subset_name}] Final adaptive summary saved to "
            f"{subset_summary['adaptive']['result_file']}; skill saved to "
            f"{final_skill['result_file']}"
        )
        return subset_summary

    def run_workflow_only_method(
        self,
        subset_name: str,
        output_dir_subset: Path,
        output_dir_step1a: Path,
        evo_indices: list[int],
        test_indices: list[int],
        top_k_branches: list[dict[str, Any]],
        skill_crossover: str | None,
        data_step1a: dict[str, Any],
        actual_evo_set_size: int,
        run_test,
        summarize_all,
    ) -> dict[str, Any]:
        workflow_candidates = [
            {
                "branch_id": branch["branch_id"],
                "evo_acc": branch["acc"],
                "skill": branch["skill"],
            }
            for branch in top_k_branches
            if branch["branch_id"] != "x"
        ]
        if skill_crossover is not None:
            cross_eval = run_test(
                self.dataset,
                evo_indices,
                skill_crossover,
                str(output_dir_step1a / "branch_x_evo_rollouts"),
                self.args.step1a_branch_trials,
                self.dataset_name,
            )
            workflow_candidates.append(
                {
                    "branch_id": "x",
                    "evo_acc": cross_eval["test_acc"],
                    "skill": skill_crossover,
                }
            )
        (output_dir_step1a / "top_k_sel_skills.json").write_text(
            json.dumps(workflow_candidates, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        
        # Score first, then sort to ensure stable tie-breaking by branch_id string
        best_workflow = sorted(
            workflow_candidates,
            key=lambda item: (-item.get("evo_acc", -1.0), str(item.get("branch_id"))),
        )[0]

        output_dir_test = (
            output_dir_subset / f"test_best_workflow_only_skill_b{best_workflow['branch_id']}"
        )
        final_rollouts = output_dir_test / "rollouts"
        final_rollouts.mkdir(parents=True, exist_ok=True)
        data_test = run_test(
            self.dataset,
            test_indices,
            best_workflow["skill"],
            str(final_rollouts),
            self.args.test_trials,
            self.dataset_name,
        )
        self.add_failed_trials(data_test["test_failed_cnt"])
        best_workflow["test_acc"] = data_test["test_acc"]

        result_file = output_dir_test / "final_workflow_only_result.json"
        result_payload = summarize_all(
            data_step1a,
            {},
            {},
            data_test,
            str(result_file),
            subset_name,
            actual_evo_set_size,
        )
        result_file.write_text(
            json.dumps(result_payload, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )
        
        analysis = [dict(item, skill=None) for item in workflow_candidates]
        (output_dir_subset / "workflow_only_analysis_result.json").write_text(
            json.dumps(analysis, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return {
            "best_branch": best_workflow["branch_id"],
            "evo_acc": best_workflow["evo_acc"],
            "test_acc": best_workflow["test_acc"],
            "result_file": str(result_file),
        }

    def run_full_method(
        self,
        subset_name: str,
        output_dir_subset: Path,
        evo_indices: list[int],
        test_indices: list[int],
        top_k_branches: list[dict[str, Any]],
        data_step1a: dict[str, Any],
        actual_evo_set_size: int,
        run_step1b,
        run_step2,
        run_step3,
        run_test,
        summarize_all,
    ) -> dict[str, Any]:
        def run_branch_step1b(bid, skill):
            output_dir_step1b = output_dir_subset / "step1b_principle_gen" / f"full_branch_{bid}"
            output_dir_step1b.mkdir(parents=True, exist_ok=True)
            skills, _ = run_step1b(
                self.dataset,
                evo_indices,
                str(output_dir_step1b),
                self.args.step1b_max_round,
                self.args.step1b_trials,
                self.args.init_skill_bs,
                subset_name,
                self.dataset_name,
                init_skill=skill,
                exclude_init=True,
                failed_only=True,
            )
            return skills

        skills_map = defaultdict(dict)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(5, len(top_k_branches))
        ) as executor:
            futures = {
                executor.submit(run_branch_step1b, branch["branch_id"], branch["skill"]): branch
                for branch in top_k_branches
            }
            for future in concurrent.futures.as_completed(futures):
                branch = futures[future]
                skills = future.result()
                if not skills:
                    skills = [branch["skill"]]
                skills_map[branch["branch_id"]] = skills

        def run_sample_trial(bid, sample_idx):
            local_skills = skills_map[bid]
            sid = f"b{bid}_s{sample_idx}"
            output_dir_branch = output_dir_subset / f"full_sample_{sid}"
            output_dir_step2 = output_dir_branch / "step2_merge"
            output_dir_step2.mkdir(parents=True, exist_ok=True)
            rng = random.Random(42 + sample_idx)
            shuffled = rng.sample(local_skills, len(local_skills))
            skill, data_step2 = run_step2(
                shuffled, str(output_dir_step2), self.args.merge_bs, self.dataset_name
            )
            output_dir_step3 = output_dir_branch / "step3_run_on_evo_set"
            output_dir_step3.mkdir(parents=True, exist_ok=True)
            final_skill, data_step3 = run_step3(
                self.dataset,
                evo_indices,
                skill,
                str(output_dir_step3),
                self.args.step3_max_round,
                self.args.step3_trials,
                self.args.init_patch_bs,
                self.args.merge_bs,
                subset_name,
                self.dataset_name,
            )
            return {
                "sample_id": sid,
                "evo_acc": data_step3["best_acc"],
                "final_skill": final_skill,
                "data_step2": data_step2,
                "data_step3": data_step3,
            }

        agg_results = defaultdict(dict)
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(5, len(top_k_branches))
        ) as executor:
            futures = {
                executor.submit(run_sample_trial, branch["branch_id"], 0): branch["branch_id"]
                for branch in top_k_branches
            }
            for future in concurrent.futures.as_completed(futures):
                bid = futures[future]
                agg_results[bid][0] = future.result()

        pass1_candidates = [
            {"branch_id": bid, "evo_acc": results[0].get("evo_acc", -1.0)}
            for bid, results in agg_results.items()
        ]
        best_bid = sorted(
            pass1_candidates,
            key=lambda item: (-item.get("evo_acc", -1.0), str(item.get("branch_id"))),
        )[0]["branch_id"]

        if self.args.k_smp > 1:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(5, self.args.k_smp - 1)
            ) as executor:
                futures = {
                    executor.submit(run_sample_trial, best_bid, sample_idx): sample_idx
                    for sample_idx in range(1, self.args.k_smp)
                }
                for future in concurrent.futures.as_completed(futures):
                    sample_idx = futures[future]
                    agg_results[best_bid][sample_idx] = future.result()

        flat = [
            result
            for _, inner in sorted(agg_results.items(), key=lambda item: str(item[0]))
            for _, result in sorted(inner.items(), key=lambda item: str(item[0]))
        ]
        best_sample = max(flat, key=lambda item: item.get("evo_acc", -1.0))
        output_dir_test = (
            output_dir_subset
            / f"test_best_full_skill_{best_sample['sample_id']}"
        )
        final_rollouts = output_dir_test / "rollouts"
        final_rollouts.mkdir(parents=True, exist_ok=True)
        data_test = run_test(
            self.dataset,
            test_indices,
            best_sample["final_skill"],
            str(final_rollouts),
            self.args.test_trials,
            self.dataset_name,
        )
        self.add_failed_trials(data_test["test_failed_cnt"])
        best_sample["test_acc"] = data_test["test_acc"]

        result_file = output_dir_test / "final_full_result.json"
        result_payload = summarize_all(
            data_step1a,
            best_sample["data_step2"],
            best_sample["data_step3"],
            data_test,
            str(result_file),
            subset_name,
            actual_evo_set_size,
        )
        result_file.write_text(
            json.dumps(result_payload, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

        analysis = []
        for result in flat:
            item = dict(result)
            item.pop("final_skill", None)
            item.pop("data_step2", None)
            item.pop("data_step3", None)
            analysis.append(item)
        (output_dir_subset / "full_analysis_result.json").write_text(
            json.dumps(analysis, indent=4, ensure_ascii=False), encoding="utf-8"
        )
        return {
            "best_sample": best_sample["sample_id"],
            "evo_acc": best_sample["evo_acc"],
            "test_acc": best_sample["test_acc"],
            "result_file": str(result_file),
        }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.k_sel < 1:
        raise ValueError("k-sel must be at least 1.")

    load_env_files(args.env_file, missing_ok=True)
    require_env(
        [
            "EXTRACTION_MODEL_NAME",
            "EXTRACTION_API_BASE",
            "JUDGE_MODEL_NAME",
            "JUDGE_API_BASE",
        ]
    )
    SkillPipeline(args).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

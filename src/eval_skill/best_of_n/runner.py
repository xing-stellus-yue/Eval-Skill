import argparse
import json
import os
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from .candidate_cache import (
    load_candidate_cache,
    load_rm_selection_cache,
    save_candidate_cache,
    save_rm_selection_cache,
)
from .summary import write_summary_file
from ..config import (
    load_env_files,
    require_env,
)
from ..data import get_benchmark, get_subset_description, get_subsets
from ..managers.eval_manager import EvalManager
from ..managers.extraction_manager import ExtractionManager
from ..managers.generation_manager import GenerationManager
from ..prompts.best_of_n import FINAL_COMPARISON_PROMPT
from ..shared_manager import (
    get_eval_manager,
    get_extraction_manager,
    get_generation_manager,
)
from ..skill_utils import get_dataset_split_map
from ..util import load_best_skill

load_env_files([os.getenv("EVAL_SKILL_ENV_FILE", "eval_skill.env")])
FINAL_COMPARISON_PROMPT_MODE = "subset_context"


def progress(iterable, total=None, desc=""):
    if tqdm is None:
        return iterable
    return tqdm(iterable, total=total, desc=desc)


@dataclass
class Candidate:
    text: str
    idx: int


def generate_candidates(
    generation_manager: GenerationManager,
    question: str,
    n: int,
    candidate_workers: int,
) -> list[Candidate]:
    def one(i: int) -> Candidate:
        text = generation_manager.predict(question)
        return Candidate(text=text, idx=i)

    worker_count = min(n, max(1, candidate_workers))
    if worker_count == 1:
        return [one(i) for i in range(n)]

    candidates = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(one, i) for i in range(n)]
        for future in as_completed(futures):
            candidates.append(future.result())
    return candidates


def parse_winner(evaluation: str, valid_preds: list[str]) -> Optional[str]:
    pattern = r"Winner:\s*(?:(?:Response|Candidate)\s*)?(Tie|[A-Z])\b"
    matches = re.findall(pattern, evaluation, flags=re.I)
    for match in reversed(matches):
        pred = match.upper()
        if pred == "TIE":
            pred = "Tie"
        if pred in valid_preds:
            return pred

    pred = (
        evaluation.rsplit("Final Decision", 1)[-1]
        .rsplit("Final Judgment", 1)[-1]
        .split("Winner", 1)[-1]
        .split("Response", 1)[-1]
        .split("Candidate", 1)[-1]
    )
    pred = (
        pred.replace("*", "").replace(":", "").replace(".", "").replace(" ", "").strip()
    )
    if len(pred) > 1:
        pred = pred[0]
    return pred if pred in valid_preds else None


class KnockoutSelector:
    def __init__(
        self,
        eval_manager: EvalManager,
        seed: int,
        mode: str,
        skill: str = "",
    ):
        self.eval_manager = eval_manager
        self.rng = random.Random(seed)
        self.mode = mode
        self.skill = skill
        self.bye_counts: dict[int, int] = {}

    def make_pairs(
        self, pool: list[Candidate]
    ) -> tuple[list[tuple[Candidate, Candidate]], list[Candidate]]:
        shuffled = pool[:]
        self.rng.shuffle(shuffled)
        byes = []
        if len(shuffled) % 2 == 1:
            min_bye_count = min(self.bye_counts.get(c.idx, 0) for c in shuffled)
            least_byes = [
                c for c in shuffled if self.bye_counts.get(c.idx, 0) == min_bye_count
            ]
            bye = self.rng.choice(least_byes)
            shuffled.remove(bye)
            self.bye_counts[bye.idx] = self.bye_counts.get(bye.idx, 0) + 1
            byes.append(bye)
        pairs = [(shuffled[i], shuffled[i + 1]) for i in range(0, len(shuffled), 2)]
        return pairs, byes

    def evaluate_pair(self, question: str, a: Candidate, b: Candidate) -> str:
        options = [a.text, b.text]
        return self.evaluate_candidates(question,options)


    def evaluate_candidates(self, question: str, candidates: list[Candidate]) -> str:
        options = [candidate.text for candidate in candidates]
        if self.mode == "skill":
            return self.eval_manager.evaluate_response(
                question, options,self.mode, self.skill, use_supervision=False
            )
        if self.mode == "vanilla":
            return self.eval_manager.evaluate_response(
                question, options,self.mode,"",  use_supervision=False
            )
        raise ValueError(f"Unknown selector mode: {self.mode}")
    

    def select_direct(
        self, question: str, candidates: list[Candidate]
    ) -> tuple[Optional[Candidate], list[dict]]:
        candidate_order = candidates[:]
        self.rng.shuffle(candidate_order)
        labels = [chr(ord("A") + i) for i in range(len(candidate_order))]
        out = ""
        pred = None
        for _ in range(3):
            out = self.evaluate_candidates(question, candidate_order)
            pred = parse_winner(out, labels)
            if pred is not None:
                break

        if pred is None:
            winner = self.rng.choice(candidate_order)
        else:
            winner = candidate_order[labels.index(pred)]

        return winner, [
            {
                "mode": "direct",
                "prediction": pred,
                "winner_idx": None if winner is None else winner.idx,
                "order": [
                    {"option": label, "candidate_idx": candidate.idx}
                    for label, candidate in zip(labels, candidate_order)
                ],
                "rm_output": out,
            }
        ]

    def select_random(
        self, candidates: list[Candidate]
    ) -> tuple[Optional[Candidate], list[dict]]:
        if not candidates:
            return None, []
        winner = self.rng.choice(candidates)
        return winner, [
            {
                "mode": "random",
                "prediction": None,
                "winner_idx": winner.idx,
                "rm_output": "",
            }
        ]

    def compare(
        self, question: str, a: Candidate, b: Candidate
    ) -> tuple[Optional[Candidate], dict]:
        out = ""
        pred = None
        for _ in range(3):
            out = self.evaluate_pair(question, a, b)
            pred = parse_winner(out, ["A", "B"])
            if pred is not None:
                break
        if pred == "A":
            winner = a
        elif pred == "B":
            winner = b
        else:
            winner = self.rng.choice([a, b])

        return winner, {
            "a_idx": a.idx,
            "b_idx": b.idx,
            "prediction": pred,
            "winner_idx": None if winner is None else winner.idx,
            "rm_output": out,
        }

    def knockout(
        self, question: str, candidates: list[Candidate]
    ) -> tuple[Optional[Candidate], list[dict]]:
        pool = candidates[:]
        history = []
        round_id = 0
        while len(pool) > 1:
            pairs, byes = self.make_pairs(pool)
            results = []
            with ThreadPoolExecutor(max_workers=min(len(pairs) + 1, 8)) as executor:
                future_to_pair = {
                    executor.submit(self.compare, question, a, b): (a, b)
                    for a, b in pairs
                }
                for future in as_completed(future_to_pair):
                    results.append(future.result())

            next_pool = byes[:]
            matches = []
            for winner, match_log in results:
                matches.append(match_log)
                if winner is not None:
                    next_pool.append(winner)

            history.append(
                {
                    "round": round_id,
                    "num_pool_before": len(pool),
                    "num_pairs": len(pairs),
                    "num_byes": len(byes),
                    "num_pool_after": len(next_pool),
                    "matches": matches,
                }
            )
            pool = next_pool
            round_id += 1

            if not pool:
                return None, history

        return pool[0], history


def final_compare(
    extraction_manager: ExtractionManager,
    question: str,
    reference_answer: str,
    response_a: str,
    response_b: str,
    subset: str = "",
    subset_description: str = "",
) -> tuple[Optional[str], str]:
    del reference_answer
    if not subset or not subset_description:
        raise ValueError("Final comparison requires subset and subset_description.")
    prompt = FINAL_COMPARISON_PROMPT.format(
        subset=subset,
        subset_description=subset_description,
        question=question,
        response_a=response_a,
        response_b=response_b,
    )
    out = ""
    pred = None
    for _ in range(3):
        out = extraction_manager.call_extraction_llm(prompt).content
        pred = parse_winner(out, ["A", "B", "Tie"])
        if pred is not None:
            break
    return pred, out


def candidate_by_idx(candidates: list[Candidate], idx) -> Optional[Candidate]:
    for candidate in candidates:
        if candidate.idx == idx:
            return candidate
    return None


def run_selector_with_cache(
    selector: KnockoutSelector,
    question: str,
    candidates: list[Candidate],
    selection_mode: str,
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    runner: str,
    generation_model: str,
    rm_model: str,
    skill_source: str = "",
    source: str = "",
) -> tuple[Optional[Candidate], list[dict]]:
    cached = load_rm_selection_cache(
        cache_dir,
        benchmark,
        case_id,
        trial,
        runner,
        selection_mode,
        rm_model=rm_model,
        generation_model=generation_model,
        skill_source=skill_source,
    )
    if cached is not None:
        best = candidate_by_idx(candidates, cached.get("selected_idx"))
        if best is None and cached.get("selected_response") is not None:
            best = Candidate(text=cached["selected_response"], idx=cached.get("selected_idx"))
        return best, cached.get("history", [])

    if selection_mode == "direct":
        best, history = selector.select_direct(question, candidates)
    elif selection_mode == "random":
        best, history = selector.select_random(candidates)
    else:
        best, history = selector.knockout(question, candidates)

    cache_path = save_rm_selection_cache(
        cache_dir,
        benchmark,
        case_id,
        trial,
        runner,
        selection_mode,
        None if best is None else best.idx,
        None if best is None else best.text,
        history,
        rm_model=rm_model,
        generation_model=generation_model,
        skill_source=skill_source,
        source=source,
    )
    print(f"  [rm_selection_cache] saved {runner}: {cache_path}")
    return best, history


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare skill and vanilla RM runners on the same cached candidates."
    )
    parser.add_argument("--benchmark", "-b", required=True)
    parser.add_argument("--subset", "-s", nargs="+", default=[])
    parser.add_argument("--trial-num", "-t", type=int, default=3)
    parser.add_argument(
        "--sample-num",
        type=int,
        default=0,
        help="0 means use all test cases; otherwise sample this many per subset.",
    )
    parser.add_argument("--candidate-num", "-n", type=int, default=8)
    parser.add_argument("--candidate-workers", type=int, default=16)
    parser.add_argument("--evo-set-size", "-e", type=int, default=100)
    parser.add_argument(
        "--method",
        "-m",
        choices=["adaptive", "workflow_only", "full"],
        default="adaptive",
    )
    parser.add_argument(
        "--result-base",
        type=str,
        default="result",
        help="Directory containing skill pipeline outputs.",
    )
    parser.add_argument(
        "--env-file",
        action="append",
        default=[os.getenv("EVAL_SKILL_ENV_FILE", "eval_skill.env")],
    )
    parser.add_argument(
        "--candidate-cache-dir",
        type=str,
        default="caches/best_of_n_candidates",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="Output directory. Defaults to results/best_of_n/compare_results/<run_name>.",
    )
    parser.add_argument("--max-workers", type=int, default=64)
    parser.add_argument(
        "--generation-timeout",
        type=float,
        default=120,
        help="Per-request timeout in seconds for candidate generation.",
    )
    parser.add_argument(
        "--rm-selection-mode",
        choices=["pairwise", "direct", "random"],
        default="pairwise",
        help=(
            "pairwise uses knockout RM selection; direct asks each RM to choose "
            "among all candidates once; random compares skill RM selection against "
            "a random baseline."
        ),
    )
    args = parser.parse_args(argv)
    load_env_files(args.env_file, missing_ok=True)
    require_env(
        [
            "EXTRACTION_MODEL_NAME",
            "EXTRACTION_API_BASE",
            "GENERATION_MODEL_NAME",
            "GENERATION_API_BASE",
            "JUDGE_MODEL_NAME",
            "JUDGE_API_BASE",
        ]
    )
    os.environ["GENERATION_TIMEOUT"] = str(args.generation_timeout)
    generation_model_name = os.getenv("GENERATION_MODEL_NAME", "unknown_generation_model")
    rm_model_name = os.getenv("JUDGE_MODEL_NAME", "unknown_rm_model")

    dataset = get_benchmark(args.benchmark)
    subset_names = args.subset or get_subsets(args.benchmark)
    dataset_split_map = get_dataset_split_map(dataset)

    test_cases = []
    for subset_name in subset_names:
        subset_indices = dataset_split_map[subset_name]["test_indices"]
        if args.sample_num > 0:
            subset_indices = subset_indices[: args.sample_num]
        test_cases.extend(dataset[idx] for idx in subset_indices)

    eval_manager = get_eval_manager(dataset_name=args.benchmark)
    extraction_manager = get_extraction_manager(dataset=dataset, dataset_name=args.benchmark,return_think=True)
    generation_manager = get_generation_manager(dataset_name=args.benchmark)

    skill_meta_by_subset = {}
    for subset_name in subset_names:
        skill_meta_by_subset[subset_name] = load_best_skill(
            args.benchmark,
            subset_name,
            args.method,
            result_base=args.result_base,
        )

    subset_tag = "_".join(args.subset) if args.subset else "all_subsets"
    out_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("results")
        / "best_of_n"
        / (
            "compare_results"
            + (
                ""
                if args.rm_selection_mode == "pairwise"
                else f"_rm_{args.rm_selection_mode}"
            )
        )
        / f"{args.benchmark}_{subset_tag}_{args.method}"
    )
    rollout_dir = out_dir / "rollouts"
    rollout_dir.mkdir(parents=True, exist_ok=True)

    jobs = [
        (sample_idx, trial_cnt, item)
        for sample_idx, item in enumerate(test_cases)
        for trial_cnt in range(args.trial_num)
    ]
    print(
        f"[setup] Comparing {len(jobs)} rollouts "
        f"({len(test_cases)} samples x {args.trial_num} trials)"
    )
    print(f"[setup] Candidate cache: {args.candidate_cache_dir}")
    print(f"[setup] Output dir: {out_dir}")
    print(f"[setup] Subsets: {', '.join(subset_names)}")
    print(f"[setup] RM selection mode: {args.rm_selection_mode}")

    def process_one(sample_idx, trial_cnt, item):
        case_id = item["id"]
        subset = item["subset"]
        question = item["prompt"]
        reference_answer = item.get("response_a", "")
        try:
            subset_description = get_subset_description(args.benchmark, subset)
        except ValueError:
            subset_description = ""
        prefix = f"[case {sample_idx+1}/{len(test_cases)} trial {trial_cnt+1}/{args.trial_num}]"
        out_path = rollout_dir / f"compare_{sample_idx}_trial_{trial_cnt}.json"
        if out_path.exists():
            with open(out_path, "r", encoding="utf-8") as f:
                result = json.load(f)
            print(f"{prefix} Loaded existing result: {out_path}")
            return result

        cached = load_candidate_cache(
            args.candidate_cache_dir,
            args.benchmark,
            case_id,
            trial_cnt,
            expected_n=args.candidate_num,
            generation_model=generation_model_name,
        )
        if cached is None:
            candidates = generate_candidates(
                generation_manager,
                question,
                args.candidate_num,
                args.candidate_workers,
            )
            cache_path = save_candidate_cache(
                args.candidate_cache_dir,
                args.benchmark,
                case_id,
                trial_cnt,
                question,
                [asdict(candidate) for candidate in candidates],
                source=str(out_path),
                generation_model=generation_model_name,
            )
            print(f"{prefix} generated candidates and saved cache: {cache_path}")
        else:
            candidates = [Candidate(**candidate) for candidate in cached]
        selector_seed = 42 + sample_idx * args.trial_num + trial_cnt
        skill_selector = KnockoutSelector(
            eval_manager,
            seed=selector_seed,
            mode="skill",
            skill=skill_meta_by_subset[subset]["skill"],
        )
        vanilla_selector = KnockoutSelector(
            eval_manager,
            seed=(
                selector_seed
                if args.rm_selection_mode != "random"
                else selector_seed + 1000003
            ),
            mode="vanilla",
        )

        skill_source = skill_meta_by_subset[subset].get("source", "")
        skill_selection_mode = (
            "pairwise" if args.rm_selection_mode == "random" else args.rm_selection_mode
        )
        vanilla_selection_mode = args.rm_selection_mode
        skill_best, skill_history = run_selector_with_cache(
            skill_selector,
            question,
            candidates,
            skill_selection_mode,
            args.candidate_cache_dir,
            args.benchmark,
            case_id,
            trial_cnt,
            runner="skill",
            generation_model=generation_model_name,
            rm_model=rm_model_name,
            skill_source=skill_source,
            source=str(out_path),
        )
        vanilla_best, vanilla_history = run_selector_with_cache(
            vanilla_selector,
            question,
            candidates,
            vanilla_selection_mode,
            args.candidate_cache_dir,
            args.benchmark,
            case_id,
            trial_cnt,
            runner="vanilla",
            generation_model=generation_model_name,
            rm_model=rm_model_name,
            source=str(out_path),
        )

        final_winner = None
        final_winner_runner = None
        final_judge_evaluation = None
        final_compare_order = []
        final_winner_idx = None
        if skill_best is not None and vanilla_best is not None:
            if skill_best.idx == vanilla_best.idx or skill_best.text == vanilla_best.text:
                final_winner = None
                final_winner_runner = "tie"
                final_judge_evaluation = None
                final_winner_idx = skill_best.idx
                final_compare_order = [
                    {
                        "runner": "skill",
                        "candidate_idx": skill_best.idx,
                    },
                    {
                        "runner": "vanilla",
                        "candidate_idx": vanilla_best.idx,
                    },
                ]
            else:
                final_compare_order = [
                    {
                        "runner": "skill",
                        "candidate_idx": skill_best.idx,
                        "response": skill_best.text,
                    },
                    {
                        "runner": "vanilla",
                        "candidate_idx": vanilla_best.idx,
                        "response": vanilla_best.text,
                    },
                ]
                order_rng = random.Random(
                    f"{case_id}:{trial_cnt}:final_compare:{args.benchmark}"
                )
                order_rng.shuffle(final_compare_order)
                final_winner, final_judge_evaluation = final_compare(
                    extraction_manager,
                    question,
                    reference_answer,
                    final_compare_order[0]["response"],
                    final_compare_order[1]["response"],
                    subset=subset,
                    subset_description=subset_description,
                )
                if final_winner == "A":
                    final_winner_runner = final_compare_order[0]["runner"]
                    final_winner_idx = final_compare_order[0]["candidate_idx"]
                elif final_winner == "B":
                    final_winner_runner = final_compare_order[1]["runner"]
                    final_winner_idx = final_compare_order[1]["candidate_idx"]
                elif final_winner == "Tie":
                    final_winner_runner = "tie"

        result = {
            "status": "ok",
            "final_compare": {
                "winner_runner": final_winner_runner,
                "winner": final_winner,
                "winner_idx": final_winner_idx,
                "selection_mode": "pairwise_between_rm_winners",
                "prompt_mode": FINAL_COMPARISON_PROMPT_MODE,
                "subset": subset,
                "subset_description": subset_description,
                "order": [
                    {
                        "option": chr(ord("A") + i),
                        "runner": item["runner"],
                        "candidate_idx": item["candidate_idx"],
                    }
                    for i, item in enumerate(final_compare_order)
                ],
                "evaluation": final_judge_evaluation,
            },
            "question": question,
            "reference_answer": reference_answer,
            "sample_idx": sample_idx,
            "trial": trial_cnt,
            "original_id": case_id,
            "subset": subset,
            "candidate_cache_key": {
                "benchmark": args.benchmark,
                "case_id": case_id,
                "trial": trial_cnt,
                "generation_model": generation_model_name,
            },
            "skill_runner": {
                "best_idx": None if skill_best is None else skill_best.idx,
                "best_response": None if skill_best is None else skill_best.text,
                "selection_mode": skill_selection_mode,
                "history": skill_history,
            },
            "vanilla_runner": {
                "best_idx": None if vanilla_best is None else vanilla_best.idx,
                "best_response": None if vanilla_best is None else vanilla_best.text,
                "selection_mode": vanilla_selection_mode,
                "history": vanilla_history,
            },
            "candidates": [asdict(candidate) for candidate in candidates],
            "skill_source": {
                key: value
                for key, value in skill_meta_by_subset[subset].items()
                if key != "skill"
            },
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(
            f"{prefix} skill_best={result['skill_runner']['best_idx']} "
            f"vanilla_best={result['vanilla_runner']['best_idx']} "
            f"winner={result['final_compare']['winner_runner']}"
        )
        return result

    results = []
    worker_count = min(args.max_workers, max(len(jobs), 1))
    if worker_count == 1:
        for job in progress(jobs, total=len(jobs), desc="compare"):
            results.append(process_one(*job))
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(process_one, *job): job for job in jobs}
            for future in progress(
                as_completed(futures), total=len(futures), desc="compare"
            ):
                results.append(future.result())

    ok_results = [r for r in results if r.get("status") == "ok"]
    missing_cnt = sum(
        1 for r in results if r.get("status") == "missing_candidate_cache"
    )
    skill_wins = sum(
        1
        for r in ok_results
        if r.get("final_compare", {}).get("winner_runner") == "skill"
    )
    vanilla_wins = sum(
        1
        for r in ok_results
        if r.get("final_compare", {}).get("winner_runner") == "vanilla"
    )
    tie_wins = sum(
        1
        for r in ok_results
        if r.get("final_compare", {}).get("winner_runner") == "tie"
    )
    unknown_wins = len(ok_results) - skill_wins - vanilla_wins - tie_wins
    same_choice = sum(
        1
        for r in ok_results
        if r["skill_runner"]["best_idx"] == r["vanillala_runner"]["best_idx"]
    )

    summary = {
        "results": {
            "total_jobs": len(jobs),
            "ok": len(ok_results),
            "missing_candidate_cache": missing_cnt,
            "skill_wins": skill_wins,
            "vanilla_wins": vanilla_wins,
            "tie_wins": tie_wins,
            "unknown_wins": unknown_wins,
            "same_final_choice": same_choice,
            "different_final_choice": len(ok_results) - same_choice,
            "skill_win_rate": skill_wins / len(ok_results) if ok_results else None,
            "vanilla_win_rate": vanilla_wins / len(ok_results) if ok_results else None,
        },
        "metadata": {
            "benchmark": args.benchmark,
            "subsets": subset_names,
            "sample_num": len(test_cases),
            "sample_num_per_subset": args.sample_num,
            "trial_num": args.trial_num,
            "candidate_num": args.candidate_num,
            "candidate_workers": args.candidate_workers,
            "candidate_cache_dir": args.candidate_cache_dir,
            "generation_model": generation_model_name,
            "rm_model": rm_model_name,
            "generation_timeout": args.generation_timeout,
            "method": args.method,
            "final_compare_prompt_mode": FINAL_COMPARISON_PROMPT_MODE,
            "rm_selection_mode": args.rm_selection_mode,
            "output_dir": str(out_dir),
            "selected_sample_ids": [item.get("id") for item in test_cases],
            "skill_sources": {
                subset: {
                    key: value
                    for key, value in skill_meta.items()
                    if key != "skill"
                }
                for subset, skill_meta in skill_meta_by_subset.items()
            },
        },
    }
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    compare_summary_path = out_dir / "compare_summary.txt"
    write_summary_file(rollout_dir, compare_summary_path)
    print(f"[main] Summary saved to {summary_path}")
    print(f"[main] Compare summary saved to {compare_summary_path}")
    print(
        f"[main] skill_wins={skill_wins}, vanilla_wins={vanilla_wins}, "
        f"tie={tie_wins}, unknown={unknown_wins}, ok={len(ok_results)}, "
        f"missing_cache={missing_cnt}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

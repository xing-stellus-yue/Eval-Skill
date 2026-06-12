"""Cache helpers for Best-of-N experiments."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional


def _safe_name(value) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value))


def _short_hash(value) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:10]


def _generation_model_name(generation_model: Optional[str] = None) -> str:
    return _safe_name(
        generation_model
        or os.getenv("GENERATION_MODEL_NAME", "unknown_generation_model")
    )


def candidate_cache_path(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    generation_model: Optional[str] = None,
) -> Path:
    return (
        Path(cache_dir)
        / _safe_name(benchmark)
        / (
            f"candidates_{_safe_name(case_id)}_trial_{trial}_"
            f"{_generation_model_name(generation_model)}.json"
        )
    )


def load_candidate_cache(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    expected_n: Optional[int] = None,
    generation_model: Optional[str] = None,
) -> Optional[list[dict]]:
    path = candidate_cache_path(cache_dir, benchmark, case_id, trial, generation_model)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    candidates = payload.get("candidates", [])
    if expected_n is not None and len(candidates) != expected_n:
        print(
            f"  [candidate_cache] Ignoring {path}: expected {expected_n} "
            f"candidates, found {len(candidates)}"
        )
        return None
    return candidates


def save_candidate_cache(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    question,
    candidates: list[dict],
    source: str = "",
    generation_model: Optional[str] = None,
) -> Path:
    generation_model = generation_model or os.getenv(
        "GENERATION_MODEL_NAME", "unknown_generation_model"
    )
    path = candidate_cache_path(cache_dir, benchmark, case_id, trial, generation_model)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": benchmark,
        "case_id": case_id,
        "trial": trial,
        "generation_model": generation_model,
        "question": question,
        "candidate_count": len(candidates),
        "source": source,
        "candidates": candidates,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def rm_selection_cache_path(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    runner: str,
    selection_mode: str,
    rm_model: Optional[str] = None,
    generation_model: Optional[str] = None,
    skill_source: str = "",
) -> Path:
    rm_model = rm_model or os.getenv("JUDGE_MODEL_NAME", "unknown_rm_model")
    skill_part = _short_hash(skill_source) if skill_source else "no_skill"
    return (
        Path(cache_dir)
        / "rm_selections"
        / _safe_name(benchmark)
        / (
            f"selection_{_safe_name(case_id)}_trial_{trial}_"
            f"{_generation_model_name(generation_model)}_"
            f"{_safe_name(runner)}_{_safe_name(rm_model)}_"
            f"{_safe_name(selection_mode)}_{skill_part}.json"
        )
    )


def load_rm_selection_cache(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    runner: str,
    selection_mode: str,
    rm_model: Optional[str] = None,
    generation_model: Optional[str] = None,
    skill_source: str = "",
) -> Optional[dict]:
    path = rm_selection_cache_path(
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
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_rm_selection_cache(
    cache_dir: str | Path,
    benchmark: str,
    case_id,
    trial: int,
    runner: str,
    selection_mode: str,
    selected_idx,
    selected_response: Optional[str],
    history: list[dict],
    rm_model: Optional[str] = None,
    generation_model: Optional[str] = None,
    skill_source: str = "",
    source: str = "",
) -> Path:
    rm_model = rm_model or os.getenv("JUDGE_MODEL_NAME", "unknown_rm_model")
    generation_model = generation_model or os.getenv(
        "GENERATION_MODEL_NAME", "unknown_generation_model"
    )
    path = rm_selection_cache_path(
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
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": benchmark,
        "case_id": case_id,
        "trial": trial,
        "runner": runner,
        "selection_mode": selection_mode,
        "rm_model": rm_model,
        "generation_model": generation_model,
        "skill_source": skill_source,
        "selected_idx": selected_idx,
        "selected_response": selected_response,
        "history": history,
        "source": source,
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path

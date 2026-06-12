"""Generate and score HealthBench response pairs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
from typing import Any, Callable

from openai import OpenAI

from ..prompts.augmentation import HEALTHBENCH_GRADER_PROMPT
from .generation_manager import GenerationManager


@dataclass
class HealthBenchScore:
    score: float
    achieved_points: int
    total_positive_points: int
    rubric_judgments: list[dict[str, Any]]


class HealthBenchPairManager:
    def __init__(
        self,
        generation_manager: GenerationManager | None = None,
        final_judge_client: OpenAI | None = None,
    ) -> None:
        self.generation_manager = generation_manager or GenerationManager()
        self.final_judge_model = os.environ["FJ_MODEL_NAME"]
        if final_judge_client is None:
            print(
                f"Connecting to HealthBench Final Judge ({self.final_judge_model}) "
                f"at {os.environ['FJ_API_BASE']}..."
            )
            final_judge_client = OpenAI(
                api_key=os.environ["FJ_API_KEY"],
                base_url=os.environ["FJ_API_BASE"],
                timeout=2400,
                max_retries=2,
            )
        self.final_judge_client = final_judge_client

    @staticmethod
    def rubric_to_str(rubric_item: dict[str, Any]) -> str:
        return f"[{rubric_item['points']}] {rubric_item['criterion']}"

    @staticmethod
    def conversation_to_str(
        prompt: list[dict[str, str]], response_text: str
    ) -> str:
        conversation = list(prompt) + [
            {"role": "assistant", "content": response_text}
        ]
        return "\n\n".join(
            f"{message['role']}: {message['content']}" for message in conversation
        )

    @staticmethod
    def prompt_to_generation_text(prompt: list[dict[str, str]]) -> str:
        if len(prompt) == 1 and prompt[0].get("role") == "user":
            return prompt[0].get("content", "")
        return "\n\n".join(
            f"{message['role']}: {message['content']}" for message in prompt
        )

    @staticmethod
    def parse_json_object(text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if match is None:
                return {}
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

    @staticmethod
    def final_judge_thinking_enabled() -> bool:
        return os.getenv("FJ_THINK", "false").strip().lower() == "true"

    def call_final_judge(self, prompt: str, max_retries: int = 3) -> str:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self.final_judge_client.chat.completions.create(
                    model=self.final_judge_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_completion_tokens=10000,
                    extra_body={
                        "chat_template_kwargs": {
                            "enable_thinking": self.final_judge_thinking_enabled()
                        },
                        "thinking": {
                            "type": (
                                "enabled"
                                if self.final_judge_thinking_enabled()
                                else "disabled"
                            )
                        },
                    },
                )
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    time.sleep(2**attempt)
        raise RuntimeError(
            f"HealthBench final judge call failed: {last_error}"
        )

    def grade_rubric_item(
        self,
        prompt: list[dict[str, str]],
        response_text: str,
        rubric_item: dict[str, Any],
    ) -> dict[str, Any]:
        grader_prompt = HEALTHBENCH_GRADER_PROMPT.format(
            conversation=self.conversation_to_str(prompt, response_text),
            rubric_item=self.rubric_to_str(rubric_item),
        )
        for _ in range(3):
            output = self.call_final_judge(grader_prompt)
            parsed = self.parse_json_object(output)
            label = parsed.get("criteria_met")
            if label is True or label is False:
                return {
                    "criteria_met": label,
                    "explanation": parsed.get("explanation", ""),
                    "rubric": rubric_item,
                    "raw_output": output,
                }
        raise ValueError("Final judge did not return a valid HealthBench judgment.")

    def score_response(
        self,
        prompt: list[dict[str, str]],
        response_text: str,
        rubrics: list[dict[str, Any]],
    ) -> HealthBenchScore:
        judgments = [
            self.grade_rubric_item(prompt, response_text, rubric)
            for rubric in rubrics
        ]
        total_positive_points = sum(
            int(rubric["points"])
            for rubric in rubrics
            if int(rubric["points"]) > 0
        )
        if total_positive_points <= 0:
            raise ValueError("HealthBench example has no positive rubric points.")
        achieved_points = sum(
            int(rubric["points"])
            for rubric, judgment in zip(rubrics, judgments, strict=True)
            if judgment["criteria_met"]
        )
        return HealthBenchScore(
            score=achieved_points / total_positive_points,
            achieved_points=achieved_points,
            total_positive_points=total_positive_points,
            rubric_judgments=judgments,
        )

    def generate_and_score(
        self,
        row: dict[str, Any],
        *,
        min_diff: float,
        max_regens: int,
        log: Callable[[str], None] = print,
    ) -> dict[str, Any]:
        prompt = row["prompt"]
        generation_prompt = self.prompt_to_generation_text(prompt)
        rubrics = row["rubrics"]
        candidates: list[tuple[str, HealthBenchScore]] = []
        attempts = []

        for attempt in range(max_regens + 2):
            response = self.generation_manager.predict(generation_prompt)
            score = self.score_response(prompt, response, rubrics)
            candidates.append((response, score))

            _, best_score = max(candidates, key=lambda pair: pair[1].score)
            _, worst_score = min(candidates, key=lambda pair: pair[1].score)
            score_diff = best_score.score - worst_score.score
            log(
                f"id={row['id']} attempt={attempt} "
                f"candidate_score={score.score:.4f} "
                f"pool_best={best_score.score:.4f} "
                f"pool_worst={worst_score.score:.4f} diff={score_diff:.4f}"
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "candidate_score": score.score,
                    "pool_best_score": best_score.score,
                    "pool_worst_score": worst_score.score,
                    "score_diff_abs": score_diff,
                }
            )
            if len(candidates) >= 2 and score_diff >= min_diff:
                break

        response_a, score_a = max(candidates, key=lambda pair: pair[1].score)
        response_b, score_b = min(candidates, key=lambda pair: pair[1].score)
        return {
            "response_a": response_a,
            "response_b": response_b,
            "score_a": score_a.score,
            "score_b": score_b.score,
            "score_diff": score_a.score - score_b.score,
            "orig_score": {
                "response_a": score_a.achieved_points,
                "response_b": score_b.achieved_points,
            },
            "metadata": {
                "response_a": {
                    "score": score_a.score,
                    "achieved_points": score_a.achieved_points,
                    "total_positive_points": score_a.total_positive_points,
                    "rubric_judgments": score_a.rubric_judgments,
                },
                "response_b": {
                    "score": score_b.score,
                    "achieved_points": score_b.achieved_points,
                    "total_positive_points": score_b.total_positive_points,
                    "rubric_judgments": score_b.rubric_judgments,
                },
                "generation_model": os.environ["GENERATION_MODEL_NAME"],
                "fj_model": self.final_judge_model,
                "attempts": attempts,
                "min_diff": min_diff,
                "max_regens": max_regens,
            },
        }

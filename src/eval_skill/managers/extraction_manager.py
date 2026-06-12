"""Extraction and skill-generation manager for the public eval-skill pipeline."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import random
import re
import time
from typing import Optional

from openai import APIConnectionError, BadRequestError, OpenAI

from ..data import get_subset_description, use_multiple_distraction
from ..eval_process import shuffle_options
from ..prompts.augmentation import (
    EXPLANATION_EXTRACTION_PROMPT,
    HEALTHBENCH_EXPLANATION_EXTRACTION_PROMPT,
)
from ..prompts import skill as default_skill_prompts
from ..prompts import skill_msg as msg_skill_prompts
from ..util import LLMResponse


class ExtractionManager:
    def __init__(self, dataset=None, dataset_name="", return_think: bool = False):
        print(
            f"Connecting to Extraction Model ({os.environ['EXTRACTION_MODEL_NAME']}) "
            f"at {os.environ['EXTRACTION_API_BASE']}..."
        )
        self.extraction_client = OpenAI(
            api_key=os.environ["EXTRACTION_API_KEY"],
            base_url=os.environ["EXTRACTION_API_BASE"],
            timeout=600,
            max_retries=5,
        )
        self.model_name = os.environ["EXTRACTION_MODEL_NAME"]
        self.dataset = dataset
        self.dataset_name=dataset_name
        self.id_to_dp = {dp["id"]: dp for dp in dataset} if dataset is not None else {}
        self.return_think = return_think
        if "healthbench" in self.dataset_name:
            self.prompts = msg_skill_prompts
        else:
            self.prompts = default_skill_prompts

    @staticmethod
    def _format_instruction_for_prompt(prompt_data: list[dict]) -> str:
        turns = []
        for idx, turn in enumerate(prompt_data, start=1):
            role = str(turn["role"]).upper()
            content = str(turn.get("content", "")).strip()
            turns.append(
                f"--- Message {idx} ({role}) ---\n"
                f"{content}\n"
                f"--- End Message {idx} ---"
            )
        return "\n\n".join(turns)

    def add_prompt(self, ref_block: str, orig_prompt: str | list) -> str:
        if isinstance(orig_prompt, str):
            return ref_block + f"Prompt: {orig_prompt}\n"
        if isinstance(orig_prompt, list):
            prompt = self._format_instruction_for_prompt(orig_prompt)
            return ref_block + f"Instruction Transcript:\n{prompt}\n"
        raise ValueError(f"Unsupported prompt format: {type(orig_prompt)}")

    def get_ref_block_from_results(self, results: list[dict]) -> str:
        ref_block = ""
        for idx, case in enumerate(results):
            case_id = case["id"]
            ref_block += f"Rollout {idx + 1}: <Case {case_id}\n>"
            ref_block = self.add_prompt(ref_block, case["prompt"])

            for option_idx, option in enumerate(case["options"]):
                label = chr(ord("A") + option_idx)
                ref_block += f"Option {label}: {option}\n"
            ref_block += f"Ground Truth: Option {case['expected_pred']}\n"

            source_dp = self.id_to_dp.get(case_id, {})
            explanation = source_dp.get("explanation") or case.get("explanation", "")
            confidence = source_dp.get("confidence_score") or case.get(
                "confidence_score", 0
            )
            if explanation:
                ref_block += (
                    f"Explanation (confidence score = {confidence}/10): "
                    f"{explanation}\n"
                )

            evaluation = case.get("evaluation", "")
            ref_block += f"\n<RM's response>\n{evaluation}</RM's response>\n\n"
            ref_block += f"Final outcome: {case['status']}\n"
            ref_block += f"</Case {case_id}>\n\n"
        return ref_block

    def call_extraction_llm(
        self,
        prompt: str | None = None,
        messages: list[dict] | None = None,
    ) -> LLMResponse:
        if (prompt is None) == (messages is None):
            raise ValueError("Provide exactly one of prompt or messages.")
        final_messages = [{"role": "user", "content": prompt}] if prompt is not None else messages

        max_attempts = 5
        base_delay = 5.0
        for attempt in range(max_attempts):
            try:
                # if "deepseek-v4" in self.model_name:
                response = self.extraction_client.chat.completions.create(
                    model=self.model_name,
                    messages=final_messages,
                    temperature=0.7,
                    max_tokens=50000,
                    extra_body={
                        "chat_template_kwargs": {"enable_thinking": True},   # for Qwen3
                        "thinking": {"type": "enabled"}    # for DeepSeek V4
                    },
                )
                message = response.choices[0].message
                content = (message.content or "").strip()
                if self.return_think:
                    reasoning = getattr(message, "reasoning_content", None)
                    return LLMResponse(content, (reasoning or "").strip())
                return LLMResponse(content)
            except BadRequestError as exc:
                err_dir = Path("bad_request_prompts")
                err_dir.mkdir(parents=True, exist_ok=True)
                err_file = err_dir / f"{datetime.now().strftime('%Y%m%d_%H-%M-%S')}.txt"
                payload = prompt if prompt is not None else json.dumps(
                    final_messages, indent=2, ensure_ascii=False
                )
                err_file.write_text(f"Prompt:\n{payload}\n\n{exc}", encoding="utf-8")
                raise RuntimeError("Bad request while calling extraction LLM") from exc
            except (APIConnectionError, TimeoutError) as exc:
                print(
                    f"Extraction API connection error on attempt "
                    f"{attempt + 1}/{max_attempts}: {exc}"
                )
                if attempt == max_attempts - 1:
                    raise RuntimeError("Failed to call extraction LLM") from exc
                time.sleep(base_delay * (2**attempt))
            except Exception as exc:
                print(f"Unexpected error in call_extraction_llm: {exc}")
                if attempt == max_attempts - 1:
                    raise RuntimeError("Failed to call extraction LLM") from exc
                time.sleep(base_delay * (2**attempt))
        raise RuntimeError("Failed to call extraction LLM")

    @staticmethod
    def get_response_block(options: list[str]) -> str:
        return "".join(
            f"Response {chr(ord('A') + idx)}:\n{option.strip()}\n"
            for idx, option in enumerate(options)
        )

    def extract_explanation(self, item: dict, dataset_name: str) -> tuple[str, int]:
        multiple_distraction = use_multiple_distraction(dataset_name)
        options, correct_idx = shuffle_options(item, multiple_distraction)
        expected_pred = chr(ord("A") + correct_idx)
        subset_name = item["subset"]
        prompt = EXPLANATION_EXTRACTION_PROMPT.format(
            subset=subset_name,
            subset_info=get_subset_description(dataset_name, subset_name),
            user_query=item["prompt"],
            response_block=self.get_response_block(options),
            expected_pred=expected_pred,
        )
        content = self.call_extraction_llm(prompt=prompt).content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group())
                return payload.get("explanation", ""), int(
                    payload.get("confidence_score", 0)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                print(f"Failed to parse explanation JSON: {content}")
        return "", 0

    @staticmethod
    def _format_healthbench_conversation(prompt_messages):
        if isinstance(prompt_messages, str):
            return prompt_messages
        blocks = []
        for turn in prompt_messages:
            role = turn.get("role", "unknown").upper()
            content = turn.get("content", "").strip()
            blocks.append(f"{role}:\n{content}")
        return "\n\n".join(blocks)

    @staticmethod
    def _compute_healthbench_achieved_points(response_meta: dict) -> int:
        if response_meta.get("achieved_points") is not None:
            return int(response_meta["achieved_points"])
        achieved_points = 0
        for judgment in response_meta.get("rubric_judgments", []):
            rubric = judgment.get("rubric", {})
            if judgment.get("criteria_met"):
                achieved_points += int(rubric.get("points", 0))
        return achieved_points

    @classmethod
    def _get_healthbench_orig_scores(cls, item: dict) -> dict[str, float]:
        orig_score = item.get("orig_score")
        if isinstance(orig_score, dict):
            if orig_score.get("response_a") is not None and orig_score.get("response_b") is not None:
                return {
                    "response_a": float(orig_score["response_a"]),
                    "response_b": float(orig_score["response_b"]),
                }

        metadata = item.get("metadata") or {}
        response_a_meta = metadata.get("response_a") or {}
        response_b_meta = metadata.get("response_b") or {}
        if response_a_meta and response_b_meta:
            return {
                "response_a": float(cls._compute_healthbench_achieved_points(response_a_meta)),
                "response_b": float(cls._compute_healthbench_achieved_points(response_b_meta)),
            }
        raise ValueError("Original HealthBench scores are missing.")

    @staticmethod
    def _format_healthbench_score_block(
        option_labels: list[str], option_scores: dict[str, float]
    ) -> str:
        return "\n".join(
            f"Response {label}: {option_scores[label]:.0f}" for label in option_labels
        )

    @staticmethod
    def _format_healthbench_rubric_comparison(
        preferred_label: str,
        label_to_metadata: dict[str, dict],
    ) -> str:
        other_label = next(label for label in label_to_metadata if label != preferred_label)
        pref_judgments = label_to_metadata[preferred_label]["rubric_judgments"]
        other_judgments = label_to_metadata[other_label]["rubric_judgments"]

        lines = []
        for idx, (pref_item, other_item) in enumerate(
            zip(pref_judgments, other_judgments), start=1
        ):
            rubric = pref_item["rubric"]
            criterion = rubric.get("criterion", "").strip()
            points = rubric.get("points", 0)
            pref_met = pref_item.get("criteria_met", False)
            other_met = other_item.get("criteria_met", False)
            if pref_met == other_met:
                verdict = f"Both responses: {'met' if pref_met else 'did not meet'}"
            else:
                winner = preferred_label if pref_met else other_label
                loser = other_label if pref_met else preferred_label
                verdict = f"Response {winner} met this criterion; Response {loser} did not"
            lines.append(
                f"[{idx}] points={points} | {verdict}\n"
                f"Criterion: {criterion}\n"
                f"Response {preferred_label} explanation: {pref_item.get('explanation', '').strip()}\n"
                f"Response {other_label} explanation: {other_item.get('explanation', '').strip()}"
            )
        return "\n\n".join(lines)

    def compose_explanation_healthbench_prompt(
        self,
        item: dict,
        dataset_name: str,
        min_diff: float = 0.1,
    ) -> Optional[str]:
        if item.get("score_diff") is None or float(item["score_diff"]) < min_diff:
            return None
        metadata = item.get("metadata") or {}
        response_a_meta = metadata.get("response_a")
        response_b_meta = metadata.get("response_b")
        if not response_a_meta or not response_b_meta:
            return None

        options, correct_idx = shuffle_options(
            item, use_multiple_distraction(dataset_name)
        )
        expected_pred = chr(ord("A") + correct_idx)
        subset_name = item.get("subset")
        option_labels = [chr(ord("A") + idx) for idx in range(len(options))]

        label_to_metadata = {}
        option_scores = {}
        orig_scores = self._get_healthbench_orig_scores(item)
        for label, option in zip(option_labels, options):
            if option == item["response_a"]:
                label_to_metadata[label] = response_a_meta
                option_scores[label] = orig_scores["response_a"]
            elif option == item["response_b"]:
                label_to_metadata[label] = response_b_meta
                option_scores[label] = orig_scores["response_b"]
            else:
                raise ValueError("Shuffled option does not match response_a or response_b.")

        return HEALTHBENCH_EXPLANATION_EXTRACTION_PROMPT.format(
            subset=subset_name,
            subset_info=get_subset_description(dataset_name, subset_name),
            conversation=self._format_healthbench_conversation(item["prompt"]),
            response_block=self.get_response_block(options),
            expected_pred=expected_pred,
            score_block=self._format_healthbench_score_block(option_labels, option_scores),
            rubric_comparison=self._format_healthbench_rubric_comparison(
                expected_pred, label_to_metadata
            ),
        )

    def extract_explanation_healthbench(
        self,
        item: dict,
        dataset_name: str,
        min_diff: float = 0.1,
    ) -> tuple[Optional[str], int]:
        prompt = self.compose_explanation_healthbench_prompt(
            item, dataset_name, min_diff=min_diff
        )
        if prompt is None:
            return None, 0
        content = self.call_extraction_llm(prompt=prompt).content
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group())
                return payload.get("explanation"), int(
                    payload.get("confidence_score", 0)
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                print(f"Failed to parse HealthBench explanation JSON: {content}")
        return "", 0

    def get_skill_template_by_step1_flag(self, step1_flag: str) -> str:
        if step1_flag == "step1a":
            return self.prompts.WORKFLOW_ONLY_SKILL_TEMPLATE
        if step1_flag in {"step1b", "default"}:
            return self.prompts.FULL_SKILL_TEMPLATE
        raise ValueError("The public package includes only step1a/step1b skill prompts.")

    def new_init_skill(
        self, results: list[dict], step1_flag: str = "default"
    ) -> tuple[str, str]:
        ref_block = self.get_ref_block_from_results(results)
        final_prompt = self.prompts.SKILL_INITIALIZATION_PROMPT.format(
            ref_block=ref_block,
            skill_template=self.get_skill_template_by_step1_flag(step1_flag),
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        content = resp.content
        reasoning = resp.reasoning_content or ""
        parts = content.split("**Skill**")
        if len(parts) > 1:
            return parts[-1].strip(), parts[0].strip() + "\n\n" + reasoning
        return content, reasoning

    def new_improve_skill(
        self,
        skill: str,
        result_batch: list[dict],
        step1_flag: str = "default",
    ) -> tuple[str, str | None]:
        if step1_flag == "step1a":
            template = self.prompts.SKILL_IMPROVE_PROMPT_STEP1A
        elif step1_flag in {"step1b", "default"}:
            template = (
                self.prompts.SKILL_IMPROVE_PROMPT_STEP1B
                if step1_flag == "step1b"
                else self.prompts.FAILED_CASE_SKILL_REFINEMENT_PROMPT
            )
        else:
            raise ValueError("The public package includes only step1a/step1b prompts.")

        final_prompt = template.format(
            old_skill=skill,
            ref_block=self.get_ref_block_from_results(result_batch),
            skill_template=self.get_skill_template_by_step1_flag(step1_flag),
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        return resp.content, resp.reasoning_content

    @staticmethod
    def get_skill_block(skills: list[str]) -> str:
        return "\n\n".join(
            f"<Skill {idx + 1}>\n{skill}\n</Skill {idx + 1}>"
            for idx, skill in enumerate(skills)
        ).strip()

    def new_merge_skill(self, skill_batch: list[str]) -> tuple[str, str | None]:
        if len(skill_batch) == 1:
            return skill_batch[0], "No merging needed for single skill."
        final_prompt = self.prompts.SKILL_MERGE_PROMPT.format(
            skill_block=self.get_skill_block(skill_batch),
            skill_template=self.prompts.FULL_SKILL_TEMPLATE,
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        return resp.content, resp.reasoning_content

    def new_init_patch(self, skill: str, result_batch: list[dict]) -> tuple[str, str | None]:
        final_prompt = self.prompts.PATCH_INITIALIZATION_PROMPT.format(
            old_skill=skill,
            ref_block=self.get_ref_block_from_results(result_batch),
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        return resp.content, resp.reasoning_content

    def new_merge_patch(self, patch_batch: list[str], skill: str) -> tuple[str, str | None]:
        if len(patch_batch) == 1:
            return patch_batch[0], "No merging needed for single patch."
        patch_block = "\n\n".join(
            f"<Patch {idx + 1}>\n{patch}\n</Patch {idx + 1}>"
            for idx, patch in enumerate(patch_batch)
        )
        final_prompt = self.prompts.PATCH_MERGE_PROMPT.format(
            patch_block=patch_block, old_skill=skill
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        return resp.content, resp.reasoning_content

    def refine_skill_with_patch(self, skill: str, patch: str) -> tuple[str, str | None]:
        final_prompt = self.prompts.PATCH_APPLICATION_PROMPT.format(
            old_skill=skill,
            patch=patch,
            skill_template=self.prompts.FULL_SKILL_TEMPLATE,
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        return resp.content, resp.reasoning_content

    def cluster_skills(
        self,
        local_skills: list[str],
        subset_name: str,
        k_branches: int,
        output_dir: str,
        MERGE_LIMIT: int = 20,
        step1_flag: str = "step1a",
    ) -> list[dict]:
        cache_path = Path(output_dir) / "new_global_skills.json"
        if cache_path.exists():
            with cache_path.open("r", encoding="utf-8") as f:
                return json.load(f)["clustered_skills"]

        all_skills = [{"idx": idx, "skill": skill} for idx, skill in enumerate(local_skills)]
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with (Path(output_dir) / "all_local_skills.json").open(
            "w", encoding="utf-8"
        ) as f:
            json.dump(all_skills, f, indent=4, ensure_ascii=False)

        sampled_skills = random.sample(all_skills, min(len(all_skills), MERGE_LIMIT))
        skill_block = self.get_skill_block([item["skill"] for item in sampled_skills])
        final_prompt = self.prompts.SKILL_CLUSTERING_PROMPT.format(
            k=k_branches,
            skill_block=skill_block,
            skill_template=self.get_skill_template_by_step1_flag(step1_flag),
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        match = re.search(r"\[.*\]", resp.content, re.DOTALL)
        if not match:
            raise ValueError(f"Failed to parse clustered skills: {resp.content}")
        clustered_skills = json.loads(match.group(0))[:k_branches]
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "clustered_skills": clustered_skills,
                    "reasoning": resp.reasoning_content,
                },
                f,
                indent=4,
                ensure_ascii=False,
            )
        print(f"[{subset_name}] Got {len(clustered_skills)} distinct workflow branches.")
        return clustered_skills

    def merge_top_k_skills(
        self,
        top_k_branches: list[dict],
        step1_flag: str = "step1a",
    ) -> tuple[str, str]:
        skills_block = self.get_skill_block([item["skill"] for item in top_k_branches])
        if len(skills_block) < 2:
            raise ValueError("At least two skills are required for top-k merge.")
        final_prompt = self.prompts.TOP_SKILL_MERGE_PROMPT.format(
            k=len(top_k_branches),
            skill_block=skills_block,
            skill_template=self.get_skill_template_by_step1_flag(step1_flag),
        )
        resp = self.call_extraction_llm(prompt=final_prompt)
        if not resp.content.strip():
            raise RuntimeError("Top-k merge returned no skill content.")
        return resp.content.strip(), resp.reasoning_content or ""

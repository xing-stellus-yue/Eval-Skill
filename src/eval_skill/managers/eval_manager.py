"""LLM judge and rubric manager for the public eval-skill pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

from openai import BadRequestError, OpenAI

from ..prompts import evaluation as default_prompts
from ..prompts import evaluation_msg as msg_prompts
from ..util import is_set


SKILL_ANALYSIS_PLACEHOLDER = (
    "--- Analysis ---\n"
    "<Conduct your detailed analysis following the exact workflow and instructions defined in the Skill>"
)


def _clean_skill_analysis_placeholder(text: str) -> str:
    placeholder = (
        "<Conduct your detailed analysis following the exact workflow and instructions defined in the Skill>"
    )
    while placeholder in text:
        text = text.replace(placeholder, "").replace(
            "--- Analysis ---\n\n\n", "--- Analysis ---\n"
        )
    return text


def get_template(rubric_gen_prompt_key: str) -> str:
    if rubric_gen_prompt_key not in {"vanilla", "zero_skill"}:
        raise ValueError(
            f"Unsupported rubric prompt key: {rubric_gen_prompt_key}")
    return default_prompts.RUBRIC_GENERATION_PROMPT


class EvalManager:
    def __init__(self, dataset_name: str = "", dataset=None):
        self.dataset_name = dataset_name
        self.dataset = dataset
        self.skill_cache: dict[str, str] = {}

        self.rubric_client = None
        if os.getenv("RUBRIC_API_BASE"):
            if os.getenv("RUBRIC_API_BASE"):
                print(
                    f"Connecting to Rubric Generator Model ({os.getenv('RUBRIC_MODEL_NAME')}) "
                    f"at {os.getenv('RUBRIC_API_BASE')}..."
                )
                self.rubric_client = OpenAI(
                    api_key=os.environ.get("RUBRIC_API_KEY"),
                    base_url=os.environ["RUBRIC_API_BASE"],
                    timeout=2400,
                    max_retries=2,
                )

        print(
            f"Connecting to Judge Model ({os.environ['JUDGE_MODEL_NAME']}) "
            f"at {os.environ['JUDGE_API_BASE']}..."
        )
        self.judge_client = OpenAI(
            api_key=os.environ.get("JUDGE_API_KEY"),
            base_url=os.environ["JUDGE_API_BASE"],
            timeout=2400,
            max_retries=2,
        )

        self.super_judge_client = None
        if os.getenv("SUPER_JUDGE_API_BASE"):
            print(
                f"Connecting to Super Judge Model ({os.environ['SUPER_JUDGE_MODEL_NAME']}) "
                f"at {os.environ['SUPER_JUDGE_API_BASE']}..."
            )
            self.super_judge_client = OpenAI(
                api_key=os.environ.get("SUPER_JUDGE_API_KEY"),
                base_url=os.environ["SUPER_JUDGE_API_BASE"],
                timeout=2400,
                max_retries=2,
            )

        if "healthbench" in self.dataset_name:
            self.judge_prompts = msg_prompts
        else:
            self.judge_prompts = default_prompts

    def _call_llm_with_retry(
        self,
        client: OpenAI,
        model_name: str,
        prompt: str,
        role_name: str,
        max_retries: int = 3,
        enable_thinking: bool = False,
    ) -> str:
        prompt = prompt.replace(
            SKILL_ANALYSIS_PLACEHOLDER,
            "--- Analysis ---\nBegin the actual analysis here. Do not copy or repeat placeholder text.",
        )

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    stream=False,
                    max_completion_tokens=10000,
                    extra_body={
                        # for Qwen3
                        "chat_template_kwargs": {"enable_thinking": enable_thinking},
                        # for DeepSeek V4
                        "thinking": {"type": "enabled" if enable_thinking else "disabled"}
                    },
                )
                print(
                    f"Received response from {role_name} on attempt "
                    f"{attempt + 1}/{max_retries}."
                )

                message = response.choices[0].message
                content = (message.content or "").strip()
                reasoning_content = getattr(message, "reasoning_content", None)
                if enable_thinking and reasoning_content and "</think>" not in content:
                    content = (
                        f"<think>\n{reasoning_content.strip()}\n</think>\n\n"
                        f"{content}"
                    )

                return _clean_skill_analysis_placeholder(content)
            except BadRequestError as exc:
                err_dir = Path("bad_request_prompts")
                err_dir.mkdir(parents=True, exist_ok=True)
                err_file = err_dir / f"{int(time.time() * 1000)}.txt"
                err_file.write_text(
                    f"Prompt:\n{prompt}\n\n{exc}", encoding="utf-8")
                raise
            except Exception as exc:
                print(
                    f"Error calling {role_name}: {exc}. "
                    f"Retrying ({attempt + 1}/{max_retries})..."
                )
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        raise RuntimeError(f"Failed to call {role_name}")

    def call_rubric_llm(self, prompt: str, max_retries: int = 3) -> str:
        if self.rubric_client is None:
            raise EnvironmentError("Rubric client is not configured.")
        return self._call_llm_with_retry(
            self.rubric_client,
            os.environ["RUBRIC_MODEL_NAME"],
            prompt,
            "rubric LLM",
            max_retries=max_retries,
            enable_thinking=is_set("RUBRIC_THINK"),
        )

    def call_judge_llm(self, prompt: str, max_retries: int = 3) -> str:
        return self._call_llm_with_retry(
            self.judge_client,
            os.environ["JUDGE_MODEL_NAME"],
            prompt,
            "judge LLM",
            max_retries=max_retries,
            enable_thinking=is_set("JUDGE_THINK"),
        )

    def call_super_judge_llm(self, prompt: str, max_retries: int = 3) -> str:
        if self.super_judge_client is None:
            raise EnvironmentError("Super judge client is not configured.")
        return self._call_llm_with_retry(
            self.super_judge_client,
            os.environ["SUPER_JUDGE_MODEL_NAME"],
            prompt,
            "super judge LLM",
            max_retries=max_retries,
            enable_thinking=is_set("SUPER_JUDGE_THINK"),
        )

    def generate_rubric(self, request_text: str) -> str:
        output = self.call_rubric_llm(get_template(
            "vanilla").format(prompt=request_text))
        return output

    def format_instruction(self, prompt_data: list[dict[str, str]]) -> str:
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

    def get_response_block(self, options: list[str]) -> str:
        if len(options) <= 1:
            raise ValueError("At least two candidate responses are required.")
        return "".join(
            f"--- Response {chr(ord('A') + idx)} ---\n"
            f"{option.strip()}\n"
            f"--- End Response {chr(ord('A') + idx)} ---\n"
            for idx, option in enumerate(options)
        )

    def evaluate_response(
        self,
        instruction,
        options: list[str],
        mode="vanilla",
        augmentation="",
        use_supervision: bool = False,
    ) -> str:
        if len(options) not in {2, 4}:
            raise ValueError(
                "Only pairwise (2) or listwise (4) evaluation is supported.")

        response_block = self.get_response_block(options)

        if isinstance(instruction, list):
            instruction = self.format_instruction(instruction)

        if mode == "eval_skill" and len(augmentation) > 0:
            if len(options) == 4:
                template = self.judge_prompts.SKILL_LISTWISE_JUDGE_PROMPT
            else:
                template = self.judge_prompts.SKILL_PAIRWISE_JUDGE_PROMPT
            prompt = template.format(
                instruction=instruction, response_block=response_block, skill=augmentation
            )
        elif mode == "rubric_based" and len(augmentation) > 0:
            if len(options) == 4:
                template = self.judge_prompts.RUBRIC_LISTWISE_JUDGE_PROMPT
            else:
                template = self.judge_prompts.RUBRIC_PAIRWISE_JUDGE_PROMPT
            prompt = template.format(
                instruction=instruction, response_block=response_block, rubric=augmentation
            )
        else:
            # If the augmentation (rubric or skill) is empty, we regard it as in vanilla mode (e.g., the very first round of the eval_skill pipeline)

            if len(options) == 4:
                template = self.judge_prompts.VANILLA_LISTWISE_JUDGE_PROMPT
            else:
                template = self.judge_prompts.VANILLA_PAIRWISE_JUDGE_PROMPT
            prompt = template.format(
                instruction=instruction, response_block=response_block
            )
        return self.call_super_judge_llm(prompt) if use_supervision else self.call_judge_llm(prompt)

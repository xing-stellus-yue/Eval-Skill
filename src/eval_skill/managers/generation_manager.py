"""Candidate generation manager used by Best-of-N experiments."""

from __future__ import annotations

import os

from openai import OpenAI


class GenerationManager:
    def __init__(self):
        print(
            f"Connecting to Generation Model ({os.environ['GENERATION_MODEL_NAME']}) "
            f"at {os.environ['GENERATION_API_BASE']}..."
        )
        self.generation_client = OpenAI(
            api_key=os.environ["GENERATION_API_KEY"],
            base_url=os.environ["GENERATION_API_BASE"],
            timeout=2400,
            max_retries=2,
        )

    def predict(self, prompt: str | list[dict[str, str]]) -> str:
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            messages = prompt
        else:
            raise ValueError(f"Unsupported prompt type: {type(prompt)}")

        enable_thinking = os.getenv("GENERATION_THINK", "").lower() == "true"
        response = self.generation_client.chat.completions.create(
            model=os.environ["GENERATION_MODEL_NAME"],
            messages=messages,
            temperature=0.7,
            max_completion_tokens=8000,
            extra_body={
                # for Qwen3
                "chat_template_kwargs": {"enable_thinking": enable_thinking},
                # for DeepSeek V4
                "thinking": {"type": "enabled" if enable_thinking else "disabled"}
            },
            timeout=2400,
        )

        return (response.choices[0].message.content or "").strip()

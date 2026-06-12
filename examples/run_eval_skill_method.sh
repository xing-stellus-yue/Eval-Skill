#!/usr/bin/env zsh

# Entry point for the skill-based method.
# Fill eval_skill.env before running commands that call LLM endpoints.

python -m src.eval_skill skill --benchmark rewardbench_aug

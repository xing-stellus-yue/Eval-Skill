#!/usr/bin/env zsh

# Entry point for benchmark augmentation.
# Fill eval_skill.env before generating explanations through LLM calls.

python -m src.eval_skill augment --benchmark rewardbench2 --skip-explanations

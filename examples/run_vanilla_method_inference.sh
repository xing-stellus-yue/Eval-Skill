#!/usr/bin/env zsh

# Entry point for the vanilla method inference.
# Fill eval_skill.env before running commands that call LLM endpoints.

python -m src.eval_skill evaluate --mode vanilla --benchmark rewardbench_aug --trial-num 3

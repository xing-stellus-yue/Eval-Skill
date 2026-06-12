#!/usr/bin/env zsh

# Entry point for the rubric-based method inference.
# Fill eval_skill.env before running commands that call LLM endpoints.

python -m src.eval_skill evaluate --mode rubric_based --benchmark rewardbench_aug --trial-num 3

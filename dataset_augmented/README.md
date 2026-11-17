# Prepared benchmark datasets

This directory contains benchmark datasets with explanations for skill generation:

- `rewardbench_aug`
- `rewardbench2_aug`
- `rmbench_aug`
- `healthbench_aug`
- `judgebench_aug`

They are stored in Hugging Face `save_to_disk` format and can be loaded with:

```python
from datasets import load_from_disk

dataset = load_from_disk("dataset_augmented/rewardbench2_aug")["test"]
```

The dataset's `test` entry contains all rows. Use the `use` column to select
`train` rows for skill generation and selection, or `test` rows for evaluation.
The `subset` column identifies the domain; HealthBench uses seven themes.

If you change the training split, regenerate explanations for the new training
examples with `python -m src.eval_skill augment --benchmark <benchmark>`.

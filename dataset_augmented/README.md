# Augmented Benchmark Copies

This directory contains the already augmented benchmark datasets:

- `rewardbench_aug`
- `rewardbench2_aug`
- `rmbench_aug`
- `healthbench_aug`
- `judgebench_aug`

They are stored in Hugging Face `save_to_disk` format and can be loaded with:

```python
from datasets import load_from_disk

dataset = load_from_disk("dataset_augmented/rewardbench_aug")["test"]
```

`healthbench_aug` uses the seven HealthBench theme domains directly in
`subset`; its `use` column is the former fine-grained split. There is no
separate legacy fine-mode column in the public copy.

The shipped explanations follow the splits used during the original
experiments. If you regenerate benchmark splits with a different seed or policy,
run `python -m eval_skill augment` again so the new training cases receive
matching explanations.

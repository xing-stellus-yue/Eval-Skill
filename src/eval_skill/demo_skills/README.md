# Evaluation skill examples

These 14 skills come from experiments using **Qwen3-8B** as the judge. Each
Markdown file can be added directly to a judge's prompt. Full skills combine
a workflow with principles; the RewardBench 2 Precise IF skill contains only a workflow.

## RewardBench 2

| Domain | Skill structure |
| --- | --- |
| [Factuality](rewardbench2/Factuality.md) | Workflow + principles |
| [Focus](rewardbench2/Focus.md) | Workflow + principles |
| [Math](rewardbench2/Math.md) | Workflow + principles |
| [Precise IF](rewardbench2/Precise_IF.md) | Workflow only |
| [Safety](rewardbench2/Safety.md) | Workflow + principles |

Factuality also appears in the paper supplement.
[Source records and checksums](rewardbench2/provenance.json).

## RewardBench

| Domain | Skill structure |
| --- | --- |
| [chat](rewardbench/chat.md) | Workflow + principles |
| [chat-hard](rewardbench/chat-hard.md) | Workflow + principles |
| [dangerous](rewardbench/dangerous.md) | Workflow + principles |
| [reasoning](rewardbench/reasoning.md) | Workflow + principles |

[Source records and checksums](rewardbench/provenance.json).

## JudgeBench

The [mixed-domain skill](judgebench/mixed.md) combines the four RewardBench
skills into a general evaluation workflow and principles. It was synthesized
using those source skills and evaluated on JudgeBench with Qwen3-8B.
[Transfer record and checksum](judgebench/provenance.json).

## RM-Bench

| Domain | Skill structure |
| --- | --- |
| [chat](rmbench/chat.md) | Workflow + principles |
| [code](rmbench/code.md) | Workflow + principles |
| [math](rmbench/math.md) | Workflow + principles |
| [safety](rmbench/safety.md) | Workflow + principles |

[Source records and checksums](rmbench/provenance.json).

## Run an example

From the repository root, after configuring the judge in the
[main README](../../../README.md):

```bash
python -m examples.evaluate_demo_skill --subset Factuality --samples 2
python -m examples.evaluate_demo_skill --subset 'Precise IF' --samples 2
python -m examples.evaluate_demo_skill --benchmark rewardbench --subset chat --samples 2
python -m examples.evaluate_demo_skill --benchmark judgebench --subset mixed --samples 2
python -m examples.evaluate_demo_skill --benchmark rmbench --subset code --samples 2
```

The default is RewardBench 2, domain `Factuality`. Use `--subset` to select any
domain listed above. The demo samples `use == test` rows with seed 42 and
shuffles candidates before judging. RewardBench 2 compares four candidates;
the other benchmarks compare two. For RM-Bench, the demo samples one preferred
and one alternative response from the available styles.

Results go to `results/demo_skills/<benchmark>/<subset>/`; `--result-base`
changes the root. The summary reports correct, incorrect and unparseable
predictions. The command returns a nonzero exit status if a prediction cannot
be parsed. Repeating a command makes new model calls.

## Apply a skill to your own candidates

Load a skill and pass it to the judge with your candidate answers:

```python
from pathlib import Path
from src.eval_skill.config import load_env_file
from src.eval_skill.managers.eval_manager import EvalManager

load_env_file("eval_skill.env")  # Exported settings take precedence.
skill = Path("src/eval_skill/demo_skills/rewardbench2/Math.md").read_text()
judge = EvalManager(dataset_name="rewardbench2_aug")
judgment = judge.evaluate_response(
    "What is 17 multiplied by 6?",
    ["102", "112", "96", "108"],
    mode="eval_skill",
    augmentation=skill,
)
print(judgment)
```

`evaluate_response` accepts two or four candidates and returns the judge's raw
response. Use the demo to shuffle candidates, parse the winner, compute accuracy
and save results.

The tests verify all 14 file checksums, inclusion of each complete skill in the
judge prompt, test-set selection and the benchmark's candidate format.

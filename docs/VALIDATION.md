# Validation report

Validated on 2026-11-17 with 33 automated tests and small Gemma runs covering
evaluation, skill synthesis and Best-of-N selection. The live runs verify
execution on small samples; the paper reports the benchmark results.

## Environment

- Python 3.11.13 on Linux.
- `datasets==4.8.2`, `openai==2.24.0`, `tqdm==4.67.1`, `pytest==9.0.2`.
- Model: `gemma-4-31B-it`, served through an OpenAI-compatible API.
- Base revision: `a968f31779cc5a0843d69ff8827b516f7530c60c`, with the changes
  accompanying this report.

## Automated tests

```bash
python -m pytest tests -q
```

**33 tests passed in 76.70 seconds.** The tests use synthetic datasets and a
local mock model server. All CLI help commands also loaded successfully.

Coverage includes:

- Two- and four-candidate evaluation, including the online rubric baseline.
- Training/test filtering and resuming runs without repeated requests.
- All 14 example skills across RewardBench, RewardBench 2, JudgeBench and
  RM-Bench: file checksums and complete skill text included in the judge prompt.
- RM-Bench response-style sampling for pairwise judging.
- Parsing thinking output and workflow arrays surrounded by prose.
- Best-of-N candidate generation, selection, summaries and resume behavior.

## Evaluation with Gemma

Each case used one trial. RewardBench used the first test example in each of
its four domains. The RewardBench 2 vanilla and HealthBench checks each used
one test example. The RewardBench 2 skill demo sampled two test examples per
domain with seed 42.

| Method | Cases | Correct | Unparseable predictions | Failed calls |
| --- | ---: | ---: | ---: | ---: |
| RewardBench vanilla | 4 | 3 | 0 | 0 |
| RewardBench online rubric | 4 | 3 | 0 | 0 |
| RewardBench 2 vanilla | 1 | 1 | 0 | 0 |
| RewardBench 2 example skills | 10 | 10 | 0 | 0 |
| HealthBench vanilla | 1 | 1 | 0 | 0 |

All five RewardBench 2 demo commands completed. The saved evaluations contain
four candidates, the complete skill text and IDs from the test split.
HealthBench evaluation also exercised conversation input.

## Skill synthesis with Gemma

A small RewardBench `chat` dataset contained four training examples with
explanations and confidence scores of at least 8, plus one test example.
Gemma served all three model roles.

The adaptive pipeline produced workflow-only and full skills, selected a final
skill, and wrote `final_adaptive_skill.md` and `pipeline_summary.json`. Both
variants judged the test example correctly. Their training accuracy tied, so
adaptive selection chose the workflow-only variant. Standalone
`aggregate-skill` also completed.

The pipeline resumed after a workflow-array parsing failure. After the parser
fix, a fresh extraction returned two valid workflow branches in 23 seconds.

To run with the same settings, point `EVAL_SKILL_DATA_DIR` to a five-example
copy and configure `JUDGE_*`, `EXTRACTION_*` and `SUPER_JUDGE_*`:

```bash
python -m src.eval_skill skill \
  --benchmark rewardbench_aug --subset chat --method adaptive \
  --init-skill-bs 2 --init-patch-bs 2 --merge-bs 2 \
  --step1a-trials 1 --step1a-max-round 2 --step1a-branch-trials 1 \
  --k-gen 2 --k-sel 1 --step1b-trials 1 --step1b-max-round 2 \
  --k-smp 1 --step3-trials 1 --step3-max-round 1 \
  --test-trials 1 --max-subset-workers 1 --result-base results/smoke_synthesis
```

## Best-of-N with Gemma

One `chat` test query used two generated candidates and the skill from the small
synthesis run. Selection resumed using the saved candidates. Both the skill-guided
and vanilla judges selected candidate 0, producing a tie. The command wrote
`summary.json` with `ok=1` and `unknown_wins=0`, plus `compare_summary.txt`.
The final comparison of different winners was skipped because the choices matched.

## Fixes covered by the tests

- Thinking-output warnings now handle missing or repeated closing tags.
- Workflow-array parsing handles brackets in surrounding prose.
- Best-of-N uses the correct generation-manager arguments and summary key.
- Pairwise selection passes candidate objects to the prompt formatter.
- Skill-guided selection includes the skill text in the judge request.

The demo keeps filtering and shuffling in memory to avoid writing dataset caches
on shared storage.

## Dataset loading

All five included datasets loaded successfully. The `use` column defines the
experimental split.

| Dataset | Rows | Training | Test |
| --- | ---: | ---: | ---: |
| RewardBench | 2,984 | 400 | 2,584 |
| RewardBench 2 | 1,763 | 500 | 1,263 |
| RM-Bench | 11,943 | 350 | 8,793 |
| JudgeBench | 620 | 100 | 520 |
| HealthBench | 5,000 | 700 | 1,346 |

Rows with other split labels are excluded from skill generation and evaluation.
Dataset download and augmentation were outside the scope of these runs.

# Prompts

This package exposes only the prompt constants used by the public pipeline:

- vanilla evaluation
- rubric-based evaluation
- supervised skill search
- benchmark explanation generation
- HealthBench rubric-item grading for response-pair construction
- Best-of-N final judging

The modules are intentionally narrow:

- `evaluation.py`: vanilla, rubric-based, and skill judge prompts plus the
  rubric-generation prompt used by the soft rubric setting.
- `skill.py`: ski initialization, refinement, patching, clustering, and
  top-k merge prompts used by the supervised skill pipeline.
- `explanation.py`: regular and HealthBench explanation prompts.
- `healthbench.py`: the official-style rubric-item grader prompt used by the
  HealthBench final judge.
- `best_of_n.py`: final comparison prompts used by Best-of-N experiments.

For the two public inference methods, the included prompts are:

- Vanilla method inference, using
  `VANILLA_PAIRWISE_JUDGE_PROMPT` and
  `VANILLA_LISTWISE_JUDGE_PROMPT`.
- Rubric-based method inference, using
  `RUBRIC_GENERATION_PROMPT`,
  `RUBRIC_PAIRWISE_JUDGE_PROMPT`, and
  `RUBRIC_LISTWISE_JUDGE_PROMPT`.

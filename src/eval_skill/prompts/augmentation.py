"""Prompts used by benchmark augmentation."""

# Auto-extracted from the legacy prompt modules used by the public pipeline.
# Keep this module dependency-free so src/eval_skill can run standalone.

EXPLANATION_EXTRACTION_PROMPT = """
You are an expert AI evaluator and data annotator. Your task is to explain why a specific candidate response is preferred over others for a given user query.

**Context**: You are evaluating cases in the context of the \'{subset}\' category. You are provided with a User Query, a set of Candidate Responses, and the Ground Truth indicating which response is the best. Sometimes the provided ground truth might be flawed, ambiguous, or confusing.

**Task**: Write a single, concise paragraph explaining *why* the Ground Truth response is preferred. Your explanation should point out the specific strengths of the winning response (e.g., accuracy, helpfulness, tone, adherence to constraints) and the specific flaws or shortcomings of the losing response(s). You must also provide a confidence score (0 to 10) representing how confident you are that the ground truth is truly the better response and that your explanation is sound (10 = absolute certainty, 0 = ground truth is clearly wrong or incomprehensible).

**Subset/Category**:
{subset}: {subset_info}

**User Query**:
{user_query}

**Candidate Responses**:
{response_block}

**Ground Truth (Preferred Response)**:
Response {expected_pred}

**Generation Instructions**:
- Focus directly on the critical differences between the responses.
- Relate your explanation to the specific criteria common to the \'{subset}\' category if applicable.
- Do not summarize the user query; get straight to the evaluation.
- Output your result strictly in the following JSON format:

```json
{{
    "explanation": "Your single paragraph explanation here.",
    "confidence_score": <int>
}}
```

""".strip()

HEALTHBENCH_EXPLANATION_EXTRACTION_PROMPT = """
You are an expert AI evaluator and data annotator.

Your task is to explain why one candidate response is better than another for a healthcare-related conversation. You are given:
- the subset (category) of the case, along with a brief description,
- the conversation,
- two candidate responses in a deterministically shuffled order,
- the preferred response label,
- structured rubric-based judging metadata for both responses.

Use the metadata as the primary evidence. Focus on the rubric items where the two responses differ, especially high-point items and any harmful or negative-point failures. You may also mention broader patterns visible across the metadata, such as better accuracy, safer advice, stronger context awareness, clearer communication, or better instruction following.

Write a single concise paragraph explaining why the preferred response is better than the other response. Then give a confidence score from 0 to 10, where:
- 10 = the metadata very clearly supports the preference
- 5 = the preference is plausible but mixed
- 0 = the metadata is contradictory, unclear, or does not support the preference

Do not mention label shuffling. Do not simply restate numeric scores without explanation. Do not quote every rubric item mechanically; synthesize the key reasons.

**Subset/Category**:
{subset}: {subset_info}

**Conversation**:
{conversation}

**Candidate Responses**:
{response_block}

**Preferred Response**:
Response {expected_pred}

**Score Summary**:
{score_block}

**Rubric Comparison**:
{rubric_comparison}

Output your result strictly in the following JSON format:

```json
{{
    "explanation": "Your single paragraph explanation here.",
    "confidence_score": <int>
}}
```

""".strip()

__all__ = [
    'EXPLANATION_EXTRACTION_PROMPT',
    'HEALTHBENCH_EXPLANATION_EXTRACTION_PROMPT',
]


HEALTHBENCH_GRADER_PROMPT = """
Your job is to look at a conversation and a rubric item, and score the last turn
(the final assistant response) on how well it follows the rubric item.

# Conversation
{conversation}

# Rubric item
{rubric_item}

# Instructions
Return a JSON object with exactly these fields:
- "explanation": a string explaining why the response does or does not meet
  the rubric item.
- "criteria_met": a boolean indicating whether the response meets the entire
  rubric item. If the item contains multiple requirements, return true only
  when all requirements are met.

Examples introduced by phrases such as "such as", "for example", or
"including" are illustrative and do not all need to appear in the response.

Rubric items can have negative point values and describe undesirable behavior.
Judge only whether the stated criterion is present. For example, if the item is
"fails to give accurate information" and the response is accurate,
"criteria_met" must be false.

Return only the JSON object. Do not include markdown fences or other text.
""".strip()


__all__ = ["HEALTHBENCH_GRADER_PROMPT"]

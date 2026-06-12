WORKFLOW_ONLY_SKILL_TEMPLATE = """
---
name: [SkillName]
description: [Clear, concise description of what this skill does and when to use it.
1-2 sentences focusing on the core purpose and benefits.]
version: 1.0.0
---
# [Skill Title]
## Overview
[1-2 sentences on the core approach]

## Workflow
1. **Analysis**: [Instruct the RM to conduct its detailed analysis under the `--- Analysis ---` section. DO NOT just copy this hint; specify the exact step-by-step format and output layout the RM should use (e.g., examining each candidate response or criteria one by one, applying this skill's principles and the generated rubric, while following the core intent of the user instruction).]
2. **Final Judgment**: [Instruct the RM to aggregate findings under the `--- Final Judgment ---` section and explicitly select exactly ONE winner (never "None" or "Neither"). DO NOT just copy this hint; provide concrete guidance on how to weigh the criteria and aggregate findings to pick the winner, generating the exact fields `Aggregation Summary:`, `Justification:`, and `Winner:`.]
""".strip()

FULL_SKILL_TEMPLATE = """
---
name: [SkillName]
description: [Clear, concise description of what this skill does and when to use it.
1-2 sentences focusing on the core purpose and benefits.]
version: 1.0.0
---
# [Skill Title]
## Overview
[1-2 sentences on the core approach]

## Workflow
1. **Analysis**: [Instruct the RM to conduct its detailed analysis under the `--- Analysis ---` section. DO NOT just copy this hint; specify the exact step-by-step format and output layout the RM should use (e.g., examining each candidate response or criteria one by one, applying this skill's principles and the generated rubric, while following the core intent of the user instruction).]
2. **Final Judgment**: [Instruct the RM to aggregate findings under the `--- Final Judgment ---` section and explicitly select exactly ONE winner (never "None" or "Neither"). DO NOT just copy this hint; provide concrete guidance on how to weigh the criteria and aggregate findings to pick the winner, generating the exact fields `Aggregation Summary:`, `Justification:`, and `Winner:`.]

## Principles
1. **[Short Name]**
**Condition**: [Trigger condition for the principle]
**Principle**: [How to implement the principle in evaluating candidate responses. Must not contradict the forced-choice rule.]
**Example**: [One or more concise example(s) illustrating the condition and the principle. Don't include case IDs or specific options. ]
**Anti-Pattern**: [What to avoid when applying this principle]
2. ...
""".strip()

SKILL_INITIALIZATION_PROMPT = """
You are an expert AI evaluator and prompt engineer. Your task is to generate a high-quality, operational, and reusable skill, which will be used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

You are provided with several reference rollouts. Each reference rollout consists of a User Query, a set of Candidate Responses, the Ground Truth preference among the candidates, an Explanation of why it is preferred, and the RM's evaluation. For each rollout, you should:
- Check if the RM's choice is correct.
- If the RM's choice is correct:
    - Compare the RM's evaluation with the explanation, and verify whether the evaluation is well-reasoned and effective.
    - If the evaluation is good, extract the correct patterns and insights for improvement over the current behavior, and incorporate these insights into the skill you will generate.
- If the RM's choice is incorrect:
    - Compare the RM's evaluation with the explanation, and analyze the reason for the failure.
    - Analyze the failure and extract insights for improvement on how the RM should have evaluated the candidates, and incorporate these into the skill you will generate.

You will generate a skill with a practical, actionable, and step-by-step  SOP for the RM to improve future evaluations. Your skill should strike a balance between specificity and generality, and be applicable to a wide range of future cases.
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this structure and the forced-choice rule without contradiction.


**Reference Rollouts**:
{ref_block}

--------------------------------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Output Format:

**Analysis**
[For each rollout, briefly describe whether the evaluation is good, and analyze the reason for the failure if the RM's choice is incorrect. This part is only for analysis and won't be included in the final skill output.]

**Skill**
[You skill (~1000 words)]

Your Output:

""".strip()

SKILL_IMPROVE_PROMPT_STEP1A = """
You are an expert AI evaluator and prompt engineer. Your task is to refine the skill, which is used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

You are provided with several reference rollouts and the old skill. Each reference rollout consists of a User Query, a set of Candidate Responses, the Ground Truth preference among the candidates, an Explanation of why it is preferred, and the RM's evaluation. For each rollout, you should:
- Check if the RM's choice is correct.
- If the RM's choice is correct:
    - Compare the RM's evaluation with the explanation, and verify whether the evaluation is well-reasoned and effective.
    - If the evaluation is good, extract the correct patterns and insights for improvement over the old skill, and incorporate these into the refined skill.
- If the RM's choice is incorrect:
    - Compare the RM's evaluation with the explanation, and analyze the reason for the failure.
    - Analyze the failure and extract insights to fix the blind spots and limitations of the old skill, and incorporate these insights into the refined skill.

You should output the refined skill for the RM to improve future evaluations. Your skill should strike a balance between specificity and generality, and be applicable to a wide range of future cases.
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this analysis structure and the forced-choice rule without contradiction.

**Reference Rollouts**:
{ref_block}

**Old Skill**:
{old_skill}

-----------------END OF THE SKILL------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Your Output (Skill only, ~1000 words):

""".strip()

SKILL_IMPROVE_PROMPT_STEP1B = """
You are an expert AI evaluator and prompt engineer. Your task is to refine the skill, which is used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

You are provided with several failed reference rollouts and the old skill. For each rollout, the RM made an incorrect choice. Each reference rollout consists of a User Query, a set of Candidate Responses, the Ground Truth preference among the candidates, an Explanation of why it is preferred, and the RM's evaluation. For each rollout, you should:
- Compare the RM's evaluation with the explanation, and analyze the reason for the failure.
- Analyze the failure and extract insights to fix the blind spots and limitations of the old skill by defining new Principles or refining existing ones.

**Crucially**, your refinement should emphasize generating or refining the "Principles" section of the skill (it may or may not be initiated now). Do NOT perform a major overhaul to the core "Analysis" and "Final Judgment" steps in the "Skill" workflow section, as they have already been established. Focus on adding and refining specific principles (with conditions, explanations, examples, and anti-patterns) that address the failed cases.

You should output the refined skill for the RM to improve future evaluations. Your skill should strike a balance between specificity and generality, and be applicable to a wide range of future cases. 
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this analysis structure and the forced-choice rule without contradiction.

**Failed Reference Rollouts**:
{ref_block}

**Old Skill**:
{old_skill}

-----------------END OF THE SKILL------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Your Output (Skill only, ~1000 words):

""".strip()

SKILL_MERGE_PROMPT = """
You are an expert AI evaluator and prompt engineer. Your task is to merge the skills, which are used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

Now you are given multiple skills. You should analyze the commonalities and differences among the skills, and merge them into a single coherent piece of skill that guides the RM's reasoning structure. Your skill should strike a balance between specificity and generality.
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this analysis structure and the forced-choice rule without contradiction.

**Skills to Be Merged**:
{skill_block}

-----------------END OF THE SKILLS------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Your Output (Skill only, ~1000 words):

""".strip()

PATCH_INITIALIZATION_PROMPT = """
You are an expert analysis agent. Your task is to provide modification proposals to the skill, which is used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

You are provided with several failed reference rollouts and the old skill. Each reference rollout consists of a User Query, a set of Candidate Responses, the Ground Truth preference among the candidates, an Explanation of why it is preferred, and the RM's evaluation. For each rollout, you should:
- Compare the RM's evaluation with the explanation, and analyze the reason for the failure.
- Analyze the failure and extract insights to fix the blind spots and limitations of the old skill, and propose modifications for the skill patch. 
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this analysis structure and the forced-choice rule without contradiction.

**Reference Rollouts**:
{ref_block}

**Old Skill**:
{old_skill}

-----------------END OF THE SKILL------------------

**Template for Modification Proposals**
1. **[Action and Target/Location. E.g., Amend Principle 2, Insert a new Workflow Step between 2 and 3]**
**Motivation**: [A short sentence].
**Description**: [A concise and specific description of the modification].

2. ...

-----------------END OF THE TEMPLATE------------------

Generally, you should generate at most one modification for each rollout. Your modification proposal should be concise and specific.

Your Output (Proposals only, in numbered list):

""".strip()

PATCH_MERGE_PROMPT = """
You are an expert editor. Your task is to merge the modifications independently proposed into a single set. The modifications are proposed to refine the skill, which are in turn used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

Now you are given multiple modification proposals and the old skill. You will merge the proposals into a single set and take the old skill as reference.

Principles for merging:
- Pruning: If multiple proposals suggest conceptually similar changes, even across different targets, deduplicate them and only keep one representative entry.
- Consolidation: If multiple proposals modify the same target (e.g., a specific principle or workflow step), combine them into a single, cohesive entry.

**Modification Proposals**:
{patch_block}

**Old Skill**:
{old_skill}

-----------------END OF THE SKILL------------------

Your Output (Proposals only, in numbered list):

""".strip()

PATCH_APPLICATION_PROMPT = """
You are an expert AI evaluator and prompt engineer. Your task is to refine the skill, which is used to guide the Reward Model (RM) in evaluating candidate responses and selecting the best one. You refinement should based on the modification proposals provided.

**Context**: The Reward Model (RM) serves as an evaluator that reads a User Query and a set of candidate responses, and selects the best response for the user query. This skill is meant to directly guide the RM to make better and more accurate evaluations.

Now you are given the modification proposals and the old skill. You will apply each entry of the modification proposals into the old skill, and write the refined skill. You should apply the modifications thoughtfully, and make sure the refined skill is coherent, consistent, and completely directs the RM on how to structure its analysis.

Since we may update the skill iteratively, and a skill of exploding length can even degrade the performance, you should extend the length of the skill sparingly. You should prioritize the modifications that are more fundamental and impactful, and can lead to more improvements in future cases. You may trim down the less important details in the old skill to make room for the new modifications. Your skill should retain a balance between specificity and generality, and be applicable to a wide range of future cases.
**Important RM Settings**: The RM operates by analyzing the user instruction and evaluating candidates in an `--- Analysis ---` section. Your generated skill must seamlessly integrate with this structure. Furthermore, the RM MUST explicitly pick exactly ONE winner (A, B, etc.) in the `--- Final Judgment ---` section and never predict "None" or "Neither". The skill you generate must enforce this analysis structure and the forced-choice rule without contradiction.

**Modification Proposals**:
{patch}

**Old Skill**:
{old_skill}

-----------------END OF THE SKILL------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Your Output (New skill only, ~1000 words):

""".strip()

SKILL_CLUSTERING_PROMPT = """
You are an expert AI evaluator and skill designer. 
Below are some reference skills developed for analyzing and selecting the best candidate responses to user queries.
We want you to take inspiration from them, and extract exactly {k} highly diverse, high-quality new skills representing different perspectives to maximize exploration, while aiming to solve the same task. Each of the {k} generated skills should represent a distinct, valid, and effective approach to analyzing responses and picking a winner.

The structure of each generated skill MUST follow the format expected for downstream use:
1. **Analysis**: How to step-by-step evaluate the candidates and select the best one.
2. **Final Judgment**: How to aggregate findings, explicitly outputting "Aggregation Summary:", "Justification:", and declaring a "Winner:" (precisely one candidate).

Here are the reference skills:
{skill_block}

-----------------END OF THE SKILLS------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

For each generated skill, also indicate which reference skills (by their Skill ID, e.g., 1, 2, 3) inspired it.
Output exactly a JSON list of {k} objects. No markdown formatting for JSON, just the raw JSON text.
[
  {{
    "skill": "skill string 1",
    "inspired_by": [1, 3]
  }},
  {{
    "skill": "skill string 2",
    "inspired_by": [2, 4, 5]
  }},
...
]

""".strip()

TOP_SKILL_MERGE_PROMPT = """
You are an expert AI evaluator and skill designer. 
Below are {k} top-performing skills developed for analyzing and selecting the best candidate responses to user queries.
We want you to combine and learn from these top skills to propose a new, single optimal skill. 
This new skill should synthesize the best practices, most effective steps, and most robust reasoning patterns from the provided references.

The structure of each generated skill MUST follow the format expected for downstream use:
1. **Analysis**: How to step-by-step evaluate the candidates and select the best one.
2. **Final Judgment**: How to aggregate findings, explicitly outputting "Aggregation Summary:", "Justification:", and declaring a "Winner:" (precisely one candidate).

Here are the reference skills:
{skill_block}

-----------------END OF THE SKILLS------------------

**Skill Template**
{skill_template}

-----------------END OF THE TEMPLATE------------------

Please synthesize the core ideas from the references to generate the new optimal skill.
Your Output:

""".strip()

__all__ = [
    'WORKFLOW_ONLY_SKILL_TEMPLATE',
    'FULL_SKILL_TEMPLATE',
    'SKILL_INITIALIZATION_PROMPT',
    'SKILL_IMPROVE_PROMPT_STEP1A',
    'SKILL_IMPROVE_PROMPT_STEP1B',
    'FAILED_CASE_SKILL_REFINEMENT_PROMPT',
    'SKILL_MERGE_PROMPT',
    'PATCH_INITIALIZATION_PROMPT',
    'PATCH_MERGE_PROMPT',
    'PATCH_APPLICATION_PROMPT',
    'SKILL_CLUSTERING_PROMPT',
    'TOP_SKILL_MERGE_PROMPT',
]

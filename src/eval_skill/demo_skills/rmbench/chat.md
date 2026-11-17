name: IntentAccuracyConstraintEvaluator  
description: Evaluates candidate responses by prioritizing core intent fulfillment and strict factual accuracy (including cultural authenticity, misconception detection, and thorough verification), while enforcing only explicitly stated constraints and preferring concise correctness over verbose errors. Ensures logical coherence and rewards transparent reasoning when relevant.  
version: 1.0.0  
---  
# Intent & Accuracy Constraint Evaluator  
## Overview  
This skill guides the Reward Model to select the response that best fulfills the user’s core request, maintains factual and logical precision adheres to all explicitly stated constraints, and avoids invented requirements. It treats factual errors (including cultural inaccuracies, self‑contradictions, and misconception propagation) as disqualifying flaws over formatting or length, and enforces a forced‑choice winner.  

## Workflow  
1. **Analysis**: Under `--- Analysis ---`, evaluate each candidate separately. For each, provide a structured justification using the following criteria **in this order of priority**:  
   - **Core Intent Fulfillment**: Does the response directly address the user’s primary request? If the user asked for a step‑by‑step explanation, a single sentence fails this criterion even if technically correct. If the user asked for code, providing correct code fulfills intent; verbose commentary without code does not.  
   - **Factual Accuracy (Thorough Verification)**: Examine every objective claim from start to finish (including introductory statements, intermediate steps, and concluding remarks). Verify numbers, dates, definitions, ingredients, code logic, and causal statements independently. Treat any single significant factual error (wrong number, incorrect step, cultural inauthenticity, self‑contradiction, reinforcement of a common misconception) as a major flaw. **Self‑contradictions** (e.g., stating “the answer is 5” then later deriving 10) count as factual errors even if the final answer is correct. For cultural/domain queries, verify that ingredients, methods, and terminology match traditional norms; unrealistic or impractical suggestions (e.g., “shoes drawer” for clothes) are factual errors. Misconception propagation (e.g., “finders‑keepers is law”) is a factual error.  
   - **Explicit Constraint Compliance**: Only enforce constraints **literally stated** in the user query (e.g., “no markdown”, “within 200 words”, “use bullet points”, “step‑by‑step”). Do **not** infer additional constraints (e.g., “no markdown” if unmentioned, “must be concise” if not specified). A non‑trivial violation of an explicit constraint is a demerit, but can be overridden if the violating candidate is the only one that meets core intent and factual accuracy.  
   - **Logical Coherence & Consistency**: Check for internal contradictions, logical fallacies, or statements that undermine the response’s own thesis. A logically flawed response (e.g., claiming “no change” then describing evolution) cannot be preferred over a coherent one.  
   - **Reasoning Transparency** (apply only when the query involves estimation, analysis, explanation, or open‑ended reasoning): Prefer responses that show their work, cite assumptions, or admit limitations over those that give unsupported conclusions. Transparency adds reliability but is secondary to factual accuracy and logic.  
   - **Completeness & Proportionality**: Does the response address all parts of the request? For simple, factual queries (definition, yes/no, classification), favor concise answers that directly answer the core question without extraneous padding. Verbose ethical commentary or tangential details reduce completeness for straightforward queries.  
   - **Clarity & Structure**: Use only as a final tiebreaker when all above criteria are equal between candidates.  

   Format: `**Candidate [Letter]:** [criterion‑by‑criterion analysis, starting with core intent, then factual accuracy (including thorough verification and self‑contradiction check), then explicit constraints, then logical coherence, then transparency (if applicable), then completeness, then clarity. State clearly which criteria are met or violated.]`  

2. **Final Judgment**: Under `--- Final Judgment ---`.  
   - **Aggregation Summary**: First, identify candidates that pass Core Intent Fulfillment **and** have no significant factual errors (including cultural errors, contradiction, misconception). If exactly one such candidate exists, it wins. If multiple exist, apply the following tiebreaker order: **Explicit Constraint Compliance** → **Logical Coherence** → **Reasoning Transparency** (if applicable) → **Completeness & Proportionality** → **Clarity**. If all candidates fail Core Intent or have significant factual errors, select the candidate with the best Core Intent Fulfillment and the fewest/least severe factual errors (weigh factual accuracy slightly higher). Never choose a candidate that violates a core instruction if another addresses it correctly and is factually sound.  
   - **Justification**: Explicitly explain the reasoning, referencing the criteria and principles. For example: “Candidate X fulfills the core request, is factually accurate (verified calculation), and complies with explicit constraints, while Candidate Y contains a factual error (wrong ingredient) even though it is more detailed.” Address cultural authenticity, misconception detection, and self‑contradictions if relevant.  
   - **Winner**: Exactly one letter (e.g., `Winner: B`). Never output “None” or “Neither”.  

## Principles  
1. **Core Intent Over Formatting**  
   **Condition**: The user explicitly requests a specific content structure (e.g., “step‑by‑step”, “explain your reasoning”, “provide a recipe”).  
   **Principle**: Treat fulfilling the requested content structure as a core requirement—not a formatting constraint. A candidate that delivers the asked‑for format should be preferred even if it uses markdown or exceeds a word limit, unless the user explicitly prohibits those. A candidate that fails to deliver the requested format (e.g., gives a single sentence when steps are requested) fails core intent.  
   **Example**: User asks “Explain step‑by‑step.” Candidate A gives a single sentence. Candidate B gives numbered steps with markdown. Prefer B even if A is shorter.  
   **Anti‑Pattern**: Penalizing a response for using markdown when the user did not forbid it; assuming “no markdown” is implied.  

2. **Factual Accuracy Primacy (Thorough Verification & No Self‑Contradiction)**  
   **Condition**: Always applicable.  
   **Principle**: Independently verify every objective claim from start to finish. A single significant factual error (wrong number, incorrect step, cultural inauthenticity, self‑contradiction, or myth propagation) disqualifies a candidate from being chosen over any error‑free candidate, regardless of length, structure, or reasoning transparency. Self‑contradictions (e.g., initial claim of 5 then later derivation of 10) are factual errors. Cultural authenticity errors (e.g., using sour cream in a traditional dish that calls for mayonnaise) are treated as factual errors.  
   **Example**: In a math problem, Candidate A writes “The answer is 5” then correctly solves to 10. Candidate B writes “The answer is 10” directly. B wins because A’s initial claim is factually wrong.  
   **Anti‑Pattern**: Overlooking an incorrect introductory statement because the final answer is correct; accepting a claim at face value without verification.  

3. **Only Enforce Stated Constraints**  
   **Condition**: Evaluating constraint compliance.  
   **Principle**: Only enforce constraints that are literally stated in the user query. Do not infer “no markdown”, “must be objective”, or “must be concise” if the user did not specify them. Treat formatting as neutral when unmentioned.  
   **Example**: User asks “Give me a recipe.” Both plain text and markdown‑formatted recipes are equally compliant.  
   **Anti‑Pattern**: Automatically flagging structured formatting as a violation; assuming common expectations are requirements.  

4. **Proportional Conciseness for Simple Queries**  
   **Condition**: The query is straightforward, factual, or seeks a definition/classification without explicit request for extensive detail.  
   **Principle**: Favor responses that are concise and directly answer the core question. Overly detailed responses with tangents (ethical advice, long background) are considered less helpful and less complete for simple queries.  
   **Example**: Query: “Is JavaScript front‑end or back‑end?” A three‑paragraph essay vs. “primarily front‑end, but also back‑end with Node.js.” Prefer the concise answer.  
   **Anti‑Pattern**: Equating length with quality; treating irrelevant context as helpful.  

5. **Logical Coherence Over Conciseness**  
   **Condition**: Always applicable.  
   **Principle**: Check for internal contradictions, logical fallacies, or statements that undermine the response’s own thesis. A logically flawed response is automatically inferior to any logically coherent one, even if the coherent one is longer or less concise. Conciseness is only a tiebreaker after all other criteria are equal.  
   **Example**: Candidate A says “The species did not evolve” then lists evolutionary changes. Candidate B consistently says “The species evolved slowly.” B wins despite being longer.  
   **Anti‑Pattern**: Overlooking a contradictory opening because the rest appears well‑structured.  

6. **Practical Realism & Domain Authenticity**  
   **Condition**: The query involves a practical activity (cooking, organizing) or references a specific culture/domain.  
   **Principle**: Evaluate whether suggestions are realistic, typical, and culturally appropriate. Treat unusual or impractical items (e.g., “shoes drawer” for clothes, chicken substitute in a traditional beef dish) as factual errors. Prefer responses that reflect real‑world common practices over those that pad lists with unrealistic entries.  
   **Example**: User asks for drawer categories – a list including “Shoes Drawer” is impractical and counts as an error.  
   **Anti‑Pattern**: Counting items and choosing the longer list; ignoring common sense because the query is not explicitly labeled “cultural”.
name: Requirement-First Rigorous Evaluation  
description: A comprehensive evaluation skill for both code and math/logic responses, enforcing requirement-first compliance, independent ground-truth derivation, step-by-step mental simulation, error severity classification, and forced-choice winner selection. Balances accuracy and clarity across domains.  
version: 1.0.0  
---  
# Requirement-First Rigorous Evaluation  
## Overview  
This skill guides the Reward Model to systematically evaluate each candidate by first extracting all explicit requirements, then independently deriving the correct answer for provided examples and critical edge cases, and finally simulating the candidate’s reasoning step by step. Errors are classified by severity, and the forced-choice rule ensures exactly one winner is selected.

## Workflow  
1. **Analysis**: Under the `--- Analysis ---` section, for each candidate (A, B, …) perform the following:  
   - **Restate the specification**: Clearly list all explicit constraints, required output format, input types, function signature (if code), and any provided examples.  
   - **Derive the expected answer independently**: Using only the problem definition and standard mathematical/logical rules, compute the correct result for the provided example(s) and at least one critical edge case (e.g., empty input, single element, boundary value, all-equal numbers). Write down this ground‑truth value.  
   - **Simulate the candidate’s reasoning mentally**:  
     * *For code*: Walk through the candidate’s code line by line on the chosen inputs, tracking variable states, array contents, loop iterations, and branch decisions. Write down intermediate values explicitly.  
     * *For math/logic*: Trace each algebraic, geometric, or logical step. Independently recompute every numeric claim (e.g., modulo, divisibility, inequality) and test concrete values from each claimed interval or condition.  
   - **Compare against ground‑truth**: Determine whether the simulated output matches the independently derived expected answer exactly. Flag any discrepancy as a critical error.  
   - **Check for additional critical errors**:  
     * Violations of core requirements (e.g., wrong digit set, ignoring a constraint, inverted condition, off‑by‑one, variable misuse).  
     * Arithmetic or algebraic mistakes that affect the final result.  
     * Inconsistency between reasoning and final answer.  
     * Missing handling of input categories (e.g., lowercase vs uppercase, digits).  
   - **Note minor issues**: Ambiguous phrasing, missing intermediate steps that do not affect correctness, style choices, unused code or diagrams that are not misleading.  
   - **Write a concise justification** for each candidate in the format: `**Response A:** Justification: [detail based on simulation and principles].`  

2. **Final Judgment**: Under the `--- Final Judgment ---` section, determine the winner.  
   - **Aggregation Summary**: Compare candidates primarily on correctness of logic, requirement compliance, and error severity. A single critical error (e.g., wrong final answer, violation of a core constraint) generally disqualifies a candidate. If both are correct, prefer clarity, efficiency, and thoroughness. If both have errors, select the one with fewer or less severe errors.  
   - **Justification**: Explain why the chosen response is better (or less wrong), referencing the simulation, ground‑truth comparison, and error classification. Explicitly note the errors in the losing response.  
   - **Winner**: `Winner: [A/B/…]` (never “None” or “Neither”).

## Principles  
1. **Requirement‑First Compliance**  
   **Condition**: When evaluating any candidate response.  
   **Principle**: Begin by listing every explicit constraint from the user query. For each candidate, verify adherence to all core requirements before considering any other aspect. A single violation of a core requirement (e.g., using wrong coefficient set, ignoring a constraint like “distinct roots”, using a wrong digit set, inverted condition‑action mapping) disqualifies that candidate, regardless of elegance.  
   **Example**: A problem asks to replace three spaces with a single dash. Candidate A replaces three spaces with three dashes (`---`) while Candidate B replaces with a single dash (`-`). Candidate B is correct; A has a critical requirement violation.  
   **Anti‑Pattern**: Selecting a candidate because its answer matches a quick mental estimate without first checking that it respects all given constraints.

2. **Independent Ground‑Truth Derivation**  
   **Condition**: Always, especially when the problem requires computing a numerical or logical result.  
   **Principle**: Before looking at any candidate, derive the correct answer for the provided example(s) and at least one critical edge case using only the problem specification and standard knowledge. Use this ground‑truth as the primary benchmark. Do not accept a candidate’s formula or reasoning as correct without verifying it matches the independently derived result.  
   **Example**: For “compute average of integers from n to m, floor”, ground‑truth: `avg = (n+m)//2` (integer division gives floor when positive). Test on `(2,3)` → ground‑truth is `2`. A candidate returning `3` is incorrect.  
   **Anti‑Pattern**: Using the candidate’s own logic to validate itself, or assuming a plausible output is correct without checking against the problem definition.

3. **Step‑by‑Step Mental Simulation**  
   **Condition**: Always, for every candidate, whether evaluating code or multi‑step reasoning.  
   **Principle**: Mentally simulate the solution line by line (code) or step by step (math/logic) without skipping any statement. Track variable states, recompute every arithmetic operation, and test concrete inputs. For code, explicitly write down intermediate variable values after each iteration. For math, write intermediate expansions or simplifications. If your simulation yields a result that contradicts the candidate’s conclusion, re‑simulate from the candidate’s original material and check your own arithmetic before flagging an error.  
   **Example**: Expanding `(√2+√3)(5+2√6)`: correct is `11√2+9√3`. Candidate writes `5√2+10√6+5√3+6√6=5√2+5√3+16√6` – simulation catches the error in cross‑term multiplication.  
   **Anti‑Pattern**: Skipping intermediate steps; trusting that code “looks correct” without mentally executing it with concrete inputs.

4. **Error Severity Classification**  
   **Condition**: When comparing errors across candidates.  
   **Principle**: Classify each error as **Critical** (causes the final answer to violate a stated requirement, yields an incorrect result from a logical gap, or contains a factual mistake that changes the conclusion) or **Minor** (cosmetic, such as missing a minor justification, unclear phrasing, or a typo that does not affect the core reasoning). A candidate with any critical error cannot be chosen over one with only minor errors. If both have critical errors, select the one whose error is less severe (closer to correct or more easily fixable). Always pick a winner; never “None” or “Neither”.  
   **Example**: Candidate A incorrectly calculates the sum of roots due to an arithmetic mistake (final answer wrong) – critical. Candidate B gives the correct answer but forgets to mention that roots are distinct – minor omission. Candidate B wins.  
   **Anti‑Pattern**: Penalizing a candidate for a small algebraic slip when the overall reasoning is sound and the final answer is correct; or labeling a correct but incomplete approach as “minor error” when it actually misses a key requirement.

5. **Logical Consistency and Faithful Reading**  
   **Condition**: When analyzing any candidate response.  
   **Principle**: Read the response exactly as written; do not infer missing steps or assume errors that are not present. The final answer must be logically consistent with the entire body of reasoning. If the reasoning contains an error that would produce a different answer, but the candidate states the correct answer, the response is still flawed because the reasoning is unsound. Conversely, a correct reasoning with a wrong final answer is also flawed.  
   **Example**: A candidate correctly deduces that the condition implies x > 2, but then writes “x ≥ 2” – the reasoning is inconsistent with the final answer. That is a critical error.  
   **Anti‑Pattern**: Misreading a candidate’s text and penalizing it for an error it did not make, or ignoring a mismatch between intermediate logic and the final stated answer.

6. **Edge‑Case and Strictness Verification**  
   **Condition**: When evaluating edge cases (e.g., empty inputs, single elements, same values, boundary conditions) or conditions involving inequalities (e.g., triangle inequality, range constraints).  
   **Principle**: Test at least one critical edge case implied by the problem (e.g., empty list, single element, all‑equal numbers, maximum/minimum). Enforce the correct strictness (e.g., triangle inequality requires >, not ≥). For code, verify that domain‑excluding values (e.g., denominator zero) are handled correctly. Only penalize a response if the code or reasoning clearly fails on an edge case that is logically required by the problem scope or that differentiates candidates.  
   **Example**: For sides 1 and 3, triangle condition `1 + x > 3` yields x > 2. A response that tests x=2 and claims `1+2>3` (false) is critically wrong. For code, an off‑by‑one loop bound that causes incorrect output for a single‑element input is critical.  
   **Anti‑Pattern**: Downgrading a correct implementation based on an unforeseeable edge case not part of the specification, while ignoring a clear mistake in the other candidate that fails the example. Overlooking strictness (e.g., counting equality as valid when it is not).

7. **Forced‑Choice Enforcement**  
   **Condition**: At the final judgment stage.  
   **Principle**: Always select exactly one candidate as winner. If both candidates are correct, pick the one that is more efficient, clearer, or better handles edge cases. If both are incorrect, pick the one with fewer or less severe critical errors. If they are identical in content, pick the earlier response (A). Never output “None” or “Neither”. This principle overrides any ambiguity.  
   **Example**: Both code responses have a missing function wrapper but one has a correct algorithm and the other has a logical bug – the winner is the one with the correct algorithm.  
   **Anti‑Pattern**: Avoiding a decision by stating “both are equally flawed” or “cannot determine”. The analysis must rank the candidates.
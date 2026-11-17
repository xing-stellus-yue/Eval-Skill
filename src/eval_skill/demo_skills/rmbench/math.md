name: Comprehensive Mathematical Verification and Reasoning Evaluator
description: Evaluates candidate responses for mathematical and logical problems by combining independent verification, logical consistency auditing, and domain-specific checks. Ensures accurate selection of the best response with forced single winner.
version: 1.0.0
---
# Comprehensive Mathematical Verification and Reasoning Evaluator
## Overview
This skill instructs the Reward Model to independently compute a verified ground truth, then assess each candidate through rigorous numerical verification and logical consistency auditing. Domain-specific checks prevent common pitfalls in algebra, geometry, combinatorics, and arithmetic. The RM must always select exactly one winner.

## Workflow
1. **Analysis**: Under the `--- Analysis ---` section, perform the following steps in order:
   a. **Self‑Verified Ground Truth**: Before reading candidates, compute the correct answer using at least two distinct methods (e.g., direct multiplication and stepwise cancellation; algebraic derivation and numeric substitution). If results disagree, recalc until consistent. Record this verified answer as ground truth.
   b. **For each candidate response**, produce two concise paragraphs:
      - **Numerical Verification**: Recompute the final answer from the problem’s raw data using your own independent method (first principles, alternative approach, or order‑of‑magnitude estimate). Perform a substitution test (plug the candidate’s values into original equations/constraints). Confirm the answer respects all explicit constraints (domain, integer requirements, sign conventions, place values). For geometric problems, extract dimensions from the problem description and recalculate area or other quantities. For algebraic problems, re‑derive key steps independently and test with simple numeric substitutions. Flag any discrepancies immediately.
      - **Logical Consistency Audit**: List key assumptions (justified or not). Trace reasoning step‑by‑step, flagging gaps, misapplied theorems, arithmetic errors, internal contradictions, or unjustified shortcuts. Apply the domain‑specific principles below to validate or refute critical steps. Distinguish fatal errors (would change the conclusion) from non‑fatal ones.
   Write these paragraphs under the `--- Analysis ---` header.

2. **Final Judgment**: Under the `--- Final Judgment ---` section, aggregate findings and select exactly one winner. Use the fields exactly: `Aggregation Summary:`, `Justification:`, `Winner:`.  
   - In the summary, briefly compare verification outcomes and reasoning soundness of both candidates.
   - In the justification, apply the correctness priority rule: a candidate with a verified correct final answer wins unless its reasoning contains a fatal logical flaw that makes the answer coincidental. If both answers are correct or both incorrect, use severity of logical gaps to break ties. Never output “None” or “Neither”.

## Principles
1. **Self‑Verified Ground Truth**
   **Condition**: Always, before evaluating any candidate.
   **Principle**: Compute the correct answer using at least two independent methods (e.g., direct multiplication and stepwise cancellation; algebraic derivation and numeric substitution). If results differ, identify the error and recalc until consistent. Record this verified answer as ground truth.
   **Example**: For a product of fractions, multiply numerators and denominators directly, then simplify. Separately, cancel common factors step by step. Both methods must give the same result (e.g., 16). If they disagree (e.g., 24 vs. 16), re‑examine both until the correct value is found.
   **Anti-Pattern**: Relying on a single computation method; assuming that because the RM is an AI, its arithmetic is always correct.

2. **Algebraic and Arithmetic Rigor**
   **Condition**: When responses involve algebraic manipulation, solving equations, or arithmetic calculations.
   **Principle**: Re‑derive all key algebraic steps independently, especially when the candidate’s steps lead to different results. Check for sign errors, incorrect expansion, mis‑applied operations, and arithmetic mistakes. Test derived equations by substituting a simple numeric value and comparing to the original condition. Substitute claimed solutions into the original equation (not the candidate’s derived one) to verify they satisfy it. Flag any mismatch as a critical flaw.
   **Example**: For a fixed‑point problem, if a candidate derives x² - 7x - 42 = 0, re-derive from the given recurrence. The correct equation might be x² - x - 6 = 0; testing x=7 shows the candidate’s equation fails.
   **Anti-Pattern**: Trusting the candidate’s algebraic manipulation without re‑derivation; relying on apparent logical flow when math is flawed.

3. **Sign and Place Value Rigor**
   **Condition**: When evaluating expressions with sign conventions (e.g., Vieta’s formulas) or multi‑digit numbers.
   **Principle**: Pay meticulous attention to sign conventions. For a polynomial with leading coefficient 1, the product of roots is (-1)^n times the constant term. Immediately flag any candidate that writes “product = constant term” without the sign factor. Also verify magnitude: for 5‑digit numbers, the average must be around 50,000; a result like 5,332.8 indicates a missing place value and is a critical error.
   **Example**: For x³ - 6x² + 21x + a, product of roots = -a. A candidate claiming “product = a” makes a sign error; the correct equation (2-3i)(2)(2+3i) = -a gives 26 = -a, so a = -26.
   **Anti-Pattern**: Accepting a candidate’s statement that “product equals a” without verifying sign; overlooking a missing place value because intermediate numbers look plausible.

4. **Geometric and Diagram Interpretation**
   **Condition**: Problem involves geometric figures (coordinates, diagrams, labeled dimensions).
   **Principle**: Independently extract dimensions from the problem description (including Asymptote code) and reconstruct the shape. Verify that the candidate’s decomposition matches the labels. If a candidate misreads a dimension, uses wrong side lengths, or omits a part of the shape, flag it as a critical error. Check side identification (hypotenuse vs. legs), ratio application (e.g., 30-60-90), and ensure area formulas use only the legs. Verify derived lengths satisfy the Pythagorean theorem and triangle inequality.
   **Example**: An L‑shaped region with labels “4 yds” top, “5 yds” left, “2 yds” right, “3 yds” interior. Correct decomposition is 4×5 + 5×2 = 30 sq yd. A candidate using 3×5 for the second rectangle (total 35 sq yd) misreads the interior dimension and is incorrect.
   **Anti-Pattern**: Accepting the candidate’s dimensions at face value; failing to redraw the shape mentally; assuming a common decomposition without verifying labels.

5. **Symmetry and Counting Verification**
   **Condition**: Problem involves establishing symmetry about a diagonal, axis, or other line in a grid or geometric arrangement, and the candidate lists symmetric pairs or counts required colorings.
   **Principle**: Independently enumerate all unordered pairs of cells that are symmetric across the designated line, including self‑symmetric cells (on the line). Determine the current coloring from the problem description. Then compute the minimum number of additional colorings needed: each mismatched pair (one colored, one uncolored) requires one additional coloring. Do not rely on the candidate’s list; construct your own from the problem’s visual or coordinate description.
   **Example**: For a 4×4 grid with diagonal from bottom‑left to top‑right, list all pairs (i,j) and (j,i) with i<j. Check each pair against the given diagram. Count mismatched pairs; that is the minimum additional colored squares required.
   **Anti-Pattern**: Accepting the candidate’s pairing and count without checking each pair individually; misidentifying reflection direction; forgetting self‑symmetric cells.

6. **Fraction Reduction and Factorial Validation**
   **Condition**: Answers expressed as fractions, probabilities, or expressions involving factorials and powers.
   **Principle**: Verify that the fraction is fully reduced (numerator and denominator are coprime). For factorial terms, count the exponent of each prime (especially 2) using floor summation (e.g., for 40!, exponent of 2 = 20+10+5+2+1=38). Ensure the final denominator after cancellation matches the problem’s “relatively prime” requirement. Do not assume a denominator is correct without checking common factors.
   **Example**: Probability 40! / 2^780 reduces to 1 / 2^(780–38)=1/2^742. A candidate that gives denominator 2^780 is incorrect.
   **Anti-Pattern**: Accepting a “simple” power without verifying cancellation of factorial factors.

7. **Boundary Precision for Floor/Ceiling**
   **Condition**: When the candidate calculates digit counts, ranges, or any quantity that involves floor/ceiling of logarithms or similar functions, especially at boundaries where the argument is close to a power of the base.
   **Principle**: Use exact arithmetic rather than approximations. For example, for n = 2^k – 1, the floor of log_2 n is exactly k – 1, not k. Verify the bound by comparing n to the nearest powers of two. Compute the exact inequality.
   **Example**: If a candidate claims that for n = 4095, d = floor(log_2 4095) + 1 = 13 (because log_2 4095 ≈ 12), this is incorrect because 2^12 = 4096 > 4095, so floor is 11 and d = 12.
   **Anti-Pattern**: Assuming that an approximate logarithm value gives the floor without checking the exact inequality.

8. **Logical Fallacy and Assumption Scrutiny**
   **Condition**: When candidates apply algebraic manipulations, coefficient comparison, functional equation solving, or combinatorial modelling.
   **Principle**: Scrutinize each step for validity. Flag coefficient comparison errors (e.g., equating coefficients in an identity that still contains a variable), division by a variable without checking zero, misapplication of stars‑and‑bars (variables summing to wrong total), or misuse of combinatorial formulas. List all explicit and implicit assumptions; if an assumption is not justified by the problem (e.g., “the triangle must be right‑angled to maximize area”), treat it as a severe logical flaw. Prefer candidates that systematically enforce constraints from the start.
   **Example**: In a functional equation, a candidate writes “a²x = (a+1)x² + x” and then “equates coefficients” to get a² = a+1. This is invalid because the equation involves both x² and x; the correct deduction is a+1=0 and 1–a²=0. The candidate’s reasoning is flawed and its answer is wrong.
   **Anti-Pattern**: Overlooking a step that appears plausible but is mathematically unsound; accepting a plausible shortcut without justification.

9. **Context-Aware Constraint Verification**
   **Condition**: Problems impose specific constraints (e.g., leading digit non‑zero, non‑decreasing digits, domain restrictions, required answer format).
   **Principle**: Ensure the candidate’s model and final answer respect all explicit constraints. For combinatorial problems, check that variables sum correctly (e.g., number of digits, not digit sum). For “for all x” problems, consider the domain. If a candidate misinterprets a constraint (e.g., treats “non‑decreasing” as “strictly increasing” when repetition is allowed), that constitutes a fundamental error regardless of internal consistency.
   **Example**: Counting 7‑digit numbers with non‑decreasing digits (repetition allowed). The correct model is stars‑and‑bars with 7 items and 9 bins → C(15,7)=6435. A candidate using x1+…+x7=9 (sum to 9 instead of 7) is wrong.
   **Anti-Pattern**: Accepting a candidate’s model without verifying it matches the problem statement exactly.

10. **Completeness and Optimality Check**
    **Condition**: The problem asks for the smallest, largest, first, etc., or the candidate’s method restricts the search space (e.g., testing only numbers with a specific ending).
    **Principle**: The RM must evaluate whether the candidate’s reasoning exhaustively covers all plausible candidates or provides a rigorous justification for the restriction. If a valid alternative exists that the candidate did not test and that leads to a different (especially better) answer, the candidate’s reasoning is incomplete and should be considered a fatal flaw.
    **Example**: For “smallest integer whose cube ends in 888”, a candidate that tests only numbers ending in 42 (obtaining 842) is incomplete because a smaller solution (192) exists ending in 92. That candidate’s answer is not the smallest, so it should be rejected.
    **Anti-Pattern**: The RM concludes a response is correct solely because its answer satisfies the condition, ignoring that a better (smaller/larger) answer exists and that the candidate’s method was not exhaustive.

11. **Accurate Content Reading and Cross-Reference**
    **Condition**: At the start of evaluation, and when comparing candidates.
    **Principle**: Restate the problem in your own words to confirm correct interpretation. Identify the exact question, constraints, required output. Then, before drawing conclusions about a candidate's answer, explicitly double‑check what the candidate actually states (e.g., which numbers are listed, which steps are shown). Misreading a candidate’s content can lead to an incorrect comparison and is a critical failure.
    **Example**: If candidate B says the numbers are 14, 28, 41, 82, the RM must not claim that B omitted 28. Correct reading is essential.
    **Anti-Pattern**: Relying on memory or pattern‑matching; assuming a candidate omitted a number based on an initial glance without explicit verification.

12. **Verification Depth and Efficiency Balance (Tie-breaker)**
    **Condition**: Both candidates are numerically correct and logically sound.
    **Principle**: Favor the response that demonstrates appropriate verification depth without unnecessary clutter. Extra verification steps (e.g., back‑substitution, consistency checks, plausibility reasoning) that reinforce rigor are a positive attribute. However, steps that are irrelevant, redundant, or include invalid cases detract from clarity. A concise, systematic progression that directly addresses the problem is preferred over a verbose enumeration that includes extraneous or invalid entries. Conciseness with correct logic is valued, but not at the expense of skipping meaningful verification.
    **Example**: In a “smallest N” problem, a candidate that lists only valid constraints in order and checks divisibility directly is preferred over one that lists many invalid pairs and then discards them, unless the discard process is necessary for clarity.
    **Anti-Pattern**: Automatically favoring the longer response as “more thorough” if it includes invalid or irrelevant steps; automatically favoring the shorter response as “more efficient” if it omits important verification that would catch errors.
name: RigorousCodeEvaluatorWithSpecificationAwareness  
description: Evaluates programming responses by combining specification-grounded independent output derivation, thorough compilation and runtime safety checks, meticulous simulation of all examples and adversarial edge cases, and deep logical correctness analysis to select the most correct, safe, and specification-faithful solution.  
version: 1.0.0  
---  
# Rigorous Code Evaluation with Specification Awareness  
## Overview  
This skill first derives expected outputs solely from the problem statement and examples, then for each candidate performs compilation, safety, specification conformance, and semantic alignment checks, followed by line‑by‑line simulation of all provided examples and at least three targeted adversarial edge cases, plus a mandatory logical correctness analysis. It enforces a forced‑choice selection with a clear priority hierarchy.

## Workflow  
1. **Analysis**: Under the `--- Analysis ---` section, follow these steps in strict order.  
   - **Problem Interpretation (Applied Once)**: Before any candidate simulation, derive the expected outputs for **all** user‑provided examples and for at least three key adversarial edge cases **directly from the problem statement alone**. Write these expectations in a sub‑section “Derived Expected Outputs”. Document reasoning, especially for implicit values (e.g., deriving `tri(0)` from an even‑number rule). This step is performed once and applied to all candidates.  
   - **For each candidate response X**:  
     - **Compilation Check**: Mentally compile the code. Check missing imports (e.g., `use std::collections::HashSet;`, `#include <vector>`), syntax errors, type mismatches, undefined functions. State “Compiles cleanly” or “Compilation error: [precise description]”. If a compilation error exists, mark candidate as **defective** and skip remaining steps.  
     - **Runtime Safety Check**: Simulate with **minimal valid inputs according to the problem domain** (e.g., non‑empty lists if required). Look for unsigned underflow (`vec.len() - n` when `len() < n`), slice bounds panics, unwrap on `None`, null dereference, arithmetic overflow. Mark as **defective** if any unsafe behavior is found. **Note:** `0..len()` is always safe.  
     - **Specification Conformance**: Compare against the exact function signature (name, parameter types, return type) and any explicit constraints (output format, method name) given in the user query. Any deviation (e.g., returning `pair` instead of `vector`) is a critical failure.  
     - **Semantic Alignment**: Derive the intended meaning of key problem terms (e.g., “word”, “distinct”, “even palindrome”) from the problem statement and examples. Flag any candidate that misinterprets these definitions (e.g., classifying by digit length instead of numeric parity for “even”).  
     - **Simulation of Provided Examples**: For each example, independently trace the candidate’s code line by line. Track all intermediate variable states and the final output; compare to the derived expected output from the Problem Interpretation step. Do **not** rely on the candidate’s own test output or comments. If any example fails, mark candidate as **INCORRECT** and skip remaining steps.  
     - **Simulation of Adversarial Edge Cases**: Using the adversarial inputs already defined in Problem Interpretation, perform the same detailed line‑by‑line simulation. At least one adversarial case must probe implicit domain‑specific constraints not covered by the examples (e.g., leading zeros, overlapping patterns, rounding ties). If any case fails, note the mismatch.  
     - **Logical Correctness Analysis (Mandatory)**: Even if all simulations pass, examine the core algorithm for hidden bugs:  
       - Condition Verification: Compare every conditional operator and threshold against the specification (e.g., `shift > length` vs `>=`). Test boundary values.  
       - Arithmetic Transformation Verification: Manually compute character additions, modulo operations, etc., for all relevant inputs.  
       - Deep Logic Check: Look for language‑specific pitfalls (e.g., Go loop‑variable aliasing, JavaScript comma operator, Rust unsigned underflow in capacity calculations), double‑counting, off‑by‑one, wrong loop invariants.  
       If a logical flaw is found, mark the candidate as **logically incorrect**.  
     - **Summary**: Conclude with a clear statement of all findings (compilation, safety, spec conformance, semantic alignment, simulation results, logical flaws). Use structured format:  
       ```  
       **Candidate X:**  
       - Compilation: Compiles cleanly.  
       - Runtime Safety: Safe – no panics on valid input.  
       - Specification Conformance: Pass – matches function signature.  
       - Semantic Alignment: Correct interpretation of problem terms.  
       - Provided Examples: Example 1 passed, Example 2 passed.  
       - Adversarial Cases: Adversarial 1 (overlap) – expected 3, actual 2 (incorrect).  
       - Logical Correctness Analysis: Off‑by‑one in loop condition – logically incorrect.  
       - Summary: Compiles, safe, spec conformant, but fails adversarial case 1 and has a logical flaw.  
       ```  

2. **Final Judgment**: Under the `--- Final Judgment ---` section:  
   - **Aggregation Summary**: Compare candidates in strict priority order:  
     1. **Compilation and Safety**: Any candidate with a compilation error or runtime safety defect is automatically inferior to any candidate that compiles and is safe.  
     2. **Specification Conformance**: Among safe/compilable candidates, a candidate that violates the spec (signature, output format) is inferior to one that conforms.  
     3. **Semantic Alignment**: A candidate that misinterprets the problem’s core definitions is inferior, even if examples coincidentally pass.  
     4. **Provided Example Failures**: A candidate that fails any provided example (after independent expected‑output derivation) is inferior to one that passes all.  
     5. **Logical Correctness**: Among candidates passing all examples, a candidate with a proven logical error (condition, arithmetic, deep bug) is inferior to one that is logically sound.  
     6. **Adversarial Performance**: If still tied, compare the number and severity of adversarial failures. Prefer the candidate with fewer or less critical failures.  
     7. **Code Quality Tiebreaker (if all else equal)**: Use idiomatic style, efficiency, readability as a final decider, along with standard conventions (e.g., ascending order for “sorted list”, contiguous for “substring”).  
   - **Justification**: Explain why the winner is chosen, referencing specific compilation errors, safety defects, specification violations, semantic misinterpretations, simulation mismatches, logical flaws, or adversarial case results. Emphasize that independent expected outputs are used, not candidate comments.  
   - **Winner**: Exactly one winner (e.g., `Winner: Response B`). Never output “None” or “Neither”. If all candidates fail all tests, select the one that compiles, is safe, and passes the most total tests (or fails on the least critical input) and justify.

## Principles  
1. **Specification‑Grounded Interpretation**  
   **Condition**: Before any simulation or comparison.  
   **Principle**: Derive expected outputs for all provided examples and for at least three key adversarial edge cases **solely from the problem statement and its examples**. Do not rely on the candidate’s code or any external assumptions. If the problem implicitly defines a value (e.g., `tri(0)` from an even‑number rule), derive it logically. Document these expectations in a “Problem Interpretation” subsection. Only then simulate candidates against these expectations.  
   **Example**: For an exchange problem where the rule is “exchange of elements between them” without requiring value matching, derive that the condition is `count(odds in lst1) <= count(evens in lst2)`.  
   **Anti-Pattern**: Relying on your own ad‑hoc assumptions about what the code should do, or testing inputs outside the problem’s domain.

2. **Compilation Rigor**  
   **Condition**: Always during the compilation check.  
   **Principle**: Perform a deep mental compilation. Trace every method chain step‑by‑step, noting intermediate types. Verify that all external functions, macros, or methods are either part of the language prelude or explicitly imported. For example, in Rust, `min()` requires `use std::cmp::min;` unless using the `.min()` method. In C++, `std::round` requires `#include <cmath>`. Also check that `.collect()` target types match the iterator’s item type.  
   **Example**: In Rust, `let rotated: String = b.iter().cycle().skip(i).take(len_b).cloned().collect();` where `b: &[u8]` → compilation error because `String` cannot be built from `u8` items.  
   **Anti-Pattern**: Assuming code compiles because it “looks right”; ignoring missing imports or type mismatches.

3. **Unsigned Underflow and Safety Vigilance**  
   **Condition**: Code uses unsigned types (e.g., `usize` in Rust) for arithmetic, especially loop bounds or capacity calculations.  
   **Principle**: Immediately check if subtraction from an unsigned length can underflow. For example, `vec.len() - n` is unsafe if `vec.len() < n`. Similarly, `Vec::with_capacity(len*2-1)` underflows on empty input. Mark as defective unless the code explicitly handles the underflowing case (e.g., early return). **Do not flag `0..len()`, `len-0`, or similar safe patterns.**  
   **Example**: `for i in 0..sorted_nmbs.len() - 2` is unsafe on vectors of length 0,1,2; candidate with early return `if sorted_nmbs.len() < 3 { return ... }` is safe.  
   **Anti-Pattern**: Calling all subtractions unsafe; ignoring that the problem guarantees non‑empty input, but robust code should still avoid panics.

4. **Meticulous Step‑by‑Step Simulation**  
   **Condition**: When simulating any test case (provided examples or adversarial).  
   **Principle**: Perform a line‑by‑line mental trace, recording exact variable values after each operation. Do not shortcut or rely on intuition. Independently derive the correct output from the problem statement (via Problem Interpretation) before simulating the code, so that you can catch cases where the code produces the correct numeric answer through an incorrect path.  
   **Example**: For `fruit_distribution(s,n)` with `s="5 apples and 6 oranges"`, trace: `s.split()` → `['5','apples','and','6','oranges']`. Then verifying indexing: `parts[2]` is `'and'`, not `'6'`. Mark as incorrect even if the final result appears plausible.  
   **Anti-Pattern**: Assuming the final output matches expectation without verifying each intermediate step.

5. **Logical Correctness Beyond Examples**  
   **Condition**: When candidates pass all provided examples.  
   **Principle**: Perform a deeper analysis of the algorithm’s core logic, including condition thresholds (e.g., `>=` vs `>`), arithmetic transformations, and language‑specific pitfalls. A candidate with a provable logical error is inferior even if examples accidentally match.  
   **Example**: Problem: “if shift > number of digits, reverse”. Candidate uses `if shift >= length`. Simulate (12,2): shift=2, length=2 → condition true → returns reversed “21”, but spec expects “12”. Logical error detected.  
   **Anti-Pattern**: Assuming examples fully verify correctness; ignoring subtle condition mismatches.

6. **Targeted Adversarial Testing and Differentiating Cases**  
   **Condition**: When constructing adversarial test cases and when comparing tied candidates.  
   **Principle**: Design at least three edge cases that directly stress the problem’s core requirements (e.g., overlapping patterns, rounding at halves, powers of 1, boundary values). At least one case must probe implicit domain‑specific constraints not covered by the examples. Additionally, if both candidates pass all provided examples and are otherwise tied, design a **differentiating case** that isolates the algorithmic difference between the two implementations. The candidate producing the correct expected output on that case is preferred.  
   **Example**: For carrot‑eating, Candidate A uses `Math.min(number+need, remaining)` and B uses `number + Math.min(need, remaining)`. Test `eat(5,6,10)`: A outputs `[10,0]` (incorrect), B outputs `[11,4]` (correct). Differentiating case decides winner.  
   **Anti-Pattern**: Using only generic edge cases; failing to design a case that exposes the logical difference.

7. **Forced Choice with Principled Tie‑Breaking**  
   **Condition**: Always, because a single winner must be selected.  
   **Principle**: After applying all prior criteria (compilation, safety, spec, semantic alignment, examples, logical correctness, adversarial), if a tie remains, break by preferring the implementation that is more robust (handles edge cases explicitly) or better aligned with standard conventions (e.g., ascending order for “sorted list”, contiguous for “substring”). If still tied, use code quality (readability, efficiency) as a final tiebreaker. Never output “None” or “Neither”.  
   **Example**: Two identical implementations; clarity decides winner. But if one fails a differentiating case, clarity is irrelevant.  
   **Anti-Pattern**: Arbitrarily choosing the shorter answer when a clear logical distinction exists; ignoring robustness differences.
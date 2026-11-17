name: **StringentFormatVerifier**
description: Evaluates candidate responses by performing strict character‑by‑character verification of all explicit formatting and delimiters. Use when the user instruction demands exact strings (e.g., specific separator, forced‑choice options, tag syntax) and any deviation is unacceptable.
version: 1.0.0
---
# StringentFormatVerifier
## Overview
This skill treats explicit formatting constraints as absolute binary gates. The RM must match every required character sequence precisely, ignoring only leading/trailing whitespace. No partial credit is given; a single misplaced character disqualifies the candidate unless no candidate fully complies.

## Workflow
1. **Analysis**: Under `--- Analysis ---`, first extract every explicit format constraint from the user query (e.g., "use `!?!?` as list separator", "answer exactly with a), b), c), or d)", "must start with the word 'Consider'"). For each constraint, define the exact string pattern (case‑sensitive, punctuation included). Then examine each candidate response. For each candidate, produce a list of constraints and mark each as `Pass` (exact match) or `Fail` (any mismatch, extra characters, missing characters). Provide the actual text that caused the failure. Do not evaluate content quality before completing this check. If a candidate fails any format constraint, note that it is disqualified unless all candidates fail.
2. **Final Judgment**: Under `--- Final Judgment ---`, aggregate findings. If at least one candidate passes **all** format constraints, disqualify all that failed and select the best among the passing candidates using secondary criteria (completeness, clarity, relevance). If no candidate passes all, select the candidate with the fewest or least severe formatting deviations (e.g., missing a single character vs. completely different delimiter). Always pick exactly one winner. Output `Aggregation Summary:`, `Justification:`, and `Winner: Response [X]`.
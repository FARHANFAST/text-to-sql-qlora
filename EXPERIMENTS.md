# Experiments

| Exp ID | Description | Model | Prompt | Fine-tuned? | Self-correct? | EX (dev) | 95% CI | Easy | Medium | Hard | Extra | EX (test) | Real-world EX | Avg latency | Cost / 1K queries | Predictions file |
|--------|-------------|-------|--------|-------------|----------------|----------|--------|------|--------|------|-------|-----------|---------------|-------------|-------------------|-------------------|
| 1 | Baseline, prompt v1 (schema only, zero-shot) | Qwen2.5-Coder-1.5B-Instruct | v1 | no | no | 58.8% | [55.7%, 61.9%] | 80.6% | 59.9% | 46.0% | 36.7% | pending | pending | 0.30s/query (batched, T4) | pending | results/predictions_exp_baseline_v1.jsonl |
| 2 | Prompt v2 (+ foreign keys, sample rows) | Qwen2.5-Coder-1.5B-Instruct | v2 | no | no | 64.3% | [61.4%, 67.4%] | 82.7% | 67.7% | 50.0% | 42.8% | pending | pending | 0.43s/query (batched, T4) | pending | results/predictions_exp_baseline_v2.jsonl |
| 3 | Prompt v3 (+ 3 few-shot examples) | Qwen2.5-Coder-1.5B-Instruct | v3 | no | no | 63.1% | [60.1%, 65.9%] | 85.5% | 66.1% | 55.7% | 28.9% | pending | pending | 0.95s/query (batched, T4) | pending | results/predictions_exp_baseline_v3.jsonl |
| 4 | QLoRA run A (rank 16, alpha 32, 1 epoch) | Qwen2.5-Coder-1.5B-Instruct + LoRA | v2 | yes | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | results/predictions_exp4_run_a.jsonl (pending) |
| 5 | QLoRA run B | pending | pending | yes | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 6 | Self-correction on best fine-tuned model | pending | pending | yes | yes | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 7 | 70B comparison (Groq) | pending | pending | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 8 | Real-world eval | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9a | Real-world: schema descriptions | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9b | Real-world: value hints + linking | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9c | Real-world: schema pruning | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9d | Real-world: self-consistency voting | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

`EX (test)` is filled in only once per final configuration (best baseline, best fine-tuned model, best with self-correction, 70B) — see CLAUDE.md's dev-vs-test rule. All numbers come only from files in `results/` produced by real runs. A row stays "pending" until that run has actually happened.

Notes on Exp 1-3:
- `EX (dev)`, the 95% CI, and the per-difficulty breakdown are all from the official evaluator (test-suite-sql-eval, `--etype exec`), not my own quick evaluator. My quick evaluator is stricter (plain Counter comparison of result rows), while the official one allows column-order permutation and ignores DISTINCT mismatches by default, so it scores a few points higher on real model output. Both evaluators agree on the sanity check (gold predictions score 100%, broken SQL scores 0%); the gap only shows up on real predictions, so I kept my evaluator for fast iteration and the official one for the numbers reported here.
- "Avg latency" is labeled with its actual meaning for these rows: average generation time per query, measured in a batch on a T4 GPU, not single-query latency (a single query run alone would be slower per-token but not batched against others).
- Test-suite accuracy isn't required for every prompt-comparison run (only for final configurations — best baseline, best fine-tuned model, best pipeline), but a fast evaluator (`scripts/test_suite_eval.py`) made it practical here too, so I'm reporting it as a secondary, clearly-labeled number, not in the main table because the table has no column for it:
  - Exp 1 (v1): test-suite accuracy 50.9%, 95% CI [47.7%, 54.3%]
  - Exp 2 (v2): test-suite accuracy 55.0%, 95% CI [52.0%, 58.0%]
  - Exp 3 (v3): test-suite accuracy 54.1%, 95% CI [51.1%, 57.0%]

  Test-suite accuracy is lower than plain EX for all three, as expected — it catches predictions that coincidentally returned the right rows on one database but not on the perturbed variants. The ranking (v2 > v3 > v1) matches plain EX, so the two metrics agree on which prompt is best.
- McNemar's test (on official per-example correctness): v2 beats v1 with p = 2.8e-06, and v3 beats v1 with p = 0.0086 — both real improvements over the zero-shot baseline. v2 vs v3 gives p = 0.43, so they're statistically indistinguishable in accuracy. I'm using prompt v2 for fine-tuning: same accuracy as v3 within noise, but about 2x faster to generate and roughly a third of the prompt length, so there's no measured upside to the extra few-shot tokens at this prompt length.

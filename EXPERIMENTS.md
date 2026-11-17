# Experiments

| Exp ID | Description | Model | Prompt | Fine-tuned? | Self-correct? | EX (dev) | 95% CI | Easy | Medium | Hard | Extra | EX (test) | Real-world EX | Avg latency | Cost / 1K queries | Predictions file |
|--------|-------------|-------|--------|-------------|----------------|----------|--------|------|--------|------|-------|-----------|---------------|-------------|-------------------|-------------------|
| 1 | Baseline, prompt v1 (schema only, zero-shot) | Qwen2.5-Coder-1.5B-Instruct | v1 | no | no | 58.8% | [55.7%, 61.9%] | 80.6% | 59.9% | 46.0% | 36.7% | pending | pending | 0.30s/query (batched, T4) | pending | results/predictions_exp_baseline_v1.jsonl |
| 2 | Prompt v2 (+ foreign keys, sample rows) | Qwen2.5-Coder-1.5B-Instruct | v2 | no | no | 64.3% | [61.4%, 67.4%] | 82.7% | 67.7% | 50.0% | 42.8% | 64.4% [62.4%, 66.3%] | pending | 0.43s/query (batched, T4) | pending | results/predictions_exp_baseline_v2.jsonl |
| 3 | Prompt v3 (+ 3 few-shot examples) | Qwen2.5-Coder-1.5B-Instruct | v3 | no | no | 63.1% | [60.1%, 65.9%] | 85.5% | 66.1% | 55.7% | 28.9% | pending | pending | 0.95s/query (batched, T4) | pending | results/predictions_exp_baseline_v3.jsonl |
| 4 | QLoRA run A (rank 16, alpha 32, 1 epoch) | Qwen2.5-Coder-1.5B-Instruct + LoRA | v2 | yes | no | 72.0% | [69.1%, 74.9%] | 86.7% | 76.0% | 60.3% | 51.2% | 73.9% [72.0%, 75.6%] | pending | 0.43s/query (batched, T4) | pending | results/predictions_exp4_run_a.jsonl |
| 5 | QLoRA run B (rank 32, alpha 64, 1 epoch — best of 4 evaluated checkpoints: steps 63/126/189 + final) | Qwen2.5-Coder-1.5B-Instruct + LoRA | v2 | yes | no | 72.0% | [68.9%, 74.7%] | 87.5% | 76.7% | 58.6% | 50.0% | pending | pending | 0.45s/query (batched, T4) | pending | results/predictions_exp5_run_b_final.jsonl |
| 6 | Run A with self-correction: retry on SQL error with the error text fed back, max 2 retries | Qwen2.5-Coder-1.5B-Instruct + LoRA | v2 | yes | yes | 74.2% | [71.5%, 76.7%] | 88.3% | 77.8% | 63.8% | 54.2% | 74.7% [72.8%, 76.4%] | pending | about +0.13s/query over 0.43s (batched, T4) | pending | results/predictions_exp6_error_retry.jsonl |
| 7 | 70B comparison (Groq) | pending | pending | no | no | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 8 | Real-world eval | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9a | Real-world: schema descriptions | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9b | Real-world: value hints + linking | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9c | Real-world: schema pruning | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| 9d | Real-world: self-consistency voting | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

`EX (test)` is filled in only once per final configuration (best baseline, best fine-tuned model, best with self-correction, 70B): development and model/prompt selection happen entirely on Spider dev, and the test split is touched exactly once per final configuration, with no further tuning afterward (see README.md). All numbers come only from files in `results/` produced by real runs. A row stays "pending" until that run has actually happened.

Notes on Exp 1-3:
- `EX (dev)`, the 95% CI, and the per-difficulty breakdown are all from the official evaluator (test-suite-sql-eval, `--etype exec`), not my own quick evaluator. My quick evaluator is stricter (plain Counter comparison of result rows), while the official one allows column-order permutation and ignores DISTINCT mismatches by default, so it scores a few points higher on real model output. Both evaluators agree on the sanity check (gold predictions score 100%, broken SQL scores 0%); the gap only shows up on real predictions, so I kept my evaluator for fast iteration and the official one for the numbers reported here.
- "Avg latency" is labeled with its actual meaning for these rows: average generation time per query, measured in a batch on a T4 GPU, not single-query latency (a single query run alone would be slower per-token but not batched against others).
- Test-suite accuracy isn't required for every prompt-comparison run (only for final configurations — best baseline, best fine-tuned model, best pipeline), but a fast evaluator (`scripts/test_suite_eval.py`) made it practical here too, so I'm reporting it as a secondary, clearly-labeled number, not in the main table because the table has no column for it:
  - Exp 1 (v1): test-suite accuracy 50.9%, 95% CI [47.7%, 54.3%]
  - Exp 2 (v2): test-suite accuracy 55.0%, 95% CI [52.0%, 58.0%]
  - Exp 3 (v3): test-suite accuracy 54.1%, 95% CI [51.1%, 57.0%]

  Test-suite accuracy is lower than plain EX for all three, as expected — it catches predictions that coincidentally returned the right rows on one database but not on the perturbed variants. The ranking (v2 > v3 > v1) matches plain EX, so the two metrics agree on which prompt is best.
- McNemar's test (on official per-example correctness): v2 beats v1 with p = 2.8e-06, and v3 beats v1 with p = 0.0086 — both real improvements over the zero-shot baseline. v2 vs v3 gives p = 0.43, so they're statistically indistinguishable in accuracy. I'm using prompt v2 for fine-tuning: same accuracy as v3 within noise, but about 2x faster to generate and roughly a third of the prompt length, so there's no measured upside to the extra few-shot tokens at this prompt length.

Notes on Exp 4 (QLoRA run A):
- Trained with Unsloth (confirmed from the adapter's own `adapter_config.json`: `base_model_name_or_path` is Unsloth's pre-quantized repo, `unsloth/Qwen2.5-Coder-1.5B-Instruct-bnb-4bit`, with `"unsloth_fixed": true`), rank 16, alpha 32, dropout 0.05, 1 epoch, on all LoRA target projections. Training loss: 0.111 at the last logged step (252/252), 0.182 averaged over the whole epoch. Evaluated merged into the full fp16 base model, not the 4-bit base it trained against — a small, expected train/inference precision difference (standard QLoRA practice), noted in `results/step8_run_a/run_metadata.json`.
- 1,034/1,034 outputs cleaned into SQL with `strip_sql_fences` (0 empty, 0 not starting with SELECT/WITH) — same as the baseline, so the EX gap below is a real accuracy difference, not a formatting/parsing artifact.
- Official EX jumped from 64.3% (baseline v2) to 72.0% — a 7.7-point gain. Test-suite accuracy: 64.9%, 95% CI [61.9%, 67.8%] (up from v2's 55.0%).
- McNemar's test, Run A vs baseline v2 (official per-example correctness): b = 141 (Run A fixed), c = 62 (Run A broke), p = 4.4e-08 — a real, large improvement, not noise.
- Secondary: exact match (normalized string comparison — lowercase, whitespace-collapsed, not the official parsed-SQL exact match) is 41.9% for Run A vs 24.9% for baseline v2, a bigger jump (+17 points) than the EX gain (+7.7 points). Part of that gap is the fine-tuned model imitating gold SQL formatting and style more closely (keyword case, spacing, column order) rather than purely getting more questions right — exact match is reported here only as a secondary, clearly-labelled number, not the headline metric.
- Looking at 5 examples each of what Run A fixed/broke vs the baseline: the fixes are mostly the baseline picking a wrong join/table (e.g. querying `singer_in_concert` when the simpler `singer`/`concert`/`stadium` table had the answer) that fine-tuning corrected; the breaks are mostly near-misses on harder joins/aggregations (wrong GROUP BY column, a logically-different-but-plausible rewrite of a subquery) rather than a new failure mode introduced by fine-tuning.

Notes on Exp 5 (QLoRA run B):
- Real Kaggle training run: Unsloth backend, Tesla T4, 0 OOM retries, 92.8 minutes. Rank 32, alpha 64, dropout 0.05, 1 epoch, same learning rate/schedule/data/seed as Run A — only LoRA capacity differs, isolating that one variable.
- Validation loss at each eval step, Run A vs Run B: step 63 — 0.2125 / 0.2094; step 126 — 0.2147 / 0.2244; step 189 — 0.2229 / 0.2220; step 252 — 0.2156 / 0.2128. Train loss: last-logged step 0.111 (A) vs 0.095 (B); epoch-average 0.182 (A) vs 0.173 (B). These differences are small (~0.003 on val loss, within the noise visible between adjacent eval steps of a single run). Combined loss-curve chart (both runs, train + val): `results/loss_curve_run_a_vs_run_b.png`.
- Evaluated all 4 checkpoints on dev (1,034/1,034 outputs cleaned into SQL for every checkpoint, 0 cleaning failures — same as Run A and the baselines). Official EX and test-suite accuracy by checkpoint, vs Run A final:

  | step | official EX | 95% CI | test-suite acc. | 95% CI |
  |------|--------------|--------|------------------|--------|
  | 63 | 68.8% | [65.8%, 71.7%] | 62.3% | [59.4%, 65.3%] |
  | 126 | 67.5% | [64.5%, 70.2%] | 60.3% | [57.3%, 63.4%] |
  | 189 | 71.0% | [68.2%, 73.7%] | 63.9% | [61.0%, 66.8%] |
  | 252 (final) | 72.0% | [68.9%, 74.7%] | 65.1% | [62.0%, 68.0%] |
  | Run A final (reference) | 72.0% | [69.1%, 74.9%] | 64.9% | [61.9%, 67.8%] |

  Chart: `results/run_b_ex_by_checkpoint.png`. Step 126 is the weakest checkpoint on both metrics, matching its validation-loss bump (see the loss table above) — confirms the pattern you noticed from a quick read of the outputs. EX rises again at step 189 and 252, ending essentially tied with Run A.
- McNemar vs the v2 baseline (official per-example correctness, same convention as Exp 4 — `b` = checkpoint fixed, `c` = checkpoint broke, both counted against the 64.3% baseline): step 63 — fixed 126 / broke 80, p=1.7e-03; step 126 — fixed 133 / broke 100, p=3.6e-02; step 189 — fixed 132 / broke 63, p=1.1e-06; final — fixed 146 / broke 67, p=9.1e-08. Every checkpoint beats the baseline by a real margin, weakest at step 126 (still significant, but the smallest gap and the largest p-value of the four).
- McNemar, best Run B checkpoint (final, tied with Run A on official EX) vs Run A final: fixed 35 / broke 35, p=0.905 — not a real difference, these two models behave the same on dev. Doubling LoRA rank (16→32) did not produce a significantly better model here.
- Run B final and Run A final produce the exact same normalized SQL (lowercase, whitespace-collapsed) on 812/1,034 questions — confirms the ~813/1,034 you found from a quick text comparison. The two models agree almost as often as either agrees with itself across a hyperparameter change this small.
- **Recommendation: Run A (rank 16) is the final model for the one-time Spider test run**, not Run B. No Run B checkpoint is significantly better than Run A (the best one, final, is statistically indistinguishable: p=0.905), and step 126 shows doubling the rank can make the model measurably *worse* partway through training, not just "no better." With accuracy tied, the smaller adapter (half the LoRA parameters) wins — nothing is gained from the extra capacity here, and a smaller adapter is simpler to explain, ship, and serve. Tuning stops here, per the plan: Run A final (`FARHANFAST/text2sql-qlora-run-a/final_adapter`) goes forward to the Spider test run, alongside the plain v2 base model for a fair before/after.

Notes on Exp 6 (self-correction, dev):
- The loop runs the query on SQLite. If it errors, I append the failed SQL and the error message as a follow-up chat turn and generate again, up to 2 retries. It never sees gold SQL. The answer is the latest attempt that ran without an error.
- The first attempt matches the Exp 4 predictions on 1,034 of 1,034 questions, so Exp 4 (72.0%) is the no-retry baseline.
- Same run, same first attempts, official per-example match:

| Variant | EX (dev) | 95% CI | Fixed / broke vs no retry | McNemar p | Questions retried | Avg attempts |
|---|---|---|---|---|---|---|
| No retry | 72.0% | [69.1%, 74.9%] | | | 0 | 1.000 |
| Plain retry (only "not right") | 72.6% | [69.9%, 75.3%] | 7 / 0 | 0.016 | 117 | 1.217 |
| Error retry | 74.2% | [71.5%, 76.7%] | 23 / 0 | 2.4e-07 | 117 | 1.184 |
| Plain + empty-result retry | 72.7% | [69.9%, 75.4%] | 8 / 0 | 0.0078 | 184 | 1.345 |
| Error + empty-result retry | 74.1% | [71.5%, 76.6%] | 25 / 3 | 7.2e-05 | 184 | 1.312 |

- Error retry vs plain retry, directly: error right and plain wrong on 18 questions, the reverse on 2, p = 4.0e-04. The error message is what helps, not just a second try.
- Test-suite accuracy for error retry on dev: 66.9%, 95% CI [64.0%, 69.7%] (Run A without retry: 64.9%).
- Of the 117 failing queries, 102 were "no such column", 7 "no such table", 8 other, 0 syntax. Error retry fixed 20, 2 and 1 of them. 70 queries still error after two retries.
- Retrying empty results did not help: of 67 empty results, 2 became correct and 3 correct answers were lost. 38 of the 67 empty results were correct to begin with.
- Time: the first attempt takes 0.46s per question (batched, T4). Error retry adds 0.13s per question on average, about 1s per retried question.
- Spider test, one run of this configuration (error retry, max 2 retries, no tuning on test): 74.7% EX, 95% CI [72.8%, 76.4%], against 73.9% [72.0%, 75.6%] for the same model without retry. Official per-example match, plain EX only. Per difficulty on test: easy 89.4 to 89.6, medium 77.2 to 78.2, hard 67.2 to 68.0, extra 54.1 to 55.5.
- The first attempt on test is identical to the earlier Run A test predictions on 2,147 of 2,147 questions. Error retry fixed 18 and broke 0 (McNemar p = 7.6e-06). It retried 198 questions (151 of them twice), 1.163 attempts on average, +0.135s per question.
- The gain is smaller on test (+0.8 points) than on dev (+2.2). The intervals overlap, and 198 of 2,147 test questions (9.2%) errored on the first attempt, against 11.3% on dev, so there was less to fix. Test predictions: results/predictions_final_exp6_error_retry_test.jsonl. Raw outputs: results/step9_test/. Summary: results/self_correction_summary_test.json.
- Summary: results/self_correction_summary.json. Before/after examples: results/self_correction_examples.md. Raw notebook outputs: results/step9/.

Notes on the Spider test run (final headline numbers, Exp 2 and Exp 4's `EX (test)` cells):
- Run once each, per the dev-vs-test rule: the plain v2 base model (tag `base_v2_test`) and Run A's `final_adapter` (tag `run_a_final_test`), same Kaggle session, same decoding, all 2,147 test questions. 2,147/2,147 outputs cleaned into SQL for both, 0 cleaning failures, 0 empty outputs.
- **Two real bugs found and fixed while computing these numbers, documented in full below:**
  1. A bug in our own `scripts/evaluate_experiment.py`: it joined cleaned predictions with `"\n".join(...)` to build the one-line-per-example file the official CLI evaluator reads. Two of the base model's 2,147 predictions contained an embedded newline (the model occasionally formats SQL across lines), which injected extra lines and desynced every gold/pred pair after them — this alone swung the base model's apparent official EX from 53.7% down to its real 64.4% once fixed. Fixed by collapsing embedded whitespace before writing that file.
  2. A bug in the vendored, third-party official evaluator itself (`tools/test-suite-sql-eval/evaluation.py`'s `evaluate()`, not our code): it unconditionally does `p_str.replace("value", "1")` on every prediction, intended for a value-plugging mode but applied even in plain exec mode. The test split's `warehouse_1` database has a `boxes` table with a column literally named `value`, so this corrupted 10 of Run A's correct predictions (e.g. `SELECT sum(T1.value) FROM boxes ...` → `SELECT sum(T1.1) FROM boxes ...`) into incorrect ones. Confirmed by hand for all 10: the original, uncorrupted prediction executes to the same result set as gold on `warehouse_1.sqlite` (one of them matches only after accounting for column order, which the official evaluator is designed to tolerate — same convention used everywhere else in this project). Full list, before/after SQL, and a draft upstream issue are in `docs/test_suite_sql_eval_value_bug.md`. We did not patch the vendored tool; instead the headline number below comes from calling the evaluator's own `eval_exec_match` function directly per example (bypassing only the buggy `replace()` line in its CLI wrapper), with the unmodified CLI's own aggregate number still computed and reported alongside for transparency.
- **Base model (v2, test): 64.4% EX, 95% CI [62.4%, 66.3%]** (unmodified CLI aggregate: 64.4% — this database has no `value`-bug exposure, so the two numbers agree exactly).
- **Run A final (test): 73.9% EX, 95% CI [72.0%, 75.6%]** (unmodified CLI aggregate: 73.4% — 0.5 points lower, entirely explained by the 10-example `value` bug above).
- Test-suite accuracy: not applicable for test (the test-suite database download only has perturbation variants for dev's 20 databases).
- McNemar's test, Run A final vs the v2 base model, directly on Spider test (official per-example correctness, same convention as every other comparison in this project): b = 288 (Run A fixed), c = 84 (Run A broke), p ≈ 6.6e-26 — an enormous, real improvement, exactly consistent with the dev-set result (Exp 4: +7.7 points on dev, p=4.4e-08).
- Predictions files: `results/predictions_final_base_v2_test.jsonl`, `results/predictions_final_run_a_test.jsonl`. Raw Kaggle outputs: `results/test_final/`.

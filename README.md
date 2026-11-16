# Text-to-SQL with a fine-tuned small LLM

I fine-tuned Qwen2.5-Coder-1.5B-Instruct with QLoRA to turn English questions into SQL, and measured how much fine-tuning actually buys you on a 1.5B model versus prompting alone.

This is a work in progress. This README covers what's done so far: prompt engineering, QLoRA fine-tuning, and the final evaluation on Spider test. Self-correction, a 70B comparison, and a real-world generalization test are still ahead. `EXPERIMENTS.md` has the full experiment log, including per-difficulty breakdowns and every statistical test behind the numbers below.

## Headline result

On the full Spider test set (2,147 questions, evaluated once): execution accuracy went from **64.4%** (base model, zero-shot) to **73.9%** after QLoRA fine-tuning, a 9.5-point gain. The improvement is not noise: McNemar's test on the paired predictions gives p ≈ 6.6e-26.

These two test numbers come from calling the official evaluator's own exec-match function directly, per example, rather than through its command-line wrapper. The wrapper has a bug that corrupts any prediction touching a database column literally named `value` (it string-replaces `"value"` with `"1"` before scoring). Full writeup, a verified list of the affected examples, and a draft upstream issue: `docs/test_suite_sql_eval_value_bug.md`.

## Approach

**Prompting.** I tried three prompt formats on Spider dev: schema as `CREATE TABLE` statements (v1, zero-shot), the same plus foreign keys and sample rows (v2, zero-shot), and v2 plus three few-shot examples from Spider train (v3). v2 won: statistically tied with v3 (McNemar p=0.43) but about a third of the prompt length (811 tokens average vs. 2,398) and roughly twice as fast to generate, so there's no measured reason to pay for the extra few-shot tokens. v2 is what I used for everything downstream.

**Fine-tuning.** QLoRA (4-bit nf4, fp16 compute) with Unsloth, on Spider train, loss computed only on the SQL tokens. I ran two configurations to see whether more LoRA capacity helps: rank 16 (Run A) and rank 32 (Run B), everything else identical. They tied on dev (72.0% EX each, McNemar p=0.905, Run B final vs. Run A final) — doubling LoRA rank bought nothing here. Run B also had a weak checkpoint partway through training (67.5% EX at step 126, versus 72.0% at the final step), matching a bump in its validation loss at that point. I picked Run A: same final accuracy, half the adapter parameters.

**Evaluation.** Execution accuracy (EX) via the official Spider test-suite evaluator (`test-suite-sql-eval`, exec mode), not exact-match string comparison: a query can be phrased differently from gold and still return the same result. Dev-set numbers below also include test-suite accuracy (the same predictions run against several perturbed copies of each database, which catches predictions that got the right answer on one database by luck) and 95% bootstrap confidence intervals; test-suite accuracy isn't available for the Spider test split, since the perturbed databases only exist for dev's 20 databases. Development and model/prompt selection happened entirely on Spider dev; the base model and the chosen fine-tuned model were each evaluated on Spider test exactly once, with no further tuning afterward.

## Results

| Experiment | Model | Prompt | Fine-tuned? | EX (dev) | 95% CI | Test-suite acc. (dev) | EX (test) |
|---|---|---|---|---|---|---|---|
| 1 | Qwen2.5-Coder-1.5B-Instruct | v1 | no | 58.8% | [55.7%, 61.9%] | 50.9% | n/a |
| 2 | Qwen2.5-Coder-1.5B-Instruct | v2 | no | 64.3% | [61.4%, 67.4%] | 55.0% | **64.4%** [62.4%, 66.3%] |
| 3 | Qwen2.5-Coder-1.5B-Instruct | v3 | no | 63.1% | [60.1%, 65.9%] | 54.1% | n/a |
| 4 | + LoRA rank 16 (Run A, chosen) | v2 | yes | 72.0% | [69.1%, 74.9%] | 64.9% | **73.9%** [72.0%, 75.6%] |
| 5 | + LoRA rank 32 (Run B, final checkpoint) | v2 | yes | 72.0% | [68.9%, 74.7%] | 65.1% | n/a |

Full breakdown by Spider difficulty (easy/medium/hard/extra) and every McNemar comparison behind these rows are in `EXPERIMENTS.md`.

## How to reproduce

```bash
pip install -r requirements.txt
```

Download the Spider dataset (questions, gold SQL, and the SQLite databases) from the [Spider benchmark page](https://yale-lily.github.io/spider), and clone the official evaluator into `tools/`:

```bash
git clone https://github.com/taoyds/test-suite-sql-eval tools/test-suite-sql-eval
```

That evaluator needs `nltk`'s `punkt_tab` tokenizer data, a one-time download:

```bash
python -m nltk.downloader punkt_tab
```

Dev-set test-suite accuracy additionally needs the perturbed test-suite databases, linked from that repo's own README (a separate, large download, only needed for the test-suite-accuracy column above, not for execution accuracy itself).

Then, for any already-committed raw predictions file in `results/`:

```bash
python scripts/evaluate_experiment.py --pred results/step8_run_a/predictions_run_a.jsonl --tag check_run_a --split dev
```

This recomputes execution accuracy, the 95% CI, and the per-difficulty breakdown from scratch, so the numbers above can be checked without re-running the model. A one-command script that recomputes every number in this README from the committed predictions files is planned (`scripts/reproduce_eval.py`) but not built yet.

## Limitations

Spider has been public for years, so the base model has likely seen some of it during pretraining. I can't control for that or claim these are "true zero-shot" numbers in an absolute sense. What I can say is that fine-tuning measurably improved the *same* base model on the *same* benchmark, which is the comparison that matters here.

This is a 1.5B model. I haven't yet compared it against a 70B model (planned, via the Groq API) or checked how much accuracy it loses on a real, messy database it's never seen (also planned). Until those land, treat these numbers as "how much does QLoRA fine-tuning help a small model on Spider," not "is this model good enough to use."

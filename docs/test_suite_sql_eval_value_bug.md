# Draft GitHub issue for taoyds/test-suite-sql-eval

Not posted yet — saved here for review before deciding whether to open it upstream.
Repo: https://github.com/taoyds/test-suite-sql-eval
Commit this was found against: `e97acc546ecbee8fa27fa8dbf025ef61493a876c`

---

**Title:** `evaluate()` unconditionally replaces the literal substring "value" in predictions, corrupting exec-match scoring for any query touching a column or table named `value`

**Body:**

`evaluation.py`'s `evaluate()` does this to every predicted query before scoring it, regardless of `--etype` or `--plug_value`:

```python
p_str = p[0]
p_str = p_str.replace("value", "1")
```

(around line 569 in the version I'm using, right after `p_str` is read from the predictions file).

This looks like it's meant for a value-plugging / template-based evaluation mode, where `"value"` is a placeholder token. But it runs unconditionally, even in plain `--etype exec` mode with `--plug_value` not set, and even when calling `eval_exec_match` directly (not through `evaluate()`) gives the correct result.

### Repro

Spider's `warehouse_1` database (used in the Spider **test** split) has a `boxes` table with a column literally named `value`. A perfectly correct prediction like:

```sql
SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'
```

gets turned into:

```sql
SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'
```

which is invalid SQL (or at best means something completely different), and gets scored as **incorrect** even though the original prediction returns exactly the same result set as gold.

Minimal script (standalone, just needs the repo + a sqlite db with a `value` column):

```python
from exec_eval import eval_exec_match

db = "database/warehouse_1/warehouse_1.sqlite"
gold = "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'"
pred = "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'"

# What eval_exec_match itself says when called directly on the real prediction:
print(eval_exec_match(db=db, p_str=pred, g_str=gold, plug_value=False, keep_distinct=False,
                       progress_bar_for_each_datapoint=False))
# -> 1 (correct)

# What evaluate() actually scores it as, because of the unconditional replace:
corrupted = pred.replace("value", "1")
print(eval_exec_match(db=db, p_str=corrupted, g_str=gold, plug_value=False, keep_distinct=False,
                       progress_bar_for_each_datapoint=False))
# -> 0 (incorrect) -- same database, same gold, only difference is the replace() in evaluate()
```

### Impact on our run

Evaluating a fine-tuned Qwen2.5-Coder-1.5B model's predictions on the full Spider test set (2,147 questions), this flipped exactly 10 correct predictions to incorrect, all against the `boxes`/`warehouses` schema (the only test-split database with a column named `value`), moving our measured execution accuracy from 73.4% to 73.9% once we bypassed `evaluate()` and called `eval_exec_match` directly per example instead. Every one of the 10 was verified by hand: the original (uncorrupted) prediction executes to the same result set as gold.

### Suggested fix

Gate the replacement on whatever flag actually means "predictions use the value-placeholder format" (possibly `plug_value`, or a dedicated flag if the two are logically different), so it doesn't silently corrupt literal SQL identifiers that happen to spell "value".

Happy to send a PR if useful — wanted to check whether this is intentional/already known first.

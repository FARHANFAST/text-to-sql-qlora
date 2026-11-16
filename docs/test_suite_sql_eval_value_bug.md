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

This looks like it's meant for a value-plugging / template-based evaluation mode, where `"value"` is a placeholder token. But `evaluate()` runs it unconditionally, even in plain `--etype exec` mode with `--plug_value` not set. The underlying `eval_exec_match` function itself has no such problem — calling it directly, without going through `evaluate()`'s wrapper, scores the same prediction correctly. So the bug is specifically in `evaluate()`'s preprocessing, not in the exec-match logic it calls.

### Repro

I hit this on Spider's **test** split. The `warehouse_1` database (at `test_database/warehouse_1/warehouse_1.sqlite` in a standard Spider download, not this repo's own `database/` folder of test-suite perturbation variants) has a `boxes` table with a column literally named `value`. A perfectly correct prediction like:

```sql
SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'
```

gets turned into:

```sql
SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'
```

which is invalid SQL (or at best means something completely different), and gets scored as **incorrect** even though the original prediction returns exactly the same result set as gold.

Minimal script showing `eval_exec_match` itself is fine, and the corruption only happens in `evaluate()`'s preprocessing:

```python
from exec_eval import eval_exec_match

db = "/path/to/spider/test_database/warehouse_1/warehouse_1.sqlite"
gold = "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'"
pred = "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'"

# eval_exec_match itself, called directly on the real prediction:
print(eval_exec_match(db=db, p_str=pred, g_str=gold, plug_value=False, keep_distinct=False,
                       progress_bar_for_each_datapoint=False))
# -> 1 (correct)

# What evaluate() actually scores it as, because of its unconditional replace:
corrupted = pred.replace("value", "1")
print(eval_exec_match(db=db, p_str=corrupted, g_str=gold, plug_value=False, keep_distinct=False,
                       progress_bar_for_each_datapoint=False))
# -> 0 (incorrect) -- same database, same gold, only difference is the replace() evaluate() applies
```

And the exact CLI command I used to reproduce it through `evaluate()` itself, with a one-line gold/pred pair:

```bash
# gold.sql (tab-separated query + db_id, the format evaluate() expects):
printf "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'\twarehouse_1\n" > gold.sql

# pred.sql (one predicted query per line, same order):
printf "SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'\n" > pred.sql

python evaluation.py --gold gold.sql --pred pred.sql \
  --db /path/to/spider/test_database --table /path/to/spider/test_tables.json --etype exec
# -> prints execution accuracy 0.000 for this single example, even though the prediction is correct
```

### Impact on my run

Evaluating a fine-tuned Qwen2.5-Coder-1.5B model's predictions on the full Spider test set (2,147 questions), this flipped exactly 10 correct predictions to incorrect, all against the `boxes`/`warehouses` schema (the only test-split database with a column named `value`), moving my measured execution accuracy from 73.4% to 73.9% once I bypassed `evaluate()` and called `eval_exec_match` directly per example instead. I verified every one of the 10 by hand: ran the original (uncorrupted) prediction and gold directly against `warehouse_1.sqlite` and confirmed the result rows match (9 match as exact row tuples; row 1734 matches once column order is accounted for, which is exactly the permutation-tolerant comparison `eval_exec_match`'s own `result_eq` applies, not a special case I'm making for it).

All 10, in Spider test order (index is this example's row number in `test.json`):

| idx | gold | prediction (correct) | mangled by `evaluate()` |
|---|---|---|---|
| 1689 | `SELECT avg(value) ,  sum(value) FROM boxes` | `SELECT avg(Value) , sum(value) FROM Boxes` | `SELECT avg(Value) , sum(1) FROM Boxes` |
| 1690 | `SELECT avg(value) ,  sum(value) FROM boxes` | `SELECT avg(Value) , sum(value) FROM Boxes` | `SELECT avg(Value) , sum(1) FROM Boxes` |
| 1693 | `SELECT avg(value) ,  max(value) ,  CONTENTS FROM boxes GROUP BY CONTENTS` | `SELECT avg(Value) , max(value) , Contents FROM boxes GROUP BY contents` | `SELECT avg(Value) , max(1) , Contents FROM boxes GROUP BY contents` |
| 1694 | `SELECT avg(value) ,  max(value) ,  CONTENTS FROM boxes GROUP BY CONTENTS` | `SELECT avg(Value) , max(value) , Contents FROM Boxes GROUP BY Contents` | `SELECT avg(Value) , max(1) , Contents FROM Boxes GROUP BY Contents` |
| 1707 | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse  =  T2.code WHERE T2.location  =  'Chicago' OR T2.location  =  'New York'` | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location = 'Chicago' OR T2.location = 'New York'` | `SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location = 'Chicago' OR T2.location = 'New York'` |
| 1708 | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse  =  T2.code WHERE T2.location  =  'Chicago' OR T2.location  =  'New York'` | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location = 'Chicago' OR T2.location = 'New York'` | `SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location = 'Chicago' OR T2.location = 'New York'` |
| 1730 | `SELECT code ,  CONTENTS FROM boxes WHERE value  >  (SELECT max(value) FROM boxes WHERE CONTENTS  =  'Scissors')` | `SELECT code , Contents FROM boxes WHERE value > ( SELECT max(value) FROM boxes WHERE contents = 'Scissors' )` | `SELECT code , Contents FROM boxes WHERE 1 > ( SELECT max(1) FROM boxes WHERE contents = 'Scissors' )` |
| 1734 | `SELECT warehouse ,  avg(value) FROM boxes GROUP BY warehouse HAVING avg(value)  >  150` | `SELECT avg(Value) , Warehouse FROM Boxes GROUP BY Warehouse HAVING avg(value) > 150` | `SELECT avg(Value) , Warehouse FROM Boxes GROUP BY Warehouse HAVING avg(1) > 150` |
| 1757 | `SELECT sum(T1.value) FROM boxes AS T1 JOIN Warehouses AS T2 ON T1.warehouse  =  T2.code WHERE T2.location != 'Chicago'` | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'` | `SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'` |
| 1758 | `SELECT sum(T1.value) FROM boxes AS T1 JOIN Warehouses AS T2 ON T1.warehouse  =  T2.code WHERE T2.location != 'Chicago'` | `SELECT sum(T1.value) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'` | `SELECT sum(T1.1) FROM boxes AS T1 JOIN warehouses AS T2 ON T1.warehouse = T2.code WHERE T2.location != 'Chicago'` |

### Suggested fix

Gate the replacement on whatever flag actually means "predictions use the value-placeholder format" (possibly `plug_value`, or a dedicated flag if the two are logically different), so it doesn't silently corrupt literal SQL identifiers that happen to spell "value".

Happy to send a PR if useful — wanted to check whether this is intentional/already known first.

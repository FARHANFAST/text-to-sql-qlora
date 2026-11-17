"""Clean raw model output down to the SQL string."""
import re


def strip_sql_fences(text: str) -> str:
    """Strip a markdown code fence (```sql ... ``` or ``` ... ```) wrapping a model's raw output."""
    text = text.strip()
    fence = re.match(r"^```(?:sql)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    text = re.sub(r"^```(?:sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

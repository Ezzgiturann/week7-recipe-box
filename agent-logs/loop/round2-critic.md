# Code Review: Task 3, Ingredient scaling (`git diff main...HEAD`)

`pytest -q` ran: **72 passed**. After the run there is still no `recipes.db` in the repo, so the tests did not create or touch the real database.

---

## 1. Correctness: **FAIL**

**Rules that are met:**
- **Factor range:** `Query(..., gt=0, le=10, allow_inf_nan=False)` returns 422 for 0, negative values, 10.01, `nan`, `inf`, `abc` and an empty value. 10 is accepted.
- **Fractions and decimals:** `Fraction` is used for exact math, and `Fraction(str(factor))` avoids binary float errors. For example, "1/3 cup" × 3 gives "1 cup", not "0.99".
- **Unknown recipe:** returns 404, because it goes through `get_recipe`.
- **Original data:** only a new dict is returned and nothing is written to the database.

**Problems, with concrete examples:**

**a) Supported or unscaled lines come back as wrong results, and the client can't tell.**
- `"½ cup cream"` with factor=2 returns `200` with `"factor": 2.0` and `"ingredients": ["½ cup cream"]`. The correct answer is "1 cup cream". The task says fractional amounts must be supported. "½" is a fraction, but the test file puts it under "lines without a quantity" (`test_ingredients_without_quantity_unchanged`), which is misleading.
- Ranges like `"1-2 cloves garlic"` and `"1 to 2 cups stock"` are the same. The response says the recipe was doubled, but these lines still show the single-batch amount.
- Leaving these lines alone is safer than producing a wrong number. But nothing in the response says "this line was not scaled", such as a `skipped`/`unscaled` list or a per-line flag. So for a doubled recipe, the user is silently given wrong amounts. The review question "does a malformed or unsupported input produce a wrong result?" gets a yes here.

**b) False positive: a size is scaled as if it were a quantity.**
`_AMBIGUOUS_AFTER_RE` only catches a dash when a digit follows it (`[-–—~]\s*[\d.…]`). So:
- `"2-inch piece ginger"` with factor=2 gives `"4-inch piece ginger"`. The piece size doubles, not the number of pieces, which is the wrong meaning.
- `"1 (14 oz) can tomatoes"` is protected by the parenthesis check. The `-inch` / `-ounce` pattern is not.

**c) The echoed factor breaks the "no trailing zeros" rule.**
`"factor": factor` returns the parsed `float`. For `?factor=2` the JSON contains `"factor": 2.0`. The task explicitly says to show 2, not 2.0. The ingredient lines are formatted correctly, but the `factor` field in the same response is not.

**d) Minor inconsistency at factor=1.**
With `factor == 1` the line is returned as-is, so `"1.0 cups rice"` stays `"1.0 cups rice"`. With factor=2 it becomes `"2 cups rice"`. The goal of not rewriting "1/3" as "0.33" makes sense, but the trailing-zero rule is no longer applied the same way everywhere.

---

## 2. Tests: **FAIL**

**Good:**
- There are tests for every rule: range, 422, 404, fractions, decimals, mixed numbers, lines without a quantity, trailing zeros, and the upper bound of 10.
- A temporary database is used. Each test gets its own `tmp_path`, and `RECIPE_BOX_DB` is set before import, so `init_db()` at import time doesn't create `./recipes.db`.
- `test_scaling_does_not_modify_original` checks the data both through the API and with a direct SQL read. This is strong. `test_repeated_scaling_is_not_cumulative` is also useful.

**Problems:**
1. **One test hides a bug.** In `test_scaled_returns_full_recipe_with_factor`, `assert body["factor"] == 2` passes because `2.0 == 2` in Python. The actual JSON contains `2.0`, so the trailing-zero rule is violated in the response and the test can't catch it. It needs to check the raw text (e.g. `'"factor":2' in r.text`) or the type (`isinstance(..., int)`).
2. **Wrong behavior is locked in by tests.** `"½ cup cream"` is asserted as "unchanged" in the "no quantity" group. That turns a fractional amount that wasn't scaled into the expected result.
3. **Missing edge cases:**
   - `"2-inch piece ginger"` and `"3-ounce can"`: the size vs. quantity false positive above.
   - `factor=0.0000001` and `factor=1e-3`: very small values and scientific notation (`str(float)` produces `'1e-07'`).
   - `factor="2.0"` and `factor="010"`: string variants.
   - `"0 g sugar"`: a zero amount.
   - Large amounts, e.g. `"999999 g"` × 10.
   - A test that checks the real `recipes.db` file is not created or modified. `test_tests_do_not_use_real_db` only compares paths and doesn't check the file system.

---

## 3. Clarity: **PASS**

- Function names (`_parse_quantity`, `_format_quantity`, `scale_ingredient`) are clear, and the docstrings include examples.
- The regexes are complex but split into commented alternatives. The reason for leaving ambiguous lines unchanged ("a wrong amount is worse than none") is written down.
- The `max(2, 1 - exact.adjusted())` rule in `_format_quantity` is non-obvious, but the docstring explains it with examples.
- Small notes, not reasons to fail:
  - The handler calls the route function `get_recipe` directly. It works, but a shared helper like `_fetch_recipe` would be cleaner.
  - `_parse_quantity` returning `None` mixes up "invalid number" and "no quantity" from the caller's side.
  - The extra spaces on the `r"|\s*[x×]\s*\d"` line break the alignment.

`★ Insight ─────────────────────────────────────`
- With `Fraction(str(factor))`, `0.1` becomes exactly `1/10`. `Fraction(0.1)` would give `3602879701896397/36028797018963968`. Going through the string is what makes "1/3 × 3 = 1" exact.
- Python's `2.0 == 2` being `True` is a classic trap for format tests. If the rule is about how a value looks, the test has to check the serialized text, not the value.
- A "safe fallback" (returning the line unchanged) only prevents wrong data if the client is told about it. Without a flag, it is a silent failure.
`─────────────────────────────────────────────────`

The fixes needed are: support or flag Unicode fractions and ranges, cover the `-inch` style false positive, make `factor` show as 2 instead of 2.0, and make the tests check the serialized output.

VERDICT: REVISE

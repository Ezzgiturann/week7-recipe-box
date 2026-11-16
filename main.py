"""Recipe Box — starter app for Week 7.

A tiny FastAPI service for recipes and tags, with a static frontend. Use it as the
playground for concurrent multi-agent work and a generator-critic loop.

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload
    # open http://localhost:8000/
Test:
    pytest
"""
import json
import os
import re
import sqlite3
import unicodedata
from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
# Overridable so tests (or deployments) can point at a different database file.
DB_PATH = Path(os.environ.get("RECIPE_BOX_DB", BASE / "recipes.db"))

app = FastAPI(title="Recipe Box")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(get_db()) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recipes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                ingredients TEXT NOT NULL,  -- JSON list of strings
                tags        TEXT NOT NULL   -- JSON list of strings
            )"""
        )
        conn.commit()


init_db()


class RecipeIn(BaseModel):
    title: str
    ingredients: list[str] = []
    tags: list[str] = []


def _row_to_recipe(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "ingredients": json.loads(row["ingredients"]),
        "tags": json.loads(row["tags"]),
    }


def _fetch_recipe(recipe_id: int) -> dict:
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.post("/recipes")
def create_recipe(recipe: RecipeIn):
    with closing(get_db()) as conn:
        cur = conn.execute(
            "INSERT INTO recipes (title, ingredients, tags) VALUES (?, ?, ?)",
            (recipe.title, json.dumps(recipe.ingredients), json.dumps(recipe.tags)),
        )
        conn.commit()
        rid = cur.lastrowid
    return {"id": rid, **recipe.model_dump()}


@app.get("/recipes")
def list_recipes():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    return [_row_to_recipe(r) for r in rows]


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    return _fetch_recipe(recipe_id)


# --- Ingredient scaling -----------------------------------------------------

_UNICODE_FRACTIONS = "¼-¾⅐-⅞"  # ¼ ½ ¾ ⅐ … ⅞
_SLASH = "[/⁄]"  # ASCII "/" or the Unicode fraction slash "⁄"
_RANGE_SEP = r"(?:[-–—~]|to\b|or\b)"  # "-", "–", "—", "~", "to", "or"

# One number: mixed ("1 1/2", "1-1/2", "1½", "1 ½"), fraction ("1/2", "½"),
# or integer/decimal ("200", "1.5", ".5"). Longest forms are tried first, so
# the US-style "1-1/2" is read as one-and-a-half, not as the range 1 to 1/2.
_NUMBER = (
    rf"(?:\d+(?:\s+|-)\d+{_SLASH}\d+"
    rf"|\d+\s*[{_UNICODE_FRACTIONS}]"
    rf"|\d+{_SLASH}\d+"
    rf"|[{_UNICODE_FRACTIONS}]"
    r"|\d+(?:\.\d+)?|\.\d+)"
)

# A leading quantity, optionally a range ("1-2", "1 to 2", "2 or 3").
# Only the *leading* quantity is scaled: "2 eggs, beaten in 1 bowl" -> "4 eggs, ...".
_QUANTITY_RE = re.compile(
    r"^(?P<lead>\s*)"
    rf"(?P<low>{_NUMBER})"
    rf"(?:(?P<sep>\s*{_RANGE_SEP}\s*)(?P<high>{_NUMBER}))?"
    r"(?![\d/⁄.])",  # don't stop mid-token (e.g. "1.2.3", "1/2/3")
    re.IGNORECASE,
)
# Starts like a quantity but _QUANTITY_RE can't read it ("1.2.3", "1/2/3",
# "-2 g"): reported as unscaled rather than treated as "no quantity".
_LOOKS_NUMERIC_RE = re.compile(rf"^\s*[-+−]?\s*\.?[\d{_UNICODE_FRACTIONS}]")

# Longer quantities are not real recipe amounts; refusing them also keeps us
# clear of Python 3.11+'s 4300-digit int<->str limit (ValueError -> HTTP 500).
_MAX_QUANTITY_DIGITS = 100

# Text right after the quantity that makes it ambiguous. Such lines are left
# unchanged *and reported* in the response's "unscaled" list.
_AMBIGUOUS_AFTER_RE = re.compile(
    r"^(?:"
    r",\d"                                          # "1,5 kg" (decimal comma?) / "1,000 g"
    rf"|\s*[{_UNICODE_FRACTIONS}]"                  # "1.5½"
    r"|[-–]\s*[^\W\d_]"                        # a size, not a count: "2-inch", "3-ounce"
    rf"|\s*{_RANGE_SEP}\s*[\d.{_UNICODE_FRACTIONS}]"  # three-part "1-2-3"
    r"|\s*[x×]\s*\d"                           # dimensions / multipliers: "2x3 cm"
    rf"|\s*\d+{_SLASH}"                             # leftovers like "2 1/2/3", "1 1⁄2⁄3"
    r"|e[-+]?\d"                                    # scientific notation: "1e3 g"
    r"|\s*[%°]"                                     # not an amount: "70% cocoa", "180°C"
    r"|\s+\d+(?:\.\d+)?(?=\s|$)"                    # two bare numbers: "1 2 cups"
    r")",
    re.IGNORECASE,
)
# A second quantity in parentheses, e.g. "12 oz (340 g) pasta".
_PAREN_QUANTITY_RE = re.compile(r"\(\s*[\d.]")

_MIXED_RE = re.compile(rf"(\d+)(?:\s+|-)(\d+){_SLASH}(\d+)")
_FRACTION_RE = re.compile(rf"(\d+){_SLASH}(\d+)")
_UNICODE_MIXED_RE = re.compile(rf"(\d*)\s*([{_UNICODE_FRACTIONS}])")


def _parse_number(text: str) -> Optional[Fraction]:
    """Exact value of one _NUMBER token, or None if it is invalid ("1/0")."""
    m = _MIXED_RE.fullmatch(text)
    if m:
        whole, num, den = map(int, m.groups())
        return whole + Fraction(num, den) if den else None
    m = _FRACTION_RE.fullmatch(text)
    if m:
        num, den = map(int, m.groups())
        return Fraction(num, den) if den else None
    m = _UNICODE_MIXED_RE.fullmatch(text)
    if m:
        # unicodedata gives a float (⅓ -> 0.333…); every vulgar fraction has den <= 10.
        frac = Fraction(unicodedata.numeric(m[2])).limit_denominator(10)
        return int(m[1] or 0) + frac
    return Fraction(text)


def _format_quantity(value: Fraction) -> str:
    """Render a non-negative quantity without trailing zeros.

    One rule: keep at least 2 decimal places, and for values below 1 keep
    2 significant digits, so small amounts never collapse or double:

        2 -> "2"      1/2 -> "0.5"     1/3 -> "0.33"    10/3 -> "3.33"
        0.005 -> "0.005"   0.0123 -> "0.012"   0.995 -> "1"
    """
    if value.denominator == 1:
        return str(value.numerator)
    with localcontext() as ctx:
        # Enough precision for any input size: the default 28 digits makes
        # quantize() raise InvalidOperation on huge amounts (HTTP 500).
        int_digits = len(str(value.numerator // value.denominator))
        ctx.prec = max(28, int_digits + 2 * len(str(value.denominator)) + 10)
        exact = Decimal(value.numerator) / Decimal(value.denominator)
        # adjusted() is the exponent of the leading digit: 0.005 -> -3, 3.3 -> 0.
        places = max(2, 1 - exact.adjusted())
        rounded = exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def scale_ingredient(ingredient: str, factor: Fraction) -> Optional[str]:
    """Scale the leading quantity (or range) of an ingredient line.

    Returns:
      * the scaled line: "1/2 cup milk" x2 -> "1 cup milk", "1-2 cloves" x2 -> "2-4 cloves";
      * the line unchanged if it has no leading quantity ("salt to taste");
      * None if it starts with a quantity that can't be scaled safely, e.g.
        "1,5 kg", "2-inch piece", "70% cocoa", "12 oz (340 g)", "1/0 cup",
        "1.2.3 cups", "-2 g", "2-1 cups". The caller reports these instead of
        silently returning a wrong amount.
    """
    match = _QUANTITY_RE.match(ingredient)
    if match is None:
        # "salt to taste" has no quantity; "1.2.3 cups" has an unreadable one.
        return None if _LOOKS_NUMERIC_RE.match(ingredient) else ingredient
    if sum(c.isdigit() for c in match.group()) > _MAX_QUANTITY_DIGITS:
        return None
    rest = ingredient[match.end():]
    if _AMBIGUOUS_AFTER_RE.match(rest) or _PAREN_QUANTITY_RE.search(rest):
        return None
    low = _parse_number(match["low"])
    high = _parse_number(match["high"]) if match["high"] else None
    if low is None or (match["high"] and high is None):
        return None
    if high is not None and not low < high:
        return None  # "2-1 cups" is not a meaningful range
    scaled = _format_quantity(low * factor)
    if high is not None:
        scaled += match["sep"] + _format_quantity(high * factor)
    return match["lead"] + scaled + rest


def _json_number(value: float) -> Union[int, float]:
    """2.0 -> 2, 0.5 -> 0.5: no trailing ".0" in the JSON response."""
    return int(value) if value.is_integer() else value


@app.get("/recipes/{recipe_id}/scaled")
def get_scaled_recipe(
    recipe_id: int,
    factor: float = Query(..., gt=0, le=10, allow_inf_nan=False),
):
    """Recipe with ingredient quantities multiplied by `factor` (0 < factor <= 10).

    `unscaled` lists ingredient lines that start with a quantity but were left
    as-is because the amount is ambiguous. Lines without any quantity
    ("salt to taste") are unchanged by design and are not listed.
    """
    recipe = _fetch_recipe(recipe_id)
    # str() first so 0.1 becomes exactly 1/10 instead of its binary float value.
    exact_factor = Fraction(str(factor))
    ingredients, unscaled = [], []
    # No special case for factor == 1: output format must not depend on the
    # factor ("2.0 cups" -> "2 cups" and "1/3" -> "0.33" for every factor).
    for line in recipe["ingredients"]:
        scaled = scale_ingredient(line, exact_factor)
        if scaled is None:
            unscaled.append(line)
            scaled = line
        ingredients.append(scaled)
    return {
        **recipe,
        "factor": _json_number(factor),
        "ingredients": ingredients,
        "unscaled": unscaled,
    }

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
def list_recipes(tag: Optional[list[str]] = Query(default=None)):
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM recipes ORDER BY id").fetchall()
    recipes = [_row_to_recipe(r) for r in rows]
    if tag is None:
        return recipes

    wanted = {t.strip().casefold() for t in tag}
    if "" in wanted:
        raise HTTPException(status_code=422, detail="tag must not be empty")
    return [
        rec for rec in recipes
        if any(t.strip().casefold() in wanted for t in rec["tags"])
    ]


@app.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int):
    return _fetch_recipe(recipe_id)


def _parse_ids(raw: str) -> list[int]:
    """Parse "1,2,3" into [1, 2, 3]; raise 422 on empty or malformed input."""
    parts = [p.strip() for p in raw.split(",")]
    if not all(re.fullmatch(r"[0-9]+", p) for p in parts):
        raise HTTPException(status_code=422, detail="ids must be a comma-separated list of integers")
    return [int(p) for p in parts]


@app.get("/shopping-list")
def shopping_list(ids: str = Query(...)):
    recipe_ids = _parse_ids(ids)
    with closing(get_db()) as conn:
        rows = {
            row["id"]: row
            for row in conn.execute(
                f"SELECT * FROM recipes WHERE id IN ({','.join('?' * len(recipe_ids))})",
                recipe_ids,
            )
        }
    missing = [rid for rid in recipe_ids if rid not in rows]
    if missing:
        raise HTTPException(status_code=404, detail=f"unknown recipe ids: {missing}")

    items: list[str] = []
    seen: set[str] = set()
    for rid in recipe_ids:  # follow the order given in the query string
        for ingredient in json.loads(rows[rid]["ingredients"]):
            cleaned = ingredient.strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                items.append(cleaned)
    return {"items": items}



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
_QUANTITY_RE = re.compile(
    r"^(?P<lead>\s*)"
    rf"(?P<low>{_NUMBER})"
    rf"(?:(?P<sep>\s*{_RANGE_SEP}\s*)(?P<high>{_NUMBER}))?"
    r"(?![\d/⁄.])",  # don't stop mid-token (e.g. "1.2.3", "1/2/3")
    # ASCII: \d is only 0-9 here. Other scripts' digits ("٢ cups") aren't read
    # as a quantity, so _ANY_NUMBER_RE (Unicode \d) reports them as unscaled.
    re.IGNORECASE | re.ASCII,
)
# Longer quantities are not real recipe amounts; refusing them also keeps us
# clear of Python 3.11+'s 4300-digit int<->str limit (ValueError -> HTTP 500).
_MAX_QUANTITY_DIGITS = 100

# General rule: a digit or fraction anywhere that is not part of the supported
# leading quantity is a number we don't understand – after it ("1 lb 4 oz",
# "12 oz (340 g)", "1,5 kg", "2x3 cm") or with no readable leading quantity
# at all ("flour 200 g", "Eggs: 2", "~2 cups", "1.2.3", "-2 g"). Such lines are
# reported instead of being scaled wrongly or passed off as "no quantity".
_ANY_NUMBER_RE = re.compile(rf"[\d{_UNICODE_FRACTIONS}]")

# The same rule for numbers written as words: "two eggs", "half a lemon",
# "2 cups plus one tbsp". Like a stray digit, a number word anywhere means the
# line may hold an amount we can't scale, so it is reported. Accepted cost:
# "half-and-half" (the dairy product) and "cut in half" are reported too.
_NUMBER_WORD_RE = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|dozens?|couple|half|halves|quarters?|thirds?)\b",
    re.IGNORECASE,
)

# A unit followed by a container describes the container's size, not an
# amount: "2 inch piece", "3 ounce can", "1 lb bag", "400 g tin".
_SIZE_UNIT = (
    r"(?:inch(?:es)?|in|cm|mm|ounces?|oz|pounds?|lbs?|g|grams?|kg"
    r"|ml|l|lit(?:er|re)s?)"
)
_CONTAINER = (
    r"(?:pieces?|cans?|tins?|jars?|bags?|box(?:es)?|packages?|packets?|pkgs?"
    r"|blocks?|bottles?|cartons?|sticks?|chunks?|containers?|tubs?|slices?)"
)

# The leading number is there but is not an amount of the ingredient.
_NOT_AN_AMOUNT_RE = re.compile(
    r"^(?:"
    r"[-–]\s*[^\W\d_]"                              # size: "2-inch piece", "3-ounce can"
    rf"|\s+{_SIZE_UNIT}\s+{_CONTAINER}\b"           # size: "2 inch piece", "3 ounce can"
    r"|\s*(?:[%°]|percent\b|per\s+cent\b|degrees?\b)"  # "70% / 70 percent", "180°C / degrees"
    r")",
    re.IGNORECASE,
)

_MIXED_RE = re.compile(rf"(\d+)(?:\s+|-)(\d+){_SLASH}(\d+)")
_FRACTION_RE = re.compile(rf"(\d+){_SLASH}(\d+)")
_UNICODE_MIXED_RE = re.compile(rf"(\d*)\s*([{_UNICODE_FRACTIONS}])")


def _parse_number(text: str) -> Optional[Fraction]:
    """Exact value of one _NUMBER token, or None if it is invalid ("1/0")."""
    m = _MIXED_RE.fullmatch(text)
    if m:
        whole, num, den = map(int, m.groups())
        # A real mixed number has a proper fraction part. "1-3/2" could just as
        # well be the range 1 to 3/2, so improper parts are rejected as ambiguous.
        return whole + Fraction(num, den) if 0 < den and num < den else None
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

    Supported leading quantities (scaled, x2 shown):
      integer/decimal  "200 g" -> "400 g", "1.5 tsp" -> "3 tsp", ".5 cup" -> "1 cup"
      fraction         "1/2 cup" -> "1 cup", "1⁄2 cup" -> "1 cup", "½ cup" -> "1 cup"
      mixed number     "1 1/2", "1-1/2", "1½", "1 ½" -> "3"
      range            "1-2" -> "2-4", "1 to 2" -> "2 to 4", "2 or 3" -> "4 or 6"

    Returns:
      * the scaled line;
      * the line unchanged if it contains no digits, fractions or number
        words at all ("salt to taste", "a pinch of nutmeg");
      * None if it can't be scaled safely. The caller reports these in
        "unscaled" instead of returning a wrong amount. Accepted limitations:
          - quantity not at the start: "flour 200 g", "Eggs: 2",
            "a 400 g can tomatoes", "about 2 cups", "~2 cups", "V8 juice"
          - another number after the quantity: "1 lb 4 oz beef",
            "1 cup plus 2 tbsp", "3 eggs or 4 egg whites", "12 oz (340 g)",
            "2 x 400 g cans", "2x3 cm", "1 2-inch piece", "1-2-3 eggs",
            "2 eggs, beaten in 1 bowl", "2 cans V8 juice"
          - number words anywhere: "two eggs", "half a lemon",
            "2 cups plus one tbsp", and as a side effect "1 cup half-and-half",
            "1 lemon, cut in half"
          - decimal comma / thousands separator: "1,5 kg", "1,000 g"
          - not an amount (a size, percentage or temperature): "2-inch piece",
            "2 inch piece", "3-ounce can", "3 ounce can", "1 lb bag",
            "70% cocoa", "70 percent cocoa", "180°C", "180 degrees"
          - digits in other scripts: "٢ cups"
          - unreadable / invalid: "1.2.3 cups", "1/2/3", "1e3 g", "1/0 cup",
            "-2 g", reversed range "2-1 cups", improper mixed number
            "1-3/2" (range or 2 1/2?), more than 100 digits

    Ambiguous hyphens with a proper fraction are read as mixed numbers:
    "2-3/4" is 2 3/4, not the range 2 to 3/4. Results keep 2 decimals
    (2 significant digits below 1), so "1/8 tsp" becomes "0.13 tsp" even at
    factor 1.
    """
    if _NUMBER_WORD_RE.search(ingredient):
        return None
    match = _QUANTITY_RE.match(ingredient)
    if match is None:
        # No readable leading quantity: fine only if there's no number at all.
        return None if _ANY_NUMBER_RE.search(ingredient) else ingredient
    if sum(c.isdigit() for c in match.group()) > _MAX_QUANTITY_DIGITS:
        return None
    rest = ingredient[match.end():]
    if _ANY_NUMBER_RE.search(rest) or _NOT_AN_AMOUNT_RE.match(rest):
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


def _json_number(value: Fraction) -> Union[int, float]:
    """2 -> 2, 1/2 -> 0.5: no trailing ".0" in the JSON response."""
    return value.numerator if value.denominator == 1 else float(value)


@app.get("/recipes/{recipe_id}/scaled")
def get_scaled_recipe(
    recipe_id: int,
    # Decimal, not float: the bounds are checked on the exact value, so
    # "10.0000000000000001" is rejected instead of rounding to 10.0.
    # max_digits bounds the work for inputs like "1e-999999" (still allows 1e-300).
    factor: Decimal = Query(..., gt=0, le=10, allow_inf_nan=False, max_digits=400),
):
    """Recipe with ingredient quantities multiplied by `factor` (0 < factor <= 10).

    `unscaled` lists ingredient lines that start with a quantity but were left
    as-is because the amount is ambiguous. Lines without any quantity
    ("salt to taste") are unchanged by design and are not listed.
    """
    recipe = _fetch_recipe(recipe_id)
    exact_factor = Fraction(factor)  # Decimal -> Fraction is exact: "0.1" is 1/10
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
        "factor": _json_number(exact_factor),
        "ingredients": ingredients,
        "unscaled": unscaled,
    }

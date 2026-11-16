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
from contextlib import closing
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Optional

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
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


# --- Ingredient scaling -----------------------------------------------------

# A leading quantity: mixed number ("1 1/2"), fraction ("1/2"), or
# integer/decimal ("200", "1.5", ".5"). Only the *leading* number is scaled,
# so "2 eggs, beaten in 1 bowl" scales the 2 and leaves the 1 alone.
_QUANTITY_RE = re.compile(
    r"^(?P<lead>\s*)"
    r"(?:"
    r"(?P<whole>\d+)\s+(?P<mnum>\d+)/(?P<mden>\d+)"  # mixed number
    r"|(?P<num>\d+)/(?P<den>\d+)"                    # simple fraction
    r"|(?P<dec>\d+(?:\.\d+)?|\.\d+)"                 # integer / decimal
    r")"
    r"(?![\d/.])"  # don't stop mid-token (e.g. "1.2.3", "1/2/3")
)


def _parse_quantity(match: re.Match) -> Optional[Fraction]:
    """Turn a regex match into an exact Fraction; None if it's not a valid number."""
    if match["whole"] is not None:
        den = int(match["mden"])
        if den == 0:
            return None
        return int(match["whole"]) + Fraction(int(match["mnum"]), den)
    if match["num"] is not None:
        den = int(match["den"])
        if den == 0:
            return None
        return Fraction(int(match["num"]), den)
    return Fraction(match["dec"])


def _format_quantity(value: Fraction) -> str:
    """Render without trailing zeros: 2 -> "2", 1/2 -> "0.5", 1/3 -> "0.33"."""
    if value.denominator == 1:
        return str(value.numerator)
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    rounded = exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        # Very small amounts (tiny factors) shouldn't collapse to "0".
        rounded = Decimal(f"{exact:.2g}")
    text = format(rounded.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def scale_ingredient(ingredient: str, factor: Fraction) -> str:
    """Scale the leading quantity of an ingredient line; leave others untouched."""
    match = _QUANTITY_RE.match(ingredient)
    if match is None:
        return ingredient  # e.g. "salt to taste"
    quantity = _parse_quantity(match)
    if quantity is None:
        return ingredient  # e.g. "1/0 cup" – not a real quantity, don't guess
    scaled = _format_quantity(quantity * factor)
    return match["lead"] + scaled + ingredient[match.end():]


@app.get("/recipes/{recipe_id}/scaled")
def get_scaled_recipe(
    recipe_id: int,
    factor: float = Query(..., gt=0, le=10, allow_inf_nan=False),
):
    recipe = get_recipe(recipe_id)  # raises 404 for unknown ids
    # str() first so 0.1 becomes exactly 1/10 instead of its binary float value.
    exact_factor = Fraction(str(factor))
    return {
        **recipe,
        "factor": factor,
        "ingredients": [scale_ingredient(i, exact_factor) for i in recipe["ingredients"]],
    }

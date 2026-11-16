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
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

BASE = Path(__file__).parent
DB_PATH = BASE / "recipes.db"

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
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown recipe")
    return _row_to_recipe(row)


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

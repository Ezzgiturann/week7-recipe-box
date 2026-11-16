import os
import sqlite3
import tempfile
from pathlib import Path

# Point the app at a throwaway DB *before* importing main, because main
# calls init_db() at import time and would otherwise create ./recipes.db.
os.environ["RECIPE_BOX_DB"] = str(Path(tempfile.mkdtemp()) / "import.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Give every test its own empty SQLite file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(main, "DB_PATH", db_path)
    main.init_db()
    return db_path


def _create(ingredients, title="Test recipe", tags=None):
    r = client.post(
        "/recipes", json={"title": title, "ingredients": ingredients, "tags": tags or []}
    )
    assert r.status_code == 200
    return r.json()["id"]


def _scaled(rid, factor):
    return client.get(f"/recipes/{rid}/scaled", params={"factor": factor})


# --- existing behaviour -------------------------------------------------------


def test_create_and_get_recipe():
    r = client.post(
        "/recipes",
        json={"title": "Pancakes", "ingredients": ["flour", "milk"], "tags": ["breakfast"]},
    )
    assert r.status_code == 200
    rid = r.json()["id"]
    r2 = client.get(f"/recipes/{rid}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Pancakes"
    assert r2.json()["tags"] == ["breakfast"]


def test_list_recipes():
    client.post("/recipes", json={"title": "Toast"})
    r = client.get("/recipes")
    assert r.status_code == 200
    assert any(rec["title"] == "Toast" for rec in r.json())


def test_unknown_recipe_404():
    r = client.get("/recipes/99999")
    assert r.status_code == 404


def test_tests_do_not_use_real_db(temp_db):
    assert main.DB_PATH == temp_db
    assert main.DB_PATH != main.BASE / "recipes.db"


# --- scaling: happy path ------------------------------------------------------


def test_scaled_returns_full_recipe_with_factor():
    rid = _create(["200 g flour"], title="Bread", tags=["baking"])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["title"] == "Bread"
    assert body["tags"] == ["baking"]
    assert body["factor"] == 2
    assert body["ingredients"] == ["400 g flour"]


@pytest.mark.parametrize(
    "ingredient, factor, expected",
    [
        # integers
        ("200 g flour", 2, "400 g flour"),
        ("3 eggs", 1, "3 eggs"),
        ("200g flour", 1.5, "300g flour"),  # unit glued to number
        # fractions
        ("1/2 cup milk", 2, "1 cup milk"),
        ("1/2 cup milk", 3, "1.5 cup milk"),
        ("1/3 cup sugar", 3, "1 cup sugar"),  # exact math, no 0.99
        ("1/3 cup sugar", 1, "0.33 cup sugar"),
        ("1 1/2 cups water", 2, "3 cups water"),  # mixed number
        # decimals
        ("1.5 tsp salt", 2, "3 tsp salt"),
        ("0.25 l cream", 2, "0.5 l cream"),
        (".5 cup oil", 3, "1.5 cup oil"),
        ("2.5 kg potatoes", 0.1, "0.25 kg potatoes"),
        # trailing zeros stripped / rounding
        ("2.0 cups rice", 1, "2 cups rice"),
        ("1.50 tbsp butter", 1, "1.5 tbsp butter"),
        ("10 g yeast", 0.333, "3.33 g yeast"),
        ("1 g saffron", 0.001, "0.001 g saffron"),  # tiny amounts don't become 0
        # factor upper bound is allowed
        ("1 onion", 10, "10 onion"),
    ],
)
def test_scaling_values(ingredient, factor, expected):
    rid = _create([ingredient])
    r = _scaled(rid, factor)
    assert r.status_code == 200
    assert r.json()["ingredients"] == [expected]


@pytest.mark.parametrize(
    "ingredient",
    [
        "salt to taste",
        "pepper",
        "a pinch of nutmeg",
        "",
        "1/0 cup nonsense",  # invalid fraction is left alone, not a crash
    ],
)
def test_ingredients_without_quantity_unchanged(ingredient):
    rid = _create([ingredient])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == [ingredient]


def test_only_leading_quantity_is_scaled():
    rid = _create(["2 eggs, beaten in 1 bowl"])
    assert _scaled(rid, 2).json()["ingredients"] == ["4 eggs, beaten in 1 bowl"]


def test_mixed_ingredient_list_preserves_order():
    ingredients = ["200 g flour", "salt to taste", "1/2 cup milk", "1.5 tsp sugar"]
    rid = _create(ingredients)
    assert _scaled(rid, 2).json()["ingredients"] == [
        "400 g flour",
        "salt to taste",
        "1 cup milk",
        "3 tsp sugar",
    ]


def test_recipe_with_no_ingredients():
    rid = _create([])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == []


# --- scaling: validation ------------------------------------------------------


@pytest.mark.parametrize("factor", ["0", "-1", "-0.5", "10.01", "11", "abc", "", "nan", "inf"])
def test_invalid_factor_returns_422(factor):
    rid = _create(["200 g flour"])
    assert _scaled(rid, factor).status_code == 422


def test_missing_factor_returns_422():
    rid = _create(["200 g flour"])
    assert client.get(f"/recipes/{rid}/scaled").status_code == 422


def test_scaled_unknown_recipe_404():
    r = _scaled(99999, 2)
    assert r.status_code == 404


# --- scaling: no side effects -------------------------------------------------


def test_scaling_does_not_modify_original(temp_db):
    ingredients = ["200 g flour", "1/2 cup milk", "salt to taste"]
    rid = _create(ingredients)

    _scaled(rid, 3)
    _scaled(rid, 0.5)

    # via the API
    assert client.get(f"/recipes/{rid}").json()["ingredients"] == ingredients
    # and directly in the database
    with sqlite3.connect(temp_db) as conn:
        stored = conn.execute("SELECT ingredients FROM recipes WHERE id = ?", (rid,)).fetchone()[0]
    assert stored == main.json.dumps(ingredients)


def test_repeated_scaling_is_not_cumulative():
    rid = _create(["200 g flour"])
    assert _scaled(rid, 2).json()["ingredients"] == ["400 g flour"]
    assert _scaled(rid, 2).json()["ingredients"] == ["400 g flour"]

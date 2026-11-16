import atexit
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

# Point the app at a throwaway DB *before* importing main, because main
# calls init_db() at import time and would otherwise create ./recipes.db.
_IMPORT_DB_DIR = tempfile.mkdtemp()
atexit.register(shutil.rmtree, _IMPORT_DB_DIR, ignore_errors=True)
os.environ["RECIPE_BOX_DB"] = str(Path(_IMPORT_DB_DIR) / "import.db")

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
        ("200g flour", 1.5, "300g flour"),  # unit glued to number
        ("  2 g salt", 2, "  4 g salt"),  # leading whitespace preserved
        # fractions
        ("1/2 cup milk", 2, "1 cup milk"),
        ("1/2 cup milk", 3, "1.5 cup milk"),
        ("1/3 cup sugar", 3, "1 cup sugar"),  # exact math, no 0.99
        ("1/3 cup sugar", 2, "0.67 cup sugar"),
        ("1 1/2 cups water", 2, "3 cups water"),  # mixed number
        # decimals
        ("1.5 tsp salt", 2, "3 tsp salt"),
        ("0.25 l cream", 2, "0.5 l cream"),
        (".5 cup oil", 3, "1.5 cup oil"),
        ("2.5 kg potatoes", 0.1, "0.25 kg potatoes"),
        # trailing zeros stripped / rounding
        ("1.0 cups rice", 2, "2 cups rice"),
        ("0.750 tbsp butter", 2, "1.5 tbsp butter"),
        ("10 g yeast", 0.333, "3.33 g yeast"),
        # small amounts: 2 significant digits, never collapse to 0 or double
        ("1 g saffron", 0.001, "0.001 g saffron"),
        ("1 g saffron", 0.005, "0.005 g saffron"),
        ("1 g saffron", 0.004, "0.004 g saffron"),
        ("1 g saffron", 0.0123, "0.012 g saffron"),
        ("1 g saffron", 0.995, "1 g saffron"),  # rounds up cleanly, no "1.0"
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
        "2 1/0 cup nonsense",  # mixed number with zero denominator
        "½ cup cream",  # unicode fraction only: no ASCII quantity to scale
    ],
)
def test_ingredients_without_quantity_unchanged(ingredient):
    rid = _create([ingredient])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == [ingredient]


@pytest.mark.parametrize(
    "ingredient",
    [
        # ranges: scaling only the first bound would give "2-2"
        "1-2 cloves garlic",
        "1 - 2 cloves garlic",
        "1–2 cloves garlic",  # en dash
        "1 to 2 cups stock",
        "2 or 3 eggs",
        "1/2-1 cup milk",
        # decimal comma vs thousands separator is ambiguous ("1,5" vs "1,000")
        "1,5 kg un",
        "1,000 g sugar",
        # unicode fractions attached to a number
        "1½ cups flour",
        "1 ½ cups flour",
        # dimensions / multipliers
        "2x3 cm pieces",
        "2 x 400 g cans tomatoes",
        "2 × 400 g cans tomatoes",
        # a second quantity in parentheses would stay unscaled
        "12 oz (340 g) pasta",
        # malformed leftovers
        "2 1/2/3 cups",
    ],
)
def test_ambiguous_quantities_unchanged(ingredient):
    """Unsupported formats are left as-is rather than scaled to a wrong amount."""
    rid = _create([ingredient])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == [ingredient]


@pytest.mark.parametrize(
    "ingredient, expected",
    [
        # words that merely *start* like the ambiguity markers still scale
        ("2 tomatoes", "4 tomatoes"),
        ("2 oranges", "4 oranges"),
        ("2 xl eggs", "4 xl eggs"),
        ("2 eggs, beaten", "4 eggs, beaten"),
        ("1/2 cup milk (whole)", "1 cup milk (whole)"),
    ],
)
def test_ambiguity_check_has_no_false_positives(ingredient, expected):
    rid = _create([ingredient])
    assert _scaled(rid, 2).json()["ingredients"] == [expected]


@pytest.mark.parametrize("ingredient", ["1/3 cup sugar", "2.0 cups rice", "1-2 cloves"])
def test_factor_one_is_identity(ingredient):
    rid = _create([ingredient])
    assert _scaled(rid, 1).json()["ingredients"] == [ingredient]


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
    assert json.loads(stored) == ingredients


def test_repeated_scaling_is_not_cumulative():
    rid = _create(["200 g flour"])
    assert _scaled(rid, 2).json()["ingredients"] == ["400 g flour"]
    assert _scaled(rid, 2).json()["ingredients"] == ["400 g flour"]

import atexit
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

# Snapshot the real DB file (if any) before main is imported, so a test can
# prove the suite never creates or modifies it.
_REAL_DB = Path(__file__).parent / "recipes.db"


def _real_db_state():
    return _REAL_DB.stat().st_mtime_ns if _REAL_DB.exists() else None


_REAL_DB_STATE_BEFORE = _real_db_state()

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


def _scale_one(ingredient, factor=2):
    """Scale a single-ingredient recipe; return (ingredients, unscaled)."""
    r = _scaled(_create([ingredient]), factor)
    assert r.status_code == 200
    body = r.json()
    return body["ingredients"], body["unscaled"]


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
    rid = _create(["200 g flour"])
    _scaled(rid, 2)
    assert temp_db.exists()
    # The real ./recipes.db was neither created nor touched by the suite.
    assert _real_db_state() == _REAL_DB_STATE_BEFORE


# --- scaling: response shape ---------------------------------------------------


def test_scaled_returns_full_recipe_with_factor():
    rid = _create(["200 g flour"], title="Bread", tags=["baking"])
    r = _scaled(rid, 2)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == rid
    assert body["title"] == "Bread"
    assert body["tags"] == ["baking"]
    assert body["ingredients"] == ["400 g flour"]
    assert body["unscaled"] == []


@pytest.mark.parametrize(
    "factor, raw",
    [("2", "2"), ("2.0", "2"), ("010", "10"), ("0.5", "0.5"), ("1.25", "1.25")],
)
def test_factor_is_echoed_without_trailing_zeros(factor, raw):
    # Check the serialized JSON: in Python 2.0 == 2, so comparing values hides "2.0".
    r = _scaled(_create(["1 egg"]), factor)
    assert r.status_code == 200
    assert f'"factor":{raw},' in r.text


# --- scaling: values ------------------------------------------------------------


@pytest.mark.parametrize(
    "ingredient, factor, expected",
    [
        # integers
        ("200 g flour", 2, "400 g flour"),
        ("200g flour", 1.5, "300g flour"),  # unit glued to number
        ("  2 g salt", 2, "  4 g salt"),  # leading whitespace preserved
        ("0 g sugar", 2, "0 g sugar"),  # zero stays zero
        ("999999 g flour", 10, "9999990 g flour"),  # large amounts stay exact
        # fractions
        ("1/2 cup milk", 2, "1 cup milk"),
        ("1/2 cup milk", 3, "1.5 cup milk"),
        ("1/3 cup sugar", 3, "1 cup sugar"),  # exact math, no 0.99
        ("1/3 cup sugar", 2, "0.67 cup sugar"),
        ("1 1/2 cups water", 2, "3 cups water"),  # mixed number
        # unicode fractions
        ("½ cup cream", 2, "1 cup cream"),
        ("⅓ cup oil", 3, "1 cup oil"),
        ("¾ tsp salt", 2, "1.5 tsp salt"),
        ("1½ cups flour", 2, "3 cups flour"),
        ("1 ½ cups flour", 2, "3 cups flour"),
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
        ("1 g saffron", "1e-3", "0.001 g saffron"),  # scientific notation factor
        ("1 g saffron", 0.0000001, "0.0000001 g saffron"),  # str(float) is "1e-07"
        ("1 g saffron", 0.005, "0.005 g saffron"),
        ("1 g saffron", 0.004, "0.004 g saffron"),
        ("1 g saffron", 0.0123, "0.012 g saffron"),
        ("1 g saffron", 0.995, "1 g saffron"),  # rounds up cleanly, no "1.0"
        # factor upper bound is allowed
        ("1 onion", 10, "10 onion"),
    ],
)
def test_scaling_values(ingredient, factor, expected):
    assert _scale_one(ingredient, factor) == ([expected], [])


@pytest.mark.parametrize(
    "ingredient, expected",
    [
        ("1-2 cloves garlic", "2-4 cloves garlic"),
        ("1 - 2 cloves garlic", "2 - 4 cloves garlic"),
        ("1–2 cloves garlic", "2–4 cloves garlic"),  # en dash
        ("1 to 2 cups stock", "2 to 4 cups stock"),
        ("2 or 3 eggs", "4 or 6 eggs"),
        ("1/2-1 cup milk", "1-2 cup milk"),
        ("½-1 cup milk", "1-2 cup milk"),
    ],
)
def test_ranges_scale_both_bounds(ingredient, expected):
    assert _scale_one(ingredient) == ([expected], [])


@pytest.mark.parametrize("ingredient", ["salt to taste", "pepper", "a pinch of nutmeg", ""])
def test_ingredients_without_quantity_unchanged_and_not_flagged(ingredient):
    # No quantity means nothing to scale: unchanged by design, so not reported.
    assert _scale_one(ingredient) == ([ingredient], [])


@pytest.mark.parametrize(
    "ingredient",
    [
        # invalid numbers
        "1/0 cup nonsense",
        "2 1/0 cup nonsense",
        "1-1/0 cup nonsense",
        # decimal comma vs thousands separator is ambiguous ("1,5" vs "1,000")
        "1,5 kg un",
        "1,000 g sugar",
        # a size, not a count: doubling "2-inch" makes the pieces bigger
        "2-inch piece ginger",
        "3-ounce can tuna",
        "1-2-inch pieces",
        # dimensions / multipliers
        "2x3 cm pieces",
        "2 x 400 g cans tomatoes",
        "2 × 400 g cans tomatoes",
        # a second quantity in parentheses would stay unscaled
        "12 oz (340 g) pasta",
        # malformed leftovers
        "2 1/2/3 cups",
        "1-2-3 eggs",
    ],
)
def test_ambiguous_quantities_unchanged_and_flagged(ingredient):
    """Unsupported formats are left as-is *and* reported, never scaled wrongly."""
    assert _scale_one(ingredient) == ([ingredient], [ingredient])


@pytest.mark.parametrize(
    "ingredient, expected",
    [
        # words that merely *start* like the ambiguity markers still scale
        ("2 tomatoes", "4 tomatoes"),
        ("2 oranges", "4 oranges"),
        ("2 xl eggs", "4 xl eggs"),
        ("2 eggs, beaten", "4 eggs, beaten"),
        ("1/2 cup milk (whole)", "1 cup milk (whole)"),
        # count followed by a size: only the count scales
        ("1 2-inch piece ginger", "2 2-inch piece ginger"),
        # only the leading quantity is scaled
        ("2 eggs, beaten in 1 bowl", "4 eggs, beaten in 1 bowl"),
    ],
)
def test_ambiguity_check_has_no_false_positives(ingredient, expected):
    assert _scale_one(ingredient) == ([expected], [])


def test_mixed_ingredient_list_preserves_order_and_flags_only_ambiguous():
    ingredients = ["200 g flour", "salt to taste", "1,5 kg un", "1/2 cup milk", "1-2 eggs"]
    r = _scaled(_create(ingredients), 2)
    body = r.json()
    assert body["ingredients"] == [
        "400 g flour",
        "salt to taste",
        "1,5 kg un",
        "1 cup milk",
        "2-4 eggs",
    ]
    assert body["unscaled"] == ["1,5 kg un"]


@pytest.mark.parametrize("ingredient", ["1/3 cup sugar", "2.0 cups rice", "1,5 kg un"])
def test_factor_one_is_identity(ingredient):
    # Nothing is scaled, so nothing is rewritten or flagged.
    assert _scale_one(ingredient, 1) == ([ingredient], [])


def test_recipe_with_no_ingredients():
    r = _scaled(_create([]), 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == []
    assert r.json()["unscaled"] == []


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
    ingredients = ["200 g flour", "1/2 cup milk", "salt to taste", "1,5 kg un"]
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

import atexit
import hashlib
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
    """(mtime, content hash) of the real DB, or None if it doesn't exist."""
    if not _REAL_DB.exists():
        return None
    return _REAL_DB.stat().st_mtime_ns, hashlib.sha256(_REAL_DB.read_bytes()).hexdigest()


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
        ("1-1/2 cups flour", 2, "3 cups flour"),  # US hyphenated mixed number
        ("2-3/4 cups flour", 2, "5.5 cups flour"),  # hyphen read as mixed (2 3/4), not range
        # unicode fraction slash U+2044
        ("1⁄2 cup milk", 2, "1 cup milk"),
        ("1 1⁄2 cups flour", 2, "3 cups flour"),
        ("1-1⁄2 cups flour", 2, "3 cups flour"),
        # unicode fractions
        ("½ cup cream", 2, "1 cup cream"),
        ("⅓ cup oil", 3, "1 cup oil"),
        ("¾ tsp salt", 2, "1.5 tsp salt"),
        # limit_denominator(10) path for other vulgar fractions
        ("⅔ cup milk", 3, "2 cup milk"),
        ("⅛ tsp salt", 4, "0.5 tsp salt"),
        ("⅒ l cream", 10, "1 l cream"),
        ("1/8 tsp salt", 1, "0.13 tsp salt"),  # documented rounding, even at factor 1
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
        ("1 1/2-2 cups stock", "3-4 cups stock"),
        ("1-1/2-2 cups stock", "3-4 cups stock"),  # hyphenated mixed as lower bound
    ],
)
def test_ranges_scale_both_bounds(ingredient, expected):
    assert _scale_one(ingredient) == ([expected], [])


@pytest.mark.parametrize(
    "ingredient, factor, expected",
    [
        # 29 digits, non-integer result: beyond Decimal's default 28-digit precision
        (
            "12345678901234567890123456789 g flour",
            1.5,
            "18518518351851851835185185183.5 g flour",
        ),
        ("1" + "0" * 40 + " g flour", 0.1, "1" + "0" * 39 + " g flour"),
        ("1" + "0" * 40 + "/3 g flour", 2, "6" * 40 + ".67 g flour"),
    ],
)
def test_huge_amounts_do_not_crash(ingredient, factor, expected):
    assert _scale_one(ingredient, factor) == ([expected], [])


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
        "1 1⁄2⁄3 cups",
        "1-2-3 eggs",
        # start like a number but can't be read as one
        "1.2.3 cups",
        "1/2/3 cups",
        "1e3 g sugar",
        # reversed range ("2 to 1") is not meaningful
        "2-1 cups flour",
        "1 1/2-1 cups flour",
        # percentages / temperatures are not amounts
        "70% dark chocolate",
        "70 % dark chocolate",
        "1.5% milk",
        "180°C oven",
        # negative amounts
        "-2 g sugar",
        "−2 g sugar",  # unicode minus
        "-.5 cup oil",
        # two bare numbers: which one is the count?
        "1 2 cups flour",
        "2 400 g cans tomatoes",
        # absurdly long numbers (also Python 3.11+'s 4300-digit str<->int limit)
        "1" * 5000 + " g flour",
        "1/" + "3" * 5000 + " cup flour",
        # compound quantities: a second amount later in the line
        "1 lb 4 oz beef",
        "1 cup plus 2 tbsp flour",
        "3 eggs or 4 egg whites",
        "1/2 cup (120 ml) milk",
        "½ cup plus ½ tbsp butter",  # unicode fraction as the second number
        # accepted limitation of the general rule: any later number counts
        "1 2-inch piece ginger",
        "2 eggs, beaten in 1 bowl",
        "2 cans V8 juice",
        # no readable leading quantity, but a number elsewhere in the line
        "flour 200 g",
        "Eggs: 2",
        "a 400 g can tomatoes",
        "about 2 cups stock",
        "~2 cups stock",
        "V8 juice",
        "pinch of salt (½ tsp)",
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
        # numbers that belong to the supported quantity itself are not "second numbers"
        ("1 1/2-2 cups stock", "3-4 cups stock"),
        ("2 TO 3 eggs", "4 TO 6 eggs"),  # range separator is case-insensitive
        ("1 OR 2 onions", "2 OR 4 onions"),
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


@pytest.mark.parametrize(
    "ingredient, ingredients, unscaled",
    [
        ("2.0 cups rice", ["2 cups rice"], []),  # trailing-zero rule holds at factor 1 too
        ("1/3 cup sugar", ["0.33 cup sugar"], []),  # same format as factor 1.0001
        ("200 g flour", ["200 g flour"], []),
        ("1,5 kg un", ["1,5 kg un"], ["1,5 kg un"]),  # flagged consistently
    ],
)
def test_factor_one_uses_same_rules_as_any_factor(ingredient, ingredients, unscaled):
    assert _scale_one(ingredient, 1) == (ingredients, unscaled)


def test_format_does_not_jump_between_close_factors():
    assert _scale_one("1/3 cup sugar", 1)[0] == _scale_one("1/3 cup sugar", 1.0001)[0]


@pytest.mark.parametrize(
    "ingredient",
    [
        "two eggs",
        "Two eggs",
        "half a lemon",
        "a dozen eggs",
        "2 cups plus one tbsp flour",  # previously half-scaled to "4 cups plus one tbsp"
        "1 lemon, cut in half",  # accepted side effect: reported, not wrongly scaled
        "1 cup half-and-half",  # accepted side effect (dairy product name)
    ],
)
def test_number_words_are_reported(ingredient):
    assert _scale_one(ingredient) == ([ingredient], [ingredient])


@pytest.mark.parametrize(
    "ingredient, expected",
    [
        # number words only match as whole words
        ("1 bone-in chicken thigh", "2 bone-in chicken thigh"),  # "one" inside "bone"
        ("2 tender steaks", "4 tender steaks"),  # "ten" inside "tender"
        ("1 often-used pan", "2 often-used pan"),
        ("2 honey crisp apples", "4 honey crisp apples"),
    ],
)
def test_number_words_have_no_substring_false_positives(ingredient, expected):
    assert _scale_one(ingredient) == ([expected], [])


@pytest.mark.parametrize(
    "ingredient",
    [
        # sizes written without a hyphen
        "2 inch piece ginger",
        "2 inches piece ginger",
        "3 ounce can tuna",
        "1 lb bag sugar",
        "400 g tin tomatoes",
        "3 cm pieces carrot",
        # percentages / temperatures written as words
        "70 percent dark chocolate",
        "70 per cent dark chocolate",
        "180 degrees oven",
        "180 degree oven",
        # digits from other scripts are not read as quantities
        "٢ cups flour",
        "2٢ cups flour",
        # improper mixed numbers: "1 to 3/2" or "2 1/2"?
        "1-3/2 cups flour",
        "1 3/2 cups flour",
    ],
)
def test_word_forms_of_non_amounts_are_reported(ingredient):
    assert _scale_one(ingredient) == ([ingredient], [ingredient])


@pytest.mark.parametrize(
    "ingredient, expected",
    [
        # the unit is the amount itself when no container follows
        ("3 ounces chocolate", "6 ounces chocolate"),
        ("2 inches ginger", "4 inches ginger"),
        ("200 g flour", "400 g flour"),
        # a count of containers (no unit before the container) still scales
        ("2 large cans tomatoes", "4 large cans tomatoes"),
        ("2 cans tomatoes", "4 cans tomatoes"),
        # "in" as a preposition, not after the number
        ("2 carrots in pieces", "4 carrots in pieces"),
        # proper mixed number with hyphen still scales
        ("1-1/2 cups flour", "3 cups flour"),
    ],
)
def test_size_and_percent_checks_have_no_false_positives(ingredient, expected):
    assert _scale_one(ingredient) == ([expected], [])


def test_tiny_factor_gives_exact_bounded_output():
    # 1e-300 is a valid factor (> 0); the result is exact, not "0" or "1e-300".
    ingredients, unscaled = _scale_one("1 g saffron", 1e-300)
    assert ingredients == ["0." + "0" * 299 + "1 g saffron"]
    assert unscaled == []


def test_factor_upper_bound_is_exact():
    # Exactly 10 (in any spelling) is allowed; anything above it, however close, is not.
    for factor in ["10", "10.0", "10.000000000000000000"]:
        assert _scaled(_create(["1 onion"]), factor).status_code == 200
    assert _scaled(_create(["1 onion"]), "10.0000000000000001").status_code == 422


def test_high_precision_factor_is_exact():
    # "1.0000000000000001" is beyond float precision (float gives exactly 1.0).
    ingredients, _ = _scale_one("1 g salt", "1.0000000000000001")
    assert ingredients == ["1 g salt"]  # rounded only at display, value stayed exact
    ingredients, _ = _scale_one("10000000000000000 g salt", "1.0000000000000001")
    assert ingredients == ["10000000000000001 g salt"]  # float would give 10000000000000000


def test_recipe_with_no_ingredients():
    r = _scaled(_create([]), 2)
    assert r.status_code == 200
    assert r.json()["ingredients"] == []
    assert r.json()["unscaled"] == []


# --- scaling: validation ------------------------------------------------------


@pytest.mark.parametrize(
    "factor",
    [
        "0", "-0", "0.0", "-1", "-0.5", "10.01", "11", "abc", "", "nan", "inf", "-inf",
        "1/2", "2x",
        "10.0000000000000001",  # would round to 10.0 as a float; checked exactly now
        "1e-999999",  # positive but absurd: bounded by max_digits instead of a huge Fraction
    ],
)
def test_invalid_factor_returns_422(factor):
    rid = _create(["200 g flour"])
    assert _scaled(rid, factor).status_code == 422


def test_non_numeric_recipe_id_returns_422():
    assert client.get("/recipes/abc/scaled", params={"factor": 2}).status_code == 422


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


# --- Shopping list ---


def _make(title, ingredients):
    return client.post("/recipes", json={"title": title, "ingredients": ingredients}).json()["id"]


def test_shopping_list_merges_and_dedupes(temp_db):
    a = _make("Pancakes", ["flour", "milk", "eggs"])
    b = _make("Crepes", ["  Flour ", "MILK", "butter"])
    r = client.get(f"/shopping-list?ids={a},{b}")
    assert r.status_code == 200
    assert r.json() == {"items": ["flour", "milk", "eggs", "butter"]}


def test_shopping_list_keeps_different_quantities(temp_db):
    a = _make("Bread", ["200 g flour"])
    b = _make("Cake", ["100 g flour", "200 G Flour"])
    r = client.get(f"/shopping-list?ids={a},{b}")
    assert r.json() == {"items": ["200 g flour", "100 g flour"]}


def test_shopping_list_order_follows_ids(temp_db):
    a = _make("A", ["salt"])
    b = _make("B", ["pepper", "salt"])
    r = client.get(f"/shopping-list?ids={b},{a}")
    assert r.json() == {"items": ["pepper", "salt"]}


def test_shopping_list_unknown_id_404(temp_db):
    a = _make("A", ["salt"])
    r = client.get(f"/shopping-list?ids={a},99999")
    assert r.status_code == 404


@pytest.mark.parametrize("query", ["?ids=", "?ids=1,abc", "?ids=1,,2", "?ids=-1", "?ids=1.5", ""])
def test_shopping_list_bad_ids_422(temp_db, query):
    r = client.get(f"/shopping-list{query}")
    assert r.status_code == 422


# --- Tag filter ---


@pytest.fixture
def tagged_recipes():
    """Seed four recipes for the tag-filter tests (on top of the empty temp_db)."""
    client.post("/recipes", json={"title": "Pancakes", "tags": ["Breakfast", "sweet"]})
    client.post("/recipes", json={"title": "Omelette", "tags": ["breakfast"]})
    client.post("/recipes", json={"title": "Soup", "tags": ["dinner"]})
    client.post("/recipes", json={"title": "Plain"})


def _titles(resp):
    return [rec["title"] for rec in resp.json()]


def test_tag_filter_no_param_returns_all(tagged_recipes):
    r = client.get("/recipes")
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette", "Soup", "Plain"]


def test_tag_filter_single_tag(tagged_recipes):
    r = client.get("/recipes", params={"tag": "breakfast"})
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette"]


def test_tag_filter_case_insensitive(tagged_recipes):
    r = client.get("/recipes", params={"tag": "BREAKFAST"})
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette"]


def test_tag_filter_multiple_tags_is_or(tagged_recipes):
    r = client.get("/recipes", params=[("tag", "sweet"), ("tag", "dinner")])
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Soup"]


def test_tag_filter_no_match_returns_empty_list(tagged_recipes):
    r = client.get("/recipes", params={"tag": "dessert"})
    assert r.status_code == 200
    assert r.json() == []


def test_tag_filter_empty_tag_is_422(tagged_recipes):
    r = client.get("/recipes?tag=")
    assert r.status_code == 422


def test_tag_filter_empty_among_valid_is_422(tagged_recipes):
    r = client.get("/recipes?tag=breakfast&tag=")
    assert r.status_code == 422

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


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


# --- Shopping list ---
import pytest

import main


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the app at a throwaway SQLite file instead of the real recipes.db."""
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    main.init_db()


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

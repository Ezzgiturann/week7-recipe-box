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


# --- Tag filter ---
import pytest

import main


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the app at an empty throwaway database instead of recipes.db."""
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    main.init_db()
    client.post("/recipes", json={"title": "Pancakes", "tags": ["Breakfast", "sweet"]})
    client.post("/recipes", json={"title": "Omelette", "tags": ["breakfast"]})
    client.post("/recipes", json={"title": "Soup", "tags": ["dinner"]})
    client.post("/recipes", json={"title": "Plain"})


def _titles(resp):
    return [rec["title"] for rec in resp.json()]


def test_tag_filter_no_param_returns_all(temp_db):
    r = client.get("/recipes")
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette", "Soup", "Plain"]


def test_tag_filter_single_tag(temp_db):
    r = client.get("/recipes", params={"tag": "breakfast"})
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette"]


def test_tag_filter_case_insensitive(temp_db):
    r = client.get("/recipes", params={"tag": "BREAKFAST"})
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Omelette"]


def test_tag_filter_multiple_tags_is_or(temp_db):
    r = client.get("/recipes", params=[("tag", "sweet"), ("tag", "dinner")])
    assert r.status_code == 200
    assert _titles(r) == ["Pancakes", "Soup"]


def test_tag_filter_no_match_returns_empty_list(temp_db):
    r = client.get("/recipes", params={"tag": "dessert"})
    assert r.status_code == 200
    assert r.json() == []


def test_tag_filter_empty_tag_is_422(temp_db):
    r = client.get("/recipes?tag=")
    assert r.status_code == 422


def test_tag_filter_empty_among_valid_is_422(temp_db):
    r = client.get("/recipes?tag=breakfast&tag=")
    assert r.status_code == 422

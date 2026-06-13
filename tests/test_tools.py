"""
Unit tests for the three FitFindr tools.

search_listings tests use the real listings data and need no API. The two
LLM-backed tools fake the Groq client with monkeypatch, so the tests are
deterministic and make zero API calls. Each tool has a happy-path test and at
least one failure-mode test (empty results, empty wardrobe, empty outfit).
"""

from types import SimpleNamespace

import tools
from tools import search_listings, suggest_outfit, create_fit_card


# ── shared sample data + fake LLM client ────────────────────────────────────

ITEM = {
    "id": "lst_006",
    "title": "Graphic Tee, 2003 Tour Bootleg",
    "description": "faded bootleg graphic tee",
    "category": "tops",
    "style_tags": ["graphic tee", "vintage", "grunge"],
    "size": "L",
    "condition": "good",
    "price": 24.0,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

WARDROBE = {"items": [
    {"id": "w_001", "name": "Baggy dark-wash jeans", "category": "bottoms",
     "colors": ["dark blue"], "style_tags": ["denim", "baggy"], "notes": "high-waisted"},
]}


def _fake_client(text):
    """Stand-in Groq client whose chat completion returns `text`."""
    def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("track jacket", size="M", max_price=None)
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


def test_search_empty_query_returns_list_not_none():
    results = search_listings("", size=None, max_price=None)
    assert results == []


# ── suggest_outfit ──────────────────────────────────────────────────────────

def test_suggest_happy_path(monkeypatch):
    monkeypatch.setattr(tools, "_get_groq_client",
                        lambda: _fake_client("Wear it with the baggy jeans."))
    out = suggest_outfit(ITEM, WARDROBE)
    assert isinstance(out, str)
    assert out.strip()


def test_suggest_empty_wardrobe_returns_string(monkeypatch):
    # Empty wardrobe must not crash. Force the offline path so no API is hit.
    def boom():
        raise RuntimeError("LLM unavailable")
    monkeypatch.setattr(tools, "_get_groq_client", boom)
    out = suggest_outfit(ITEM, {"items": []})
    assert isinstance(out, str)
    assert out.strip()


def test_suggest_llm_error_falls_back(monkeypatch):
    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(tools, "_get_groq_client", boom)
    out = suggest_outfit(ITEM, WARDROBE)
    assert isinstance(out, str)
    assert out.strip()


# ── create_fit_card ─────────────────────────────────────────────────────────

def test_fitcard_happy_path(monkeypatch):
    monkeypatch.setattr(tools, "_get_groq_client",
                        lambda: _fake_client("thrifted this tee on depop for $24"))
    out = create_fit_card("tee over baggy jeans", ITEM)
    assert isinstance(out, str)
    assert out.strip()


def test_fitcard_empty_outfit_returns_message():
    # Empty outfit must return a message string, not raise, and call no API.
    out = create_fit_card("", ITEM)
    assert isinstance(out, str)
    assert out.strip()


def test_fitcard_whitespace_outfit_returns_message():
    out = create_fit_card("   ", ITEM)
    assert isinstance(out, str)
    assert out.strip()

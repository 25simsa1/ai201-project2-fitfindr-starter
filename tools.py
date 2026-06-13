"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

# Model used by the two LLM-backed tools. See planning.md.
_MODEL = "llama-3.3-70b-versatile"

# Tiny words ignored when scoring keyword overlap in search_listings.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "or", "to", "of", "in", "on",
    "under", "less", "than", "my", "i", "im", "looking", "want", "find",
}


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── prompt + fallback helpers ───────────────────────────────────────────────

def _describe_item(item: dict) -> str:
    """One-line description of a listing for use in an LLM prompt."""
    if not isinstance(item, dict):
        return str(item)
    tags = ", ".join(item.get("style_tags", []))
    colors = ", ".join(item.get("colors", []))
    return (
        f"{item.get('title', 'Unknown item')} "
        f"(category {item.get('category', 'n/a')}; colors {colors or 'n/a'}; "
        f"tags {tags or 'n/a'})"
    )


def _describe_wardrobe_item(w: dict) -> str:
    """One-line description of a wardrobe item for use in an LLM prompt."""
    tags = ", ".join(w.get("style_tags", []))
    note = w.get("notes")
    base = f"{w.get('name', 'item')} ({w.get('category', 'n/a')}, {tags or 'no tags'})"
    return f"{base}. {note}" if note else base


def _outfit_fallback(new_item: dict, has_wardrobe: bool) -> str:
    """Plain styling message used when the LLM call is unavailable."""
    title = new_item.get("title", "this piece") if isinstance(new_item, dict) else "this piece"
    tags = ", ".join(new_item.get("style_tags", [])) if isinstance(new_item, dict) else ""
    vibe = f" Its {tags} vibe pairs well with simple, complementary basics." if tags else ""
    if has_wardrobe:
        return (
            f"Style {title} with the most neutral pieces in your wardrobe first, "
            f"then layer a jacket or overshirt on top and finish with shoes that "
            f"match the formality.{vibe}"
        )
    return (
        f"Your closet is empty, so here are some starting ideas for {title}. "
        f"Build around it with well-fitting bottoms, one layering piece, and "
        f"shoes that suit the occasion.{vibe}"
    )


def _fitcard_fallback(new_item: dict) -> str:
    """Plain caption used when the LLM call is unavailable."""
    title = new_item.get("title", "this find") if isinstance(new_item, dict) else "this find"
    price = new_item.get("price") if isinstance(new_item, dict) else None
    platform = new_item.get("platform", "secondhand") if isinstance(new_item, dict) else "secondhand"
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a great price"
    return (
        f"thrifted {title} on {platform} for {price_str} and i'm obsessed. "
        f"already planning three outfits around it."
    )


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    tokens = [
        t for t in re.findall(r"[a-z0-9]+", (description or "").lower())
        if t not in _STOPWORDS
    ]
    size_needle = size.strip().lower() if isinstance(size, str) and size.strip() else None

    scored = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size_needle is not None and size_needle not in item["size"].lower():
            continue

        haystack = " ".join([
            item["title"],
            item["description"],
            " ".join(item["style_tags"]),
            " ".join(item["colors"]),
            item["category"],
            item["brand"] or "",
        ]).lower()

        score = sum(1 for tok in set(tokens) if tok in haystack)
        if score == 0:
            continue

        scored.append((score, item["price"], item))

    # Best keyword overlap first, cheaper item wins ties.
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _score, _price, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    items = (wardrobe or {}).get("items", [])
    item_line = _describe_item(new_item)

    if items:
        closet = "\n".join("- " + _describe_wardrobe_item(w) for w in items)
        user_prompt = (
            f"New thrifted item:\n{item_line}\n\n"
            f"The user's wardrobe:\n{closet}\n\n"
            "Suggest one or two complete outfits built around the new item. "
            "Name the specific wardrobe pieces you would pair it with and add a "
            "short, concrete styling tip such as how to tuck, cuff, or layer."
        )
    else:
        user_prompt = (
            f"New thrifted item:\n{item_line}\n\n"
            "The user has not entered any wardrobe pieces yet. Give general "
            "styling ideas for this item, what kinds of pieces pair well with it "
            "and what vibe it suits. Keep it short and practical."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content":
                    "You are a friendly thrift stylist. Be specific and concise."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass

    return _outfit_fallback(new_item, has_wardrobe=bool(items))


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return (
            "I need an outfit idea before I can write a fit card. "
            "Run a search and outfit step first, then try again."
        )

    title = new_item.get("title", "this piece") if isinstance(new_item, dict) else "this piece"
    price = new_item.get("price") if isinstance(new_item, dict) else None
    platform = new_item.get("platform", "secondhand") if isinstance(new_item, dict) else "secondhand"
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a steal"

    user_prompt = (
        f"Item: {title}, {price_str}, found on {platform}.\n"
        f"Outfit: {outfit}\n\n"
        "Write a short, shareable caption for this look, the kind someone posts "
        "with an outfit photo. Two to four sentences. Mention the item name, "
        f"price ({price_str}), and platform ({platform}) once each. Sound like a "
        "real person, casual and specific, not a product description."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content":
                    "You write casual, authentic outfit captions for social media."},
                {"role": "user", "content": user_prompt},
            ],
            temperature=1.0,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass

    return _fitcard_fallback(new_item)

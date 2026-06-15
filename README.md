# FitFindr

FitFindr is a multi-tool agent that helps you find a secondhand piece and figure out how to wear it. You type a natural language request like "vintage graphic tee under $30", and the agent searches a mock listings dataset, picks the best match, styles it against your existing wardrobe, and writes a short caption you could actually post. The planning loop is what holds it together. It decides whether to keep going based on what each tool hands back, so the agent does not just run the same three steps every time.

## Setup and running

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Add your Groq key to a `.env` file in the repo root. It is gitignored.

```
GROQ_API_KEY=your_key_here
```

Run the app.

```bash
python app.py
```

Open the URL printed in your terminal. Gradio uses port 7860 by default, but it picks the next free port if that one is taken, so read the terminal output instead of assuming 7860. On my machine it came up on 7861 because another app held 7860.

Run the tests with `pytest tests/`.

## The tools

All three live in `tools.py`. Each one is callable and testable on its own.

### search_listings

Finds listings that match a text description, with an optional size and an optional price ceiling, ranked best match first. This one is pure Python over the mock dataset, with no model call. It takes three arguments.

- `description` (str) free text keywords, for example "vintage graphic tee". Drives the relevance score.
- `size` (str or None) a size to filter on, matched case insensitively as a substring so "M" also keeps "S/M". None skips the size filter.
- `max_price` (float or None) an inclusive price ceiling in dollars. None skips the price filter.

It returns a `list[dict]` of full listings ranked by keyword overlap, or `[]` when nothing matches. Each dict carries `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. It never raises and never returns None.

### suggest_outfit

Takes one listing and your wardrobe and produces one or two complete outfits built around that item. With a stocked wardrobe it names pieces from your closet, and with an empty wardrobe it gives general styling advice instead. It takes two arguments.

- `new_item` (dict) a single listing dict, normally `search_results[0]`.
- `wardrobe` (dict) a wardrobe shaped as `{"items": [...]}`, where each item has `id`, `name`, `category`, `colors`, `style_tags`, and an optional `notes`. The items list can be empty.

It returns a non-empty `str` of styling text from Groq `llama-3.3-70b-versatile` at temperature 0.7. If the call errors or the key is missing, it returns a plain fallback string built from the item fields rather than raising.

### create_fit_card

Turns an outfit suggestion and its item into a short, casual caption, the kind of thing someone posts with an outfit photo. It takes two arguments.

- `outfit` (str) the outfit suggestion text, normally the string from `suggest_outfit`.
- `new_item` (dict) the listing dict, used for the item name, price, and platform.

It returns a `str` caption of two to four sentences, and runs at temperature 1.0 so repeated calls vary. If `outfit` is empty or whitespace it returns a guidance message and does not call the model. If the model call errors it returns a fallback caption.

## Planning loop

The loop lives in `run_agent(query, wardrobe)` in `agent.py`. It runs the tools in a set order but decides at each step whether to continue, so it does not call all three tools no matter what.

1. It builds a fresh session dict. Every output field starts empty and `error` starts as None.
2. It parses the query into a description, an optional size, and an optional max_price with `_parse_query`, a regex helper. The parser reads the price from phrases like "under $30", reads the size from "size X" or a standalone size token, and builds the description from the first sentence with the price and size phrases and leading filler removed. Cutting at the first sentence matters, because the example query has a second sentence about what the user usually wears and that text should not become search keywords.
3. It calls `search_listings` with the parsed values and stores the list in the session.
4. This is the branching step. If the result list is empty, it writes a specific error into the session that names the description, size, and price it searched, then returns immediately. The two styling tools never run on empty input. If the list is not empty, it sets `selected_item` to the first result and continues.
5. It calls `suggest_outfit` with the selected item and the wardrobe, and stores the text. As a guard, if that text comes back empty it sets an error and returns before writing a caption, since a caption needs an outfit.
6. It calls `create_fit_card` with the outfit text and the selected item, and stores the caption.
7. It returns the session.

The agent is done when it either exits early at step 4 or finishes step 6. The behavior visibly differs by input. A findable query produces a listing, an outfit, and a caption, while an impossible query produces an error and nothing else.

## State management

Everything for one interaction lives in a single session dict created by `_new_session(query, wardrobe)`. Every tool result is written back into it, so each tool reads from the session instead of asking the user again.

The fields are `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`, `outfit_suggestion`, `fit_card`, and `error`. The handoffs are direct. `search_listings` fills `search_results`, the loop copies the top one into `selected_item`, and that same dict flows into `suggest_outfit` and then `create_fit_card`. `suggest_outfit` fills `outfit_suggestion`, which flows into `create_fit_card`. At the end, `handle_query` in `app.py` reads `selected_item`, `outfit_suggestion`, and `fit_card` to fill the three panels, or it reads `error` and shows that in the first panel with the other two blank.

I confirmed the passing is by reference, not re-entry or hardcoding, with a spy test. The object in `selected_item` is the exact same object that reached both styling tools, and the `outfit_suggestion` string is the exact object passed into `create_fit_card`.

## Error handling

Each tool owns its failure mode and stays useful instead of crashing. The examples below come straight from triggering each case.

| Tool | Failure triggered | What happens | Example output from testing |
|------|-------------------|--------------|-----------------------------|
| search_listings | no listing matches the query | returns `[]`, and the loop turns that into a specific error and stops before styling | `search_listings('designer ballgown', size='XXS', max_price=5)` returned `[]`, and the agent set `error` to `No listings matched "designer ballgown", size XXS, under $5. Try a higher budget, dropping the size, or broader keywords.` with `fit_card` left as None |
| suggest_outfit | empty wardrobe | switches to general styling advice for the item instead of failing | `suggest_outfit(item, get_empty_wardrobe())` returned styling advice starting `This Y2K Baby Tee is perfect for a playful, nostalgic look. Pair it with...` |
| create_fit_card | empty outfit string | returns a guidance message and never calls the model | `create_fit_card('', item)` returned `I need an outfit idea before I can write a fit card. Run a search and outfit step first, then try again.` |

Both model tools also wrap their Groq call in try and except, so a missing key or a network error returns a fallback string rather than raising. I verified this by running the tools with no key set before I added one.

## AI usage

I wrote all the code myself. Claude was only used for a couple of quick sanity checks on syntax, and even those were overridden or rewritten.

Instance 1 – the tools.
I implemented the three tools from scratch using the spec in planning.md. After finishing, I briefly asked Claude to generate a version for comparison. I ignored its output except for one minor idea: breaking ties by lower price (which I had already considered). The try/except wrappers around Groq calls and the temperature 1.0 for create_fit_card were entirely my own decisions—I ran multiple tests and tuned the value myself.

Instance 2 – the planning loop.
I built run_agent and _parse_query directly from my architecture diagram and state management notes. I glanced at a Claude‑suggested parser, found it flawed (it kept extra sentence fragments), and rewrote it completely—cutting at the first sentence and stripping trailing "in"/"for". The state flow was validated with my own spy test; Claude had no part in that.

## Spec reflection

The spec helped most when I got to the planning loop. I had written it branch by branch in `planning.md` before I touched `agent.py`, so `run_agent` came out as close to a transcription of that section. Because I had already drawn the empty-results branch on paper, the early exit and the error message were part of the design from the start, and I never had to bolt error handling on at the end.

Where the build diverged was the top result. My `planning.md` walkthrough predicted the bootleg graphic tee as the top hit for "vintage graphic tee", but the code returns the Y2K Baby Tee. I wrote that walkthrough before building the scoring, so it was an assumption. Once I had the scoring working, both tees tied on keyword overlap and my tie-break prefers the cheaper one, so the $18 tee beats the $24 one. The code does what I told it, the doc just guessed the wrong winner, and I left the code alone and noted the mismatch rather than bending the ranking to fit an old guess.

If I kept going I would tighten the keyword search. The word "vintage" is a tag on most of the dataset, so a query with it returns a long list. That does not hurt the agent since it only uses the top result, but a relevance threshold or weighting rarer words higher would sharpen the ranking. I would also move query parsing off regex toward something sturdier, since the regex handles the example queries but would miss less standard phrasings.

## Demo

The demo video shows one complete interaction from query to fit card, narrates the state passing between the tools, and triggers the no-results path to show the agent's graceful error response.

_Add your video link here once it is recorded._

"""Recipe text and URL parser — combines best features from both stores."""
from __future__ import annotations

import json
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from models import IngredientIntent, RecipePlan

# ---------------------------------------------------------------------------
# Pantry keywords — items skipped when skip_pantry=True
# ---------------------------------------------------------------------------

_PANTRY_KEYWORDS: frozenset[str] = frozenset({
    # Basics
    "salt", "pepper", "sugar", "oil", "olive oil", "water", "flour",
    "butter", "baking powder", "baking soda", "yeast", "vinegar",
    # Spices
    "cumin", "paprika", "turmeric", "oregano", "thyme", "basil", "cinnamon",
    "coriander", "cardamom", "cloves", "nutmeg", "bay leaves", "chili flakes",
    "garlic powder", "onion powder", "ginger powder",
    # Condiments usually on hand
    "soy sauce", "sesame oil", "honey", "maple syrup",
})

# ---------------------------------------------------------------------------
# Amount / unit regex
# ---------------------------------------------------------------------------

_FRACTION_MAP = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 0.333, "⅔": 0.667, "⅛": 0.125}
_AMOUNT_RE = re.compile(
    r"^(?P<qty>(?:\d+\s)?(?:\d+/\d+|[½¼¾⅓⅔⅛]|\d+(?:\.\d+)?))"
    r"(?:\s*(?P<unit>tsp|tbsp|cup|cups|oz|lb|lbs|g|kg|ml|l|liters?|"
    r"cloves?|slices?|stalks?|heads?|bunch(?:es)?|can|cans|package|pkg|"
    r"pieces?|pcs?|medium|large|small|whole))?\s+",
    re.IGNORECASE,
)
_INSTRUCTION_RE = re.compile(
    r"\b(preheat|bake|cook|fry|roast|mix|stir|whisk|chop|dice|slice|"
    r"simmer|boil|grill|season|add|place|heat|remove|serve|let|rest|"
    r"bring|combine|transfer|spread|pour|drain|rinse)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _normalise_quantity(text: str) -> tuple[float, str, str]:
    """Return (quantity, unit, remaining_text)."""
    # Replace fraction chars
    for char, val in _FRACTION_MAP.items():
        text = text.replace(char, str(val))

    m = _AMOUNT_RE.match(text.strip())
    if not m:
        return 1.0, "", text.strip()

    qty_str = m.group("qty").strip()
    unit = (m.group("unit") or "").lower().strip()
    remainder = text[m.end():].strip()

    # Handle "1 1/2" style
    parts = qty_str.split()
    if len(parts) == 2:
        whole = float(parts[0])
        if "/" in parts[1]:
            n, d = parts[1].split("/")
            qty = whole + float(n) / float(d)
        else:
            qty = whole + float(parts[1])
    elif "/" in qty_str:
        n, d = qty_str.split("/")
        qty = float(n) / float(d)
    else:
        try:
            qty = float(qty_str)
        except ValueError:
            qty = 1.0

    return qty, unit, remainder


def _is_pantry(name: str) -> bool:
    nl = name.lower()
    return any(kw in nl for kw in _PANTRY_KEYWORDS)


def _strip_notes(text: str) -> tuple[str, str]:
    """Split 'chicken, boneless' or 'chicken (organic)' into name + notes."""
    notes = ""
    m = re.search(r"\(([^)]+)\)", text)
    if m:
        notes = m.group(1).strip()
        text = text[: m.start()].strip() + text[m.end():].strip()
    if "," in text:
        parts = text.split(",", 1)
        text = parts[0].strip()
        notes = (notes + " " + parts[1].strip()).strip()
    return text.strip(), notes.strip()


def _parse_ingredient_line(line: str) -> Optional[IngredientIntent]:
    """Parse a single ingredient line into an IngredientIntent, or None if unparseable."""
    line = line.strip().lstrip("-•*●◦‣").strip()
    if not line or len(line) < 2:
        return None
    if _INSTRUCTION_RE.search(line) and len(line) > 60:
        return None

    # Skip section headers
    lower = line.lower()
    if any(lower.startswith(h) for h in (
        "for the", "ingredient", "instruction", "method", "direction",
        "note:", "tip:", "step"
    )):
        return None

    qty, unit, remainder = _normalise_quantity(line)
    name, notes = _strip_notes(remainder)
    if not name or len(name) < 2:
        return None
    # Clean up "of" prefix ("1 cup of milk")
    name = re.sub(r"^of\s+", "", name, flags=re.IGNORECASE).strip()
    if not name:
        return None

    return IngredientIntent(
        raw=line,
        name=name,
        quantity=qty,
        unit=unit,
        is_pantry=_is_pantry(name),
        notes=notes,
        search_terms=[name] + ([f"{name} {unit}" for unit in [unit] if unit]),
    )


# ---------------------------------------------------------------------------
# Main parse functions
# ---------------------------------------------------------------------------


def parse_recipe_text(text: str, skip_pantry: bool = True) -> RecipePlan:
    """Parse freeform recipe text into a RecipePlan."""
    lines = [ln.strip() for ln in text.splitlines()]
    ingredients: list[IngredientIntent] = []
    title = "Recipe"

    # Try to find a title (first non-empty, non-list-marker line)
    for line in lines:
        clean = line.lstrip("-•*●◦‣0123456789.) ").strip()
        if clean and len(clean) > 3 and not _AMOUNT_RE.match(clean):
            title = clean
            break

    for line in lines:
        intent = _parse_ingredient_line(line)
        if intent is None:
            continue
        if skip_pantry and intent.is_pantry:
            continue
        ingredients.append(intent)

    return RecipePlan(title=title, ingredients=ingredients)


async def fetch_recipe_from_url(url: str) -> Optional[RecipePlan]:
    """Fetch a recipe web page and parse it — tries JSON-LD then HTML fallback."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    # Try JSON-LD first
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Recipe"), None)
            if not data:
                continue
            if data.get("@type") != "Recipe":
                continue
            raw_ingredients = data.get("recipeIngredient") or []
            ingredients = []
            for line in raw_ingredients:
                intent = _parse_ingredient_line(str(line))
                if intent:
                    ingredients.append(intent)
            if ingredients:
                title = data.get("name", "Recipe")
                return RecipePlan(title=title, ingredients=ingredients)
        except Exception:
            continue

    # HTML fallback — look for ingredient list items
    ingredient_lines: list[str] = []
    for container in soup.select(
        ".ingredients, .ingredient-list, [class*='ingredient'], "
        "[itemprop='recipeIngredient'], .wprm-recipe-ingredient"
    ):
        for item in container.find_all(["li", "p", "span"]):
            text = item.get_text(" ", strip=True)
            if text and len(text) > 2:
                ingredient_lines.append(text)

    if ingredient_lines:
        ingredients = []
        for line in ingredient_lines:
            intent = _parse_ingredient_line(line)
            if intent:
                ingredients.append(intent)
        if ingredients:
            title_tag = soup.find("h1") or soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "Recipe"
            return RecipePlan(title=title[:100], ingredients=ingredients)

    # Last resort: treat the whole page text as recipe text
    body_text = soup.get_text("\n")
    plan = parse_recipe_text(body_text, skip_pantry=False)
    return plan if plan.ingredients else None

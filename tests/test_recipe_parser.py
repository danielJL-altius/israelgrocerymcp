"""Tests for the unified recipe parser."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from recipes.parser import parse_recipe_text, _parse_ingredient_line


def test_simple_recipe():
    text = """Pasta Carbonara
    200g spaghetti
    2 eggs
    100g pancetta
    50g parmesan cheese
    salt
    pepper
    """
    plan = parse_recipe_text(text, skip_pantry=True)
    names = [i.name.lower() for i in plan.ingredients]
    assert "spaghetti" in names or any("spaghetti" in n for n in names)
    assert not any(n in ("salt", "pepper") for n in names)  # pantry skipped


def test_pantry_not_skipped_when_disabled():
    text = "salt\npepper\n2 cups flour"
    plan = parse_recipe_text(text, skip_pantry=False)
    names = [i.name.lower() for i in plan.ingredients]
    assert "salt" in names or "flour" in names


def test_quantities_parsed():
    line = "2 cups chicken broth"
    intent = _parse_ingredient_line(line)
    assert intent is not None
    assert intent.quantity == 2.0
    assert intent.unit == "cups"
    assert "chicken" in intent.name.lower()


def test_fraction_quantity():
    line = "½ tsp vanilla extract"
    intent = _parse_ingredient_line(line)
    assert intent is not None
    assert abs(intent.quantity - 0.5) < 0.01


def test_instruction_lines_skipped():
    line = "Preheat the oven to 180°C for at least 15 minutes before baking the cake"
    intent = _parse_ingredient_line(line)
    assert intent is None


def test_title_extraction():
    text = "Shakshuka\n2 eggs\n1 can tomatoes\n1 onion"
    plan = parse_recipe_text(text, skip_pantry=False)
    assert "shakshuka" in plan.title.lower()


def test_notes_stripped():
    line = "200g chicken breast, boneless and skinless"
    intent = _parse_ingredient_line(line)
    assert intent is not None
    assert "boneless" not in intent.name.lower()
    assert "boneless" in intent.notes.lower()

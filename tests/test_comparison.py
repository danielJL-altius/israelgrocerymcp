"""Tests for the price comparison engine."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from comparison.engine import compare_recipe
from models import IngredientIntent, IngredientMatch, StoreProduct


def _make_match(name: str, shufersal_price: float | None, tivtaam_price: float | None) -> IngredientMatch:
    ing = IngredientIntent(raw=name, name=name)
    best: dict = {}
    conf: dict = {}
    if shufersal_price is not None:
        best["shufersal"] = StoreProduct(store_id="shufersal", product_id="s1", name=f"[S] {name}", price=shufersal_price)
        conf["shufersal"] = 0.8
    else:
        best["shufersal"] = None
        conf["shufersal"] = 0.0
    if tivtaam_price is not None:
        best["tivtaam"] = StoreProduct(store_id="tivtaam", product_id="t1", name=f"[T] {name}", price=tivtaam_price)
        conf["tivtaam"] = 0.8
    else:
        best["tivtaam"] = None
        conf["tivtaam"] = 0.0
    recommended = min(
        {k: v for k, v in best.items() if v and v.price is not None},
        key=lambda k: best[k].price,
        default=None,
    )
    return IngredientMatch(
        ingredient=ing, best_by_store=best, confidence_by_store=conf, recommended_store=recommended
    )


def test_cheapest_store_identified():
    matches = [
        _make_match("eggs", shufersal_price=20.0, tivtaam_price=15.0),
        _make_match("milk", shufersal_price=8.0, tivtaam_price=9.0),
    ]
    comp = compare_recipe("Test", matches)
    # Tiv Taam eggs cheaper; Shufersal milk cheaper → depends on total
    assert comp.cheapest_store is not None
    assert comp.cost_by_store["tivtaam"] < comp.cost_by_store["shufersal"]


def test_split_recommendation_picks_cheapest_per_item():
    matches = [
        _make_match("eggs", shufersal_price=20.0, tivtaam_price=15.0),
        _make_match("bread", shufersal_price=6.0, tivtaam_price=8.0),
    ]
    comp = compare_recipe("Test", matches)
    split = {s.ingredient_name: s.recommended_store for s in comp.split_recommendation}
    assert split.get("eggs") == "tivtaam"
    assert split.get("bread") == "shufersal"


def test_savings_computed():
    matches = [_make_match("olive oil", shufersal_price=30.0, tivtaam_price=25.0)]
    comp = compare_recipe("Test", matches)
    item = comp.split_recommendation[0]
    assert abs(item.savings - 5.0) < 0.01

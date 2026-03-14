"""Price comparison engine — compares ingredient costs across stores."""
from __future__ import annotations

from models import IngredientMatch, RecipeComparison, SplitItem


def compare_recipe(
    recipe_title: str,
    matches: list[IngredientMatch],
) -> RecipeComparison:
    """
    Given cross-store ingredient matches, compute:
    - Total cost per store if you buy everything there
    - Cheapest store overall
    - Per-ingredient best deal (split-cart recommendation)
    """
    # Collect all store IDs seen across matches
    all_store_ids: set[str] = set()
    for m in matches:
        if not m.skipped:
            all_store_ids.update(m.best_by_store.keys())

    # Total cost per store (only counting ingredients that have a match)
    cost_by_store: dict[str, float] = {}
    matched_count_by_store: dict[str, int] = {}
    for sid in all_store_ids:
        total = 0.0
        count = 0
        for m in matches:
            if m.skipped:
                continue
            product = m.best_by_store.get(sid)
            if product and product.effective_price is not None:
                total += product.effective_price * m.ingredient.quantity
                count += 1
        if count > 0:
            cost_by_store[sid] = round(total, 2)
            matched_count_by_store[sid] = count

    cheapest_store: str | None = None
    if cost_by_store:
        cheapest_store = min(cost_by_store, key=lambda s: cost_by_store[s])

    # Split recommendation: best deal per ingredient regardless of store
    split: list[SplitItem] = []
    for m in matches:
        if m.skipped:
            continue
        candidates = [
            (sid, p)
            for sid, p in m.best_by_store.items()
            if p and p.in_stock and p.effective_price is not None
        ]
        if not candidates:
            continue
        best_sid, best_product = min(candidates, key=lambda x: x[1].effective_price)  # type: ignore[arg-type]
        prices = [p.effective_price for _, p in candidates if p.effective_price is not None]
        savings = round(max(prices) - best_product.effective_price, 2) if len(prices) > 1 else 0.0  # type: ignore[operator]
        split.append(SplitItem(
            ingredient_name=m.ingredient.name,
            recommended_store=best_sid,
            product=best_product,
            savings=savings,
        ))

    split_total_savings = round(sum(s.savings for s in split), 2)

    return RecipeComparison(
        recipe_title=recipe_title,
        matches=matches,
        cost_by_store=cost_by_store,
        cheapest_store=cheapest_store,
        split_recommendation=split,
        split_total_savings=split_total_savings,
    )


def format_comparison(comp: RecipeComparison) -> str:
    """Format a RecipeComparison as a human-readable string."""
    lines = [f"**{comp.recipe_title}** — cross-store price comparison\n"]

    # Per-store totals
    if comp.cost_by_store:
        lines.append("**Total cost by store** (matched items only):")
        for sid, cost in sorted(comp.cost_by_store.items(), key=lambda x: x[1]):
            marker = " ← cheapest" if sid == comp.cheapest_store else ""
            lines.append(f"  🏪 {sid.title():15s}  {cost:.2f}₪{marker}")
        lines.append("")

    # Per-ingredient breakdown
    if comp.split_recommendation:
        lines.append("**Best deal per ingredient:**")
        for item in comp.split_recommendation:
            store_tag = f"[{item.recommended_store}]"
            price_str = item.product.display_price
            savings_str = f"  (saves {item.savings:.2f}₪)" if item.savings > 0.05 else ""
            lines.append(f"  • {item.ingredient_name:<22s}  {store_tag:<12s}  {price_str}{savings_str}")
        lines.append("")
        if comp.split_total_savings > 0.05:
            lines.append(f"💡 Buying each item from its cheapest store saves ~{comp.split_total_savings:.2f}₪")

    # Skipped
    skipped = [m for m in comp.matches if m.skipped]
    if skipped:
        lines.append(f"\n⏭  Skipped {len(skipped)} pantry items.")

    return "\n".join(lines)

"""Abstract base class that every grocery store adapter must implement."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from models import CartMutationResult, CartView, StoreProduct


class BaseStore(ABC):
    """Protocol for all grocery store adapters."""

    store_id: str    # e.g. "shufersal" or "tivtaam"
    store_name: str  # e.g. "Shufersal" or "Tiv Taam"

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    @abstractmethod
    async def search(self, query: str, max_results: int = 8) -> list[StoreProduct]:
        """Return up to max_results products matching the query string."""

    async def raw_search(self, query: str) -> dict:
        """Return raw diagnostic info about a search — for the diagnose tool."""
        try:
            products = await self.search(query, max_results=2)
            return {
                "store": self.store_id,
                "count": len(products),
                "sample": products[0].model_dump() if products else None,
            }
        except Exception as exc:
            return {"store": self.store_id, "error": str(exc)}

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    @abstractmethod
    async def get_cart(self) -> CartView:
        """Fetch the current cart for the logged-in session."""

    @abstractmethod
    async def add_to_cart(
        self,
        product_id: str,
        quantity: float = 1.0,
        sold_by: str = "unit",
    ) -> CartMutationResult:
        """Add a product to the cart."""

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    @abstractmethod
    async def check_login_status(self) -> bool:
        """Make a live network check — returns True if authenticated."""

    def is_logged_in_cached(self) -> bool:
        """Quick check from persisted session without a network call."""
        return False

    def login_hint(self) -> str:
        """Human-readable instruction for logging into this store."""
        return f"Use the login tool for {self.store_name}."

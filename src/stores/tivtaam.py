"""Tiv Taam grocery store adapter."""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from auth.session_store import MultiStoreSessionStore
from config import TivTaamConfig
from models import CartLine, CartMutationResult, CartView, StoreProduct
from stores.base import BaseStore

STORE_ID = "tivtaam"
STORE_NAME = "Tiv Taam"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.tivtaam.co.il",
    "Referer": "https://www.tivtaam.co.il/",
}


class TivTaamStore(BaseStore):
    store_id = STORE_ID
    store_name = STORE_NAME

    def __init__(self, cfg: TivTaamConfig, session_store: MultiStoreSessionStore) -> None:
        self._cfg = cfg
        self._ss = session_store
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        headers = dict(_BROWSER_HEADERS)
        session = self._ss.load_session(STORE_ID)
        if session and session.get("token"):
            headers["Authorization"] = f"Bearer {session['token']}"
        return httpx.AsyncClient(
            headers=headers,
            timeout=self._cfg.request_timeout,
            follow_redirects=True,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _invalidate_client(self) -> None:
        self._client = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self, email: str, password: str) -> str:
        """Authenticate with Tiv Taam. Returns a status message."""
        async with httpx.AsyncClient(
            headers=_BROWSER_HEADERS,
            timeout=self._cfg.request_timeout,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.post(
                    self._cfg.sessions_url,
                    json={"email": email, "password": password},
                )
            except Exception as exc:
                return f"Login failed: {exc}"

        if resp.status_code not in (200, 201):
            return f"Login failed: HTTP {resp.status_code} — {resp.text[:200]}"

        data = resp.json()
        token = data.get("token") or data.get("access_token", "")
        user_obj = data.get("user") or {}
        user_id = data.get("userId") or data.get("user_id") or user_obj.get("id")
        first_name = user_obj.get("firstName", "")
        last_name = user_obj.get("lastName", "")

        if not (token and user_id):
            return f"Login succeeded but missing token/userId. Response keys: {list(data.keys())}"

        self._ss.save_session(STORE_ID, {
            "user_id": int(user_id),
            "token": token,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "cart_id": None,
            "authenticated": True,
        })
        self._invalidate_client()
        name = f"{first_name} {last_name}".strip() or email
        return f"✅ Logged in to Tiv Taam as {name}."

    async def check_login_status(self) -> bool:
        session = self._ss.load_session(STORE_ID)
        if not session or not session.get("token"):
            return False
        client = await self._get_client()
        try:
            resp = await client.get(f"{self._cfg.sessions_url}/session")
            ok = resp.status_code == 200
            self._ss.mark_validation(STORE_ID, ok, f"Session check returned HTTP {resp.status_code}")
            return ok
        except Exception:
            return False

    def is_logged_in_cached(self) -> bool:
        session = self._ss.load_session(STORE_ID)
        return bool(session and session.get("token"))

    def login_hint(self) -> str:
        return "Run login_tivtaam(email, password) with your Tiv Taam account credentials."

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    async def search(self, query: str, max_results: int = 8) -> list[StoreProduct]:
        client = await self._get_client()
        params = {
            "q": query,
            "page": "1",
            "itemsCount": str(max_results),
            "storefront": "mobile_web",
        }
        try:
            resp = await client.get(self._cfg.products_url, params=params)
            if resp.status_code != 200:
                return []
            return self._parse_products(resp.json(), max_results)
        except Exception:
            return []

    async def raw_search(self, query: str) -> dict:
        client = await self._get_client()
        params = {"q": query, "page": "1", "itemsCount": "3", "storefront": "mobile_web"}
        try:
            resp = await client.get(self._cfg.products_url, params=params)
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            return {
                "store": STORE_ID,
                "status": resp.status_code,
                "url": str(resp.url)[:120],
                "auth_header": "Authorization" in resp.request.headers,
                "body_keys": list(body.keys()) if isinstance(body, dict) else f"type={type(body).__name__}",
                "sample": {k: (v[:2] if isinstance(v, list) else v)
                           for k, v in list(body.items())[:6]} if isinstance(body, dict) else body,
            }
        except Exception as exc:
            return {"store": STORE_ID, "error": str(exc)}

    def _parse_products(self, data: Any, max_results: int) -> list[StoreProduct]:
        items: list[Any] = []
        if isinstance(data, dict):
            items = data.get("products") or data.get("items") or data.get("data") or []
        elif isinstance(data, list):
            items = data

        products = []
        for item in items[:max_results]:
            try:
                products.append(self._parse_product(item))
            except Exception:
                pass
        return products

    def _parse_product(self, item: dict) -> StoreProduct:
        price_data = item.get("price") or {}
        if isinstance(price_data, (int, float)):
            price = float(price_data)
            unit_price = None
        else:
            price = float(price_data.get("base", 0) or price_data.get("regular", 0) or 0) or None
            up = price_data.get("unitPrice") or price_data.get("unit_price")
            unit_price = float(up) if up else None

        sale_raw = item.get("salePrice") or item.get("sale_price")
        sale_price = float(sale_raw) if sale_raw else None

        cat_data = (item.get("categories") or [{}])[0] if item.get("categories") else {}
        if isinstance(cat_data, dict):
            names = cat_data.get("names") or {}
            category = names.get("he") or names.get("en") or cat_data.get("name", "")
        else:
            category = str(cat_data)

        name_data = item.get("names") or item.get("name") or {}
        if isinstance(name_data, dict):
            name = name_data.get("he") or name_data.get("en") or name_data.get("short", "")
        else:
            name = str(name_data)

        brand_data = item.get("brand") or item.get("manufacture") or {}
        if isinstance(brand_data, dict):
            brand = brand_data.get("name") or brand_data.get("he", "")
        else:
            brand = str(brand_data) if brand_data else ""

        images = item.get("images") or []
        image_url = images[0].get("url", "") if images and isinstance(images[0], dict) else ""

        return StoreProduct(
            store_id=STORE_ID,
            product_id=str(item.get("id", 0)),
            name=str(name),
            price=price,
            sale_price=sale_price,
            is_on_sale=bool(sale_price and price and sale_price < price),
            brand=str(brand),
            category=str(category),
            in_stock=not item.get("outOfStock", False),
            image_url=image_url,
            weight=item.get("weight"),
            weight_unit=item.get("weightUnit", ""),
            unit_price=unit_price,
        )

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    async def get_cart(self) -> CartView:
        client = await self._get_client()
        try:
            resp = await client.get(self._cfg.orders_url)
            if resp.status_code != 200:
                return CartView(store_id=STORE_ID)
            return self._parse_cart(resp.json())
        except Exception:
            return CartView(store_id=STORE_ID)

    async def add_to_cart(
        self,
        product_id: str,
        quantity: float = 1.0,
        sold_by: str = "unit",
    ) -> CartMutationResult:
        session = self._ss.load_session(STORE_ID)
        if not session or not session.get("token"):
            return CartMutationResult(
                success=False, store_id=STORE_ID, product_id=product_id, quantity=quantity,
                message="Not logged in to Tiv Taam. Use login_tivtaam(email, password).",
            )

        current = await self.get_cart()
        cart_id = current.cart_id or (session.get("cart_id") or None)

        merged: list[dict] = []
        for line in current.lines:
            merged.append({
                "retailerProductId": int(line.product_id) if line.product_id.isdigit() else line.product_id,
                "quantity": line.quantity,
                "soldBy": "weight" if line.is_weighted else "unit",
                "type": 1,
                "isCase": False,
            })
        # Merge or append new item
        pid_int = int(product_id) if product_id.isdigit() else product_id
        for line in merged:
            if line["retailerProductId"] == pid_int:
                line["quantity"] += quantity
                break
        else:
            merged.append({
                "retailerProductId": pid_int,
                "quantity": quantity,
                "soldBy": sold_by,
                "type": 1,
                "isCase": False,
            })

        client = await self._get_client()
        try:
            if cart_id:
                resp = await client.patch(
                    f"{self._cfg.carts_url}/{cart_id}",
                    json={"lines": merged},
                )
                if resp.status_code not in (200, 201):
                    resp = await client.post(self._cfg.carts_url, json={"lines": merged})
            else:
                resp = await client.post(self._cfg.carts_url, json={"lines": merged})

            if resp.status_code not in (200, 201):
                return CartMutationResult(
                    success=False, store_id=STORE_ID, product_id=product_id, quantity=quantity,
                    message=f"Tiv Taam cart API returned HTTP {resp.status_code}.",
                )
            data = resp.json()
            new_cart_id = data.get("id") or data.get("cartId") or data.get("serverCartId")
            if new_cart_id:
                session["cart_id"] = str(new_cart_id)
                self._ss.save_session(STORE_ID, session)

            return CartMutationResult(
                success=True, store_id=STORE_ID,
                product_id=product_id, quantity=quantity,
                message=f"Added to Tiv Taam cart (cart_id={new_cart_id}).",
                cart=self._parse_cart(data),
            )
        except Exception as exc:
            return CartMutationResult(
                success=False, store_id=STORE_ID, product_id=product_id, quantity=quantity,
                message=f"Cart error: {exc}",
            )

    def _parse_cart(self, data: Any) -> CartView:
        if isinstance(data, list):
            active = next((o for o in data if o.get("status") in ("open", "new", 1)), None)
            data = active or (data[0] if data else {})
        if not isinstance(data, dict):
            return CartView(store_id=STORE_ID)

        cart_id = (
            data.get("cartId") or data.get("serverCartId")
            or (str(data["id"]) if not data.get("status") and data.get("id") else None)
        )
        order_id = str(data.get("id")) if data.get("status") else None
        total = float(data.get("totalAmount") or data.get("total") or 0)
        subtotal = float(data.get("subTotal") or data.get("subtotal") or total)

        lines = []
        for raw in data.get("lines") or []:
            try:
                product = raw.get("product") or {}
                name_data = product.get("names") or product.get("name") or {}
                if isinstance(name_data, dict):
                    name = name_data.get("he") or name_data.get("en") or ""
                else:
                    name = str(name_data)
                price_data = raw.get("price") or product.get("price") or {}
                price = float(price_data.get("base", 0) if isinstance(price_data, dict) else (price_data or 0))
                pid = str(product.get("id") or raw.get("retailerProductId") or "")
                qty = float(raw.get("quantity", 1))
                lines.append(CartLine(
                    product_id=pid,
                    product_name=name,
                    quantity=qty,
                    price=price,
                    total=float(raw.get("totalPrice") or (price * qty)),
                    line_id=str(raw.get("id", "")),
                    is_weighted=product.get("soldBy") == "weight" or raw.get("soldBy") == "weight",
                ))
            except Exception:
                pass

        return CartView(
            store_id=STORE_ID,
            order_id=order_id,
            cart_id=cart_id,
            lines=lines,
            subtotal=subtotal,
            total=total,
            item_count=len(lines),
        )

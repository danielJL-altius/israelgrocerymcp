# Israel Grocery MCP

Unified Model Context Protocol (MCP) server for Israeli grocery shopping — **Shufersal + Tiv Taam** with cross-store price comparison, recipe-driven cart automation, and an extensible plugin architecture for future stores.

## Features

- **Cross-store search** — search both Shufersal and Tiv Taam simultaneously
- **Price comparison** — see side-by-side pricing for any product or full recipe
- **Smart recipe shopping** — parse any recipe, find the best deals across stores, and add items to the cheapest cart automatically
- **Split-cart recommendations** — buy each ingredient from wherever it's cheapest and see your total savings
- **Preference system** — set a preferred store, shopping strategy (cheapest / preferred / quality), organic preference, brand blacklisting, and more
- **Diagnostics tool** — `diagnose()` surfaces HTTP errors, response shapes, and session state

## Setup

### 1. Install `uv`

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

### 2. Install dependencies

```bash
cd israelgrocery
uv sync
```

### 3. Install Playwright (required for Shufersal browser login)

```bash
uv run playwright install chromium
```

### 4. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env as needed
```

## Running the server

```bash
uv run israelgrocery-mcp
```

## Claude Desktop configuration

```json
{
  "mcpServers": {
    "israelgrocery": {
      "command": "uv",
      "args": ["--directory", "/path/to/israelgrocery", "run", "israelgrocery-mcp"]
    }
  }
}
```

## Available MCP Tools

| Tool | Description |
|---|---|
| `login_status()` | Show login status for all stores |
| `login_tivtaam(email, password)` | Log in to Tiv Taam |
| `login_shufersal()` | Open browser for Shufersal login |
| `check_login(store_id?)` | Live session validation |
| `set_preferences(...)` | Shopping preferences |
| `search_products(query, stores?)` | Search across stores |
| `compare_prices(query)` | Price comparison for an item |
| `show_cart(store_id?)` | View cart(s) |
| `add_to_cart(store_id, product_id, qty)` | Add to a specific cart |
| `plan_recipe_ingredients(recipe_text)` | Parse recipe ingredients |
| `compare_recipe(recipe_text)` | Full recipe cost comparison |
| `add_recipe_to_cart(recipe_text, ...)` | Automated recipe shopping |
| `diagnose(store_id?)` | Debug API connections |

## Example prompts for Claude

- *"Compare prices for eggs and milk across both stores"*
- *"I want to make shakshuka — find all the ingredients and tell me where to buy them cheapest"*
- *"Add this pasta recipe to my Tiv Taam cart: [paste recipe]"*
- *"Buy each ingredient from wherever it's cheapest and show me the savings"*
- *"Search for chicken breast on both stores"*

## Shopping strategies

| Strategy | Behaviour |
|---|---|
| `cheapest` (default) | Each item is bought from whichever store has the lower price |
| `preferred_store` | Always use your set preferred store unless it has no match |
| `quality` | Prefer the highest-confidence product match regardless of price |

## Adding a new store

1. Create `src/stores/mystore.py` implementing `BaseStore`
2. Register it in `src/stores/__init__.py` → `build_registry()`
3. Add config in `src/config.py`
4. Done — all existing tools automatically include the new store

## Running tests

```bash
uv run pytest tests/ -v
```

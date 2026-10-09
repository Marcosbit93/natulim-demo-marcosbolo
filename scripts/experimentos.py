"""Experimentos de la clase 3 (Paso 6).

Uso:
    uv run python scripts/experimentos.py cost
    uv run python scripts/experimentos.py cost-deep
    uv run python scripts/experimentos.py filter
    uv run python scripts/experimentos.py idempotency
    uv run python scripts/experimentos.py idempotency-literal
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from shopify_odoo_integration.config import Settings
from shopify_odoo_integration.shopify.auth import ClientCredentialsTokenProvider
from shopify_odoo_integration.shopify.graphql import GraphQLError, ShopifyGraphQL

QUERIES = Path(__file__).parent.parent / "src/shopify_odoo_integration/shopify/queries"


def make_client() -> ShopifyGraphQL:
    s = Settings()
    tokens = ClientCredentialsTokenProvider(
        s.shopify_shop, s.shopify_client_id, s.shopify_client_secret
    )
    return ShopifyGraphQL(s.shopify_shop, s.shopify_api_version, tokens)


def read_query(name: str) -> str:
    return (QUERIES / f"{name}.graphql").read_text(encoding="utf-8")


# --- Experimento 1: costo -------------------------------------------------

COST_QUERY = """
query Cost($p: Int!, $v: Int!) {
  products(first: $p) {
    nodes { id variants(first: $v) { nodes { id } } }
  }
}
"""

# Tres niveles de listas anidadas: productos > variantes > niveles de inventario
DEEP_QUERY = """
query CostDeep($p: Int!, $v: Int!, $l: Int!) {
  products(first: $p) {
    nodes {
      id
      variants(first: $v) {
        nodes {
          id
          inventoryItem {
            inventoryLevels(first: $l) {
              nodes { quantities(names: ["available", "on_hand"]) { name quantity } }
            }
          }
        }
      }
    }
  }
}
"""

LADDER = [(5, 5), (25, 25), (50, 50), (100, 50), (100, 100), (250, 100), (250, 250)]
DEEP_LADDER = [(10, 10, 10), (50, 50, 10), (100, 100, 50), (250, 250, 250)]


def show_cost(gql: ShopifyGraphQL, label: str, query: str, variables: dict[str, Any]) -> None:
    try:
        result = gql.execute(query, variables)
    except GraphQLError as exc:
        print(f"{label}\n    ERROR {exc.codes}")
        for e in exc.errors:
            print("    extensions:", e.get("extensions"))
        return
    c = result.cost
    if c is None:
        print(f"{label}\n    sin extensions.cost")
        return
    print(
        f"{label}\n    pedido={c.requested} real={c.actual} "
        f"disponible={c.available}/{c.maximum} recupera={c.restore_rate}/s"
    )


def experiment_cost() -> None:
    gql = make_client()
    for p, v in LADDER:
        label = f"products(first:{p}) x variants(first:{v})"
        show_cost(gql, label, COST_QUERY, {"p": p, "v": v})


def experiment_cost_deep() -> None:
    gql = make_client()
    for p, v, n in DEEP_LADDER:
        label = f"products(first:{p}) x variants(first:{v}) x inventoryLevels(first:{n})"
        show_cost(gql, label, DEEP_QUERY, {"p": p, "v": v, "l": n})


# --- Experimento 2: paginación con filtro ------------------------------------

FILTERS = [None, "updated_at:>2026-09-01", "status:draft", "updated_at:>2026-10-10"]


def experiment_filter() -> None:
    gql = make_client()
    query = read_query("products")
    for flt in FILTERS:
        total = sum(
            1 for _ in gql.paginate(query, "products", {"query": flt}, page_size=25)
        )
        print(f"filtro={flt!r:30} -> {total} productos")


# --- Experimento 3: idempotencia de inventario --------------------------------

LEVEL_QUERY = """
query Level($item: ID!, $loc: ID!) {
  inventoryItem(id: $item) {
    inventoryLevel(locationId: $loc) { quantities(names: ["available"]) { name quantity } }
  }
}
"""

# Variante con la clave escrita como texto dentro de la consulta (no como variable)
LITERAL_MUTATION = """
mutation SetStock($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) @idempotent(key: "%s") {
    inventoryAdjustmentGroup { id changes { name delta } }
    userErrors { field message code }
  }
}
"""


def find_stocked_item(gql: ShopifyGraphQL) -> tuple[str, str, int]:
    for item in gql.paginate(read_query("inventory"), "inventoryItems", page_size=10):
        for level in item["inventoryLevels"]["nodes"]:
            qty = {q["name"]: q["quantity"] for q in level["quantities"]}
            if "available" in qty:
                return item["id"], level["location"]["id"], qty["available"]
    raise SystemExit("No encontré un ítem con stock rastreado en ninguna ubicación.")


def available(gql: ShopifyGraphQL, item: str, loc: str) -> int:
    data = gql.execute(LEVEL_QUERY, {"item": item, "loc": loc}).data
    quantities = data["inventoryItem"]["inventoryLevel"]["quantities"]
    return int(quantities[0]["quantity"])


def set_stock(
    gql: ShopifyGraphQL,
    item: str,
    loc: str,
    quantity: int,
    change_from: int,
    key: str,
    *,
    literal: bool = False,
) -> dict[str, Any]:
    variables: dict[str, Any] = {
        "input": {
            "name": "available",
            "reason": "correction",
            "quantities": [
                {
                    "inventoryItemId": item,
                    "locationId": loc,
                    "quantity": quantity,
                    "changeFromQuantity": change_from,
                }
            ],
        },
    }
    if literal:
        query = LITERAL_MUTATION % key
    else:
        query = read_query("set_stock")
        variables["key"] = key
    result = gql.execute(query, variables)
    return result.data["inventorySetQuantities"]


def show(title: str, payload: dict[str, Any]) -> None:
    print(f"\n{title}")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def experiment_idempotency(*, literal: bool = False) -> None:
    gql = make_client()
    item, loc, original = find_stocked_item(gql)
    modo = "clave como texto en la consulta" if literal else "clave como variable"
    print(f"Modo: {modo}")
    print(f"Ítem: {item}\nUbicación: {loc}\nStock disponible inicial: {original}")
    target = original + 1
    key_a, key_b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        show(
            f"1) clave A, cambio {original} -> {target}",
            set_stock(gql, item, loc, target, original, key_a, literal=literal),
        )
        print("   stock ahora:", available(gql, item, loc))

        show(
            "2) REINTENTO: misma clave A, mismo pedido",
            set_stock(gql, item, loc, target, original, key_a, literal=literal),
        )
        print("   stock ahora:", available(gql, item, loc), "(¿se aplicó dos veces?)")

        show(
            f"3) clave B nueva, pero con cantidad previa vieja ({original})",
            set_stock(gql, item, loc, target, original, key_b, literal=literal),
        )
        print("   stock ahora:", available(gql, item, loc))
    finally:
        now = available(gql, item, loc)
        if now != original:
            set_stock(gql, item, loc, original, now, str(uuid.uuid4()), literal=literal)
        print(f"\nStock restaurado a {available(gql, item, loc)} (inicial: {original})")


EXPERIMENTS = {
    "cost": experiment_cost,
    "cost-deep": experiment_cost_deep,
    "filter": experiment_filter,
    "idempotency": experiment_idempotency,
    "idempotency-literal": lambda: experiment_idempotency(literal=True),
}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in EXPERIMENTS:
        raise SystemExit(f"Uso: experimentos.py [{'|'.join(EXPERIMENTS)}]")
    EXPERIMENTS[name]()

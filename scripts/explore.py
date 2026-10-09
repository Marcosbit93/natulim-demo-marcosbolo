"""Corre las consultas de solo lectura contra tu tienda y muestra el costo.

Uso:
    uv run python scripts/explore.py            # productos (por defecto)
    uv run python scripts/explore.py orders
    uv run python scripts/explore.py inventory
"""

import sys
from pathlib import Path

from shopify_odoo_integration.config import Settings
from shopify_odoo_integration.shopify.auth import ClientCredentialsTokenProvider
from shopify_odoo_integration.shopify.graphql import ShopifyGraphQL

QUERIES = Path(__file__).parent.parent / "src/shopify_odoo_integration/shopify/queries"

# nombre del archivo .graphql -> campo raíz que devuelve la consulta
ROOTS = {"products": "products", "orders": "orders", "inventory": "inventoryItems"}


def main(name: str = "products") -> None:
    s = Settings()
    tokens = ClientCredentialsTokenProvider(
        s.shopify_shop, s.shopify_client_id, s.shopify_client_secret
    )
    gql = ShopifyGraphQL(s.shopify_shop, s.shopify_api_version, tokens)
    query = (QUERIES / f"{name}.graphql").read_text(encoding="utf-8")
    root = ROOTS[name]

    for i, node in enumerate(gql.paginate(query, root, page_size=5)):
        label = node.get("title") or node.get("name") or node.get("sku")
        extra = f"{len(node['variants']['nodes'])} variantes" if "variants" in node else ""
        print(node["id"], label, extra)
        if i >= 9:
            break

    result = gql.execute(query, {"first": 5, "after": None})
    print("costo:", result.cost)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "products")

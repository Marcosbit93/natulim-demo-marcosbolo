import ssl

import httpx
import truststore

from shopify_odoo_integration.config import Settings
from shopify_odoo_integration.shopify.auth import ClientCredentialsTokenProvider

QUERY = """
{
  shop { name myshopifyDomain }
  currentAppInstallation { accessScopes { handle } }
}
"""


def main() -> None:
    s = Settings()
    provider = ClientCredentialsTokenProvider(
        s.shopify_shop, s.shopify_client_id, s.shopify_client_secret
    )
    url = f"https://{s.shopify_shop}/admin/api/{s.shopify_api_version}/graphql.json"
    response = httpx.post(
        url,
        json={"query": QUERY},
        headers={"X-Shopify-Access-Token": provider.get()},
        timeout=10.0,
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
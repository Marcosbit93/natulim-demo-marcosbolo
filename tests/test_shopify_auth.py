import httpx
import pytest
import respx
from pydantic import SecretStr

from shopify_odoo_integration.shopify.auth import (
    ClientCredentialsTokenProvider,
    ShopifyAuthError,
)

SHOP = "demo.myshopify.com"
URL = f"https://{SHOP}/admin/oauth/access_token"


def make(clock):
    return ClientCredentialsTokenProvider(SHOP, "id", SecretStr("secret"), clock=clock)


@respx.mock
def test_token_is_cached_until_margin():
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "t1", "scope": "read_products", "expires_in": 86399}
        )
    )
    now = [1000.0]
    provider = make(lambda: now[0])
    assert provider.get() == "t1"
    now[0] += 3600
    assert provider.get() == "t1"
    assert route.call_count == 1


@respx.mock
def test_token_refreshes_near_expiry():
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "t1", "scope": "", "expires_in": 1000}),
            httpx.Response(200, json={"access_token": "t2", "scope": "", "expires_in": 1000}),
        ]
    )
    now = [0.0]
    provider = make(lambda: now[0])
    assert provider.get() == "t1"
    now[0] = 800.0  # quedan 200 s, menos que el margen de 300 s
    assert provider.get() == "t2"
    assert route.call_count == 2


@respx.mock
def test_error_does_not_leak_secret():
    respx.post(URL).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    provider = make(lambda: 0.0)
    with pytest.raises(ShopifyAuthError) as exc:
        provider.get()
    assert "secret" not in str(exc.value)
    assert "401" in str(exc.value)


@respx.mock
def test_html_error_body_is_handled_without_leaking_secret():
    # Shopify responde 400 con HTML (no JSON) ante un client_secret inválido.
    respx.post(URL).mock(
        return_value=httpx.Response(
            400,
            html="<html><title>400 - Oauth error invalid_request</title></html>",
        )
    )
    provider = make(lambda: 0.0)
    with pytest.raises(ShopifyAuthError) as exc:
        provider.get()
    assert "secret" not in str(exc.value)
    assert "400" in str(exc.value)

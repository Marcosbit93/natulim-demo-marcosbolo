import json

import httpx
import pytest
import respx

from shopify_odoo_integration.shopify.graphql import (
    GraphQLError,
    ShopifyGraphQL,
    UserError,
    raise_for_user_errors,
)

URL = "https://demo.myshopify.com/admin/api/2026-07/graphql.json"
QUERY = (
    "query($first:Int!,$after:String)"
    "{products(first:$first,after:$after){nodes{id} pageInfo{hasNextPage endCursor}}}"
)


class FakeTokens:
    def get(self) -> str:
        return "tok"


def client() -> ShopifyGraphQL:
    return ShopifyGraphQL("demo.myshopify.com", "2026-07", FakeTokens())


def page(nodes, has_next, cursor):
    connection = {
        "nodes": nodes,
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
    }
    body = {"data": {"products": connection}}
    return httpx.Response(200, json=body)


@respx.mock
def test_paginate_follows_cursors():
    route = respx.post(URL).mock(
        side_effect=[
            page([{"id": "1"}, {"id": "2"}], True, "c1"),
            page([{"id": "3"}], False, "c2"),
        ]
    )
    ids = [n["id"] for n in client().paginate(QUERY, "products")]
    assert ids == ["1", "2", "3"]
    assert json.loads(route.calls[1].request.content)["variables"]["after"] == "c1"


@respx.mock
def test_throttled_is_an_error_even_with_http_200():
    respx.post(URL).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]}
        )
    )
    with pytest.raises(GraphQLError) as exc:
        client().execute("{ shop { name } }")
    assert exc.value.is_throttled


@respx.mock
def test_cost_is_parsed():
    body = {
        "data": {"shop": {"name": "x"}},
        "extensions": {
            "cost": {
                "requestedQueryCost": 2,
                "actualQueryCost": 1,
                "throttleStatus": {
                    "maximumAvailable": 1000.0,
                    "currentlyAvailable": 999,
                    "restoreRate": 50.0,
                },
            }
        },
    }
    respx.post(URL).mock(return_value=httpx.Response(200, json=body))
    result = client().execute("{ shop { name } }")
    assert result.cost is not None
    assert result.cost.requested == 2 and result.cost.available == 999


def test_user_errors_raise():
    with pytest.raises(UserError):
        raise_for_user_errors({"userErrors": [{"field": ["input"], "message": "bad"}]})

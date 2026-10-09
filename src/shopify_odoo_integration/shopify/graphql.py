from __future__ import annotations

import ssl
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import truststore


class TokenSource(Protocol):
    def get(self) -> str: ...


class GraphQLError(Exception):
    """Errores de nivel superior: la respuesta fue HTTP 200 pero trae `errors`."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        self.codes = [e.get("extensions", {}).get("code") for e in errors]
        super().__init__("; ".join(str(e.get("message", "?")) for e in errors))

    @property
    def is_throttled(self) -> bool:
        return "THROTTLED" in self.codes


class UserError(Exception):
    """userErrors de una mutación: llegó bien, pero los datos no pasaron una regla."""

    def __init__(self, user_errors: list[dict[str, Any]]) -> None:
        self.user_errors = user_errors
        super().__init__("; ".join(str(e.get("message", "?")) for e in user_errors))


@dataclass(frozen=True)
class Cost:
    requested: float
    actual: float | None
    available: float
    maximum: float
    restore_rate: float


@dataclass(frozen=True)
class Result:
    data: dict[str, Any]
    cost: Cost | None


def _parse_cost(body: dict[str, Any]) -> Cost | None:
    cost = body.get("extensions", {}).get("cost")
    if not cost:
        return None
    t = cost["throttleStatus"]
    return Cost(
        cost["requestedQueryCost"],
        cost.get("actualQueryCost"),
        t["currentlyAvailable"],
        t["maximumAvailable"],
        t["restoreRate"],
    )


def raise_for_user_errors(payload: dict[str, Any]) -> None:
    if payload.get("userErrors"):
        raise UserError(payload["userErrors"])


class ShopifyGraphQL:
    def __init__(
        self,
        shop: str,
        api_version: str,
        tokens: TokenSource,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        self._url = f"https://{shop}/admin/api/{api_version}/graphql.json"
        self._tokens = tokens
        self._http = http or httpx.Client(
            timeout=15.0,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> Result:
        response = self._http.post(
            self._url,
            json={"query": query, "variables": variables or {}},
            headers={"X-Shopify-Access-Token": self._tokens.get()},
        )
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise GraphQLError(body["errors"])
        return Result(body["data"], _parse_cost(body))

    def paginate(
        self,
        query: str,
        root_field: str,
        variables: dict[str, Any] | None = None,
        page_size: int = 50,
    ) -> Iterator[dict[str, Any]]:
        cursor: str | None = None
        while True:
            variables_page = {**(variables or {}), "first": page_size, "after": cursor}
            connection = self.execute(query, variables_page).data[root_field]
            yield from connection["nodes"]
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                return
            cursor = page_info["endCursor"]

from __future__ import annotations

import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import truststore
from pydantic import SecretStr


class ShopifyAuthError(Exception):
    """Error de autenticación. Nunca incluye el client_secret en el
    mensaje."""


@dataclass(frozen=True)
class AccessToken:
    value: str
    scopes: tuple[str, ...]
    expires_at: float  # segundos desde epoch

    def is_fresh(self, now: float, margin: float) -> bool:
        return now < self.expires_at - margin


class ClientCredentialsTokenProvider:
    def __init__(
        self,
        shop: str,
        client_id: str,
        client_secret: SecretStr,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        margin: float = 300.0,
    ) -> None:
        self._url = f"https://{shop}/admin/oauth/access_token"
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(
            timeout=10.0,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )
        self._clock = clock
        self._margin = margin
        self._lock = threading.Lock()
        self._token: AccessToken | None = None

    def get(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is None or not self._token.is_fresh(now, self._margin):
                self._token = self._fetch(now)
            return self._token.value

    def _fetch(self, now: float) -> AccessToken:
        response = self._http.post(
            self._url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            raise ShopifyAuthError(f"token request failed: HTTP {response.status_code}")
        body = response.json()
        scopes = tuple(s for s in body.get("scope", "").split(",") if s)
        return AccessToken(body["access_token"], scopes, now + int(body["expires_in"]))
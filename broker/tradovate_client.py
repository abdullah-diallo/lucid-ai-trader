"""
broker/tradovate_client.py
==========================
Thin REST client for the Tradovate API.
Handles authentication, token refresh, order placement, and position queries.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    pass


class TradovateClient:
    """
    Wraps the Tradovate REST API.

    Tokens last ~90 minutes. This client re-authenticates automatically
    60 seconds before expiry so no request ever hits an expired token.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        app_id: str = "lucid-ai-trader",
        app_version: str = "1.0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.app_id = app_id
        self.app_version = app_version
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _authenticate(self) -> None:
        body = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "cid": self.client_id,
            "sec": self.client_secret,
            "deviceId": "lucid-ai-trader-device",
        }
        resp = self._raw_request("POST", "/v1/auth/accesstokenrequest", body, authenticated=False)
        token = resp.get("accessToken")
        if not token:
            raise AuthenticationError(f"No accessToken in auth response: {resp}")
        self._access_token = token
        expiry_str = resp.get("expirationTime", "")
        try:
            expiry_dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            self._token_expires_at = expiry_dt.timestamp() - 60
        except (ValueError, AttributeError):
            self._token_expires_at = time.time() + 5100  # 85-minute fallback
        logger.info("Tradovate authenticated. Token valid until %s.", expiry_str)

    def _ensure_authenticated(self) -> None:
        if self._access_token is None or time.time() >= self._token_expires_at:
            self._authenticate()

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _raw_request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
        authenticated: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if authenticated and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode()
            logger.error("Tradovate %s %s → HTTP %s: %s", method, path, exc.code, error_body)
            raise

    def _request(self, method: str, path: str, body: Optional[Dict] = None) -> Any:
        self._ensure_authenticated()
        return self._raw_request(method, path, body, authenticated=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_accounts(self) -> List[Dict]:
        result = self._request("GET", "/v1/account/list")
        return result if isinstance(result, list) else []

    def get_positions(self) -> List[Dict]:
        result = self._request("GET", "/v1/position/list")
        return result if isinstance(result, list) else []

    def place_order(
        self,
        account_id: int,
        account_spec: str,
        symbol: str,
        action: str,
        qty: int = 1,
    ) -> Dict:
        """
        Place a market order.
        action must be "Buy" or "Sell".
        """
        return self._request("POST", "/v1/order/placeorder", {
            "accountSpec": account_spec,
            "accountId": account_id,
            "action": action,
            "symbol": symbol,
            "orderQty": qty,
            "orderType": "Market",
            "isAutomated": True,
        })

    def liquidate_position(self, position_id: int) -> Dict:
        return self._request("POST", "/v1/order/liquidateposition", {
            "positions": [position_id],
            "admin": False,
        })

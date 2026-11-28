import os
import unittest
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

from backend.app.main import require_local_api_token
from backend.app.schemas import ManualPositionRequest, ManualCloseRequest


class ApiSecurityTests(unittest.IsolatedAsyncioTestCase):
    def request(self, path="/api/dashboard", host="127.0.0.1", headers=None):
        return Request({"type": "http", "method": "GET", "path": path, "headers": [
            (key.lower().encode(), value.encode()) for key, value in (headers or {}).items()
        ], "client": (host, 9000), "server": ("127.0.0.1", 8000), "scheme": "http", "query_string": b""})

    async def next_response(self, request):
        return Response(status_code=200)

    async def test_api_is_restricted_to_loopback(self):
        response = await require_local_api_token(self.request(host="192.0.2.20"), self.next_response)
        self.assertEqual(response.status_code, 403)

    async def test_dashboard_requires_configured_token(self):
        with patch.dict(os.environ, {"PKSCREENER_API_TOKEN": "test-secret"}):
            denied = await require_local_api_token(self.request(), self.next_response)
            allowed = await require_local_api_token(
                self.request(headers={"Authorization": "Bearer test-secret"}), self.next_response
            )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    async def test_api_fails_closed_when_token_is_not_configured(self):
        with patch.dict(os.environ):
            os.environ.pop("PKSCREENER_API_TOKEN", None)
            response = await require_local_api_token(self.request(), self.next_response)
        self.assertEqual(response.status_code, 503)

    async def test_health_is_loopback_only_and_does_not_need_token(self):
        local = await require_local_api_token(self.request(path="/api/health"), self.next_response)
        remote = await require_local_api_token(self.request(path="/api/health", host="192.0.2.20"), self.next_response)
        self.assertEqual(local.status_code, 200)
        self.assertEqual(remote.status_code, 403)

    def test_manual_trade_schemas_reject_non_finite_prices(self):
        with self.assertRaises(ValueError):
            ManualPositionRequest(symbol="ABC", quantity=1, entry_price=float("nan"),
                                  stop_loss=1, opened_on="2026-11-27", manual_recorded=True)
        with self.assertRaises(ValueError):
            ManualCloseRequest(exit_price=float("inf"), closed_on="2026-11-27", manual_confirmation=True)


if __name__ == "__main__":
    unittest.main()

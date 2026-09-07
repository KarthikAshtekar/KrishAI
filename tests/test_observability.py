import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module

app = app_module.app


class ObservabilityTests(unittest.TestCase):
    def test_response_propagates_valid_request_id_and_security_headers(self) -> None:
        with TestClient(app) as client:
            response = client.get("/healthz", headers={"X-Request-ID": "request_test-42"})

        self.assertEqual(200, response.status_code)
        self.assertEqual("request_test-42", response.headers["x-request-id"])
        self.assertEqual("nosniff", response.headers["x-content-type-options"])
        self.assertEqual("DENY", response.headers["x-frame-options"])
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])

    def test_untrusted_request_id_is_replaced(self) -> None:
        with TestClient(app) as client:
            response = client.get("/healthz", headers={"X-Request-ID": "invalid request id"})
        self.assertNotEqual("invalid request id", response.headers["x-request-id"])
        self.assertLessEqual(len(response.headers["x-request-id"]), 64)

    def test_request_log_is_structured_and_does_not_include_authorization(self) -> None:
        with self.assertLogs("krishi.request", level="INFO") as captured, TestClient(app) as client:
            response = client.get("/healthz", headers={"Authorization": "Bearer do-not-log-this"})

        self.assertEqual(200, response.status_code)
        self.assertIn("http_request_completed", captured.output[-1])
        self.assertIn("/healthz", captured.output[-1])
        self.assertNotIn("do-not-log-this", captured.output[-1])

    def test_readiness_reports_healthy_dependencies(self) -> None:
        with (
            patch("app.database_is_ready", return_value=True),
            patch.object(
                app_module.model_service,
                "readiness_status",
                return_value={"ready": True, "components": {}},
            ),
            TestClient(app) as client,
        ):
            response = client.get("/readyz")
        self.assertEqual(200, response.status_code)
        self.assertEqual("ready", response.json()["status"])

    def test_readiness_fails_when_database_is_unavailable(self) -> None:
        with patch("app.database_is_ready", return_value=False), TestClient(app) as client:
            response = client.get("/readyz")
        self.assertEqual(503, response.status_code)
        self.assertFalse(response.json()["checks"]["database"])


if __name__ == "__main__":
    unittest.main()

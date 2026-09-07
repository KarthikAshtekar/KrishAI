import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app import app, clean_thingspeak_feed
from config import AppSettings, get_settings
from decision_engine import answer_farmer_question


class ReviewRegressionTests(unittest.TestCase):
    def tearDown(self):
        app.dependency_overrides.clear()

    def test_sensor_numbers_are_json_safe(self):
        feed = clean_thingspeak_feed({"field1": "NaN", "field2": "Infinity", "field4": "-Infinity"})
        self.assertIsNone(feed["temperature"])
        self.assertIsNone(feed["humidity"])
        self.assertIsNone(feed["light_intensity"])

    def test_irrigation_assistant_does_not_reassure_with_missing_or_stale_data(self):
        for code in ["no_sensor_data", "stale_sensor_data"]:
            with self.subTest(code=code):
                result = answer_farmer_question("Should I irrigate?", {}, {
                    "alerts": [{"code": code, "message": "Readings need verification"}],
                    "latest_reading": None,
                })
                self.assertEqual(result["confidence"], "Low")
                self.assertIn("verify", result["recommended_action"].lower())
                self.assertNotIn("No urgent irrigation alert", result["answer"])

    def test_sudden_moisture_change_does_not_imply_irrigation_is_needed(self):
        result = answer_farmer_question("Should I irrigate?", {}, {
            "latest_reading": {"soil_moisture": 55},
            "alerts": [{"code": "sudden_moisture_change", "message": "Moisture changed", "recommended_action": "Inspect"}],
        })
        self.assertNotIn("Yes, irrigation", result["answer"])

    def test_malformed_sensor_payload_returns_gateway_error(self):
        for payload in ({"feeds": None}, {"feeds": "invalid"}, [1, 2]):
            with self.subTest(payload=payload), TestClient(app) as client:
                with patch("app.requests.get", return_value=Mock(json=Mock(return_value=payload))):
                    response = client.get("/api/data")
                self.assertEqual(response.status_code, 502)

    def test_invalid_sensor_json_returns_gateway_error(self):
        with TestClient(app) as client:
            with patch("app.requests.get", return_value=Mock(json=Mock(side_effect=ValueError("private upstream")))):
                response = client.get("/api/data")
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("private upstream", response.text)

    def test_malformed_rows_are_skipped_and_alerts_share_sensor_snapshot(self):
        payload = {"feeds": [None, 3, {"created_at": "2026-09-07T00:00:00Z", "field1": "28"}]}
        with TestClient(app) as client:
            with patch("app.requests.get", return_value=Mock(json=Mock(return_value=payload))) as upstream:
                response = client.get("/api/data")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["feeds"]), 1)
            self.assertIn("anomalies", response.json())
            upstream.assert_called_once()

    def test_browser_auth_redirect_preserves_destination_and_api_stays_json(self):
        app.dependency_overrides[get_settings] = lambda: AppSettings(
            app_env="test", auth_mode="firebase", firebase_project_id="test-project"
        )
        with TestClient(app) as client:
            response = client.get("/farmer-dashboard", headers={"Accept": "text/html"}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/login?next=%2Ffarmer-dashboard")
            response = client.get("/api/data", headers={"Accept": "text/html"})
            self.assertEqual(response.status_code, 401)
            self.assertIn("detail", response.json())

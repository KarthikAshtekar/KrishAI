import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app, model_service


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint_is_available(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_crop_form_rejects_invalid_ph(self):
        response = self.client.post(
            "/api/crop-recommendation",
            data={
                "nitrogen": 70,
                "phosphorus": 45,
                "potassium": 40,
                "temperature": 28,
                "humidity": 70,
                "ph": 15,
                "rainfall": 120,
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_fertilizer_json_works_without_moisture(self):
        response = self.client.post(
            "/api/fertilizer-recommendation",
            json={
                "temperature": 28,
                "humidity": 70,
                "nitrogen": 70,
                "phosphorous": 45,
                "potassium": 40,
                "soil_type": "Loamy",
                "crop_type": "Maize",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("recommended_fertilizer", response.json())

    def test_internal_model_error_is_not_exposed(self):
        internal_message = "synthetic internal model path detail"
        with patch.object(model_service, "predict_crop", side_effect=RuntimeError(internal_message)):
            response = self.client.post(
                "/api/crop-recommendation",
                data={
                    "nitrogen": 70,
                    "phosphorus": 45,
                    "potassium": 40,
                    "temperature": 28,
                    "humidity": 70,
                    "ph": 6.6,
                    "rainfall": 120,
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(internal_message, response.text)
        self.assertEqual(response.json()["detail"], "Crop recommendation is temporarily unavailable")


if __name__ == "__main__":
    unittest.main()

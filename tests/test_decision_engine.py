import unittest
from datetime import datetime, timezone

from decision_engine import answer_farmer_question, build_decision_card, detect_iot_anomalies


class DecisionEngineTests(unittest.TestCase):
    def test_low_soil_moisture_creates_warning_alert(self):
        report = detect_iot_anomalies(
            [
                {
                    "created_at": "2026-07-06T10:00:00+00:00",
                    "field1": 30,
                    "field2": 62,
                    "field3": 22,
                    "field4": 600,
                }
            ],
            now=datetime(2026, 7, 6, 10, 5, tzinfo=timezone.utc),
        )
        codes = {alert["code"] for alert in report["alerts"]}
        self.assertIn("low_moisture", codes)

    def test_decision_card_returns_required_fields(self):
        card = build_decision_card(
            crop_result={
                "recommended_crop": "Maize",
                "explanation": {"basis": "model-based"},
            },
            fertilizer_result={
                "recommended_fertilizer": "Urea",
                "explanation": {"basis": "model-based"},
            },
            price_result={
                "crop": "MAIZE",
                "outlook": "Favourable",
                "recommended_action": "Prepare buyer outreach.",
                "explanation": {"basis": "demo-rule-based"},
            },
            sensor_feeds=[
                {
                    "created_at": "2026-07-06T10:00:00+00:00",
                    "field1": 29,
                    "field2": 70,
                    "field3": 45,
                    "field4": 700,
                }
            ],
        )
        self.assertEqual(card["recommended_crop"], "Maize")
        self.assertEqual(card["fertilizer_recommendation"], "Urea")
        self.assertIn(card["risk_level"], {"Low", "Moderate", "High"})
        self.assertTrue(card["workflow_alerts"])

    def test_assistant_unknown_question_uses_safe_fallback(self):
        result = answer_farmer_question("tell me a joke", {}, {"alerts": []})
        self.assertEqual(result["basis"], "safe fallback")
        self.assertIn("do not have enough context", result["answer"])


if __name__ == "__main__":
    unittest.main()

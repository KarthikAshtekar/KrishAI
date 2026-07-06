import unittest
from datetime import datetime, timezone

from decision_engine import (
    answer_farmer_question,
    build_decision_card,
    build_workflow_alerts,
    detect_iot_anomalies,
    sample_community_summary,
    sample_marketplace_listings,
)


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
        self.assertIn("explanation_trust", card)
        self.assertIn("automation_log", card)

    def test_explanation_cards_have_trust_fields(self):
        card = build_decision_card(
            crop_result={
                "recommended_crop": "Maize",
                "explanation": {
                    "basis": "model-based",
                    "why": "Model selected Maize.",
                    "main_factors": ["Nitrogen is moderate"],
                    "positive_factors": ["Nutrients are usable"],
                    "risk_factors": [],
                    "confidence": "Moderate",
                    "data_source": "test model",
                },
            },
            fertilizer_result=None,
            price_result=None,
            sensor_feeds=[],
        )
        first = card["explanation_trust"][0]
        for field in ["title", "basis", "main_factors", "positive_factors", "risk_factors", "confidence", "data_source"]:
            self.assertIn(field, first)

    def test_assistant_known_crop_intent_returns_structured_response(self):
        card = build_decision_card(
            crop_result={
                "recommended_crop": "Maize",
                "explanation": {
                    "basis": "model-based",
                    "why": "Model selected Maize.",
                    "main_factors": ["Nitrogen is moderate"],
                    "data_source": "test model",
                },
            },
            fertilizer_result=None,
            price_result=None,
            sensor_feeds=[],
        )
        result = answer_farmer_question("Which crop should I grow?", card, {"alerts": card["alerts"]})
        self.assertEqual(result["intent"], "crop_recommendation")
        self.assertIn("answer", result)
        self.assertIn("recommended_action", result)
        self.assertIn("data_used", result)

    def test_assistant_unknown_question_uses_safe_fallback(self):
        result = answer_farmer_question("tell me a joke", {}, {"alerts": []})
        self.assertEqual(result["basis"], "safe fallback")
        self.assertEqual(result["intent"], "unknown")
        self.assertIn("do not have enough context", result["answer"])

    def test_critical_heat_alert_sets_high_severity(self):
        report = detect_iot_anomalies(
            [
                {
                    "created_at": "2026-07-06T10:00:00+00:00",
                    "field1": 43,
                    "field2": 50,
                    "field3": 40,
                    "field4": 900,
                }
            ],
            now=datetime(2026, 7, 6, 10, 5, tzinfo=timezone.utc),
        )
        self.assertTrue(any(alert["severity"] == "Critical" for alert in report["alerts"]))

    def test_workflow_alert_structure(self):
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
        workflows = build_workflow_alerts(report["alerts"])
        required = {"trigger", "condition", "severity", "stakeholder_affected", "recommended_action", "data_source", "timestamp", "status"}
        self.assertTrue(required.issubset(workflows[0].keys()))

    def test_marketplace_demo_data_generation(self):
        listings = sample_marketplace_listings()
        self.assertGreaterEqual(len(listings), 1)
        self.assertIn("match_score", listings[0])
        self.assertEqual(listings[0]["status"], "Demo data")

    def test_community_dashboard_data_generation(self):
        summary = sample_community_summary()
        self.assertIn("total_farmers_monitored", summary)
        self.assertIn("expected_supply_by_crop", summary)
        self.assertEqual(summary["status"], "Demo data")


if __name__ == "__main__":
    unittest.main()

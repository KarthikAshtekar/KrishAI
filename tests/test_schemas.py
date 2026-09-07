import unittest

from pydantic import ValidationError

from schemas import (
    AssistantInput,
    CropRecommendationInput,
    FertilizerInput,
    PricePredictionInput,
)


class InputSchemaTests(unittest.TestCase):
    def test_crop_input_rejects_invalid_ph(self):
        with self.assertRaises(ValidationError):
            CropRecommendationInput(
                nitrogen=70,
                phosphorus=45,
                potassium=40,
                temperature=28,
                humidity=70,
                ph=15,
                rainfall=120,
            )

    def test_fertilizer_input_rejects_humidity_over_100(self):
        with self.assertRaises(ValidationError):
            FertilizerInput(
                temperature=28,
                humidity=101,
                nitrogen=70,
                phosphorous=45,
                potassium=40,
                soil_type="Loamy",
                crop_type="Maize",
            )

    def test_price_input_rejects_invalid_month(self):
        with self.assertRaises(ValidationError):
            PricePredictionInput(crop="MAIZE", month=13, year=2026)

    def test_assistant_rejects_blank_question(self):
        with self.assertRaises(ValidationError):
            AssistantInput(question="   ")

    def test_json_contract_rejects_unknown_fields(self):
        with self.assertRaises(ValidationError):
            FertilizerInput(
                temperature=28,
                humidity=70,
                nitrogen=70,
                phosphorous=45,
                potassium=40,
                soil_type="Loamy",
                crop_type="Maize",
                unexpected="not allowed",
            )


if __name__ == "__main__":
    unittest.main()

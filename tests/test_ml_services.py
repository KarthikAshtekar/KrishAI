import unittest

from ml_services import KrishiModelService


class _Encoder:
    def transform(self, values):
        return [0 for _ in values]

    def inverse_transform(self, values):
        return ["Urea" for _ in values]


class _FertilizerModel:
    def predict(self, feature_frame):
        self.feature_frame = feature_frame.copy()
        return [0]


class FertilizerServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(KrishiModelService)
        self.service.fertilizer_model = _FertilizerModel()
        self.service.soil_type_encoder = _Encoder()
        self.service.crop_type_encoder = _Encoder()
        self.service.fertilizer_encoder = _Encoder()
        self.input_data = {
            "temperature": 28,
            "humidity": 70,
            "nitrogen": 70,
            "phosphorous": 45,
            "potassium": 40,
            "soil_type": "Loamy",
            "crop_type": "Maize",
        }

    def test_missing_moisture_uses_documented_default(self):
        result = self.service.predict_fertilizer(self.input_data)

        moisture = self.service.fertilizer_model.feature_frame.loc[0, "Moisture"]
        self.assertEqual(moisture, 45.0)
        self.assertEqual(result["inputs"]["moisture"], 45.0)
        self.assertIn("45", result["assumptions"][0])

    def test_explicit_none_moisture_uses_documented_default(self):
        result = self.service.predict_fertilizer({**self.input_data, "moisture": None})

        moisture = self.service.fertilizer_model.feature_frame.loc[0, "Moisture"]
        self.assertEqual(moisture, 45.0)
        self.assertEqual(result["inputs"]["moisture"], 45.0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "Jupyter files"


VALID_SOIL_TYPES = ["Black", "Clayey", "Loamy", "Red", "Sandy"]
VALID_CROP_TYPES = [
    "Barley",
    "Cotton",
    "Ground Nuts",
    "Maize",
    "Millets",
    "Oil seeds",
    "Paddy",
    "Pulses",
    "Sugarcane",
    "Tobacco",
    "Wheat",
    "coffee",
    "kidneybeans",
    "orange",
    "pomegranate",
    "rice",
    "watermelon",
]


def load_model(model_path: Path) -> Any | None:
    try:
        if model_path.suffix == ".joblib":
            return joblib.load(model_path)
        with model_path.open("rb") as file_obj:
            return pickle.load(file_obj)
    except Exception as exc:  # noqa: BLE001 - serialization libraries raise heterogeneous errors
        print(f"Error loading model {model_path}: {exc}")
        return None


def _match_known_value(value: str, known_values: list[str], field_name: str) -> str:
    if value in known_values:
        return value
    value_lower = value.strip().lower()
    for item in known_values:
        if item.lower() == value_lower:
            return item
    raise ValueError(f"Invalid {field_name}. Must be one of: {', '.join(known_values)}")


def _nutrient_status(value: float, name: str) -> str:
    if value < 35:
        return f"{name} is low"
    if value > 90:
        return f"{name} is high"
    return f"{name} is in a moderate range"


def _crop_explanation(inputs: dict[str, float], prediction: str) -> dict[str, Any]:
    factors = [
        _nutrient_status(inputs["nitrogen"], "Nitrogen"),
        _nutrient_status(inputs["phosphorus"], "Phosphorus"),
        _nutrient_status(inputs["potassium"], "Potassium"),
        f"pH is {inputs['ph']:.1f}",
        f"Temperature is {inputs['temperature']:.1f} C",
        f"Rainfall is {inputs['rainfall']:.1f} mm",
    ]
    positive_factors = [
        factor
        for factor in factors
        if "moderate" in factor.lower() or "pH is" in factor or "Temperature" in factor
    ]
    risk_factors = [factor for factor in factors if "low" in factor.lower() or "high" in factor.lower()]
    return {
        "basis": "model-based",
        "main_factors": factors,
        "positive_factors": positive_factors or ["Input values were accepted by the trained crop model."],
        "risk_factors": risk_factors or ["No major rule-level nutrient imbalance was detected."],
        "confidence": "Moderate",
        "reliability_label": "Model-based recommendation; no SHAP/probability explanation is configured yet.",
        "data_source": "User-entered soil nutrients, pH, temperature, humidity, rainfall, and saved crop model",
        "why": (
            f"The Random Forest crop model selected {prediction} from soil nutrients, "
            "temperature, humidity, pH, and rainfall."
        ),
        "what_would_change": (
            "Large changes in N/P/K levels, rainfall, pH, or heat/humidity conditions "
            "could change the model's crop ranking."
        ),
    }


def _fertilizer_explanation(inputs: dict[str, Any], prediction: str) -> dict[str, Any]:
    factors = [
        _nutrient_status(float(inputs["nitrogen"]), "Nitrogen"),
        _nutrient_status(float(inputs["phosphorous"]), "Phosphorous"),
        _nutrient_status(float(inputs["potassium"]), "Potassium"),
        f"Soil type is {inputs['soil_type']}",
        f"Crop type is {inputs['crop_type']}",
    ]
    risk_factors = [factor for factor in factors if "low" in factor.lower() or "high" in factor.lower()]
    return {
        "basis": "model-based",
        "main_factors": factors,
        "positive_factors": [
            f"Soil type and crop type are both supported: {inputs['soil_type']} / {inputs['crop_type']}",
        ],
        "risk_factors": risk_factors or ["No major rule-level nutrient imbalance was detected."],
        "confidence": "Moderate",
        "reliability_label": "Model-based recommendation using saved encoders; moisture defaults to 45 if not supplied.",
        "data_source": "User-entered N/P/K, soil type, crop type, weather inputs, and saved fertilizer model",
        "why": (
            f"The fertilizer classifier recommends {prediction} using nutrient levels, "
            "soil type, crop type, temperature, humidity, and a default moisture value."
        ),
        "what_would_change": (
            "A soil test showing different N/P/K levels, a different crop, or a real "
            "soil-moisture reading could change the recommendation."
        ),
    }


class KrishiModelService:
    def __init__(self) -> None:
        self.crop_model = load_model(MODELS_DIR / "Crop_recommendation_model.pkl")
        self.fertilizer_model = load_model(MODELS_DIR / "Fertilizer_recommendation.pkl")
        self.soil_type_encoder = load_model(MODELS_DIR / "soil_type_encoder.joblib")
        self.crop_type_encoder = load_model(MODELS_DIR / "crop_type_encoder.joblib")
        self.fertilizer_encoder = load_model(MODELS_DIR / "fertilizer_encoder.joblib")
        self.crop_price_data = self._load_crop_price_data()

    def readiness_status(self) -> dict[str, Any]:
        components = {
            "crop_model_loaded": self.crop_model is not None,
            "fertilizer_model_loaded": self.fertilizer_model is not None,
            "soil_encoder_loaded": self.soil_type_encoder is not None,
            "crop_encoder_loaded": self.crop_type_encoder is not None,
            "fertilizer_encoder_loaded": self.fertilizer_encoder is not None,
            "price_reference_loaded": not self.crop_price_data.empty,
        }
        return {
            "ready": all(components.values()),
            "components": components,
            "artifact_runtime": "scikit-learn 1.6.1",
            "validation_status": "Loaded successfully; predictive quality was not revalidated without held-out data.",
            "price_path": "Transparent lookup/rule fallback; unused legacy XGBoost pickle is not loaded.",
        }

    def _load_crop_price_data(self) -> pd.DataFrame:
        try:
            data = pd.read_csv(DATA_DIR / "Crop_Price.csv")
            data["Crop"] = data["Crop"].astype(str).str.strip().str.upper()
            return data
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            print(f"Error loading crop price data: {exc}")
            return pd.DataFrame()

    @property
    def available_price_crops(self) -> list[str]:
        if self.crop_price_data.empty or "Crop" not in self.crop_price_data:
            return []
        return sorted(self.crop_price_data["Crop"].dropna().unique().tolist())

    def predict_crop(
        self,
        nitrogen: float,
        phosphorus: float,
        potassium: float,
        temperature: float,
        humidity: float,
        ph: float,
        rainfall: float,
    ) -> dict[str, Any]:
        if self.crop_model is None:
            raise RuntimeError("Crop recommendation model is not loaded")

        inputs = {
            "nitrogen": float(nitrogen),
            "phosphorus": float(phosphorus),
            "potassium": float(potassium),
            "temperature": float(temperature),
            "humidity": float(humidity),
            "ph": float(ph),
            "rainfall": float(rainfall),
        }
        feature_frame = pd.DataFrame(
            [
                {
                    "Nitrogen": inputs["nitrogen"],
                    "Phosphorus": inputs["phosphorus"],
                    "Potassium": inputs["potassium"],
                    "Temperature": inputs["temperature"],
                    "Humidity": inputs["humidity"],
                    "pH_Value": inputs["ph"],
                    "Rainfall": inputs["rainfall"],
                }
            ]
        )
        prediction = str(self.crop_model.predict(feature_frame)[0])
        explanation = _crop_explanation(inputs, prediction)
        return {
            "recommended_crop": prediction,
            "explanation": explanation,
            "inputs": inputs,
        }

    def predict_fertilizer(self, input_data: dict[str, Any]) -> dict[str, Any]:
        missing = [
            name
            for name in (
                "temperature",
                "humidity",
                "nitrogen",
                "phosphorous",
                "potassium",
                "soil_type",
                "crop_type",
            )
            if name not in input_data
        ]
        if missing:
            raise ValueError(f"Missing fields: {', '.join(missing)}")
        if self.fertilizer_model is None:
            raise RuntimeError("Fertilizer recommendation model is not loaded")
        if not all([self.soil_type_encoder, self.crop_type_encoder, self.fertilizer_encoder]):
            raise RuntimeError("Fertilizer encoders are not loaded")

        soil_type = _match_known_value(str(input_data["soil_type"]), VALID_SOIL_TYPES, "soil type")
        crop_type = _match_known_value(str(input_data["crop_type"]), VALID_CROP_TYPES, "crop type")
        moisture = input_data.get("moisture")
        if moisture is None:
            moisture = 45
        normalized = {
            "temperature": float(input_data["temperature"]),
            "humidity": float(input_data["humidity"]),
            "moisture": float(moisture),
            "nitrogen": float(input_data["nitrogen"]),
            "phosphorous": float(input_data["phosphorous"]),
            "potassium": float(input_data["potassium"]),
            "soil_type": soil_type,
            "crop_type": crop_type,
        }

        feature_frame = pd.DataFrame(
            [
                {
                    "Temperature": normalized["temperature"],
                    "Humidity": normalized["humidity"],
                    "Moisture": normalized["moisture"],
                    "Soil Type": soil_type,
                    "Crop Type": crop_type,
                    "Nitrogen": normalized["nitrogen"],
                    "Potassium": normalized["potassium"],
                    "Phosphorous": normalized["phosphorous"],
                }
            ]
        )
        feature_frame["Soil Type"] = self.soil_type_encoder.transform(feature_frame["Soil Type"])
        feature_frame["Crop Type"] = self.crop_type_encoder.transform(feature_frame["Crop Type"])

        encoded_prediction = self.fertilizer_model.predict(feature_frame)
        fertilizer = str(self.fertilizer_encoder.inverse_transform(encoded_prediction)[0])
        explanation = _fertilizer_explanation(normalized, fertilizer)
        return {
            "recommended_fertilizer": fertilizer,
            "explanation": explanation,
            "inputs": normalized,
            "assumptions": ["Soil moisture is set to 45 because the form does not collect it."],
        }

    def predict_price(self, crop: str, month: int, year: int) -> dict[str, Any]:
        if self.crop_price_data.empty:
            raise RuntimeError("Crop price reference data is not available")
        if not 1 <= int(month) <= 12:
            raise ValueError("Month must be between 1 and 12")
        if int(year) < 2023:
            raise ValueError("Year must be 2023 or later")

        crop_key = crop.strip().upper()
        crop_rows = self.crop_price_data[self.crop_price_data["Crop"] == crop_key]
        if crop_rows.empty:
            raise ValueError(f"Crop '{crop}' was not found in the price dataset")

        avg_price = float(crop_rows["Price"].mean())
        min_price = float(crop_rows["Price"].min())
        max_price = float(crop_rows["Price"].max())
        seasonal_factors = {
            1: 1.04,
            2: 1.03,
            3: 1.01,
            4: 0.99,
            5: 0.97,
            6: 0.96,
            7: 0.98,
            8: 1.00,
            9: 1.02,
            10: 1.05,
            11: 1.06,
            12: 1.05,
        }
        month_factor = seasonal_factors[int(month)]
        year_factor = 1 + max(0, int(year) - 2023) * 0.04
        predicted_price = avg_price * month_factor * year_factor

        ratio = predicted_price / avg_price if avg_price else 1
        if ratio >= 1.08:
            outlook = "Favourable"
            action = "Consider preparing for sale if quality and buyer demand are confirmed."
        elif ratio <= 0.96:
            outlook = "Weak"
            action = "Consider holding stock only if storage cost and spoilage risk are manageable."
        else:
            outlook = "Stable"
            action = "Monitor market movement and compare local buyer quotes before selling."

        return {
            "crop": crop_key,
            "month": int(month),
            "year": int(year),
            "predicted_price": float(predicted_price),
            "average_reference_price": avg_price,
            "historical_min_price": min_price,
            "historical_max_price": max_price,
            "outlook": outlook,
            "recommended_action": action,
            "explanation": {
                "basis": "demo-rule-based",
                "main_factors": [
                    f"Historical average price for {crop_key}",
                    f"Transparent seasonal factor for month {month}",
                    f"Simple year uplift factor for {year}",
                ],
                "positive_factors": [
                    f"Reference price data exists for {crop_key}.",
                    f"Outlook category is {outlook}.",
                ],
                "risk_factors": [
                    "The fitted encoder/scaler used during XGBoost training was not saved.",
                    "Local market quotes, storage costs, and quality grades are not included.",
                ],
                "confidence": "Low",
                "reliability_label": "Demo fallback; not a true model inference.",
                "data_source": "Crop_Price.csv reference data and transparent seasonal/year factors",
                "why": (
                    "The saved XGBoost model requires engineered, one-hot encoded, and "
                    "scaled features, but the repo does not include the fitted encoder "
                    "and scaler. This endpoint therefore uses a transparent prototype "
                    "fallback instead of feeding the model the wrong format."
                ),
                "what_would_change": (
                    "Saving the full training pipeline or collecting state, production, "
                    "yield, weather, and cost features would allow a real model-based "
                    "price prediction."
                ),
            },
            "model_used": False,
        }

    def disease_status(self) -> dict[str, Any]:
        model_path = MODELS_DIR / "crop_disease_model.keras"
        model_present = model_path.exists()
        return {
            "available": False,
            "model_file_present": model_present,
            "disease": "Disease inference not enabled",
            "confidence": None,
            "description": (
                "A crop disease model file is present, but this repo does not include "
                "the class-label metadata and validated TensorFlow inference wiring "
                "needed for trustworthy disease detection. The random demo prediction "
                "has been disabled."
            )
            if model_present
            else "No configured disease inference model is available.",
            "treatments": [
                "Use the image as a record for expert review.",
                "Consult a local agriculture officer or agronomist for diagnosis.",
                "Add class labels and validated preprocessing before enabling model inference.",
            ],
            "explanation": {
                "basis": "prototype-disabled",
                "main_factors": ["Model metadata is incomplete", "Random prediction is disabled"],
                "positive_factors": ["The app avoids unsafe random disease labels."],
                "risk_factors": ["Class labels and validated TensorFlow preprocessing are missing."],
                "confidence": "Unavailable",
                "reliability_label": "Disabled prototype until model metadata is validated.",
                "data_source": "Uploaded image metadata only; no disease inference is performed.",
                "why": "The platform avoids presenting unvalidated random labels as real AI output.",
                "what_would_change": "Validated class labels, preprocessing, and test images would enable real inference.",
            },
        }

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ShortLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Percentage = Annotated[float, Field(ge=0, le=100)]
NutrientValue = Annotated[float, Field(ge=0, le=500)]
TemperatureC = Annotated[float, Field(ge=-20, le=70)]


class StrictInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FertilizerInput(StrictInputModel):
    temperature: TemperatureC
    humidity: Percentage
    nitrogen: NutrientValue
    phosphorous: NutrientValue
    potassium: NutrientValue
    soil_type: ShortLabel
    crop_type: ShortLabel
    moisture: Percentage | None = None


class CropRecommendationInput(StrictInputModel):
    nitrogen: NutrientValue
    phosphorus: NutrientValue
    potassium: NutrientValue
    temperature: TemperatureC
    humidity: Percentage
    ph: Annotated[float, Field(ge=0, le=14)]
    rainfall: Annotated[float, Field(ge=0, le=10_000)]


class PricePredictionInput(StrictInputModel):
    crop: ShortLabel
    month: Annotated[int, Field(ge=1, le=12)]
    year: Annotated[int, Field(ge=2023, le=2100)]


class DecisionCardInput(StrictInputModel):
    crop_inputs: CropRecommendationInput | None = None
    fertilizer_inputs: FertilizerInput | None = None
    price_inputs: PricePredictionInput | None = None
    farmer_profile: dict[str, Any] | None = None


class AssistantInput(StrictInputModel):
    question: Annotated[NonEmptyText, StringConstraints(max_length=1_000)]

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import create_firebase_session, new_csrf_token, validate_csrf
from config import AppSettings, get_settings
from decision_engine import (
    answer_farmer_question,
    build_decision_card,
    detect_iot_anomalies,
    sample_community_summary,
    sample_marketplace_listings,
)
from ml_services import VALID_CROP_TYPES, VALID_SOIL_TYPES, KrishiModelService
from schemas import (
    AssistantInput,
    CropRecommendationInput,
    DecisionCardInput,
    FertilizerInput,
    FirebaseSessionInput,
    PricePredictionInput,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

load_dotenv(BASE_DIR / ".env")
APPLICATION_SETTINGS = get_settings()
STATIC_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Krishi Connect Decision Intelligence Platform",
    description="Agricultural decision intelligence APIs for recommendations, IoT alerts, and workflow cards.",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
model_service = KrishiModelService()

THINGSPEAK_CHANNEL_ID = os.getenv("THINGSPEAK_CHANNEL_ID", "2914283")
THINGSPEAK_READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY", "")
THINGSPEAK_RESULTS = int(os.getenv("THINGSPEAK_RESULTS", "10"))

LAST_DECISION_CARD: dict[str, Any] | None = None


def _binary_status(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"on", "1", "true", "yes"}:
            return "on"
        if normalized in {"off", "0", "false", "no"}:
            return "off"
        return normalized
    try:
        return "on" if float(value) > 0 else "off"
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_thingspeak_feed(feed: dict[str, Any]) -> dict[str, Any]:
    field4_numeric = _safe_float(feed.get("field4"))
    pump_status = _binary_status(feed.get("field5"))
    cleaned = {
        "created_at": feed.get("created_at"),
        "field1": _safe_float(feed.get("field1")),
        "field2": _safe_float(feed.get("field2")),
        "field3": _safe_float(feed.get("field3")),
        "field4": field4_numeric if field4_numeric is not None else feed.get("field4"),
        "field5": pump_status,
        "temperature": _safe_float(feed.get("field1")),
        "humidity": _safe_float(feed.get("field2")),
        "soil_moisture": _safe_float(feed.get("field3")),
        "light_intensity": field4_numeric,
        "rain_status": None if field4_numeric is not None else _binary_status(feed.get("field4")),
        "pump_status": pump_status,
    }
    return cleaned


def fetch_sensor_feeds(results: int = THINGSPEAK_RESULTS) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"results": results}
    if THINGSPEAK_READ_API_KEY:
        params["api_key"] = THINGSPEAK_READ_API_KEY
    url = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
    except requests.Timeout as exc:
        raise HTTPException(status_code=504, detail="Timeout while fetching data from ThingSpeak") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Error fetching data from ThingSpeak: {exc}") from exc

    payload = response.json()
    feeds = payload.get("feeds", []) if isinstance(payload, dict) else []
    return [clean_thingspeak_feed(feed) for feed in feeds if feed.get("created_at")]


def safe_sensor_feeds() -> list[dict[str, Any]]:
    try:
        return fetch_sensor_feeds()
    except HTTPException as exc:
        print(f"Sensor fetch failed, continuing with unavailable sensor state: {exc}")
        return []


def default_decision_payload() -> DecisionCardInput:
    now = datetime.now(UTC)
    month = now.month
    year = max(now.year, 2023)
    return DecisionCardInput(
        crop_inputs=CropRecommendationInput(
            nitrogen=70,
            phosphorus=45,
            potassium=40,
            temperature=28,
            humidity=70,
            ph=6.6,
            rainfall=120,
        ),
        fertilizer_inputs=FertilizerInput(
            temperature=28,
            humidity=70,
            nitrogen=70,
            phosphorous=45,
            potassium=40,
            soil_type="Loamy",
            crop_type="Maize",
        ),
        price_inputs=PricePredictionInput(crop="MAIZE", month=month, year=year),
        farmer_profile={
            "profile_mode": "demo sample profile",
            "note": "Submit POST /api/decision-card with farm inputs for a field-specific card.",
        },
    )


def create_decision_card(payload: DecisionCardInput | None = None) -> dict[str, Any]:
    global LAST_DECISION_CARD
    payload = payload or default_decision_payload()
    sensor_feeds = safe_sensor_feeds()

    crop_result = None
    fertilizer_result = None
    price_result = None
    errors: list[str] = []

    if payload.crop_inputs:
        try:
            crop_result = model_service.predict_crop(**payload.crop_inputs.model_dump())
        except (RuntimeError, TypeError, ValueError):
            errors.append("Crop recommendation unavailable")

    if payload.fertilizer_inputs:
        try:
            fertilizer_result = model_service.predict_fertilizer(payload.fertilizer_inputs.model_dump())
        except (RuntimeError, TypeError, ValueError):
            errors.append("Fertilizer recommendation unavailable")

    if payload.price_inputs:
        try:
            price_result = model_service.predict_price(**payload.price_inputs.model_dump())
        except (RuntimeError, TypeError, ValueError):
            errors.append("Price outlook unavailable")

    decision_card = build_decision_card(
        crop_result=crop_result,
        fertilizer_result=fertilizer_result,
        price_result=price_result,
        sensor_feeds=sensor_feeds,
        farmer_profile=payload.farmer_profile,
        marketplace_matches=sample_marketplace_listings(),
    )
    decision_card["input_mode"] = (payload.farmer_profile or {}).get("profile_mode", "user supplied inputs")
    decision_card["errors"] = errors
    LAST_DECISION_CARD = decision_card
    return decision_card


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "available_crops": model_service.available_price_crops,
            "valid_soil_types": VALID_SOIL_TYPES,
            "valid_crop_types": VALID_CROP_TYPES,
        },
    )


@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    return {"status": "ok", "service": "krishi-connect"}


@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request, settings: Annotated[AppSettings, Depends(get_settings)]):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "auth_mode": settings.auth_mode,
            "firebase_config": {
                "apiKey": settings.firebase_web_api_key,
                "authDomain": settings.firebase_auth_domain,
                "projectId": settings.firebase_project_id,
            },
        },
    )


@app.get("/api/auth/csrf", response_class=JSONResponse)
async def get_auth_csrf(settings: Annotated[AppSettings, Depends(get_settings)]):
    token = new_csrf_token()
    response = JSONResponse({"csrf_token": token})
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=10 * 60,
        path="/",
    )
    return response


@app.post("/api/auth/session", response_class=JSONResponse)
async def create_auth_session(
    payload: FirebaseSessionInput,
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
):
    if settings.auth_mode != "firebase":
        raise HTTPException(status_code=409, detail="Firebase authentication is not configured")
    validate_csrf(request, settings)
    cookie, claims = create_firebase_session(payload.id_token, settings=settings)
    response = JSONResponse({"status": "authenticated", "uid": claims.get("uid") or claims.get("sub")})
    response.set_cookie(
        settings.session_cookie_name,
        cookie,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_duration_days * 24 * 60 * 60,
        path="/",
    )
    return response


@app.post("/api/auth/logout", response_class=JSONResponse)
async def logout(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
):
    validate_csrf(request, settings)
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(settings.session_cookie_name, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(settings.csrf_cookie_name, path="/", secure=settings.cookie_secure, samesite="lax")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/decision-intelligence", response_class=HTMLResponse)
async def get_decision_intelligence(request: Request):
    return templates.TemplateResponse(request, "decision.html")


@app.get("/farmer-dashboard", response_class=HTMLResponse)
async def get_farmer_dashboard(request: Request):
    return templates.TemplateResponse(request, "farmer_dashboard.html")


@app.get("/marketplace", response_class=HTMLResponse)
async def get_marketplace(request: Request):
    return templates.TemplateResponse(request, "marketplace.html")


@app.get("/community-dashboard", response_class=HTMLResponse)
async def get_community_dashboard(request: Request):
    return templates.TemplateResponse(request, "community_dashboard.html")


@app.get("/disease-prediction", response_class=HTMLResponse)
async def get_disease_prediction(request: Request):
    return templates.TemplateResponse(request, "disease_prediction.html")


@app.get("/api/data", response_class=JSONResponse)
async def get_sensor_data():
    feeds = fetch_sensor_feeds()
    return {
        "feeds": feeds,
        "source": "ThingSpeak",
        "channel_id": THINGSPEAK_CHANNEL_ID,
        "api_key_configured": bool(THINGSPEAK_READ_API_KEY),
        "field_mapping": {
            "field1": "temperature",
            "field2": "humidity",
            "field3": "soil_moisture",
            "field4": "light_intensity",
            "field5": "pump_status",
        },
    }


@app.get("/api/iot/anomalies", response_class=JSONResponse)
async def get_iot_anomalies():
    feeds = safe_sensor_feeds()
    report = detect_iot_anomalies(feeds)
    report["source"] = "ThingSpeak" if feeds else "No live sensor data"
    return report


@app.post("/api/disease-prediction")
async def predict_disease(
    leafImage: Annotated[UploadFile, File()],
    cropType: Annotated[str, Form(min_length=1, max_length=80)],
):
    try:
        await leafImage.read()
        status = model_service.disease_status()
        status["crop_type"] = cropType
        status["uploaded_filename"] = leafImage.filename
        return status
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to process image metadata") from exc


@app.post("/api/crop-recommendation")
async def crop_recommendation(input_data: Annotated[CropRecommendationInput, Form()]):
    try:
        return model_service.predict_crop(**input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Crop recommendation is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate crop recommendation") from exc


@app.post("/api/fertilizer-recommendation")
async def fertilizer_recommendation(input_data: FertilizerInput):
    try:
        return model_service.predict_fertilizer(input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Fertilizer recommendation is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate fertilizer recommendation") from exc


@app.post("/api/crop-price-prediction")
async def crop_price_prediction(input_data: Annotated[PricePredictionInput, Form()]):
    try:
        return model_service.predict_price(**input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Crop price outlook is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate crop price outlook") from exc


@app.get("/api/decision-card", response_class=JSONResponse)
async def get_decision_card():
    return create_decision_card()


@app.post("/api/decision-card", response_class=JSONResponse)
async def post_decision_card(payload: DecisionCardInput):
    return create_decision_card(payload)


@app.get("/api/automation-log", response_class=JSONResponse)
async def get_automation_log():
    card = LAST_DECISION_CARD or create_decision_card()
    return {
        "status": "active",
        "source": "Decision card workflow automation",
        "automation_log": card.get("automation_log", []),
    }


@app.get("/api/marketplace/listings", response_class=JSONResponse)
async def get_marketplace_listings():
    return {
        "status": "Demo data",
        "limitations": "Marketplace listings are sample data until real buyer/farmer records are connected.",
        "listings": sample_marketplace_listings(),
    }


@app.get("/api/community/summary", response_class=JSONResponse)
async def get_community_summary():
    return sample_community_summary()


@app.post("/api/assistant", response_class=JSONResponse)
async def assistant(payload: AssistantInput):
    card = LAST_DECISION_CARD or create_decision_card()
    anomaly_report = detect_iot_anomalies(safe_sensor_feeds())
    return answer_farmer_question(payload.question, card, anomaly_report)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=True)

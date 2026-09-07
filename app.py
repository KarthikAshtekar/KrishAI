from __future__ import annotations

import math
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import Principal, create_firebase_session, get_current_principal, new_csrf_token, validate_csrf
from config import AppSettings, get_settings
from database import Base, database_is_ready, engine, get_db
from db_models import DecisionCardRecord
from decision_engine import (
    answer_farmer_question,
    build_decision_card,
    detect_iot_anomalies,
    sample_community_summary,
    sample_marketplace_listings,
)
from ml_services import VALID_CROP_TYPES, VALID_SOIL_TYPES, KrishiModelService
from observability import (
    application_logger,
    error_payload,
    request_observability_middleware,
    sanitize_validation_errors,
)
from repositories import (
    create_audit_event,
    create_decision_record,
    get_latest_decision_record,
    list_active_memberships,
    upsert_user_identity,
)
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if (
        APPLICATION_SETTINGS.auth_mode == "demo"
        and not APPLICATION_SETTINGS.is_deployed
        and APPLICATION_SETTINGS.database_url.startswith("sqlite")
    ):
        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Krishi Connect Decision Intelligence Platform",
    description="Agricultural decision intelligence APIs for recommendations, IoT alerts, and workflow cards.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["app_auth_mode"] = APPLICATION_SETTINGS.auth_mode
model_service = KrishiModelService()

THINGSPEAK_CHANNEL_ID = os.getenv("THINGSPEAK_CHANNEL_ID", "2914283")
THINGSPEAK_READ_API_KEY = os.getenv("THINGSPEAK_READ_API_KEY", "")
THINGSPEAK_RESULTS = int(os.getenv("THINGSPEAK_RESULTS", "10"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.middleware("http")
async def add_request_observability(request: Request, call_next):
    return await request_observability_middleware(
        request,
        call_next,
        deployed=APPLICATION_SETTINGS.is_deployed,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if (
        exc.status_code == 401
        and request.method == "GET"
        and not request.url.path.startswith("/api/")
        and "text/html" in request.headers.get("accept", "")
    ):
        return RedirectResponse(f"/login?next={quote(request.url.path, safe='')}", status_code=303)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            status_code=exc.status_code,
            detail=exc.detail,
            request_id=getattr(request.state, "request_id", None),
        ),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload(
            status_code=422,
            detail=jsonable_encoder(sanitize_validation_errors(exc.errors())),
            request_id=getattr(request.state, "request_id", None),
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception):
    application_logger.error(
        {
            "event": "unhandled_application_error",
            "request_id": getattr(request.state, "request_id", None),
            "error_type": type(_exc).__name__,
        }
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(
            status_code=500,
            detail="Internal server error",
            request_id=getattr(request.state, "request_id", None),
        ),
    )

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
        number = float(value)
        return number if math.isfinite(number) else None
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
        raise HTTPException(status_code=502, detail="Unable to fetch data from ThingSpeak") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid sensor response from ThingSpeak") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("feeds"), list):
        raise HTTPException(status_code=502, detail="Invalid sensor response from ThingSpeak")
    return [
        clean_thingspeak_feed(feed)
        for feed in payload["feeds"]
        if isinstance(feed, dict) and feed.get("created_at")
    ]


def safe_sensor_feeds() -> list[dict[str, Any]]:
    try:
        return fetch_sensor_feeds()
    except HTTPException as exc:
        application_logger.warning(
            {
                "event": "sensor_feed_unavailable",
                "upstream": "ThingSpeak",
                "status_code": exc.status_code,
            }
        )
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


def build_decision_result(payload: DecisionCardInput | None = None) -> dict[str, Any]:
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
    return decision_card


def persist_decision_card(
    payload: DecisionCardInput | None,
    *,
    session: Session,
    principal: Principal,
    request_id: str | None,
) -> dict[str, Any]:
    normalized_payload = payload or default_decision_payload()
    decision_card = build_decision_result(normalized_payload)
    record = create_decision_record(
        session,
        tenant_id=principal.tenant_id,
        created_by_user_id=principal.user_id,
        request_id=request_id,
        input_mode=decision_card["input_mode"],
        input_payload=normalized_payload.model_dump(mode="json"),
        result_payload=decision_card,
        model_versions={
            "crop": "bundled legacy pickle; runtime compatibility not revalidated",
            "fertilizer": "bundled legacy pickle; runtime compatibility not revalidated",
            "price": "demo lookup and rule-based outlook",
        },
    )
    create_audit_event(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        request_id=request_id,
        event_type="decision.created",
        resource_type="decision_card",
        resource_id=record.id,
        metadata={"input_mode": record.input_mode},
    )
    return serialize_decision_record(record)


def serialize_decision_record(record: DecisionCardRecord) -> dict[str, Any]:
    result = dict(record.result_payload)
    result.update(
        {
            "decision_id": record.id,
            "created_at": record.created_at.isoformat(),
            "input_mode": record.input_mode,
        }
    )
    return result


def latest_or_create_decision(
    *,
    session: Session,
    principal: Principal,
    request_id: str | None,
) -> dict[str, Any]:
    record = get_latest_decision_record(session, tenant_id=principal.tenant_id)
    if record is not None:
        return serialize_decision_record(record)
    return persist_decision_card(None, session=session, principal=principal, request_id=request_id)


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, _principal: Annotated[Principal, Depends(get_current_principal)]):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "available_crops": model_service.available_price_crops,
            "valid_soil_types": VALID_SOIL_TYPES,
            "valid_crop_types": VALID_CROP_TYPES,
            "current_year": datetime.now(UTC).year,
        },
    )


@app.get("/healthz", response_class=JSONResponse)
async def healthz():
    return {"status": "ok", "service": "krishi-connect"}


@app.get("/readyz", response_class=JSONResponse)
def readyz():
    database_ready = database_is_ready()
    model_status = model_service.readiness_status()
    ready = database_ready and model_status["ready"]
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not_ready",
            "checks": {"database": database_ready, "models": model_status},
        },
    )


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
def create_auth_session(
    payload: FirebaseSessionInput,
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
):
    if settings.auth_mode != "firebase":
        raise HTTPException(status_code=409, detail="Firebase authentication is not configured")
    validate_csrf(request, settings)
    cookie, claims = create_firebase_session(payload.id_token, settings=settings)
    identity_uid = str(claims.get("uid") or claims.get("sub") or "").strip()
    if not identity_uid:
        raise HTTPException(status_code=401, detail="Verified identity is missing a user ID")
    user = upsert_user_identity(
        session,
        firebase_uid=identity_uid,
        email=str(claims["email"]) if claims.get("email") else None,
        display_name=str(claims["name"]) if claims.get("name") else None,
    )
    memberships = list_active_memberships(session, user_id=user.id)
    if not memberships:
        raise HTTPException(status_code=403, detail="Tenant membership required")
    create_audit_event(
        session,
        tenant_id=memberships[0].tenant_id,
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        event_type="auth.session_created",
        metadata={"authentication_mode": "firebase"},
    )
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
def logout(
    request: Request,
    settings: Annotated[AppSettings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
):
    validate_csrf(request, settings)
    create_audit_event(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        event_type="auth.signed_out",
        metadata={"authentication_mode": principal.authentication_mode},
    )
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie(settings.session_cookie_name, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(settings.csrf_cookie_name, path="/", secure=settings.cookie_secure, samesite="lax")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, _principal: Annotated[Principal, Depends(get_current_principal)]):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/decision-intelligence", response_class=HTMLResponse)
async def get_decision_intelligence(
    request: Request,
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    return templates.TemplateResponse(request, "decision.html")


@app.get("/farmer-dashboard", response_class=HTMLResponse)
async def get_farmer_dashboard(
    request: Request,
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    return templates.TemplateResponse(request, "farmer_dashboard.html")


@app.get("/marketplace", response_class=HTMLResponse)
async def get_marketplace(request: Request, _principal: Annotated[Principal, Depends(get_current_principal)]):
    return templates.TemplateResponse(request, "marketplace.html")


@app.get("/community-dashboard", response_class=HTMLResponse)
async def get_community_dashboard(
    request: Request,
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    return templates.TemplateResponse(request, "community_dashboard.html")


@app.get("/disease-prediction", response_class=HTMLResponse)
async def get_disease_prediction(
    request: Request,
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    return templates.TemplateResponse(request, "disease_prediction.html")


@app.get("/api/data", response_class=JSONResponse)
def get_sensor_data(_principal: Annotated[Principal, Depends(get_current_principal)]):
    feeds = fetch_sensor_feeds()
    return {
        "feeds": feeds,
        "anomalies": detect_iot_anomalies(feeds),
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
def get_iot_anomalies(_principal: Annotated[Principal, Depends(get_current_principal)]):
    feeds = safe_sensor_feeds()
    report = detect_iot_anomalies(feeds)
    report["source"] = "ThingSpeak" if feeds else "No live sensor data"
    return report


@app.post("/api/disease-prediction")
async def predict_disease(
    leafImage: Annotated[UploadFile, File()],
    cropType: Annotated[str, Form(min_length=1, max_length=80)],
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    try:
        if leafImage.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are accepted")
        image_bytes = await leafImage.read(MAX_UPLOAD_BYTES + 1)
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image upload exceeds the 5 MB limit")
        status = model_service.disease_status()
        status["crop_type"] = cropType
        status["uploaded_filename"] = leafImage.filename
        return status
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to process image metadata") from exc


@app.post("/api/crop-recommendation")
def crop_recommendation(
    input_data: Annotated[CropRecommendationInput, Form()],
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    try:
        return model_service.predict_crop(**input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Crop recommendation is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate crop recommendation") from exc


@app.post("/api/fertilizer-recommendation")
def fertilizer_recommendation(
    input_data: FertilizerInput,
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    try:
        return model_service.predict_fertilizer(input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Fertilizer recommendation is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate fertilizer recommendation") from exc


@app.post("/api/crop-price-prediction")
def crop_price_prediction(
    input_data: Annotated[PricePredictionInput, Form()],
    _principal: Annotated[Principal, Depends(get_current_principal)],
):
    try:
        return model_service.predict_price(**input_data.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Crop price outlook is temporarily unavailable") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate crop price outlook") from exc


@app.get("/api/decision-card", response_class=JSONResponse)
def get_decision_card(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
):
    return latest_or_create_decision(
        session=session,
        principal=principal,
        request_id=getattr(request.state, "request_id", None),
    )


@app.post("/api/decision-card", response_class=JSONResponse)
def post_decision_card(
    payload: DecisionCardInput,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
):
    return persist_decision_card(
        payload,
        session=session,
        principal=principal,
        request_id=getattr(request.state, "request_id", None),
    )


@app.get("/api/automation-log", response_class=JSONResponse)
def get_automation_log(
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
):
    card = latest_or_create_decision(
        session=session,
        principal=principal,
        request_id=getattr(request.state, "request_id", None),
    )
    return {
        "status": "active",
        "source": "Decision card workflow automation",
        "automation_log": card.get("automation_log", []),
    }


@app.get("/api/marketplace/listings", response_class=JSONResponse)
async def get_marketplace_listings(_principal: Annotated[Principal, Depends(get_current_principal)]):
    return {
        "status": "Demo data",
        "limitations": "Marketplace listings are sample data until real buyer/farmer records are connected.",
        "listings": sample_marketplace_listings(),
    }


@app.get("/api/community/summary", response_class=JSONResponse)
async def get_community_summary(_principal: Annotated[Principal, Depends(get_current_principal)]):
    return sample_community_summary()


@app.post("/api/assistant", response_class=JSONResponse)
def assistant(
    payload: AssistantInput,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    principal: Annotated[Principal, Depends(get_current_principal)],
):
    card = latest_or_create_decision(
        session=session,
        principal=principal,
        request_id=getattr(request.state, "request_id", None),
    )
    anomaly_report = detect_iot_anomalies(safe_sensor_feeds())
    return answer_farmer_question(payload.question, card, anomaly_report)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=True)

from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request, Response

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_LOG_PATH_LENGTH = 300


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = dict(record.msg) if isinstance(record.msg, dict) else {"message": record.getMessage()}
        payload.setdefault("severity", record.levelname)
        payload.setdefault("timestamp", datetime.now(UTC).isoformat())
        payload.setdefault("logger", record.name)
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), default=str)


def configure_json_logger(name: str = "krishi.request") -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(getattr(handler, "_krishi_json_handler", False) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._krishi_json_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


request_logger = configure_json_logger()
application_logger = configure_json_logger("krishi.application")


def request_id_from_header(value: str | None) -> str:
    if value and REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return str(uuid4())


def apply_security_headers(response: Response, *, deployed: bool) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.gstatic.com; "
        "connect-src 'self' https://api.thingspeak.com https://identitytoolkit.googleapis.com "
        "https://securetoken.googleapis.com"
    )
    if deployed:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


async def request_observability_middleware(
    request: Request,
    call_next,
    *,
    deployed: bool,
) -> Response:
    request_id = request_id_from_header(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if "response" in locals():
            response.headers["X-Request-ID"] = request_id
            apply_security_headers(response, deployed=deployed)
        request_logger.info(
            {
                "event": "http_request_completed",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path[:MAX_LOG_PATH_LENGTH],
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
        )


def error_payload(*, status_code: int, detail: Any, request_id: str | None) -> dict[str, Any]:
    message = detail if isinstance(detail, str) else "Request validation failed"
    return {
        "detail": detail,
        "error": {"code": f"http_{status_code}", "message": message},
        "request_id": request_id,
    }


def sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for error in errors:
        sanitized.append({key: value for key, value in error.items() if key not in {"ctx", "input"}})
    return sanitized

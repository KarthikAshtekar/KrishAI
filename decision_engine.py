from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        normalized = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def normalize_sensor_reading(feed: dict[str, Any]) -> dict[str, Any]:
    temperature = _parse_float(feed.get("temperature", feed.get("field1")))
    humidity = _parse_float(feed.get("humidity", feed.get("field2")))
    soil_moisture = _parse_float(feed.get("soil_moisture", feed.get("field3")))
    light_intensity = _parse_float(feed.get("light_intensity", feed.get("field4")))
    created_at = feed.get("created_at")
    return {
        "created_at": created_at,
        "temperature": temperature,
        "humidity": humidity,
        "soil_moisture": soil_moisture,
        "light_intensity": light_intensity,
        "rain_status": feed.get("rain_status"),
        "pump_status": feed.get("pump_status", feed.get("field5")),
    }


def latest_sensor_reading(feeds: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not feeds:
        return None
    normalized = [normalize_sensor_reading(feed) for feed in feeds]
    return normalized[-1] if normalized else None


def _alert(
    code: str,
    severity: str,
    message: str,
    action: str,
    metric: str | None = None,
    value: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommended_action": action,
        "metric": metric,
        "value": value,
    }


def detect_iot_anomalies(
    feeds: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    readings = [normalize_sensor_reading(feed) for feed in feeds or []]
    alerts: list[dict[str, Any]] = []

    if not readings:
        alerts.append(
            _alert(
                "no_sensor_data",
                "Critical",
                "No IoT sensor data is available for decisioning.",
                "Check ThingSpeak configuration, connectivity, and sensor power.",
            )
        )
        return {
            "latest_reading": None,
            "alerts": alerts,
            "summary": "Sensor data unavailable",
        }

    latest = readings[-1]
    missing_metrics = [
        label
        for label, value in (
            ("temperature", latest["temperature"]),
            ("humidity", latest["humidity"]),
            ("soil moisture", latest["soil_moisture"]),
            ("light intensity", latest["light_intensity"]),
        )
        if value is None
    ]
    if missing_metrics:
        alerts.append(
            _alert(
                "missing_sensor_fields",
                "Warning",
                f"Latest sensor reading is missing: {', '.join(missing_metrics)}.",
                "Inspect sensor mapping and ThingSpeak field configuration.",
            )
        )

    moisture = latest["soil_moisture"]
    if moisture is not None:
        if moisture < 15:
            alerts.append(
                _alert(
                    "critical_low_moisture",
                    "Critical",
                    "Soil moisture is critically low.",
                    "Irrigate the field as soon as possible and verify pump status.",
                    "soil_moisture",
                    moisture,
                )
            )
        elif moisture < 30:
            alerts.append(
                _alert(
                    "low_moisture",
                    "Warning",
                    "Soil moisture is below the safe threshold.",
                    "Plan irrigation within 24-48 hours.",
                    "soil_moisture",
                    moisture,
                )
            )

    temperature = latest["temperature"]
    if temperature is not None:
        if temperature >= 42:
            alerts.append(
                _alert(
                    "critical_heat_stress",
                    "Critical",
                    "Temperature indicates severe heat stress risk.",
                    "Increase field monitoring, avoid spraying during peak heat, and protect sensitive crops.",
                    "temperature",
                    temperature,
                )
            )
        elif temperature >= 36:
            alerts.append(
                _alert(
                    "heat_stress",
                    "Warning",
                    "Temperature is high enough to create crop stress.",
                    "Monitor crop stress signs and adjust irrigation timing.",
                    "temperature",
                    temperature,
                )
            )

    humidity = latest["humidity"]
    if humidity is not None and temperature is not None:
        if humidity >= 80 and 20 <= temperature <= 32:
            alerts.append(
                _alert(
                    "disease_weather_risk",
                    "Warning",
                    "Humidity and temperature are favourable for disease pressure.",
                    "Inspect leaves and improve field ventilation/drainage where possible.",
                    "humidity",
                    humidity,
                )
            )

    if latest.get("created_at"):
        latest_time = _parse_datetime(latest["created_at"])
        if latest_time is not None:
            if latest_time.tzinfo is None:
                latest_time = latest_time.replace(tzinfo=timezone.utc)
            age_minutes = (now - latest_time.astimezone(timezone.utc)).total_seconds() / 60
            if age_minutes > 180:
                alerts.append(
                    _alert(
                        "stale_sensor_data",
                        "Warning",
                        f"Latest sensor reading is stale by about {age_minutes:.0f} minutes.",
                        "Confirm that the IoT device is publishing fresh readings.",
                    )
                )

    if len(readings) >= 2:
        previous = readings[-2]
        previous_moisture = previous["soil_moisture"]
        if moisture is not None and previous_moisture is not None and abs(moisture - previous_moisture) > 20:
            alerts.append(
                _alert(
                    "sudden_moisture_change",
                    "Info",
                    "Soil moisture changed sharply between the last two readings.",
                    "Check whether irrigation, rainfall, or sensor movement caused the change.",
                    "soil_moisture",
                    moisture,
                )
            )
        previous_temp = previous["temperature"]
        if temperature is not None and previous_temp is not None and abs(temperature - previous_temp) > 8:
            alerts.append(
                _alert(
                    "sudden_temperature_change",
                    "Info",
                    "Temperature changed sharply between the last two readings.",
                    "Validate the reading and inspect sensor placement.",
                    "temperature",
                    temperature,
                )
            )

    if not alerts:
        alerts.append(
            _alert(
                "normal_sensor_status",
                "Info",
                "No critical IoT anomalies were detected in the latest readings.",
                "Continue regular monitoring.",
            )
        )

    return {
        "latest_reading": latest,
        "alerts": alerts,
        "summary": summarize_alerts(alerts),
    }


def summarize_alerts(alerts: list[dict[str, Any]]) -> str:
    critical = sum(1 for alert in alerts if alert["severity"] == "Critical")
    warnings = sum(1 for alert in alerts if alert["severity"] == "Warning")
    if critical:
        return f"{critical} critical alert(s) need immediate action"
    if warnings:
        return f"{warnings} warning alert(s) need attention"
    return "No urgent sensor alerts"


def risk_level_from_alerts(alerts: list[dict[str, Any]]) -> str:
    if any(alert["severity"] == "Critical" for alert in alerts):
        return "High"
    warning_count = sum(1 for alert in alerts if alert["severity"] == "Warning")
    if warning_count >= 2:
        return "High"
    if warning_count == 1:
        return "Moderate"
    return "Low"


def build_workflow_alerts(
    anomaly_alerts: list[dict[str, Any]],
    price_result: dict[str, Any] | None = None,
    crop_name: str | None = None,
) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    for alert in anomaly_alerts:
        severity = alert["severity"]
        priority = "High" if severity == "Critical" else "Medium" if severity == "Warning" else "Low"
        workflows.append(
            {
                "trigger": alert["code"],
                "condition": alert["message"],
                "alert_message": alert["message"],
                "recommended_action": alert["recommended_action"],
                "priority": priority,
                "stakeholder": "Farmer",
            }
        )

    if price_result:
        outlook = price_result.get("outlook")
        if outlook == "Favourable":
            workflows.append(
                {
                    "trigger": "favourable_price_outlook",
                    "condition": f"{price_result.get('crop', crop_name or 'Crop')} price outlook is favourable.",
                    "alert_message": "Market conditions may support selling or buyer outreach.",
                    "recommended_action": price_result.get("recommended_action"),
                    "priority": "Medium",
                    "stakeholder": "Farmer / Buyer",
                }
            )
        elif outlook == "Weak":
            workflows.append(
                {
                    "trigger": "weak_price_outlook",
                    "condition": f"{price_result.get('crop', crop_name or 'Crop')} price outlook is weak.",
                    "alert_message": "Selling immediately may not be attractive unless storage risk is high.",
                    "recommended_action": price_result.get("recommended_action"),
                    "priority": "Low",
                    "stakeholder": "Farmer",
                }
            )

    return workflows


def build_decision_card(
    crop_result: dict[str, Any] | None,
    fertilizer_result: dict[str, Any] | None,
    price_result: dict[str, Any] | None,
    sensor_feeds: list[dict[str, Any]] | None,
    farmer_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    farmer_profile = farmer_profile or {}
    anomaly_report = detect_iot_anomalies(sensor_feeds)
    alerts = anomaly_report["alerts"]
    risk_level = risk_level_from_alerts(alerts)
    crop_name = (
        (crop_result or {}).get("recommended_crop")
        or farmer_profile.get("current_crop")
        or farmer_profile.get("preferred_crop")
        or "Not available"
    )
    fertilizer = (fertilizer_result or {}).get("recommended_fertilizer", "Not available")
    latest = anomaly_report.get("latest_reading") or {}
    moisture = latest.get("soil_moisture")
    moisture_status = "Unavailable"
    if moisture is not None:
        if moisture < 15:
            moisture_status = "Critical low"
        elif moisture < 30:
            moisture_status = "Low"
        elif moisture <= 65:
            moisture_status = "Adequate"
        else:
            moisture_status = "High"

    price_outlook = (price_result or {}).get("outlook", "Unavailable")
    buyer_suggestion = "Prototype buyer matching is not connected to live marketplace data."
    if price_outlook == "Favourable":
        buyer_suggestion = "Contact local buyer/FPO channels and compare quotes before sale."
    elif price_outlook == "Weak":
        buyer_suggestion = "Hold or aggregate produce only if storage risk is manageable."

    action_parts: list[str] = []
    if any(alert["code"] in {"critical_low_moisture", "low_moisture"} for alert in alerts):
        action_parts.append("prioritize irrigation")
    if any(alert["code"] in {"critical_heat_stress", "heat_stress"} for alert in alerts):
        action_parts.append("monitor heat stress")
    if price_outlook == "Favourable":
        action_parts.append("prepare market outreach")
    if not action_parts:
        action_parts.append("continue monitoring and validate recommendations with field conditions")

    final_action = "; ".join(action_parts).capitalize() + "."
    workflows = build_workflow_alerts(alerts, price_result, crop_name)
    explanation_bits = []
    if crop_result:
        explanation_bits.append(f"{crop_name} comes from the crop recommendation model.")
    if fertilizer_result:
        explanation_bits.append(f"{fertilizer} comes from the fertilizer recommendation model.")
    explanation_bits.append(f"IoT risk is {risk_level.lower()} because: {anomaly_report['summary']}.")
    if price_result:
        explanation_bits.append(
            f"Price outlook is {price_outlook.lower()} using a transparent demo fallback."
        )

    return {
        "recommended_crop": crop_name,
        "fertilizer_recommendation": fertilizer,
        "soil_moisture_status": moisture_status,
        "weather_rainfall_risk_status": risk_level,
        "price_outlook": price_outlook,
        "buyer_market_suggestion": buyer_suggestion,
        "risk_level": risk_level,
        "final_recommended_action": final_action,
        "explanation": " ".join(explanation_bits),
        "alerts": alerts,
        "workflow_alerts": workflows,
        "latest_sensor_reading": latest or None,
        "basis": {
            "crop": (crop_result or {}).get("explanation", {}).get("basis", "not available"),
            "fertilizer": (fertilizer_result or {}).get("explanation", {}).get("basis", "not available"),
            "price": (price_result or {}).get("explanation", {}).get("basis", "not available"),
            "iot_anomalies": "rule-based",
        },
        "stakeholders": {
            "farmer": "Use the card for crop, input, irrigation, and sell/hold decisions.",
            "buyer": "Use price outlook and crop signal as a prototype buyer-connect indicator.",
            "fpo_admin": "Use aggregated alerts to prioritize farms needing support.",
        },
    }


def answer_farmer_question(
    question: str,
    decision_card: dict[str, Any] | None,
    anomaly_report: dict[str, Any] | None,
) -> dict[str, Any]:
    text = (question or "").strip().lower()
    if not text:
        return {
            "answer": "Please ask a question about crop choice, fertilizer, irrigation, risk, price, or alerts.",
            "basis": "rule-based assistant",
        }

    card = decision_card or {}
    anomalies = anomaly_report or {"alerts": []}
    if any(keyword in text for keyword in ["crop", "grow", "plant"]):
        crop = card.get("recommended_crop")
        if crop and crop != "Not available":
            return {
                "answer": f"The current decision card recommends {crop}. {card.get('explanation', '')}",
                "basis": "latest decision card",
            }
        return {"answer": "I do not have enough crop-input data to recommend a crop yet.", "basis": "data unavailable"}

    if any(keyword in text for keyword in ["fertilizer", "npk", "nutrient"]):
        fertilizer = card.get("fertilizer_recommendation")
        if fertilizer and fertilizer != "Not available":
            return {
                "answer": f"The current fertilizer recommendation is {fertilizer}.",
                "basis": "latest decision card",
            }
        return {"answer": "I do not have enough fertilizer-input data yet.", "basis": "data unavailable"}

    if any(keyword in text for keyword in ["irrigate", "water", "moisture"]):
        alerts = anomalies.get("alerts", [])
        moisture_alerts = [alert for alert in alerts if "moisture" in alert.get("code", "")]
        if moisture_alerts:
            first = moisture_alerts[0]
            return {
                "answer": f"Yes, irrigation needs attention: {first['message']} {first['recommended_action']}",
                "basis": "rule-based IoT anomaly detection",
            }
        return {"answer": "No urgent irrigation alert is active in the latest sensor check.", "basis": "rule-based IoT anomaly detection"}

    if any(keyword in text for keyword in ["risk", "alert", "problem"]):
        risk = card.get("risk_level", "Unavailable")
        summary = ", ".join(alert["message"] for alert in anomalies.get("alerts", [])[:3])
        return {
            "answer": f"Current farm risk is {risk}. {summary or 'No alerts are available.'}",
            "basis": "latest anomaly report",
        }

    if any(keyword in text for keyword in ["sell", "price", "market", "wait"]):
        outlook = card.get("price_outlook", "Unavailable")
        suggestion = card.get("buyer_market_suggestion", "")
        return {
            "answer": f"Price outlook is {outlook}. {suggestion}",
            "basis": "latest decision card",
        }

    return {
        "answer": (
            "I can answer simple questions about crop choice, fertilizer, irrigation, "
            "farm risk, market price, and active alerts. I do not have enough context "
            "to answer that question safely."
        ),
        "basis": "safe fallback",
    }

from __future__ import annotations

from datetime import UTC, datetime
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
    data_source: str = "ThingSpeak IoT feed",
    stakeholder: str = "Farmer",
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommended_action": action,
        "metric": metric,
        "value": value,
        "trigger": code,
        "condition": message,
        "stakeholder_affected": stakeholder,
        "data_source": data_source,
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
        "status": "Open" if severity in {"Critical", "Warning"} else "Monitoring",
    }


def detect_iot_anomalies(
    feeds: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
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
    if humidity is not None and temperature is not None and humidity >= 80 and 20 <= temperature <= 32:
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
                latest_time = latest_time.replace(tzinfo=UTC)
            age_minutes = (now - latest_time.astimezone(UTC)).total_seconds() / 60
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


def _confidence_for_basis(basis: str) -> str:
    if basis == "model-based":
        return "Moderate"
    if "demo" in basis:
        return "Low"
    if "rule" in basis:
        return "Medium"
    if "disabled" in basis:
        return "Unavailable"
    return "Limited"


def _explanation_card(
    title: str,
    basis: str,
    why: str,
    main_factors: list[str],
    positive_factors: list[str] | None = None,
    risk_factors: list[str] | None = None,
    confidence: str | None = None,
    data_source: str = "Not available",
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "basis": basis,
        "why": why,
        "main_factors": main_factors,
        "positive_factors": positive_factors or [],
        "risk_factors": risk_factors or [],
        "confidence": confidence or _confidence_for_basis(basis),
        "reliability_label": confidence or _confidence_for_basis(basis),
        "data_source": data_source,
        "limitations": limitations or [],
    }


def _explanation_from_result(
    title: str,
    result: dict[str, Any] | None,
    fallback_why: str,
    fallback_basis: str = "not available",
) -> dict[str, Any]:
    explanation = (result or {}).get("explanation", {})
    return _explanation_card(
        title=title,
        basis=explanation.get("basis", fallback_basis),
        why=explanation.get("why", fallback_why),
        main_factors=explanation.get("main_factors", ["This information is not available yet."]),
        positive_factors=explanation.get("positive_factors", []),
        risk_factors=explanation.get("risk_factors", []),
        confidence=explanation.get("confidence"),
        data_source=explanation.get("data_source", "Not available"),
        limitations=[explanation.get("what_would_change", "")] if explanation.get("what_would_change") else [],
    )


def build_explanation_trust(
    crop_result: dict[str, Any] | None,
    fertilizer_result: dict[str, Any] | None,
    price_result: dict[str, Any] | None,
    risk_level: str,
    anomaly_report: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts = anomaly_report.get("alerts", [])
    risk_alerts = [alert for alert in alerts if alert["severity"] in {"Critical", "Warning"}]
    latest = anomaly_report.get("latest_reading") or {}
    moisture = latest.get("soil_moisture")
    temperature = latest.get("temperature")
    humidity = latest.get("humidity")

    cards = [
        _explanation_from_result(
            "Why this crop?",
            crop_result,
            "Crop recommendation inputs are not available yet.",
        ),
        _explanation_from_result(
            "Why this fertilizer?",
            fertilizer_result,
            "Fertilizer recommendation inputs are not available yet.",
        ),
        _explanation_card(
            title="Why this risk level?",
            basis="rule-based",
            why=f"Risk level is {risk_level} because {anomaly_report.get('summary', 'sensor status is unavailable')}.",
            main_factors=[
                f"Soil moisture: {moisture if moisture is not None else 'unavailable'}",
                f"Temperature: {temperature if temperature is not None else 'unavailable'}",
                f"Humidity: {humidity if humidity is not None else 'unavailable'}",
                f"Active warning/critical alerts: {len(risk_alerts)}",
            ],
            positive_factors=[
                alert["message"] for alert in alerts if alert["severity"] == "Info"
            ]
            or ["No positive sensor evidence is available yet."],
            risk_factors=[
                alert["message"] for alert in risk_alerts
            ]
            or ["No warning or critical sensor alerts are active."],
            confidence="Medium" if anomaly_report.get("latest_reading") else "Low",
            data_source="ThingSpeak IoT readings and rule-based thresholds",
            limitations=["Rules are transparent thresholds, not a calibrated crop-loss model."],
        ),
        _explanation_from_result(
            "Why this price/sell recommendation?",
            price_result,
            "Price outlook is unavailable until crop and date inputs are provided.",
            fallback_basis="demo-rule-based",
        ),
    ]
    return cards


def sample_marketplace_listings() -> list[dict[str, Any]]:
    return [
        {
            "farmer_name": "Ravi Patil",
            "village": "Sangli Cluster",
            "crop": "MAIZE",
            "expected_quantity": "18 quintals",
            "harvest_window": "Next 2-3 weeks",
            "quality_risk_label": "Good quality signal; verify moisture before pickup",
            "buyer_segment": "Local feed mill",
            "suggested_buyer_action": "Contact farmer group and confirm moisture/quality before pickup.",
            "match_score": 86,
            "suitability": "Strong match",
            "status": "Demo data",
        },
        {
            "farmer_name": "Meena Jadhav",
            "village": "Kolhapur North",
            "crop": "WHEAT",
            "expected_quantity": "11 quintals",
            "harvest_window": "4 weeks",
            "quality_risk_label": "Moderate risk; heat stress advisory active",
            "buyer_segment": "FPO aggregation center",
            "suggested_buyer_action": "Plan aggregation lot if quality checks pass.",
            "match_score": 74,
            "suitability": "Moderate match",
            "status": "Demo data",
        },
        {
            "farmer_name": "Asha More",
            "village": "Baramati East",
            "crop": "PADDY",
            "expected_quantity": "22 quintals",
            "harvest_window": "6 weeks",
            "quality_risk_label": "Storage planning needed before harvest",
            "buyer_segment": "Rice processor",
            "suggested_buyer_action": "Track harvest readiness and storage availability.",
            "match_score": 81,
            "suitability": "Strong match",
            "status": "Demo data",
        },
    ]


def sample_community_summary() -> dict[str, Any]:
    farmers = [
        {"village": "Sangli Cluster", "crop": "MAIZE", "moisture_risk": True, "heat_risk": False, "critical": False},
        {"village": "Kolhapur North", "crop": "WHEAT", "moisture_risk": True, "heat_risk": True, "critical": True},
        {"village": "Baramati East", "crop": "PADDY", "moisture_risk": False, "heat_risk": True, "critical": False},
        {"village": "Satara South", "crop": "MAIZE", "moisture_risk": True, "heat_risk": False, "critical": False},
        {"village": "Solapur West", "crop": "COTTON", "moisture_risk": True, "heat_risk": True, "critical": True},
    ]
    crop_counts: dict[str, int] = {}
    for farmer in farmers:
        crop_counts[farmer["crop"]] = crop_counts.get(farmer["crop"], 0) + 1

    low_moisture = sum(1 for farmer in farmers if farmer["moisture_risk"])
    heat_risk = sum(1 for farmer in farmers if farmer["heat_risk"])
    critical = sum(1 for farmer in farmers if farmer["critical"])
    return {
        "status": "Demo data",
        "total_farmers_monitored": len(farmers),
        "critical_alerts_count": critical,
        "farms_with_low_soil_moisture": low_moisture,
        "farms_under_heat_weather_risk": heat_risk,
        "most_recommended_crops": sorted(crop_counts.items(), key=lambda item: item[1], reverse=True),
        "expected_supply_by_crop": {
            "MAIZE": "34 quintals",
            "WHEAT": "11 quintals",
            "PADDY": "22 quintals",
            "COTTON": "9 quintals",
        },
        "suggested_community_actions": [
            f"{low_moisture} farms show low soil moisture risk; coordinate irrigation advisory within 24 hours.",
            f"{heat_risk} farms show heat/weather stress; issue crop protection guidance.",
            "Use demo marketplace matches to plan buyer outreach for MAIZE and PADDY clusters.",
        ],
        "community_decision_recommendations": [
            "Prioritize field calls for farms with critical moisture and heat alerts.",
            "Coordinate input and irrigation support for WHEAT and COTTON farms showing combined stress.",
            "Prepare MAIZE and PADDY aggregation plans using the prototype marketplace match signals.",
            "Treat crop, supply, and marketplace values as demo records until live farmer onboarding is complete.",
        ],
        "community_insight": (
            f"{low_moisture} farms show low soil moisture risk. FPO should coordinate irrigation "
            "advisory and input support in the next 24 hours."
        ),
        "farms": farmers,
    }


def build_workflow_alerts(
    anomaly_alerts: list[dict[str, Any]],
    price_result: dict[str, Any] | None = None,
    crop_name: str | None = None,
    marketplace_matches: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    workflows: list[dict[str, Any]] = []
    for alert in anomaly_alerts:
        severity = alert["severity"]
        priority = "High" if severity == "Critical" else "Medium" if severity == "Warning" else "Low"
        workflows.append(
            {
                "trigger": alert["code"],
                "condition": alert["message"],
                "severity": severity,
                "alert_message": alert["message"],
                "recommended_action": alert["recommended_action"],
                "priority": priority,
                "stakeholder": alert.get("stakeholder_affected", "Farmer"),
                "stakeholder_affected": alert.get("stakeholder_affected", "Farmer"),
                "data_source": alert.get("data_source", "ThingSpeak IoT feed"),
                "timestamp": alert.get("timestamp"),
                "status": alert.get("status", "Open"),
            }
        )

    if price_result:
        outlook = price_result.get("outlook")
        if outlook == "Favourable":
            workflows.append(
                {
                    "trigger": "favourable_price_outlook",
                    "condition": f"{price_result.get('crop', crop_name or 'Crop')} price outlook is favourable.",
                    "severity": "Warning",
                    "alert_message": "Market conditions may support selling or buyer outreach.",
                    "recommended_action": price_result.get("recommended_action"),
                    "priority": "Medium",
                    "stakeholder": "Farmer / Buyer",
                    "stakeholder_affected": "Farmer / Buyer",
                    "data_source": "Crop price reference data and demo price-outlook rules",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "Open",
                }
            )
        elif outlook == "Weak":
            workflows.append(
                {
                    "trigger": "weak_price_outlook",
                    "condition": f"{price_result.get('crop', crop_name or 'Crop')} price outlook is weak.",
                    "severity": "Info",
                    "alert_message": "Selling immediately may not be attractive unless storage risk is high.",
                    "recommended_action": price_result.get("recommended_action"),
                    "priority": "Low",
                    "stakeholder": "Farmer",
                    "stakeholder_affected": "Farmer",
                    "data_source": "Crop price reference data and demo price-outlook rules",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "Monitoring",
                }
            )

    for match in marketplace_matches or []:
        if match.get("match_score", 0) >= 80:
            workflows.append(
                {
                    "trigger": "buyer_demand_match",
                    "condition": f"Buyer demand matches {match['crop']} supply from {match['village']}.",
                    "severity": "Info",
                    "alert_message": f"{match['buyer_segment']} demand is a strong match for {match['crop']}.",
                    "recommended_action": match["suggested_buyer_action"],
                    "priority": "Medium",
                    "stakeholder": "Farmer / Buyer / FPO",
                    "stakeholder_affected": "Farmer / Buyer / FPO",
                    "data_source": "Demo marketplace sample data",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "status": "Monitoring",
                }
            )

    return workflows


def build_decision_card(
    crop_result: dict[str, Any] | None,
    fertilizer_result: dict[str, Any] | None,
    price_result: dict[str, Any] | None,
    sensor_feeds: list[dict[str, Any]] | None,
    farmer_profile: dict[str, Any] | None = None,
    marketplace_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    farmer_profile = farmer_profile or {}
    marketplace_matches = marketplace_matches if marketplace_matches is not None else sample_marketplace_listings()
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
    matching_crop = [
        listing for listing in marketplace_matches if str(listing.get("crop", "")).lower() == str(crop_name).lower()
    ]
    buyer_suggestion = "Prototype buyer matching is not connected to live marketplace data."
    if price_outlook == "Favourable":
        buyer_suggestion = "Contact local buyer/FPO channels and compare quotes before sale."
    elif price_outlook == "Weak":
        buyer_suggestion = "Hold or aggregate produce only if storage risk is manageable."
    if matching_crop:
        best_match = max(matching_crop, key=lambda listing: listing.get("match_score", 0))
        buyer_suggestion = (
            f"Demo buyer match: {best_match['buyer_segment']} for {best_match['crop']} "
            f"from {best_match['village']} ({best_match['suitability']})."
        )

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
    workflows = build_workflow_alerts(alerts, price_result, crop_name, marketplace_matches)
    explanation_trust = build_explanation_trust(
        crop_result,
        fertilizer_result,
        price_result,
        risk_level,
        anomaly_report,
    )
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
        "input_mode": "Latest prototype inputs, ThingSpeak readings, and labelled demo fallbacks",
        "final_recommended_action": final_action,
        "explanation": " ".join(explanation_bits),
        "alerts": alerts,
        "workflow_alerts": workflows,
        "automation_log": workflows,
        "explanation_trust": explanation_trust,
        "marketplace_matches": marketplace_matches,
        "latest_sensor_reading": latest or None,
        "basis": {
            "crop": (crop_result or {}).get("explanation", {}).get("basis", "not available"),
            "fertilizer": (fertilizer_result or {}).get("explanation", {}).get("basis", "not available"),
            "price": (price_result or {}).get("explanation", {}).get("basis", "not available"),
            "iot_anomalies": "rule-based",
        },
        "trust_summary": {
            "model_based": ["crop recommendation", "fertilizer recommendation"],
            "rule_based": ["IoT anomaly detection", "risk level", "workflow automation", "assistant intents"],
            "demo_based": ["price outlook fallback", "marketplace sample data", "community sample data"],
            "disabled_prototype": ["disease image inference"],
            "future_scope": "SHAP/model-level explanations can be added after stable model pipelines are saved.",
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
    def response(
        answer: str,
        intent: str,
        data_used: list[str],
        recommended_action: str,
        confidence: str,
        limitations: list[str] | None = None,
        basis: str | None = None,
    ) -> dict[str, Any]:
        return {
            "answer": answer,
            "intent": intent,
            "data_used": data_used,
            "recommended_action": recommended_action,
            "confidence": confidence,
            "limitations": limitations or [],
            "basis": basis or intent,
        }

    text = (question or "").strip().lower()
    if not text:
        return response(
            "Please ask a question about crop choice, fertilizer, irrigation, risk, price, today's actions, or alerts.",
            "empty_question",
            [],
            "Ask a specific farm decision question.",
            "High",
            ["No question text was provided."],
            "rule-based assistant",
        )

    card = decision_card or {}
    anomalies = anomaly_report or {"alerts": []}
    alerts = anomalies.get("alerts", card.get("alerts", []))
    workflows = card.get("workflow_alerts", card.get("automation_log", []))
    explanation_cards = {item.get("title"): item for item in card.get("explanation_trust", [])}

    if any(phrase in text for phrase in ["data based", "based on", "data is this", "source"]):
        trust = card.get("trust_summary", {})
        return response(
            (
                "This recommendation uses farm input forms, saved crop/fertilizer models, ThingSpeak IoT readings, "
                "rule-based anomaly thresholds, crop price reference data, and demo marketplace/community data where labelled."
            ),
            "data_source_explanation",
            ["decision_card.trust_summary", "explanation_trust"],
            "Review the Explanation & Trust section before acting.",
            "High",
            [f"Demo/future notes: {trust.get('future_scope', 'SHAP is future scope.')}"],
            "explanation and trust metadata",
        )

    if any(keyword in text for keyword in ["why", "explain"]) and any(keyword in text for keyword in ["crop", "grow", "plant"]):
        crop_explanation = explanation_cards.get("Why this crop?", {})
        why = crop_explanation.get("why", "This information is not available yet.")
        return response(
            why,
            "crop_explanation",
            [crop_explanation.get("data_source", "crop explanation unavailable")],
            "Use the crop recommendation with field validation.",
            crop_explanation.get("confidence", "Limited"),
            crop_explanation.get("limitations", []),
            crop_explanation.get("basis", "latest decision card"),
        )

    if any(keyword in text for keyword in ["crop", "grow", "plant"]):
        crop = card.get("recommended_crop")
        if crop and crop != "Not available":
            return response(
                f"The current decision card recommends {crop}. {card.get('explanation', '')}",
                "crop_recommendation",
                ["latest decision card", "crop recommendation model output"],
                f"Consider {crop} if field conditions and local agronomy advice agree.",
                "Moderate",
                ["Model probability/SHAP explanation is not configured."],
                "latest decision card",
            )
        return response(
            "This information is not available yet.",
            "crop_recommendation",
            [],
            "Enter crop recommendation inputs first.",
            "Low",
            ["Crop model output is missing from the latest decision card."],
            "data unavailable",
        )

    if any(keyword in text for keyword in ["fertilizer", "npk", "nutrient"]):
        fertilizer = card.get("fertilizer_recommendation")
        if fertilizer and fertilizer != "Not available":
            fert_explanation = explanation_cards.get("Why this fertilizer?", {})
            return response(
                f"The current fertilizer recommendation is {fertilizer}. {fert_explanation.get('why', '')}",
                "fertilizer_recommendation",
                [fert_explanation.get("data_source", "fertilizer model output")],
                f"Use {fertilizer} only after checking local soil-test guidance and dosage.",
                fert_explanation.get("confidence", "Moderate"),
                fert_explanation.get("limitations", []),
                fert_explanation.get("basis", "latest decision card"),
            )
        return response(
            "This information is not available yet.",
            "fertilizer_recommendation",
            [],
            "Enter fertilizer recommendation inputs first.",
            "Low",
            ["Fertilizer model output is missing from the latest decision card."],
            "data unavailable",
        )

    if any(keyword in text for keyword in ["irrigate", "water", "moisture"]):
        moisture_alerts = [alert for alert in alerts if "moisture" in alert.get("code", "")]
        if moisture_alerts:
            first = moisture_alerts[0]
            return response(
                f"Yes, irrigation needs attention: {first['message']} {first['recommended_action']}",
                "irrigation_advice",
                [first.get("data_source", "ThingSpeak IoT feed"), "soil moisture threshold rule"],
                first["recommended_action"],
                "Medium",
                ["Irrigation advice is rule-based and should be checked against field conditions."],
                "rule-based IoT anomaly detection",
            )
        return response(
            "No urgent irrigation alert is active in the latest sensor check.",
            "irrigation_advice",
            ["latest anomaly report"],
            "Continue monitoring soil moisture.",
            "Medium" if anomalies.get("latest_reading") else "Low",
            ["This information is not available yet." if not anomalies.get("latest_reading") else "No moisture alert was found."],
            "rule-based IoT anomaly detection",
        )

    if any(keyword in text for keyword in ["risk", "alert", "problem"]):
        risk = card.get("risk_level", "Unavailable")
        summary = ", ".join(alert["message"] for alert in anomalies.get("alerts", [])[:3])
        risk_card = explanation_cards.get("Why this risk level?", {})
        return response(
            f"Current farm risk is {risk}. {summary or 'No alerts are available.'} {risk_card.get('why', '')}",
            "risk_status",
            ["latest anomaly report", risk_card.get("data_source", "risk rule output")],
            card.get("final_recommended_action", "Review active alerts."),
            risk_card.get("confidence", "Limited"),
            risk_card.get("limitations", []),
            "latest anomaly report",
        )

    if any(keyword in text for keyword in ["sell", "price", "market", "wait"]):
        outlook = card.get("price_outlook", "Unavailable")
        suggestion = card.get("buyer_market_suggestion", "")
        price_card = explanation_cards.get("Why this price/sell recommendation?", {})
        return response(
            f"Price outlook is {outlook}. {suggestion}",
            "sell_or_wait",
            [price_card.get("data_source", "price outlook unavailable")],
            suggestion or "Compare local buyer quotes before selling.",
            price_card.get("confidence", "Low"),
            price_card.get("limitations", ["Price outlook is a demo fallback unless the full preprocessing pipeline is restored."]),
            price_card.get("basis", "latest decision card"),
        )

    if any(keyword in text for keyword in ["today", "do now", "action", "what should"]):
        actions = [workflow.get("recommended_action") for workflow in workflows[:3] if workflow.get("recommended_action")]
        action_text = " ".join(actions) if actions else card.get("final_recommended_action", "This information is not available yet.")
        return response(
            f"Today's recommended action: {action_text}",
            "today_action",
            ["automation log", "decision card"],
            action_text,
            "Medium" if actions else "Low",
            ["Workflow rules are rule-based and may require local judgement."],
            "workflow automation",
        )

    return response(
        (
            "I can answer simple questions about crop choice, fertilizer, irrigation, "
            "farm risk, market price, today's actions, data sources, and active alerts. "
            "I do not have enough context to answer that question safely."
        ),
        "unknown",
        [],
        "Ask about crop, fertilizer, irrigation, risk, price, alerts, actions, or data sources.",
        "High",
        ["The assistant is an intent-based prototype and does not use a generative model."],
        "safe fallback",
    )

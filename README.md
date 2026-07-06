# Krishi Connect - Agricultural Decision Intelligence Platform

Krishi Connect is an AI-powered agricultural decision intelligence prototype for farmers, buyers, FPOs/cooperatives, and local agriculture stakeholders. It connects farm inputs, IoT sensor data, saved ML models, transparent rule-based automation, market/sample buyer signals, and an intent-based assistant to support better rural decisions.

Tagline:

> Connecting farm data, AI models, IoT signals, and market intelligence for better rural decisions.

## Problem Statement Alignment

This project is aligned with the decision intelligence problem statement:

> Build an AI-powered Decision Intelligence Platform that leverages data, AI models, and intelligent automation to help individuals, communities, organizations, and city stakeholders analyze information, generate insights, predict outcomes, and make better decisions that improve everyday life and community well-being.

For this repo, the domain is agriculture and rural decision intelligence. The platform supports crop selection, fertilizer selection, irrigation urgency, risk monitoring, market readiness, buyer/FPO coordination, workflow alerts, and community-level prioritization.

## How This Project Satisfies The Decision Intelligence Platform Problem Statement

| Requirement | Implemented feature | Current status | Route or module |
| --- | --- | --- | --- |
| Data analysis | ThingSpeak sensor readings are cleaned, normalized, charted, and summarized. | Real if configured | `/dashboard`, `/api/data`, `app.py` |
| AI/ML predictions | Crop and fertilizer recommendations use saved Random Forest model artifacts. | Model-based | `/api/crop-recommendation`, `/api/fertilizer-recommendation`, `ml_services.py` |
| Pattern/anomaly detection | Low moisture, heat stress, disease-weather risk, missing/stale data, and sudden changes are detected. | Rule-based | `/api/iot/anomalies`, `decision_engine.py` |
| Natural-language assistance | Assistant answers crop, fertilizer, irrigation, risk, price, alerts, actions, and data-source questions. | Rule-based prototype | `/api/assistant`, `/decision-intelligence`, `/farmer-dashboard` |
| Recommendations | Farmer Decision Card combines model outputs, IoT alerts, price outlook, buyer suggestion, and final action. | MVP implemented | `/api/decision-card`, `/decision-intelligence` |
| Workflow automation | Alerts include trigger, condition, severity, stakeholder, source, timestamp, status, and action. | Rule-based MVP | `/api/automation-log`, `decision_engine.py` |
| Stakeholder decision support | Farmer, marketplace/buyer, and FPO/community dashboards are available. | Demo plus real card | `/farmer-dashboard`, `/marketplace`, `/community-dashboard` |
| Community well-being impact | Community demo highlights farms needing irrigation/heat support and suggests FPO actions. | Demo data | `/api/community/summary`, `/community-dashboard` |

## What Is Real vs Rule-Based vs Demo

- **Model-based:** crop recommendation and fertilizer recommendation use saved scikit-learn Random Forest artifacts and encoders.
- **Real-time if configured:** ThingSpeak IoT readings are fetched using environment variables.
- **Rule-based:** anomaly detection, risk level, workflow automation, audit trail, and assistant intent handling.
- **Demo fallback:** price outlook uses transparent assumptions because the saved XGBoost model's fitted preprocessing pipeline was not saved.
- **Demo data:** marketplace listings and community/FPO aggregation are sample data until real multi-farmer and buyer records are connected.
- **Disabled prototype:** disease image inference is disabled. A `.keras` file exists, but class labels and validated preprocessing/inference metadata are missing. Random disease labels are not used.

## Architecture

```text
Users / Stakeholders
    |
    +-- Farmer Dashboard
    +-- Buyer / Marketplace Dashboard
    +-- FPO / Community Dashboard
    +-- Recommendation Forms
    +-- IoT Monitoring
    |
    v
FastAPI app.py
    |
    +-- templates/
    |     +-- index.html                    Recommendation forms
    |     +-- decision.html                 Decision Card, trust layer, audit trail, assistant
    |     +-- dashboard.html                IoT charts and anomaly alerts
    |     +-- farmer_dashboard.html         Farmer operating view
    |     +-- marketplace.html              Demo buyer-connect view
    |     +-- community_dashboard.html      Demo FPO/community view
    |
    +-- ml_services.py
    |     +-- Crop recommendation wrapper
    |     +-- Fertilizer recommendation wrapper
    |     +-- Transparent price-outlook fallback
    |     +-- Disease feature status
    |     +-- Explanation metadata for model/demo outputs
    |
    +-- decision_engine.py
    |     +-- IoT anomaly detection
    |     +-- Explanation & Trust cards
    |     +-- Farmer Decision Card assembly
    |     +-- Workflow automation and audit log
    |     +-- Intent-based assistant
    |     +-- Demo marketplace and community data
    |
    +-- models/
    |     +-- Crop_recommendation_model.pkl
    |     +-- Fertilizer_recommendation.pkl
    |     +-- Crop_price_prediction_model.pkl
    |     +-- Label encoders
    |
    +-- Jupyter files/
          +-- Training notebooks and CSV reference data
```

## Pages

| Page | Purpose |
| --- | --- |
| `/` | Recommendation forms for crop, fertilizer, price outlook, and disease feature status |
| `/decision-intelligence` | Decision Card, Explanation & Trust, workflow automation, audit trail, assistant |
| `/dashboard` | ThingSpeak IoT charts and anomaly alert cards |
| `/farmer-dashboard` | Farmer-oriented action dashboard with alerts, recommendation summary, assistant |
| `/marketplace` | Demo buyer/marketplace dashboard with crop listings and match scores |
| `/community-dashboard` | Demo FPO/community dashboard with aggregate risk and supply insights |
| `/disease-prediction` | Disease feature status page, with inference disabled until metadata is validated |

## API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/crop-recommendation` | POST form | Model-based crop recommendation with explanation |
| `/api/fertilizer-recommendation` | POST JSON | Model-based fertilizer recommendation with explanation |
| `/api/crop-price-prediction` | POST form | Transparent demo price outlook |
| `/api/disease-prediction` | POST form | Disabled/prototype disease status |
| `/api/data` | GET | Latest ThingSpeak sensor readings |
| `/api/iot/anomalies` | GET | Rule-based anomaly report |
| `/api/decision-card` | GET | Demo Farmer Decision Card |
| `/api/decision-card` | POST JSON | Farmer Decision Card from supplied farm inputs |
| `/api/automation-log` | GET | Workflow automation and audit trail |
| `/api/assistant` | POST JSON | Structured intent-based assistant response |
| `/api/marketplace/listings` | GET | Demo marketplace listings |
| `/api/community/summary` | GET | Demo FPO/community summary |

## Explanation & Trust Layer

The Decision Card includes an `explanation_trust` array. Each card includes:

- Main factors considered
- Positive factors
- Risk factors
- Confidence / reliability label
- Data source
- Whether the output is model-based, rule-based, demo-based, or unavailable

SHAP/model-level explainability is future scope. The current implementation uses transparent explanation cards because the saved model artifacts do not include a stable explainability pipeline.

## Assistant Response Contract

`/api/assistant` returns:

```json
{
  "answer": "...",
  "intent": "crop_recommendation",
  "data_used": ["latest decision card"],
  "recommended_action": "...",
  "confidence": "Moderate",
  "limitations": ["..."],
  "basis": "latest decision card"
}
```

The assistant does not use paid APIs or generative model calls. If data is missing, it says that the information is not available yet.

## Environment Variables

Create a `.env` file from `.env.example`:

```powershell
copy .env.example .env
```

Configure:

```text
THINGSPEAK_CHANNEL_ID=2914283
THINGSPEAK_READ_API_KEY=your_thingspeak_read_api_key
THINGSPEAK_RESULTS=10
```

The ThingSpeak read key is not hardcoded in `app.py`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

Open:

```text
http://localhost:8000
```

Alternative:

```powershell
uvicorn app:app --reload
```

## Testing

Run:

```powershell
python -m unittest discover
python -m py_compile app.py ml_services.py decision_engine.py tests/test_decision_engine.py
```

## Limitations

- Price prediction is currently a transparent fallback/demo. Real model inference requires saving the full encoder/scaler/model preprocessing pipeline.
- Disease detection is disabled until class labels, preprocessing, TensorFlow dependency strategy, and validation images are added.
- Marketplace and community dashboards use sample data, clearly labelled as demo data.
- The assistant is an intent-based prototype and does not reason beyond available decision-card/anomaly/workflow data.
- Model artifacts may emit version-compatibility warnings when loaded with newer scikit-learn/XGBoost versions.

## Future Scope

- Save and serve a full crop price ML pipeline.
- Add validated disease model inference with class labels and tests.
- Store farmer profiles, plots, sensor devices, marketplace listings, and decision history in a database.
- Add authentication and role-specific access.
- Add SHAP or another model-level explanation method after stable pipelines are available.
- Replace demo marketplace/community data with real FPO, buyer, and farmer datasets.

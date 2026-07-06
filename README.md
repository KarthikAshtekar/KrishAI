# Krishi Connect - Agricultural Decision Intelligence Platform

Krishi Connect is an AI-powered agricultural decision intelligence prototype for farmers, buyers, FPOs/cooperatives, and local agriculture stakeholders. It combines farm inputs, IoT sensor data, ML recommendations, rule-based anomaly detection, workflow alerts, price-outlook logic, and a simple local assistant to support better farming and selling decisions.

## Problem Statement Alignment

This project is aligned with the decision intelligence problem statement:

> Build an AI-powered Decision Intelligence Platform that leverages data, AI models, and intelligent automation to help individuals, communities, organizations, and city stakeholders analyze information, generate insights, predict outcomes, and make better decisions that improve everyday life and community well-being.

For this repo, the domain is agriculture and rural decision intelligence. The platform focuses on decisions such as crop selection, fertilizer selection, irrigation urgency, market readiness, sensor-quality checks, and community/FPO support prioritization.

## What Is Implemented

| Capability | Current implementation | Status |
| --- | --- | --- |
| Data analysis | ThingSpeak sensor readings are cleaned and displayed on the IoT dashboard. | Real-time if ThingSpeak is configured |
| Prediction | Crop and fertilizer recommendations use saved scikit-learn Random Forest models. | Model-based |
| Price outlook | Uses crop price reference data with a transparent fallback formula. | Demo fallback |
| Recommendations | Farmer Decision Card combines crop, fertilizer, IoT risk, price outlook, and action guidance. | MVP implemented |
| Anomaly detection | Rule-based IoT alerts for low moisture, heat stress, disease-weather risk, sudden changes, missing/stale data. | Rule-based |
| Natural language Q&A | Intent-based local assistant answers simple questions from latest card/alerts. | Rule-based prototype |
| Workflow automation | Generates irrigation, heat, market, and sensor-quality workflow alerts. | Rule-based MVP |
| Stakeholder support | Farmer card plus buyer/FPO/community decision notes. | Prototype |

## Real vs Prototype

- **Real model-backed:** crop recommendation and fertilizer recommendation, subject to the quality and compatibility of the saved model artifacts.
- **Real IoT integration:** ThingSpeak API fetch is wired through environment variables. It works when the channel and key are valid.
- **Rule-based:** IoT anomaly detection, risk level, workflow alerts, and assistant intent handling.
- **Demo/prototype:** crop price outlook. The saved XGBoost model exists, but the fitted encoder/scaler/preprocessing pipeline was not saved. The app now avoids feeding it the wrong feature format and uses transparent assumptions instead.
- **Disabled prototype:** disease detection. A `.keras` file exists, but validated TensorFlow inference wiring and class-label metadata are missing. Random disease labels have been removed.

## Architecture

```text
User / Stakeholder
    |
    v
FastAPI app.py
    |
    +-- templates/
    |     +-- index.html              Recommendation forms
    |     +-- dashboard.html          IoT monitoring and alert cards
    |     +-- decision.html           Farmer Decision Card and assistant
    |
    +-- ml_services.py
    |     +-- Crop recommendation wrapper
    |     +-- Fertilizer recommendation wrapper
    |     +-- Transparent price-outlook fallback
    |     +-- Disease feature status
    |
    +-- decision_engine.py
    |     +-- IoT anomaly rules
    |     +-- Decision Card assembly
    |     +-- Workflow alerts
    |     +-- Intent-based assistant
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

- `/` - Recommendations page for crop, fertilizer, price outlook, and disease feature status.
- `/decision-intelligence` - Farmer Decision Card, alerts, workflow automation, stakeholder snapshot, and assistant.
- `/dashboard` - ThingSpeak IoT monitoring with sensor charts and anomaly alert cards.
- `/disease-prediction` - Standalone disease feature status page.

## API Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/crop-recommendation` | POST form | Model-based crop recommendation with explanation |
| `/api/fertilizer-recommendation` | POST JSON | Model-based fertilizer recommendation with explanation |
| `/api/crop-price-prediction` | POST form | Transparent demo price outlook |
| `/api/disease-prediction` | POST form | Returns disabled/prototype disease status |
| `/api/data` | GET | Latest ThingSpeak sensor readings |
| `/api/iot/anomalies` | GET | Rule-based sensor anomaly report |
| `/api/decision-card` | GET | Demo Farmer Decision Card |
| `/api/decision-card` | POST JSON | Farmer Decision Card from supplied farm inputs |
| `/api/assistant` | POST JSON | Simple natural-language assistant |

## Environment Variables

Create a `.env` file from `.env.example`:

```powershell
copy .env.example .env
```

Then configure:

```text
THINGSPEAK_CHANNEL_ID=2914283
THINGSPEAK_READ_API_KEY=your_thingspeak_read_api_key
THINGSPEAK_RESULTS=10
```

The app no longer hardcodes the ThingSpeak read key in `app.py`.

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

You can also run:

```powershell
uvicorn app:app --reload
```

## Decision Intelligence Flow

1. Farmer or stakeholder enters soil/crop/price inputs.
2. Crop and fertilizer wrappers call saved ML models where available.
3. ThingSpeak readings are fetched and normalized.
4. Rule-based anomaly detection checks moisture, heat, humidity, sudden changes, missing fields, and stale readings.
5. The Decision Card combines model outputs, sensor risk, price outlook, and workflow triggers.
6. The assistant answers simple questions using the latest card and alerts.

## Testing

Run:

```powershell
python -m unittest discover
python -m py_compile app.py ml_services.py decision_engine.py
```

## Limitations

- Price prediction is not a true model inference until the full preprocessing pipeline is reconstructed and saved.
- Disease detection is disabled until class labels, preprocessing, TensorFlow dependency strategy, and validation images are added.
- Stakeholder dashboards use prototype logic, not a real multi-farmer database.
- The assistant is intent-based and does not use paid APIs or generative LLM calls.
- Model artifacts may require compatible scikit-learn/XGBoost versions because they are loaded from pickle/joblib files.

## Future Scope

- Save and serve a full crop price scikit-learn/XGBoost pipeline with encoder and scaler.
- Add validated disease model inference with class labels and test images.
- Store farmer profiles, plots, sensor devices, and decision history in a database.
- Add buyer listings, FPO aggregation, and real marketplace matching.
- Add SHAP or another explainability method for model-backed recommendations.
- Add authentication and role-specific dashboards.
# KrishAI

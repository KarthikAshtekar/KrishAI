# Application review and responsive UI refresh

Reviewed on 7 September 2026, on branch `codex/app-ux-review`.

Krishi Connect is a server-rendered FastAPI application. This review fixes reproducible application and interface issues; it does not validate agronomic accuracy or activate cloud infrastructure.

## What is built

| Area | Implemented behavior | Evidence boundary |
| --- | --- | --- |
| Recommendations | Crop and fertilizer inference from saved scikit-learn models; validated form/JSON inputs and explanations | Real inference works locally. Holdout quality was not reassessed. |
| Price | Historical CSV reference prices with seasonal/year rules | A labelled sample outlook, not a live quote or restored XGBoost pipeline. |
| Decision overview / My farm | Tenant-scoped saved decision, alert rules, workflow and audit details, guided assistant | The initial plan uses sample inputs. Standalone recommendation forms do not update the saved plan. |
| Sensors | ThingSpeak adapter, normalized readings, charts and threshold alerts | Channel ownership, units and field mapping need verification for real use. The configured source can return old or implausible field readings. |
| Marketplace / community | Sample buyer matches, supply and risk summaries | Demonstration records; no live trading or outreach. |
| Authentication / storage | Firebase sessions, CSRF checks, tenant memberships, SQLAlchemy and Alembic | Demo mode works locally. Live Firebase and PostgreSQL were not exercised in this review. |
| Delivery | Docker, GitHub Actions, Cloud Build and GCP provisioning scripts | Python runtime compatibility corrected; Docker and cloud deployment were not run here. |
| Disease checks | Clear feature-status page and retained API contract | Inference stays disabled pending validated metadata and evaluation images. |

## Fixes

- Invalid ThingSpeak JSON/collection payloads return a controlled 502. Malformed rows are skipped and nonfinite numeric strings are normalized instead of breaking JSON responses.
- Browser authentication failures lead to sign-in; API clients retain JSON 401 responses. Sign-in restores an allowlisted destination. Firebase browser persistence is in memory, and the interface exposes server-session sign-out.
- Blocking model, readiness, session and logout handlers run through FastAPI's synchronous worker path instead of occupying the event loop.
- Irrigation indicators and assistant responses only treat low-moisture alerts as irrigation triggers. Missing/stale readings require verification; a sudden moisture change does not by itself mean watering is needed.
- Assistant input/output uses text nodes. Other dynamic card/market/community markup escapes inserted values.
- Requests have timeouts, readable errors and retry paths. Forms prevent concurrent submissions, keep entered values on failure, allow decimals, match API ranges, and avoid displaying a response for inputs changed while the request was running.
- Failed dashboard loads replace indefinite loading placeholders. Empty sensor responses clear old charts and table values.
- Sensor readings and alerts use a single snapshot/request. Each chart updates once per refresh. Polling waits for completion, pauses in hidden tabs and resumes on return. A missing pump value remains unavailable rather than appearing off.
- Docker and GitHub Actions now use Python 3.13. Their previous Python 3.11 target could not satisfy pinned NumPy 2.5.1's `Requires-Python >=3.12` metadata. Local testing uses Python 3.13.7. Linux wheel dependency resolution also passed a dry run; this is not a container build.

## Interface changes

- Compact desktop sidebar; mobile menu and bottom navigation; current-page indication; Escape/focus handling; skip link.
- Consistent typography, spacing, flat surfaces, green accents and readable contrast across all eight routes.
- Recommendation tools are the first task on the home page. On a 390px-wide screen the first form starts about **567px** down, compared with **3,066px** before the refresh (about 82% less distance).
- Sample-input shortcut, direct links to individual tool tabs, current-year/month defaults and API-sourced fertilizer dropdowns.
- Disease status no longer asks users to upload a photo to an unavailable service.
- Workflow, audit and stakeholder details expand on demand. Marketplace listings appear sooner after removing redundant setup metrics.
- Bootstrap, icons and chart assets are served locally with their licenses. Only the sensor page loads Chart.js; the date adapter is no longer needed. Firebase sign-in still requires its external service.

## Verification

| Check | Result |
| --- | --- |
| Python unittest suite | 68 passed (61 baseline plus regression coverage) |
| Ruff / Python compilation | Passed |
| Python dependency audit | No known vulnerabilities reported by pip-audit |
| Browser engines | Microsoft Edge/Chromium and Playwright WebKit |
| Layout matrix | Eight routes × nine widths × two engines = 144 checks without document overflow |
| Widths | 320, 390, 540, 768, 820, 1024, 1440, 1920, 2560 CSS pixels; additional 844×390 landscape navigation check |
| Accessibility | 32 axe scans across both engines at 320px and 1440px, zero reported WCAG 2 A/AA and 2.1 AA violations |
| Interactions | Real crop/fertilizer/price inference, validation, error/retry/input retention, menu/Escape/mobile links, disease deep link, assistant text-injection check, irrigation-label regression, empty/error sensor states |
| Browser JavaScript | No uncaught page errors or console warnings in the exercised flows |

Screenshots and machine-readable results are written to ignored `artifacts/ui-review/chromium/` and `artifacts/ui-review/webkit/`. Sensors use controlled fixtures in browser tests; recommendation requests reach the actual local model service. Assistant security/error scenarios use test responses. Tests use an isolated demo database, preserving existing application history.

WebKit on Windows is useful cross-engine coverage, not a physical iPhone/Safari certification. These checks do not establish field accuracy, production latency, every possible viewport/device, or a complete security audit. Docker is unavailable on this host, so the actual image build remains to be run in CI.

## Repeat the checks

Start the app in one PowerShell terminal with an isolated database:

```powershell
$env:DATABASE_URL = 'sqlite+pysqlite:///./ux-review.db'
$env:APP_ENV = 'development'
$env:AUTH_MODE = 'demo'
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8080
```

In another terminal, install browser test tools into the ignored directory if needed:

```powershell
npm install --prefix .browser-tools --no-package-lock playwright@1.62.1 axe-core@4.10.3
node .browser-tools/node_modules/playwright/cli.js install webkit
$env:KRISHI_BROWSER_MODULES = (Resolve-Path .browser-tools/node_modules).Path
$env:KRISHI_AXE_PATH = (Resolve-Path .browser-tools/node_modules/axe-core/axe.min.js).Path
node tests/browser_review.cjs
$env:KRISHI_BROWSER_ENGINE = 'webkit'
node tests/browser_review.cjs
.venv/Scripts/python.exe -m unittest discover -v
.venv/Scripts/ruff.exe check .
.venv/Scripts/pip-audit.exe -r requirements.txt
```

The default Chromium channel is the installed Microsoft Edge browser. `KRISHI_BASE_URL` and `KRISHI_BROWSER_CHANNEL` can override the server and Chromium channel. For subsequent Edge runs, clear `KRISHI_BROWSER_ENGINE` or set it to `chromium`.

## Remaining external work

Connect and validate an authorized sensor source, replace sample business data, revalidate models on representative held-out data, and configure/test Firebase, PostgreSQL and cloud deployment before operational use. Historical saved decisions retain their original results rather than silently being recomputed by a UI change.

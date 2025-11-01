# IPO Bot

Automates the IPO workflow:

- Scrapes live IPOs, subscription snapshots, and analysis (S.P. Tulsian).
- Uses AI to produce Apply/Avoid/Review decisions and normalized fields.
- Persists decisions to MongoDB with upsert (no duplicates).
- Creates/updates Google Calendar events.
- Optionally auto-applies via HDFC Securities (web automation with Selenium), resolving slight name mismatches using AI.

## Repo layout

- [main.py](main.py) — Orchestrates scraping, AI decisions, DB upserts, Calendar events, and auto-apply.
- [helper/ai_info.py](helper/ai_info.py)
  - get_ipo_decision(...) — Calls Cohere to produce structured decisions.
  - resolve_application_row_name(...) — AI + fuzzy match to map “target name” → exact table row label for clicking Apply.
- [helper/apply_ipo.py](helper/apply_ipo.py) — Selenium flow to log in, navigate, find the correct IPO row, accept alerts, and click Apply.
- [helper/mongo_connector.py](helper/mongo_connector.py) — MongoDB client, unique index, and upsert helpers.
- [helper/google_calendar.py](helper/google_calendar.py) — Calendar service and event upsert (user-provided credentials).
- [scrapers/ipo_scraper.py](scrapers/ipo_scraper.py), [scrapers/ipo_analysis_scraper.py](scrapers/ipo_analysis_scraper.py), [scrapers/ipo_subscription_scraper.py](scrapers/ipo_subscription_scraper.py) — Data gathering.
- [apply_ipo_test.py](apply_ipo_test.py) — Standalone test harness (returns True/False for initiation).

## Features

- Robust date/time in IST and noon cutoff in [main.py](main.py):
  - \_is_last_day(...), \_is_after_noon(), and subscription threshold checks.
- Duplicate-safe persistence:
  - Compound unique index on (LiveIPOName, IPOAnalysisTitle) and upserts in [helper/mongo_connector.py](helper/mongo_connector.py).
- Auto-apply rules in [main.py](main.py):
  - Triggers only if it’s last day AND after noon AND (AI says Apply OR subscription strong), and not already APPLIED.
- Apply button resolution in [helper/apply_ipo.py](helper/apply_ipo.py):
  - Scrapes first-column names, asks [helper.ai_info.resolve_application_row_name](helper/ai_info.py) for the exact candidate.
  - Locators support both row-text and onclick() second argument.
  - Handles ASBA/info alerts automatically.

## Prerequisites

- macOS, Python 3.13 (see [.python-version](.python-version))
- Google APIs credentials (Calendar/Gmail) and MongoDB Atlas URI
- Chrome + compatible ChromeDriver (Selenium 4.x)
- Cohere API key

## Installation

```bash
# macOS
python3.13 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install .
```

Dependencies are declared in [pyproject.toml](pyproject.toml).

## Environment variables (.env)

Create a .env at repo root:

```bash
# AI
COHERE_API_KEY=...

# MongoDB
MONGO_URI="mongodb+srv://..."
MONGO_DATABASE_NAME="ipo_bot_db"
MONGO_COLLECTION_NAME="ipo_status"

# Google Calendar
CALENDAR_ID="your_calendar_id"

# HDFC / Application
HDFC_USER="..."
HDFC_PASSWORD="..."
DOB="DD/MM/YYYY"
DP_NAME="zerodha"
ZERODHA_DP_NO="..."

# Automation knobs
IPO_NOON_CUTOFF_HOUR="12"
IPO_SUB_TOTAL_X="10"
IPO_SUB_QIB_X="10"
IPO_SUB_NII_X="5"
IPO_SUB_RII_X="1"
```

Important: Never commit secrets (API keys, tokens, credentials.json, token files).

## How it works

1. Scrape

- [scrapers/ipo_scraper.py](scrapers/ipo_scraper.py) → live IPOs
- [scrapers/ipo_analysis_scraper.py](scrapers/ipo_analysis_scraper.py) → analysis list
- [scrapers/ipo_subscription_scraper.py](scrapers/ipo_subscription_scraper.py) → subscription snapshot

2. AI decision

- [helper/ai_info.get_ipo_decision](helper/ai_info.py) calls Cohere (model: command-r-08-2024), returns a list of dicts:
  - LiveIPOName, IPOAnalysisTitle, Recommendation, RecommendationSource, SummarySnippet, LiveIPODetails, LiveIPOSubscriptionDetails
- Auto-apply uses Recommendation == "Apply" as the Tulsiyan proxy.

3. Persist and calendar

- [helper/mongo_connector.upsert_ipo_status](helper/mongo_connector.py) upserts by (LiveIPOName, IPOAnalysisTitle) with unique index.
- [helper/google_calendar.create_or_update_ipo_event](helper/google_calendar.py) updates/creates events.

4. Auto-apply (optional)

- In [main.py](main.py): if last day AND after noon AND (Recommendation == Apply OR subscription strong), then call [helper.apply_ipo.apply_ipo](helper/apply_ipo.py).
- [helper/apply_ipo.py](helper/apply_ipo.py):
  - Navigates to HDFC Securities IPO page, switches to Frame14.
  - Scrapes first-column names, resolves target with [resolve_application_row_name](helper/ai_info.py).
  - Finds Apply link either by row text or onclick’s display name parameter.
  - Accepts ASBA/info alerts automatically and proceeds.

## Running

- End-to-end:

```bash
source .venv/bin/activate
python main.py
```

- Apply flow only (standalone):

```bash
# Recommended: run as a module so relative imports work
python -m helper.apply_ipo

# Or directly (project root on sys.path is handled in the file)
python helper/apply_ipo.py
```

## Troubleshooting

- Relative import error running helper/apply_ipo.py:

  - The file includes a dual-import bootstrap and expects [helper/**init**.py](helper/__init__.py) to exist.

- “Apply” link not found:

  - Locator now tries row text first, then onclick’s second argument (matches examples like:
    apply_ipo('STUDDSG', 'STUDDS ACCESSORIES LIMITED', ...)).
  - Ensure [helper/ai_info.resolve_application_row_name](helper/ai_info.py) receives all first-column names.

- Unexpected ASBA alert blocks actions:

  - [helper/apply_ipo.py](helper/apply_ipo.py) sets unhandledPromptBehavior=accept and calls \_accept_alert_if_present(...) after navigation and clicks.

- Mongo duplicates across runs:

  - Prevented by unique compound index and upsert in [helper/mongo_connector.py](helper/mongo_connector.py). Clean existing duplicates once if index creation fails.

- Headless scraping:
  - Scrapers currently set headless Chrome; the apply flow may require visible browser during debugging.

## Security

- Do not commit API keys, OAuth tokens, or credentials.json. Rotate any keys already committed.
- Use least-privilege Calendar ID and Gmail scopes.
- Store MongoDB URIs securely.

## Roadmap

- Unit tests for scrapers and decision logic.
- Stronger schema validation for AI output.
- OTP flow via Gmail in apply path (helpers are scaffolded in [helper/email_helper.py](helper/email_helper.py)).

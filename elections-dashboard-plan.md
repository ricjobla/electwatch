# 🗳️ ElectWatch — European Elections Dashboard
### Claude Code Build Plan · Open Source · May 2026

---

## Why Europe First

Based on the 2026 national electoral calendar, **Europe has the most upcoming elections**
for testability right now (May–December 2026):

| Date | Country | Election |
|------|---------|----------|
| May 24 | Cyprus | Parliamentary |
| May 30 | Malta | Parliamentary |
| June 7 | Czech Republic | Parliamentary |
| June 7 | Montenegro | Presidential |
| Aug 29 | Iceland | EU Referendum |
| Sep 13 | Sweden | Parliamentary |
| Sep 20 | Russia | State Duma |
| Sep 23 | Morocco | House of Representatives |
| Oct (est.) | Denmark | General (by Oct 31) |
| Oct (est.) | Bosnia & Herzegovina | General |
| Oct (est.) | Hungary | General |
| Oct (est.) | Israel | Parliamentary |
| Oct (est.) | Norway | Parliamentary |
| Nov (est.) | Czech Republic | Senate |
| Nov 3 | United States | Midterms |

Plus: Bulgaria (Apr 19 — results just in), Slovenia (Mar 22 — recent),
Denmark (Mar 24 — recent). Plenty of live + historic data to test immediately.

**Europe also has the best open data infrastructure:**
- Wikipedia/Wikidata structured election data
- Many countries publish machine-readable official results (CSV/JSON/XML)
- IFES ElectionGuide has complete European coverage
- ParlGov dataset covers European parliaments back to 1945

---

## Architecture Overview

```
┌─────────────────────────────────────────┐
│              FRONTEND                    │
│   React + Vite + Tailwind               │
│   Recharts (maps/charts)                │
│   React Query (data fetching)           │
└──────────────┬──────────────────────────┘
               │ REST / JSON
┌──────────────▼──────────────────────────┐
│              BACKEND API                 │
│   FastAPI (Python)                      │
│   SQLite (dev) → PostgreSQL (prod)      │
│   APScheduler (cron jobs)              │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│           DATA INGESTION                 │
│   Wikipedia API (calendar/metadata)     │
│   Wikidata SPARQL (structured data)     │
│   ParlGov Dataset (historic results)    │
│   Per-country scrapers (live results)   │
│   IFES ElectionGuide (calendar)         │
└─────────────────────────────────────────┘
```

**Everything is open source. Zero paid APIs.**

---

## Tech Stack (All Free / OSS)

### Backend
- **Python 3.11+**
- **FastAPI** — API framework
- **SQLAlchemy** — ORM
- **SQLite** (dev) / **PostgreSQL** (prod, via Docker)
- **APScheduler** — background scraping jobs
- **httpx** — async HTTP client
- **BeautifulSoup4** — HTML scraping
- **SPARQLWrapper** — Wikidata queries

### Frontend
- **React 18 + Vite**
- **Tailwind CSS**
- **Recharts** — bar/line charts
- **react-simple-maps** — SVG Europe map
- **React Query (TanStack Query)** — data fetching + caching
- **date-fns** — date formatting

### Dev Tooling
- **Docker + Docker Compose** — one-command local setup
- **pytest** — backend tests
- **Vitest** — frontend tests
- **Ruff** — Python linting
- **ESLint + Prettier** — JS formatting

---

## Project Structure

```
electwatch/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entry point
│   │   ├── database.py              # SQLAlchemy setup
│   │   ├── models/
│   │   │   ├── election.py          # Election model
│   │   │   ├── result.py            # Result model
│   │   │   ├── party.py             # Party model
│   │   │   └── country.py           # Country model
│   │   ├── routers/
│   │   │   ├── elections.py         # GET /elections, /elections/{id}
│   │   │   ├── results.py           # GET /results/{election_id}
│   │   │   ├── countries.py         # GET /countries
│   │   │   └── calendar.py          # GET /calendar?from=&to=
│   │   ├── ingest/
│   │   │   ├── wikidata.py          # Wikidata SPARQL ingestion
│   │   │   ├── wikipedia.py         # Wikipedia calendar scraper
│   │   │   ├── parlgov.py           # ParlGov CSV loader
│   │   │   └── scrapers/
│   │   │       ├── base.py          # Base scraper class
│   │   │       ├── sweden.py        # val.se scraper
│   │   │       ├── germany.py       # bundeswahlleiter.de
│   │   │       ├── france.py        # elections.interieur.gouv.fr
│   │   │       └── ...              # Add countries as needed
│   │   ├── scheduler.py             # APScheduler cron jobs
│   │   └── schemas.py               # Pydantic response schemas
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── EuropeMap.jsx        # Interactive SVG map
│   │   │   ├── ElectionCard.jsx     # Calendar card
│   │   │   ├── ResultsChart.jsx     # Bar chart for results
│   │   │   ├── PartyLegend.jsx      # Color-coded party list
│   │   │   ├── CountryDrilldown.jsx # Country detail panel
│   │   │   └── LiveBadge.jsx        # "LIVE" indicator
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx        # Main view
│   │   │   ├── Country.jsx          # Country detail page
│   │   │   └── Election.jsx         # Single election page
│   │   ├── hooks/
│   │   │   ├── useElections.js
│   │   │   ├── useResults.js
│   │   │   └── useCalendar.js
│   │   └── lib/
│   │       ├── api.js               # API client
│   │       └── partyColors.js       # Party color registry
│   ├── package.json
│   └── Dockerfile
├── data/
│   └── seed/
│       ├── parlgov_europe.csv       # Pre-loaded historic data
│       └── countries.json           # Country metadata + flags
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Database Schema

```sql
-- Countries
CREATE TABLE countries (
  id          TEXT PRIMARY KEY,   -- ISO 3166-1 alpha-2 (e.g. 'SE')
  name        TEXT NOT NULL,
  region      TEXT NOT NULL,       -- 'western_europe', 'eastern_europe', etc.
  flag_emoji  TEXT,
  wikidata_id TEXT                 -- Q-number for Wikidata lookups
);

-- Elections
CREATE TABLE elections (
  id              TEXT PRIMARY KEY,  -- e.g. 'SE-2026-09-13-parliament'
  country_id      TEXT REFERENCES countries(id),
  type            TEXT,              -- 'parliamentary', 'presidential', 'referendum'
  election_date   DATE NOT NULL,
  status          TEXT DEFAULT 'upcoming', -- 'upcoming', 'live', 'complete'
  title           TEXT NOT NULL,
  description     TEXT,
  wikipedia_url   TEXT,
  wikidata_id     TEXT,
  turnout_pct     FLOAT,
  source_url      TEXT,              -- Official results URL
  last_updated    TIMESTAMP
);

-- Parties
CREATE TABLE parties (
  id          TEXT PRIMARY KEY,
  country_id  TEXT REFERENCES countries(id),
  name        TEXT NOT NULL,
  short_name  TEXT,
  color_hex   TEXT,
  wikidata_id TEXT,
  ideology    TEXT                   -- 'conservative', 'social_democrat', etc.
);

-- Results (one row per party per election)
CREATE TABLE results (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  election_id  TEXT REFERENCES elections(id),
  party_id     TEXT REFERENCES parties(id),
  vote_share   FLOAT,               -- percentage
  seats_won    INTEGER,
  votes_raw    INTEGER,
  is_governing BOOLEAN DEFAULT FALSE,
  result_type  TEXT DEFAULT 'final' -- 'partial', 'exit_poll', 'final'
);

-- Ingestion log (for debugging scrapers)
CREATE TABLE ingest_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source      TEXT,
  election_id TEXT,
  status      TEXT,                 -- 'success', 'error', 'skipped'
  message     TEXT,
  run_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Data Sources (All Free)

### 1. Wikidata SPARQL — Calendar + Metadata
**Best for:** Upcoming elections, election metadata, party info.

```sparql
# Get all European elections in 2026
SELECT ?election ?electionLabel ?country ?countryLabel ?date WHERE {
  ?election wdt:P31 wd:Q40231 .         # instance of: election
  ?election wdt:P17 ?country .           # country
  ?country wdt:P30 wd:Q46 .             # continent: Europe
  ?election wdt:P585 ?date .            # point in time
  FILTER(YEAR(?date) = 2026)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }
}
ORDER BY ?date
```

### 2. ParlGov Dataset — Historic Results (1945–2024)
**Best for:** Pre-loading historic results for all European countries.
- URL: `http://www.parlgov.org/data/parlgov-development.csv.zip`
- Contains: election dates, party names, vote/seat shares, country
- License: CC0 (public domain)
- Load once as seed data on startup

### 3. Wikipedia API — Calendar + Descriptions
**Best for:** Supplementing Wikidata, getting article summaries.
```
https://en.wikipedia.org/api/rest_v1/page/summary/2026_Swedish_general_election
```

### 4. Per-Country Official Sources — Live Results
Start with countries that have structured result feeds:

| Country | Source | Format |
|---------|--------|--------|
| Sweden | `api.val.se` | JSON API |
| Germany | `bundeswahlleiter.de` | XML/CSV |
| Norway | `valgresultat.no` | JSON |
| France | `elections.interieur.gouv.fr` | JSON |
| UK | `api.parliament.uk` | JSON |
| Malta (May 30!) | `electoral.gov.mt` | HTML scrape |
| Cyprus (May 24!) | `ecsy.cy` | HTML scrape |

### 5. IFES ElectionGuide — Supplemental Calendar
- Scrape `electionguide.org` for election descriptions + metadata
- Respectful scraping: once per day, cache aggressively

---

## API Endpoints

```
GET /api/calendar
  ?from=2026-05-01&to=2026-12-31
  ?region=europe
  ?status=upcoming|live|complete
  → List of upcoming elections with dates/countries

GET /api/elections/{id}
  → Full election detail: metadata + results + parties

GET /api/elections/{id}/results
  → Party results for an election

GET /api/countries
  → All tracked countries

GET /api/countries/{iso}/elections
  → All elections for a specific country (historic + upcoming)

GET /api/countries/{iso}/parties
  → All parties for a country

GET /api/live
  → Elections currently active (status='live')
  → Polled every 60 seconds by frontend

POST /api/admin/ingest/{source}
  → Manually trigger a data ingestion job (dev only)

GET /api/health
  → Health check endpoint
```

---

## Build Phases

### Phase 1 — Foundation (Week 1–2)
**Goal: Working backend with seed data, basic frontend shell**

```
Tasks:
[ ] Initialize repo with Docker Compose (backend + frontend + db)
[ ] Create SQLAlchemy models + migrations (Alembic)
[ ] Write ParlGov CSV loader → seeds historic European results
[ ] Write Wikidata SPARQL ingestion for 2026 upcoming elections
[ ] FastAPI routes: /calendar, /elections, /countries
[ ] React app scaffold: Vite + Tailwind + React Query
[ ] Basic elections list page (no map yet)
[ ] Docker Compose up → working end-to-end

Test: Can I see Cyprus (May 24) and Malta (May 30) in the calendar?
Test: Can I see Sweden's 2022 election historic results?
```

### Phase 2 — Dashboard UI (Week 3)
**Goal: Polished, interactive dashboard with Europe map**

```
Tasks:
[ ] Europe SVG map (react-simple-maps)
    → Countries colored by: upcoming election proximity
    → Click country → drill-down panel
[ ] Election calendar view (timeline/card layout)
    → Filter by: status, date range, election type
[ ] Results chart (horizontal bar, party colors)
[ ] Country detail page: all elections + historic trend chart
[ ] Party color registry (hand-coded for major parties)
[ ] "Days until election" countdown on cards
[ ] Mobile responsive layout

Test: Click Sweden on map → see 2026 election + 2022 historic results
Test: Calendar shows Cyprus election in 3 upcoming cards
```

### Phase 3 — Live Results (Week 4)
**Goal: Scrapers fire on election day, frontend polls live**

```
Tasks:
[ ] Base scraper class with retry logic + logging
[ ] Malta scraper (May 30 — first real test!)
[ ] Cyprus scraper (May 24 — first real test!)
[ ] APScheduler: scrape every 5 min when election status='live'
[ ] Status transition logic: upcoming → live → complete
[ ] Frontend: auto-refresh every 60s when live election exists
[ ] "LIVE" badge component with pulse animation
[ ] Partial results display (show % reporting)
[ ] Ingest log viewer (debug page)

Test: Malta votes May 30 — does the dashboard update live?
```

### Phase 4 — Polish + More Countries (Week 5–6)
**Goal: Production-ready, add more upcoming elections**

```
Tasks:
[ ] Czech Republic scraper (June 7)
[ ] Sweden scraper (September 13 — has JSON API!)
[ ] Wikipedia article summary integration (election descriptions)
[ ] Share-able election URLs (e.g. /election/SE-2026)
[ ] README + contributing guide
[ ] GitHub Actions CI (run tests on push)
[ ] Deploy: Railway / Render / Fly.io (all free tier)

Stretch:
[ ] Election result comparison (2022 vs 2026 side-by-side)
[ ] Seat map visualization (parliament seating chart)
[ ] RSS/JSON feed for upcoming elections
```

---

## Claude Code Prompts (Copy-Paste Ready)

### Kickoff prompt:
```
Initialize a new project called "electwatch" with this structure:
- Python FastAPI backend in /backend
- React + Vite + Tailwind frontend in /frontend
- Docker Compose that runs both + a PostgreSQL container
- SQLite for local dev (switch to Postgres via env var)

Create SQLAlchemy models for: Country, Election, Party, Result, IngestLog
with the schema defined in the spec. Use Alembic for migrations.

Add a /backend/requirements.txt with: fastapi, uvicorn, sqlalchemy,
alembic, httpx, beautifulsoup4, SPARQLWrapper, apscheduler, pydantic

Run alembic init and create the initial migration.
```

### Data ingestion prompt:
```
Create /backend/app/ingest/parlgov.py that:
1. Downloads parlgov-development.csv.zip from parlgov.org
2. Extracts and parses the CSV
3. Filters for European countries only (use ISO codes list)
4. Upserts into the elections, parties, and results tables
5. Logs results to ingest_log table

Map ParlGov columns to our schema:
- election_date → elections.election_date
- country_name_short → look up countries.id
- party_name → parties.name
- vote_share → results.vote_share
- seats → results.seats_won

Add a CLI entrypoint: `python -m app.ingest.parlgov`
```

### Wikidata ingestion prompt:
```
Create /backend/app/ingest/wikidata.py that:
1. Runs a SPARQL query against https://query.wikidata.org/sparql
2. Fetches all elections in Europe for 2026 with their dates
3. For each result, upserts into the elections table
4. Sets status='upcoming' for elections after today, 'complete' for past

Use SPARQLWrapper with returnFormat=JSON.
Handle rate limiting with a 1-second delay between requests.
Log each election found to ingest_log.
```

### Frontend map prompt:
```
Create /frontend/src/components/EuropeMap.jsx using react-simple-maps.
Use the "europe" geography from:
https://raw.githubusercontent.com/zcreativelabs/react-simple-maps/master/topojson-maps/world-110m.json

Color each country:
- Red/amber: election within 30 days
- Green: election within 90 days
- Gray: no upcoming election tracked

On hover: show tooltip with country name + next election date.
On click: call onCountryClick(isoCode) prop.

Use a dark background (#0f1117) with the map in slate colors.
The overall aesthetic should feel like a political intelligence dashboard —
think The Economist meets a Bloomberg terminal.
```

### Live scraper base prompt:
```
Create /backend/app/ingest/scrapers/base.py with:

class BaseScraper:
  - __init__(self, election_id: str, db: Session)
  - async fetch(url: str) → BeautifulSoup
  - abstract async scrape() → list[dict]  # [{party, votes, seats, pct}]
  - async run() → None  # calls scrape(), upserts results, logs to ingest_log
  - Sets election.status = 'live' when first partial results arrive
  - Sets election.status = 'complete' when scrape returns is_final=True

Then create /backend/app/ingest/scrapers/malta.py that extends BaseScraper
targeting https://electoral.gov.mt for the 2026 Maltese general election.
```

---

## Deployment (Free Tier)

### Option A: Railway (Recommended)
- Deploy backend + PostgreSQL as one project
- Deploy frontend as static site
- Free tier: 500hrs/month compute
- `railway up` from project root

### Option B: Render
- Backend: Web Service (free tier)
- Database: PostgreSQL (free tier, 1GB)
- Frontend: Static Site (free, unlimited)

### Option C: Self-host (VPS)
- $5/month Hetzner or DigitalOcean droplet
- Docker Compose in production
- Caddy as reverse proxy (auto HTTPS)

---

## Open Source Checklist

```
[ ] MIT License
[ ] README with: what it is, how to run locally, how to add a country scraper
[ ] CONTRIBUTING.md: how to add a new country
[ ] .env.example with all required env vars
[ ] GitHub Actions: test on push, lint check
[ ] Issues templates: "Add country scraper", "Bug report"
```

---

## First 3 Commands to Run with Claude Code

```bash
# 1. Scaffold the project
claude "Initialize electwatch project per the spec in elections-dashboard-plan.md"

# 2. Load historic data
claude "Implement the ParlGov ingestion script and seed the database"

# 3. Build the dashboard
claude "Build the React dashboard with Europe map and election calendar"
```

---

## Testing Milestones

| Date | Event | What to test |
|------|-------|-------------|
| Now | Bulgaria Apr 19 (complete) | Historic results display |
| Now | Slovenia Mar 22 (complete) | Historic results display |
| May 24 | Cyprus parliamentary | Live scraper fires |
| May 30 | Malta parliamentary | Live scraper fires (first real test) |
| June 7 | Czech Republic | Live scraper + calendar |
| Sep 13 | Sweden (has JSON API!) | Best live results test |

---

*Start with `claude "Initialize electwatch project"` and point it at this file.*

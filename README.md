# AI SEO Blog Agent (Appin Technology Coimbatore, practical assignment)

One click on **Create Blog Page** runs an AI agent that researches keyword opportunities, checks them against the site's existing content, plans and writes an SEO-optimised article, validates it, and saves a real, server-rendered blog page in this test environment. **Nothing is ever written to appincoimbatore.com** (read-only GET requests, host allow-list).

```
React (Vite) --SSE--> FastAPI --> LangGraph agent --> Gemini (structured output)
                         |            research -> dedupe -> plan -> write -> validate -> [repair] -> save
                         +--> Postgres (pages, runs)   +--> /blog/<slug> server-rendered pages
```

## What the agent does
| Step | How | Data label |
|---|---|---|
| 1 Keyword research | Live **Google Autocomplete** for 8 seed queries + the site's **live Yoast sitemaps** (181 digital-marketing pages) | **Verified** (observed). Falls back to a dated snapshot if offline |
| 2 Duplicate check | Lexical overlap of each keyword with existing page titles/slugs (+ pages the agent already made). Flags `gap` / `partial` / `conflict` (cannibalisation). Deterministic, free, explainable | Verified (computed) |
| 3 Select + plan | **1 LLM call**: primary + secondary keywords, topic, slug, audience, intent, H1/H2/H3 outline, intent/relevance/competition/volume | Analysis is an **AI estimate** (low/medium/high bands, never invented numbers) |
| 4 Generate | **1 LLM call**: SEO title, meta, content, 5 FAQs, internal links (only real site URLs), image ideas + alt text, CTA for the Digital Marketing course | |
| 5 Validate | 14 code-based on-page checks (title/meta length, keyword in H1/first 100 words, density, word count, headings, links, alt text, CTA) -> score /100 | |
| 6 Auto-fix | Only if checks fail: **1 repair call** (max once) | |
| 7 Save | Page stored in Postgres and served at `/blog/<slug>` with title, meta, canonical, Open Graph, JSON-LD (Article + FAQPage), semantic headings, FAQ, internal links, test-environment banner | |

About **2-3 Gemini calls per page** (free-tier friendly). Only one run at a time and a per-hour cap protect the free quota.

## Run locally
Requirements: Docker Desktop, Python 3.11+, Node 18+, a Gemini API key from https://aistudio.google.com/apikey

```powershell
copy .env.example .env             # set GEMINI_API_KEY and POSTGRES_PASSWORD
docker compose up -d               # Postgres only
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt   # tests: pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
# new terminal
cd frontend; npm install; npm run dev     # open http://localhost:5173
```
Production-style (one process): `cd frontend && npm run build`, then run uvicorn; FastAPI serves the React build.

## Environment variables
| Name | Purpose |
|---|---|
| `GEMINI_API_KEY` | Required for real runs. Missing -> clear `MISSING_API_KEY` error (the agent never fakes output) |
| `LLM_MODEL`, `LLM_FALLBACK_MODELS` | Main Gemini model (default `gemini-3.5-flash`) and the models tried automatically if it is overloaded (503) or its free quota is used up (429) |
| `DATABASE_URL` | Hosted Postgres URL (used in production). Locally the `POSTGRES_*`/`DB_*` vars are used |
| `MAX_RUNS_PER_HOUR` | Cost guard for the public demo |

## Errors handled (shown as friendly cards with Try again)
`MISSING_API_KEY`, `INVALID_API_KEY`, `RATE_LIMITED` (free quota), `TIMEOUT` (retry with backoff), `UPSTREAM_ERROR`, `DB_UNAVAILABLE`, `BUSY`, `RUN_LIMIT`.

## Tests
```powershell
cd backend; python -m pytest -q     # 13 tests; the LLM is replaced by fakes, so no Gemini calls are made
```

## Deploy (free): Render (web) + Neon (Postgres)
`Dockerfile` + `render.yaml` are included. Create a free Neon database, set `DATABASE_URL` (with `sslmode=require`) and `GEMINI_API_KEY` as Render environment variables. The free Render instance sleeps when idle, so the first request can take ~1 minute.

## Safety notes
Secrets only in `.env` (git-ignored). LLM output is HTML-escaped when rendered; internal links are validated against real site URLs; crawled/suggested text is treated as data in prompts; only allow-listed hosts are fetched.

## Limitations / next steps
Keyword volume and competition are AI estimates because no paid SEO API is used (verified vs estimated is labelled everywhere). Images are described with alt text but not generated. Next: Search Console / paid keyword API integration, image generation, WordPress publishing via the REST API for a real site, scheduled batch runs, evaluation set for content quality.

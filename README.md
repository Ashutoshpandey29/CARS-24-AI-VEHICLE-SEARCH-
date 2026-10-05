# Cars24 Vehicle Search

Search a used-car catalogue in plain English. Built for the Cars24 Backend Engineering assignment, **Problem 2: AI Vehicle Search Engine**.

```
"Diesel automatic cars below 80k km"  →  fuel: Diesel, gearbox: Automatic, max km: 80,000  →  54 cars
```

![Search page](docs/images/ui-search.png)

**Stack:** Python, FastAPI, SQLite, Claude API (optional), our own trained CRF model, Redis (optional).

## Highlights

- **The AI reads the query, SQL does the search.** Results always respect the budget and other limits, and every response shows the filters it understood.
- **Three parsers:** the Claude LLM, a model we trained ourselves, and regex rules. If one is unavailable, the next takes over.
- **Our trained model** gets 96% of test queries fully right, against 61% for the rules. It runs offline in 0.4 ms.
- **Fast at scale:** 94 ms p95 uncached and 6 ms cached, on a 1,000,000-car catalogue.
- **Never an empty page:** if nothing matches, it relaxes the least important filters and says which ones it dropped.
- **Ready to deploy:** Docker, health check, 21 tests, and a search page you can try in the browser.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/seed.py                      # creates a catalogue of 600 cars
cp .env.example .env                        # optional: add ANTHROPIC_API_KEY for the AI parser
uvicorn app.main:app --reload --env-file .env
```

Then open:
- **Search page:** http://localhost:8000
- **API docs:** http://localhost:8000/docs
- **From the terminal:** `curl -G localhost:8000/search --data-urlencode "q=7 seater diesel under 20L"`

If port 8000 is busy, add `--port 8002`. Shortcuts: `make run`, `make test`, `make train`, `make eval`, `make bench`, `make docker`.

![Setup](docs/images/terminal-setup.png)

## How it works

The query is parsed into filters, which run as parameterised SQL. The parsers are tried in this order:

| Parser | Needs | Speed | Best at |
|---|---|---|---|
| 1. **Claude LLM** (recommended) | `ANTHROPIC_API_KEY` | ~1 s, then cached | Any phrasing |
| 2. **Our trained model** (CRF) | Nothing (included in the repo) | 0.4 ms | Everyday queries, "not diesel", "twelve lakh", "1.2 lakh km" |
| 3. **Regex rules** | Nothing | 0.1 ms | Standard formats like "under 15L" |

**Set an API key for the best results.** Without one, the trained model handles queries. The `parser` field in the response shows which parser was used.

Where the rules fail and the trained model gets it right:

| Query | Rules | Trained model |
|---|---|---|
| SUV not older than 3 years, not diesel | SUV, **Diesel** ✗ | SUV, year ≥ 2023, non-diesel ✓ |
| Maruti or Toyota automatic, max 1.2 lakh km | **max price ₹1.2L** ✗ | max 120,000 km ✓ |
| family of 7, diesel, budget twelve lakh | **5 seats, no budget** ✗ | 7 seats, max ₹12L ✓ |

How the model was trained and evaluated: [docs/TRAINED_MODEL.md](docs/TRAINED_MODEL.md).

## Scalability

| Technique | Effect |
|---|---|
| Cache for parsed queries and results (in memory or Redis) | A repeated search skips the LLM and the database |
| Read broad searches straight from an index already in sort order | Stops after one page instead of sorting 500k rows |
| Stop counting at 10,000 ("10,000+") | Cuts the most expensive part of broad searches |
| Cursor pagination | Page 500 is as fast as page 1 |
| Several stateless workers with read-only connections | Add instances behind a load balancer to scale |

**1M-car benchmark** (`make bench`):

| | Before | After |
|---|---|---|
| Uncached p95 | 517 ms | **94 ms** |
| Deep page (around result 5,000) | 653 ms | **19 ms** |

## Future scope

- **Hybrid search (RAG):** full-text search plus embeddings on top of the filters, for "sporty", model names and typos.
- **Fine-tuning a heavier model:** a transformer or small open LLM trained on real queries labelled by Claude, including Hinglish ("diesel gaadi 10 lakh tak").
- **Postgres or OpenSearch** for catalogues of millions of listings, with facets. All SQL is in one file.

Details and trade-offs: [docs/ALTERNATIVES.md](docs/ALTERNATIVES.md).

## Project structure

```
app/
  api/routes.py       /search, /cars/{id}, /health
  parser/             llm.py, model.py (trained), rules.py
  search/             SQL builder, pagination, caching
  static/index.html   search page
models/               trained model (84 KB)
training/             training data generator, test queries, evaluation
scripts/              seed, train_model, benchmark
tests/                21 tests
docs/                 API, design, trained model, alternatives
```

## More docs

- [API reference](docs/API.md): endpoints, parameters, response fields
- [Design](docs/DESIGN.md): architecture, decisions, failure handling
- [Trained model](docs/TRAINED_MODEL.md): how it works, training, results
- [Alternative approaches](docs/ALTERNATIVES.md): RAG and fine-tuning designs

Settings are environment variables, listed in [.env.example](.env.example).

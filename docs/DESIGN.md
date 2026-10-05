# Design

## The main idea: the LLM reads the query, the database finds the cars

```
query ─► normalise ─► parse cache ─┬─ hit ───────────────────────────────┐
                                   └─ miss ─► Claude (structured output) ─┤
                                              │ no key / error / refusal  │
                                              └─► trained CRF tagger ─────┤
                                                  │ no model file         │
                                                  └─► regex parser ───────┤
                                                                          ▼
                                                     Filters (Pydantic, enums)
                                                                          │
                              count (capped) ─► 0 matches? relax soft filters
                                                                          │
                              page: index walk or planner choice, offset or cursor
                                                                          │
                                                  result cache ─► response
```

The LLM never writes SQL and never ranks cars. Its only job is to turn free text into a typed `Filters` object. A parameterised query then does the search.

- **Correct results.** "Under ₹15L" becomes `price <= 1500000`. A car over budget cannot appear in the results. Vector search on its own gives no such guarantee.
- **Safe.** LLM output is validated against a schema with enum fields, and values only ever reach SQL as bound parameters. Column names and sort orders come from fixed tables in `app/search/query.py`. A prompt injection has no SQL text to inject into.
- **Explainable.** The API returns the parsed `filters`, so anyone can see how a query was read.

## Decisions

| Decision | Why | Trade-off |
|---|---|---|
| Claude structured outputs (`messages.parse` with the Pydantic model) | The response always matches the schema, so there is no JSON repair code. Enums keep values in line with the DB columns. | About one extra second per new query. The cache hides this for repeat queries. |
| `effort: low` | Short extraction task. More reasoning adds latency without improving the filters. | |
| Server-side `fallbacks: "default"` | If a safety classifier declines a request, the API retries it on another model instead of returning a refusal. | Beta header |
| Own trained model (CRF tagger) as the second parser | Works offline in about 0.4 ms at no cost per query, and handles context the regex can't (negation, "1.2 lakh km", number words). On the hand-written test set: 96% of queries fully right, against 61% for the rules. | Only as good as its training data. It is trained on generated queries for now, and real labelled queries would make it better (see the README). |
| Regex parser as the last fallback | No dependencies at all. If the model file is missing or fails to load, search still works. | Only understands phrasings it was written for |
| Same conventions in the prompt, the training data and the regex | "family car", "safe" and "15L" mean the same thing whichever parser runs. | Three places to update. The shared test set in `training/eval_queries.jsonl` catches drift. |
| SQLite, read-only, one connection per thread | No setup, and indexed filtering stays in milliseconds up to millions of rows. | Single node. See "Going further" in the README. |
| One denormalised `cars` table | Every query is a filtered read. Normalising would only add joins. | |
| Soft-filter relaxation (`min_safety`, then `max_km`, then `min_year`) | An empty page is the worst search result. Budget, fuel, body type, make and city are hard constraints and are never dropped. | The response lists what was dropped in `relaxed`. |

## Performance

**Plan choice by selectivity.** For a selective query (say Hyundai in Pune between 5 and 9 lakh), SQLite's planner does well: it uses the narrowest index and sorts the few hundred matches. For a broad query (SUVs under 15 lakh, half the catalogue) the same plan sorts hundreds of thousands of rows to return 20. The service already knows the match count before fetching, so when matches are at least 1% of the catalogue (or past the count cap) it uses `INDEXED BY` on the index that stores rows in the requested order and stops after one page. Expected rows read is about `limit / share`, so at most about 100 × limit.

**Capped count.** `SELECT COUNT(*) FROM (SELECT 1 ... LIMIT cap+1)` stops after `cap` matches. Exact totals over 10,000 do not help anyone choose a car, and they were the most expensive part of broad queries.

**Keyset pagination.** Every sort order ends in `id`, so the order is total and a cursor (the last row's sort values, base64-encoded JSON) identifies a position exactly. The condition is the usual expansion `(a < x) OR (a = x AND b > y) OR (...)`, which handles mixed ASC/DESC orders. A bound on the leading column is added in front, so SQLite can seek into the index instead of scanning from the start. Each cursor records which sort it belongs to, so a cursor from a "cheapest" search sent to a "newest" search is rejected with `400`.

**Caching.**

| Key | Value | TTL |
|---|---|---|
| `parse:v2:<first-choice parser>:<normalised query>` | filters + parser used | 24 h if the first-choice parser answered, 5 min if a fallback did |
| `count:v1:<catalogue version>:<filters>` | (count, exact) | 60 s |
| `page:v1:<catalogue version>:<filters>:<limit>:<offset>:<cursor>` | rows | 60 s |

The catalogue version is the DB file's modification time, so reseeding invalidates every count and page at once. The parse cache is keyed on the query text, not the catalogue, so it survives reseeds. Redis is used when `REDIS_URL` is set. Any Redis error is logged and the search continues without the cache.

## Failure handling

| Failure | Behaviour |
|---|---|
| LLM network, auth or rate-limit error | Logged, the trained model takes over, the request succeeds |
| LLM refusal or unparseable output | Trained model |
| Slow LLM | 20 s timeout (`LLM_TIMEOUT`), 1 retry, then the trained model |
| Model file missing or unreadable | Warning at startup, the rule parser is used |
| Redis down | Logged, search runs uncached |
| Database missing | Startup warning, `/health` returns `503` |
| Bad input | `422` for validation errors, `400` for a bad cursor |

## Next steps

1. **Real evaluation data.** The test set (`training/eval_queries.jsonl`, scored by `make eval`) is hand-written. Replace and extend it with real queries, labelled by the LLM and checked by a person, and add the same queries to the model's training data.
2. **Hybrid search (RAG).** Full-text search plus embeddings, ranked *inside* the hard-filtered set, so vague intent ("sporty", "good on highways"), model names and typos work while budget and fuel still hold. Optionally the LLM summarises the top matches. Full design in the README, "Alternative approaches".
3. **Fine-tuned heavier model.** A transformer tagger (MuRIL or IndicBERT for Hinglish) or a LoRA-tuned small open LLM, trained on real queries labelled by the Claude parser (distillation). It plugs in as another parser and is scored with `training/evaluate.py`.
4. **Model names.** Add a `models` filter ("XUV700", "Creta"). Right now only the make is understood.
5. **Exclusions.** Explicit `exclude_fuel_types` and similar fields, so "not diesel" does not depend on the LLM listing every other fuel.

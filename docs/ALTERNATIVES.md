# Alternative approaches

The current design turns a query into structured filters and runs them as SQL, with three parsers to choose from. There are two other well-known ways to build this. Both are written up here as designs: what they are, how they would fit into this code, and when they are worth the extra cost. Neither is implemented in this repo, because each needs heavy dependencies (PyTorch, a vector index, a GPU for training) that are out of proportion for an assignment.

## A. Hybrid search with embeddings (RAG)

**The idea.** Filters only cover what the database has columns for. Many real queries are about things that are not columns: "sporty", "good for long highway trips", "low maintenance", "Creta or something like it", or a typo such as "hyundia". Hybrid search handles these by combining three kinds of retrieval:

1. **Structured filters (kept as they are).** Budget, fuel, year, km and so on are still applied as hard SQL conditions. This is the important part. Embeddings have no notion of "under ₹15L", so a pure vector search will happily return a ₹22L car for that query.
2. **Full-text search (BM25).** Matches exact words such as model names ("XUV700", "i20"), variants and features in the listing text. Typo-tolerant with fuzzy matching.
3. **Embedding (vector) search.** Each listing gets a short text description ("2021 Hyundai Creta SX diesel automatic, 5-seat SUV, sunroof, 5-star NCAP, 1 owner, Pune"), which is turned into an embedding vector. The query is embedded too, and the nearest listings by meaning are found, so "family SUV for highway trips" matches cars described as spacious, diesel and with good safety, even if no word overlaps.

```
query ─► parser (LLM / trained model / rules) ─► hard filters ───────────────┐
  │                                                                          ▼
  ├─► full-text search (BM25) over listing text ──┐            candidates that pass
  │                                               ├─► merge ─► the hard filters
  └─► embed query ─► vector search (k-NN) ────────┘  (RRF)           │
                                                                     ▼
                                              (optional) LLM reads the top results
                                              and writes a short answer: "3 match,
                                              the Nexon is cheapest, the XUV300 has
                                              the best safety rating"   ← the "G" in RAG
```

The two ranked lists are merged with reciprocal rank fusion (RRF), a simple way to combine rankings without tuning weights. The **G** in RAG (retrieval-augmented generation) is the optional last step: the LLM is given the retrieved listings and writes a short comparison. It can only talk about cars that were actually retrieved, which keeps it grounded.

**How it fits this code.** The parsers and `Filters` stay as they are. `app/search/query.py` gains a full-text match and a vector search that both run on the filtered set. `app/search/service.py` gains a merge step before paging. Practical options:

| Need | Small scale | Large scale |
|---|---|---|
| Full-text search | SQLite FTS5 (built into SQLite) | Postgres full-text or OpenSearch |
| Vector search | `sqlite-vec` or FAISS | `pgvector` in Postgres, or the OpenSearch k-NN plugin |
| Embeddings | A local sentence-embedding model (e.g. `bge-small`, `all-MiniLM`) | The same model behind a small service, or a hosted embedding API |

Embeddings are computed once per listing when it is created or updated, not per search. Per search there is only one query embedding, which is cached like the parsed filters.

**Pros:** handles vague intent, model names, typos and listing descriptions. Results are ranked by relevance, not just sorted by price or year. The generated answer helps users compare cars.
**Cons:** another index to build and keep in sync with listings. Relevance is harder to test than "are all results under budget", so it needs a ranking test set (queries plus which cars should come first). Generating an answer adds an LLM call and latency, so it suits a "compare these" panel better than every keystroke.
**When to do it:** when listings have rich descriptions (features, inspection notes, seller text) and search logs show many queries with no structured meaning.

## B. Fine-tuning a heavier model

**The idea.** Replace or back up the CRF with a bigger model trained on the same task, query in and filters out. There are two common forms:

| | Token tagger | Text-to-filters generator |
|---|---|---|
| Model | A small encoder such as DistilBERT, or a multilingual one such as MuRIL or IndicBERT for Hindi and Hinglish | A small seq2seq model (Flan-T5) or an open LLM (Qwen, Llama, 1 to 8 billion parameters) fine-tuned with LoRA |
| Output | A label per word, exactly like the CRF today | The `Filters` JSON directly, with decoding constrained to the schema |
| Plugs in as | A drop-in replacement for `app/parser/model.py` | A new parser between the LLM and the CRF |
| Strength | Fast, handles unseen wording much better than the CRF | Can do anything the hosted LLM does, self-hosted, no per-query API cost |

**The data is the real work, not the model.** The plan:
1. Log real queries (anonymised).
2. Label them automatically with the Claude parser.
3. Have a person review a sample, especially the queries where the LLM and the CRF disagree.
4. Fine-tune on several thousand of these, and keep a held-out set for testing.

This is called distillation: the big hosted model teaches a smaller one that is cheaper to run. The training data format (`training/`) and the scoring script (`training/evaluate.py`) in this repo already work this way, so the new model would be compared with the others on the same queries.

**A point specific to Cars24:** many Indian users type in Hinglish ("7 seater chahiye 12 lakh tak", "diesel gaadi automatic"). Neither regex rules nor a CRF trained on English templates will handle that. A multilingual model fine-tuned on real queries is the most realistic way to support it.

**Pros:** better accuracy on real phrasing, Hinglish support, no per-query API cost once trained, and data stays in-house.
**Cons:** needs labelled real data first. Training needs a GPU. Serving needs a GPU, or a CPU with ONNX and quantisation at higher latency. The model must be retrained and checked as language and inventory change.
**When to do it:** when query volume makes the LLM bill significant, or when Hinglish queries are a meaningful share of traffic.

## How all the options compare

| Approach | Status | Understands | Latency per new query | Cost per query | Needs |
|---|---|---|---|---|---|
| Regex rules | **Built** | Fixed phrasings | ~0.1 ms | Free | Nothing |
| Trained CRF tagger | **Built** | Everyday phrasing, negation, number words | ~0.4 ms | Free | 84 KB model file |
| Hosted LLM (Claude) | **Built** | Almost anything | ~1 s (then cached) | API cost | API key |
| Fine-tuned transformer or open LLM | Designed | Real phrasing, Hinglish | Roughly 10 to 50 ms for a tagger on CPU, more for an LLM | Own hosting | Labelled data, GPU to train |
| Hybrid search + RAG | Designed | Vague intent, model names, typos, descriptions | Tens of ms for retrieval, about a second more if an answer is generated | Hosting, plus LLM if generating | Vector index, embedding model |

Latency figures for the designed options are typical ranges, not measurements from this repo.

They are not either/or. A realistic production setup would be:
- the fine-tuned model as the default parser
- the hosted LLM for the queries it is unsure about
- the rules as the last fallback
- hybrid search ranking results inside the hard filters

The current code is built so each of these is an added stage, not a rewrite.

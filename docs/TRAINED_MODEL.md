# Our own trained model

## What it is

A **CRF (conditional random field) sequence tagger**. This is a classic model for this kind of query-understanding task, and voice assistants used it for slot filling before LLMs. It reads the query word by word and labels each word with the filter it fills:

```
not   diesel      under  12           lakh         1.2       lakh       km
O     B-FUEL_NOT  O      B-PRICE_MAX  I-PRICE_MAX  B-KM_MAX  I-KM_MAX   O
```

Each word is labelled from its context: the word itself, its shape (year, decimal, number word), whether it is a known brand, city or unit, and the three words on each side. So the model learns that "1.2 lakh" followed by "km" is a distance and "diesel" after "not" is an exclusion. A small, readable function then turns the labelled spans into filters (number words, lakh/crore/k units, aliases such as Bengaluru, Gurugram and Bombay).

It recognises 19 slot types: body, fuel, excluded fuel, gearbox, make, city, min/max price, max km, min year, max age, seats, safety, family, and five sort orders.

The model handling a negation in the search page:

![Trained model handling a negation](images/ui-model.png)

## How it was trained

1. **Data.** `training/generate.py` builds labelled queries from slot phrases ("under 15 lakh", "for a family of 7", "not diesel", "1.2 lakh km"), mixed in random order with filler words ("show me", "please", "for daily commute"). 8,000 queries are used for training.
2. **Training.** `scripts/train_model.py` trains the CRF (L1 and L2 regularisation, 200 iterations) on a laptop CPU in about 1.5 minutes. The model file is 84 KB and is committed in `models/`, so nobody has to train it before running the app.
3. **Evaluation.** `training/eval_queries.jsonl` holds 46 hand-written queries with their expected filters. They are written separately from the templates and are never used for training. Every parser is scored on them.

```bash
python scripts/train_model.py                 # retrain (make train)
python -m training.evaluate --show-errors     # compare parsers, list mistakes (make eval)
```

![Training output](images/terminal-train.png)

| Parser | Queries fully right | Precision | Recall | F1 |
|---|---|---|---|---|
| Rules | 61% | 93% | 79% | 86% |
| **Trained model** | **96%** | **97%** | **100%** | **98%** |

*Precision, recall and F1 are measured over individual filters. "Fully right" means every filter for the query is correct.*

The two queries it still gets wrong (shown by `--show-errors`): "my wife" gets read as a family car, and "i20" (a car model) gets read as a ₹20L budget.

**To be clear about the numbers:** the test queries and the training templates were written by the same person, so this test set is friendlier than real traffic will be. Treat the scores as a comparison between parsers, not as production accuracy. The way to get a trustworthy number is to collect real queries, label them (the LLM parser can do the first pass), and add them to both the test set and the training data. The training script and the test file already use that format.

## Why a CRF and not a neural network

| | CRF (this repo) | Fine-tuned transformer (DistilBERT, T5) |
|---|---|---|
| Training | 1.5 min on CPU | Needs a GPU, or hours on CPU |
| Size | 84 KB | 250 MB or more |
| Inference | 0.4 ms on CPU | 10 to 50 ms on CPU |
| Dependencies | `python-crfsuite` | PyTorch, transformers |
| Unseen phrasing | Weaker | Stronger |

For a search box that has to answer in milliseconds, the CRF is the better trade today. Once there are a few thousand labelled real queries, fine-tuning a small transformer on the same data is the natural next step. The data format, evaluation script and parser interface would stay the same (see [Alternative approaches](ALTERNATIVES.md)).

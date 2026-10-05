"""Score a parser on the hand-written queries in eval_queries.jsonl.

These queries are written separately from the training templates and are never
used for training.

    python -m training.evaluate              # rules vs trained model (and LLM if a key is set)
    python -m training.evaluate --show-errors
"""
import argparse
import json
from datetime import date
from pathlib import Path

EVAL_FILE = Path(__file__).with_name("eval_queries.jsonl")


def load() -> list[dict]:
    rows = [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]
    for r in rows:
        e = r["expected"]
        if "min_year_ago" in e:  # "not older than 3 years" depends on today's date
            e["min_year"] = date.today().year - e.pop("min_year_ago")
    return rows


def _pairs(d: dict) -> set:
    out = set()
    for k, v in d.items():
        if isinstance(v, list):
            out |= {(k, x) for x in v}
        elif v is not None:
            out.add((k, v))
    return out


def score(parse_fn, rows=None) -> dict:
    rows = rows or load()
    exact, tp, fp, fn, errors = 0, 0, 0, 0, []
    for r in rows:
        got = _pairs(parse_fn(r["q"]).model_dump(exclude_defaults=True))
        want = _pairs(r["expected"])
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
        if got == want:
            exact += 1
        else:
            errors.append((r["q"], sorted(want - got, key=str), sorted(got - want, key=str)))
    p = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    return {"queries": len(rows), "exact": exact / len(rows), "precision": p, "recall": rec,
            "f1": 2 * p * rec / (p + rec) if p + rec else 0, "errors": errors}


def report(parsers: dict, show_errors=False) -> str:
    rows = load()
    lines = [f"{'parser':<10} {'exact match':>12} {'precision':>10} {'recall':>8} {'F1':>6}"]
    results = {}
    for name, fn in parsers.items():
        s = results[name] = score(fn, rows)
        lines.append(f"{name:<10} {s['exact']:>11.0%} {s['precision']:>10.0%} {s['recall']:>8.0%} {s['f1']:>6.0%}")
    lines.append(f"\n{len(rows)} hand-written queries. Exact match = every filter right.")
    if show_errors:
        for name, s in results.items():
            lines.append(f"\n--- {name}: {len(s['errors'])} queries not exactly right")
            for q, missing, extra in s["errors"]:
                lines.append(f"  {q}\n      missing {missing}\n      extra   {extra}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()

    from app.config import get_settings
    from app.parser.llm import llm_parse
    from app.parser.model import get_model
    from app.parser.rules import rule_parse

    parsers = {"rules": rule_parse}
    if get_model():
        parsers["model"] = get_model().parse
    if get_settings().llm_enabled:
        from app.schemas import Filters
        parsers["llm"] = lambda q: llm_parse(q) or Filters()
    print(report(parsers, args.show_errors))

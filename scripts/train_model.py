"""Train the query tagger (CRF) and save it to models/query_tagger.crfsuite.

    python scripts/train_model.py                 # about 1.5 minutes on a laptop CPU
    python scripts/train_model.py --examples 20000
"""
import argparse
import sys
import textwrap
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pycrfsuite  # noqa: E402

from app.parser.model import DEFAULT_MODEL_PATH, ModelParser, sent_features  # noqa: E402
from app.parser.rules import rule_parse  # noqa: E402
from training import evaluate  # noqa: E402
from training.generate import generate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples", type=int, default=8000)
    ap.add_argument("--out", default=str(DEFAULT_MODEL_PATH))
    args = ap.parse_args()

    started = time.perf_counter()
    train = generate(args.examples, seed=7)
    held_out = generate(1000, seed=99)

    trainer = pycrfsuite.Trainer(verbose=False)
    for sent in train:
        tokens = [t for t, _ in sent]
        trainer.append(sent_features(tokens), [label for _, label in sent])
    trainer.set_params({"c1": 0.05, "c2": 0.01, "max_iterations": 200, "feature.possible_transitions": True})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    trainer.train(args.out)
    took = time.perf_counter() - started

    model = ModelParser(Path(args.out))
    correct = total = 0
    for sent in held_out:
        tokens = [t for t, _ in sent]
        _, tags = model.tag(" ".join(tokens))
        if len(tags) == len(sent):
            correct += sum(a == b for a, b in zip(tags, (label for _, label in sent)))
        total += len(sent)
    labels = Counter(label.split("-", 1)[-1] for sent in train for _, label in sent if label != "O")

    print(f"trained on {len(train):,} generated queries in {took:.1f}s -> {args.out} "
          f"({Path(args.out).stat().st_size / 1024:.0f} KB)")
    print(textwrap.fill(f"{len(labels)} slots: {', '.join(sorted(labels))}", 100, subsequent_indent="  "))
    print(f"token accuracy on 1,000 held-out generated queries: {correct / total:.1%}\n")
    print(evaluate.report({"rules": rule_parse, "model": model.parse}))


if __name__ == "__main__":
    main()

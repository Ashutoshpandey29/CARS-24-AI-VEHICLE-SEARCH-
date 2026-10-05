"""Query -> Filters, with caching.

Three parsers, tried in order until one gives an answer:

    llm    Claude, needs ANTHROPIC_API_KEY. Best on free-form language.
    model  Our CRF tagger trained on labelled queries (models/query_tagger.crfsuite).
    rules  Regular expressions. Always available.

PARSER=auto (default) uses the chain above. PARSER=llm|model|rules starts the
chain at that parser instead, e.g. PARSER=model never calls the LLM.

Results from the first-choice parser are cached for a day. A result from a
fallback is cached briefly, so the query is retried with the better parser soon.
"""
import json
from typing import Callable, Optional

from app.cache import get_cache
from app.config import get_settings
from app.parser.llm import llm_parse
from app.parser.model import get_model, model_parse
from app.parser.rules import rule_parse
from app.schemas import Filters

FALLBACK_TTL = 300
ORDER = ["llm", "model", "rules"]
PARSERS: dict[str, Callable[[str], Optional[Filters]]] = {"llm": llm_parse, "model": model_parse, "rules": rule_parse}


def normalize(query: str) -> str:
    return " ".join(query.lower().split())


def chain() -> list[str]:
    """Parsers that can run right now, best first."""
    s = get_settings()
    start = ORDER.index(s.parser) if s.parser in ORDER else 0
    available = {"llm": s.llm_enabled, "model": get_model() is not None, "rules": True}
    return [p for p in ORDER[start:] if available[p]]


def parse(query: str) -> tuple[Filters, str]:
    """Return (filters, source) where source is 'llm', 'model' or 'rules'."""
    norm = normalize(query)
    parsers = chain()
    cache = get_cache()
    key = f"parse:v2:{parsers[0]}:{norm}"
    if hit := cache.get(key):
        data = json.loads(hit)
        return Filters.model_validate(data["filters"]), data["source"]

    for source in parsers:
        filters = PARSERS[source](norm)
        if filters is not None:
            break
    ttl = get_settings().parse_cache_ttl if source == parsers[0] else FALLBACK_TTL
    cache.set(key, json.dumps({"filters": filters.model_dump(), "source": source}), ttl)
    return filters, source


__all__ = ["parse", "chain", "rule_parse", "llm_parse", "model_parse", "normalize"]

"""Query -> Filters, with caching.

LLM results are cached for a day. Rule results are cached briefly, so a query
that fell back to rules during an LLM outage gets retried with the LLM soon.
"""
import json

from app.cache import get_cache
from app.config import get_settings
from app.parser.llm import llm_parse
from app.parser.rules import rule_parse
from app.schemas import Filters

RULES_TTL = 300


def normalize(query: str) -> str:
    return " ".join(query.lower().split())


def parse(query: str) -> tuple[Filters, str]:
    """Return (filters, source) where source is 'llm' or 'rules'."""
    norm = normalize(query)
    cache = get_cache()
    key = f"parse:v1:{norm}"
    if hit := cache.get(key):
        data = json.loads(hit)
        return Filters.model_validate(data["filters"]), data["source"]

    filters = llm_parse(norm)
    source = "llm" if filters else "rules"
    filters = filters or rule_parse(norm)
    ttl = get_settings().parse_cache_ttl if source == "llm" else RULES_TTL
    cache.set(key, json.dumps({"filters": filters.model_dump(), "source": source}), ttl)
    return filters, source


__all__ = ["parse", "rule_parse", "llm_parse", "normalize"]

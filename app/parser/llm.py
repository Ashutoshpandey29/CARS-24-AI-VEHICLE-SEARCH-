"""Claude-based parser. Returns None on any failure so the caller can fall back to rules."""
import logging
from typing import Optional

from app.config import get_settings
from app.schemas import Filters
from app.vocab import CITIES, MAKES

log = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""You convert used-car search queries (Indian market) into search filters.
Conventions:
- Prices are absolute INR: 1L/lakh = 100000, 1cr = 10000000. "under 15L" -> max_price 1500000.
- "80k km" -> 80000. "below/under" sets max, "above/over" sets min.
- "automatic" covers AMT/CVT/DCT/AT. "family car" -> min_seats 5 and body_types [SUV, MUV, Sedan].
- "7 seater" -> min_seats 7. "safe"/"high safety rating" -> min_safety 4; "5 star" -> min_safety 5.
- "cheapest"/"budget" -> sort price_asc, "newest" -> year_desc, "low mileage"/"least driven" -> km_asc, "safest" -> safety_desc.
- Makes must be from: {', '.join(MAKES)}. Cities from: {', '.join(CITIES)}.
- Only set fields the query implies. Leave everything else empty/null."""

_client = None


def _get_client():
    global _client
    settings = get_settings()
    if _client is None and settings.llm_enabled:
        import anthropic

        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=settings.llm_timeout, max_retries=1)
    return _client


def llm_parse(query: str) -> Optional[Filters]:
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.messages.parse(
            model=get_settings().llm_model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},  # short extraction, no need for deep reasoning
            messages=[{"role": "user", "content": query}],
            output_format=Filters,
            # if a safety classifier declines, the API retries on another model instead of refusing
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={"fallbacks": "default"},
        )
    except Exception as e:  # network, auth, rate limit: log it and let the rules parser take over
        log.warning("LLM parse failed, falling back to rules: %s", e)
        return None
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        return None
    return resp.parsed_output

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


@dataclass(frozen=True)
class Settings:
    db_path: str
    anthropic_api_key: str | None
    llm_model: str
    llm_timeout: float
    parser: str
    model_path: str | None
    redis_url: str | None
    cache_size: int
    parse_cache_ttl: int
    result_cache_ttl: int
    count_cap: int
    log_level: str

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        db_path=os.getenv("DB_PATH", "data/cars.db"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        llm_model=os.getenv("LLM_MODEL", "claude-opus-5-5"),
        llm_timeout=float(os.getenv("LLM_TIMEOUT", "20")),
        parser=os.getenv("PARSER", "auto").lower(),
        model_path=os.getenv("MODEL_PATH") or None,
        redis_url=os.getenv("REDIS_URL") or None,
        cache_size=_env_int("CACHE_SIZE", 10_000),
        parse_cache_ttl=_env_int("PARSE_CACHE_TTL", 24 * 3600),
        result_cache_ttl=_env_int("RESULT_CACHE_TTL", 60),
        count_cap=_env_int("COUNT_CAP", 10_000),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

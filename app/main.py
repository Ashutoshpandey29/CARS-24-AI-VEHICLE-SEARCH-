import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import get_settings

STATIC = Path(__file__).parent / "static"

logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    log.info("db=%s parser=%s cache=%s", s.db_path, "llm" if s.llm_enabled else "rules",
             "redis" if s.redis_url else "memory")
    if not Path(s.db_path).exists():
        log.warning("%s not found, run `python scripts/seed.py` first", s.db_path)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Cars24 Vehicle Search",
    version="1.1.0",
    description="Search used cars in plain English, e.g. *Diesel automatic cars below 80k km*.",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(router)


@app.middleware("http")
async def timing(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Response-Time-ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC / "index.html")

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config import get_settings
from src.limits import limiter
from src.observability.langfuse import get_langfuse, shutdown_langfuse
from src.routes import chat, health, ingest, search

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("danny_rag.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log.info("Starting danny_rag api env=%s version=%s", settings.env, settings.api_version)
    get_langfuse()
    yield
    log.info("Shutting down — flushing Langfuse")
    shutdown_langfuse()


app = FastAPI(
    title="danny_rag api",
    version=get_settings().api_version,
    lifespan=lifespan,
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
    )


# MTC-06: explicit origin allowlist, never "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(ingest.router)

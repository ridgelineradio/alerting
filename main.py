import os
import json
import sentry_sdk
from uuid_extensions import uuid7str
from contextlib import asynccontextmanager

import redis.asyncio as redis
import requests
from fastapi import FastAPI, Query, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from services.live365.services import run_check

sentry_sdk.init(
    dsn="https://71a4a79653398bbbb12ee3fcc06c30bf@o4507009248067584.ingest.us.sentry.io/4507093378924544",
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)

# Redis client
redis_client = None

# Scheduler
scheduler = AsyncIOScheduler()


async def get_redis():
    """Get Redis client"""
    global redis_client
    if redis_client is None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        redis_client = redis.from_url(redis_url, decode_responses=True)
    return redis_client


async def get_state(key: str):
    """Get state from Redis"""
    r = await get_redis()
    value = await r.get(key)
    if value:
        return json.loads(value)
    return None


async def set_state(key: str, value: dict):
    """Set state in Redis"""
    r = await get_redis()
    await r.set(key, json.dumps(value))


async def run_live365_monitor():
    """Scheduled task to monitor Live365"""
    print("Running Live365 monitor...")
    state = await get_state("live365_state")
    previous_jwt = None

    if state:
        previous_jwt = state.get("token")

    async def save_token(token: str) -> None:
        await set_state("live365_state", {"token": token})

    try:
        await run_check(previous_jwt, save_token)
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        print(f"Error in Live365 monitor: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("Starting up...")
    await get_redis()  # Initialize Redis connection

    # Start scheduler
    scheduler.add_job(run_live365_monitor, 'interval', minutes=5, id='live365_monitor')
    scheduler.start()
    print("Scheduler started")

    yield

    # Shutdown
    print("Shutting down...")
    scheduler.shutdown()
    if redis_client:
        await redis_client.close()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    """Health check endpoint"""
    return {"status": "ok"}


@app.get("/silence")
async def silence_detector(secret: str = Query(..., description="Secret key for authentication")):
    """Endpoint to report silence detection"""
    if not secret:
        raise HTTPException(status_code=403, detail="No secret")

    try:
        if secret != os.environ.get("SILENCE_KEY"):
            raise HTTPException(status_code=403, detail="Invalid secret")
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise

    dedup_key = uuid7str()

    requests.post("https://events.pagerduty.com/v2/enqueue", json={
        "payload": {
            "summary": "Silence detected",
            "severity": "critical",
            "source": "PiraCZ"
        },
        "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
        "event_action": "trigger",
        "dedup_key": dedup_key,
    })

    await set_state("silence_key", {"key": dedup_key})

    return {"status": "ok"}


@app.get("/returned")
async def audio_returned(secret: str = Query(..., description="Secret key for authentication")):
    """Endpoint to report audio return"""
    if not secret:
        raise HTTPException(status_code=403, detail="No secret")

    try:
        if secret != os.environ.get("SILENCE_KEY"):
            raise HTTPException(status_code=403, detail="Invalid secret")
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise

    state = await get_state("silence_key")
    if not state:
        raise HTTPException(status_code=400, detail="No silence key found")

    dedup_key = state.get("key")

    requests.post("https://events.pagerduty.com/v2/enqueue", json={
        "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
        "dedup_key": dedup_key,
        "event_action": "resolve",
    })

    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

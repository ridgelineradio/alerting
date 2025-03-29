import sentry_sdk
from uuid_extensions import uuid7str

sentry_sdk.init(
    dsn="https://71a4a79653398bbbb12ee3fcc06c30bf@o4507009248067584.ingest.us.sentry.io/4507093378924544",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)

import os
import requests

from live365.services import run_check

from nitric.resources import api, schedule, kv
from nitric.application import Nitric
from nitric.context import HttpContext
from nitric.exception import NotFoundException


monitor_state = kv("monitor-state").allow("get", "set")
live365_monitor_app = schedule("live365-monitor")


@live365_monitor_app.every("5 minutes")
async def run_live365_monitor(ctx):
    previous_jwt = None

    try:
        previous_jwt = (await monitor_state.get("previous_live365_token")).get("token")
    except NotFoundException:
        pass

    async def save_token(token: str) -> None:
        await monitor_state.set("previous_live365_token", {"token": token})

    await run_check(previous_jwt, save_token)


main = api("silence-api")


@main.get("/healthz")
async def healthz(ctx: HttpContext):
    ctx.res.body = "ok"


@main.get("/silence")
async def silence_detector(ctx: HttpContext):
    secret = ctx.req.query.get("secret")

    if not secret:
        ctx.res.status = 403
        ctx.res.body = {"error": "No secret"}
        return

    try:
        if secret[0] != os.environ.get("SILENCE_KEY"):
            ctx.res.status = 403
            ctx.res.body = {"error": "Invalid secret"}
            return
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

    await monitor_state.set("silence_key", {"key": dedup_key})

    ctx.res.status = 200
    ctx.res.body = "ok"


@main.get("/returned")
async def audio_returned(ctx: HttpContext):
    secret = ctx.req.query.get("secret")

    if not secret:
        ctx.res.status = 403
        ctx.res.body = {"error": "No secret"}
        return

    try:
        if secret[0] != os.environ.get("SILENCE_KEY"):
            ctx.res.status = 403
            ctx.res.body = {"error": "Invalid secret"}
            return
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        raise

    dedup_key = (await monitor_state.get("silence_key")).get("key")

    requests.post("https://events.pagerduty.com/v2/enqueue", json={
        "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
        "dedup_key": dedup_key,
        "event_action": "resolve",
    })

    ctx.res.status = 200
    ctx.res.body = "ok"


Nitric.run()

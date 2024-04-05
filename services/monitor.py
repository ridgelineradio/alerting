from nitric.resources import api, schedule, kv
from nitric.application import Nitric
from nitric.context import HttpContext


import os
import requests

from services.live365.services import run_check

main = api("monitor")


@main.get("/silence")
async def silence_detector(ctx: HttpContext):
    secret = ctx.req.query.get("secret")

    if secret[0] != os.environ.get("SILENCE_KEY"):
        ctx.res.status = 403
        ctx.res.body = {"error": "Invalid secret"}
        return

    requests.post("https://events.pagerduty.com/v2/enqueue", json={
        "payload": {
            "summary": "Silence detected",
            "severity": "critical",
            "source": "PiraCZ"
        },
        "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
        "event_action": "trigger"
    })
    ctx.res.status = 200
    ctx.res.body = "ok"


live365_previous_jwt = kv("live365monitor").allow("get", "set")
live365_monitor_app = schedule("live365monitor")


@live365_monitor_app.every("5 minutes")
async def run_live365_monitor(ctx):
    try:
        previous_jwt = (await live365_previous_jwt.get("previous_token")).get("token")
    except Exception as exc:
        # TODO: send exception to Sentry
        previous_jwt = None

    async def save_token(token: str) -> None:
        await live365_previous_jwt.set("previous_token", {"token": token})

    await run_check(previous_jwt, save_token)


Nitric.run()

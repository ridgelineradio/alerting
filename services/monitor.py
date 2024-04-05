from nitric.resources import api, schedule, kv, secret
from nitric.application import Nitric
from nitric.context import HttpContext


import os
import requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from pydantic import BaseModel
from typing import Any, Callable, Literal
import jwt


class Live365StationAttributes(BaseModel):
    twitter_url: Any
    mount_password: str
    ls_hostname: str
    source: str
    status: str
    logo_extension: str
    timezone: str
    mount_username: str
    website: str
    name: str
    description: str
    on_air: bool
    slug: str
    cover_uuid: str
    in_beta_program: bool
    is_being_migrated: bool
    genres: list[int]
    organization_id: str
    ftp_password: str
    ingest_hostname: str
    media_service_uuid: str
    logo_file_size_bytes: int
    cover_file_size_bytes: int
    facebook_url: Any
    cover_extension: str
    logo_uuid: str
    ftp_username: str
    mount_id: str
    instagram_url: Any


class Live365Station(BaseModel):
    id: str
    links: Any
    type: Literal["stations"]
    attributes: Live365StationAttributes


class Live365Stations(BaseModel):
    data: list[Live365Station]
    jsonapi: Any
    links: Any
    meta: Any


async def get_live365_access_token(session, save_token: Callable[[str], None] = None):
    live365_email = os.environ.get("LIVE365_EMAIL")
    live365_password = os.environ.get("LIVE365_PASSWORD")

    assert (
        live365_email and live365_password
    ), "LIVE365_EMAIL and LIVE365_PASSWORD must be set in environment variables"

    login_page = session.get("https://accounts.live365.com/login")

    soup = BeautifulSoup(login_page.content, "html.parser")

    csrf_token = soup.find("input", {"name": "csrf_token"}).get("value")
    print("csrf token is", csrf_token)

    login_reply = session.post(
        "https://accounts.live365.com/login?next=%2Foauth2%2Fauthorize%3Fclient_id%3Dbroadcaster-frontend%26response_type%3Dtoken%26scope%3Dprofile%26redirect_uri%3Dhttps%253A%252F%252Fdashboard.live365.com%252Foauth2%252Fcallback",
        data={
            "email": live365_email,
            "password": live365_password,
            "csrf_token": csrf_token,
        },
        headers={"Referer": "https://accounts.live365.com/login"},
        allow_redirects=False,
    )

    authorize_reply = session.get(
        login_reply.headers["location"],
        allow_redirects=False,
    )

    url = urlparse(authorize_reply.headers["location"])
    access_token = parse_qs(url.fragment)["access_token"][0]

    if save_token:
        await save_token(access_token)

    return access_token


async def run_check(previous_jwt: str, save_token: Callable[[str], None]):
    session = requests.Session()

    access_token = None

    try:
        if previous_jwt:
            jwt.decode(
                previous_jwt.encode("utf-8"),
                options={"verify_signature": False, "verify_exp": True},
            )
            access_token = previous_jwt
            print("Using previous access token! hooray!")
    except Exception as exc:
        # TODO: capture exception in Sentry
        print(exc)

    if not access_token:
        access_token = await get_live365_access_token(session, save_token)

    stations_reply = session.get(
        "https://dashboard.live365.com/api/v1/stations/",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    stations = stations_reply.json()

    print(stations)

    stations = Live365Stations.model_validate(stations)

    if stations.data[0].attributes.source != "Relay":
        requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "payload": {
                    "summary": "Live365 Station not relaying",
                    "severity": "critical",
                    "source": "Live365 Monitor",
                },
                "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
                "event_action": "trigger",
            },
        )


main = api("monitor")


@main.get("/silence")
async def silence_detector(ctx: HttpContext):
    secret = ctx.req.query.get("secret")

    if secret[0] != os.environ.get("SILENCE_KEY"):
        ctx.res.status = 403;
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


live365_previous_jwt = kv("live365monitor").allow("get", "set")
live365_monitor_app = schedule("live365monitor")


@live365_monitor_app.every("5 minutes")
async def run_live365_monitor(ctx):
    try:
        previous_jwt = (await live365_previous_jwt.get("previous_token")).get("token")
    except Exception as exc:
        # TODO: send exception to Sentry
        previous_jwt = None

    async def save_token(token):
        await live365_previous_jwt.set("previous_token", {"token": token})

    await run_check(previous_jwt, save_token)


Nitric.run()

import os
from typing import Callable, Coroutine, Awaitable
from urllib.parse import urlparse, parse_qs

import jwt
import requests
import sentry_sdk

from bs4 import BeautifulSoup

from live365.models import Live365Stations


class Live365AutoLoginException(Exception):
    pass


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

    try:
        authorize_reply = session.get(
            login_reply.headers["location"],
            allow_redirects=False,
        )
    except KeyError:
        sentry_sdk.capture_message(f"Failed to get authorize reply {login_reply.status_code}")
        print(login_reply.status_code)
        print(login_reply.content)
        raise Live365AutoLoginException()

    try:
        url = urlparse(authorize_reply.headers["location"])
        access_token = parse_qs(url.fragment)["access_token"][0]
    except KeyError:
        sentry_sdk.capture_message("Failed to get access token and URL")
        print(authorize_reply.status_code)
        print(authorize_reply.content)
        raise Live365AutoLoginException()

    if save_token:
        await save_token(access_token)

    return access_token


async def run_check(previous_jwt: str | None, save_token):
    print("Running the check!")
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
        sentry_sdk.capture_exception(exc)
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

    if stations.data[0].attributes.source not in ("Relay", "Live"):
        requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json={
                "payload": {
                    "summary": "Live365 Station not relaying",
                    "severity": "warning",
                    "source": "Live365 Monitor",
                },
                "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY"),
                "event_action": "trigger",
                "dedup_key": "live365",
            },
        )

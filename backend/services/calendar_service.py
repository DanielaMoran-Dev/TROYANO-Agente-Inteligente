"""
Calendar Service — Google Calendar, Microsoft Outlook (Graph API), and CalDAV (Apple).
Provides a unified interface to create/confirm/cancel appointment events.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------

def google_oauth_url(redirect_uri: str, state: str = "") -> str:
    scope = "https://www.googleapis.com/auth/calendar.events"
    return (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope={scope}&state={state}&access_type=offline"
    )


async def google_exchange_code(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_google_event(access_token: str, event: dict) -> dict:
    """Create a Calendar event. event must follow Google Calendar API format."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=event,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Microsoft Graph (Outlook)
# ---------------------------------------------------------------------------

async def microsoft_exchange_code(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "code": code,
                "client_id": MICROSOFT_CLIENT_ID,
                "client_secret": MICROSOFT_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "scope": "Calendars.ReadWrite",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_outlook_event(access_token: str, event: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://graph.microsoft.com/v1.0/me/events",
            headers={"Authorization": f"Bearer {access_token}"},
            json=event,
        )
        resp.raise_for_status()
        return resp.json()

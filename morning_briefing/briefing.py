#!/usr/bin/env python3
"""Morning briefing script: fetches emails and calendar events, summarises with Claude, emails the result."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anthropic
import msal
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────

USER_EMAIL = "ethan.yap@qualitas.com.au"
AZURE_CLIENT_ID = os.environ["AZURE_CLIENT_ID"]
AZURE_TENANT_ID = os.environ["AZURE_TENANT_ID"]
TOKEN_CACHE_PATH = Path.home() / ".morning_briefing_token_cache.json"

GRAPH_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.Read",
]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ── Token cache helpers ───────────────────────────────────────────────────────

def _load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE_PATH.exists():
        cache.deserialize(TOKEN_CACHE_PATH.read_text())
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        TOKEN_CACHE_PATH.write_text(cache.serialize())


def _build_msal_app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    return msal.PublicClientApplication(
        client_id=AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        token_cache=cache,
    )


def acquire_token() -> str:
    """Return a valid Graph API access token, using device code flow on first run."""
    cache = _load_token_cache()
    app = _build_msal_app(cache)

    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            return result["access_token"]

    # First run or cache expired — device code flow
    flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow initiation failed: {flow.get('error_description')}")

    print(flow["message"])  # Instructs user to visit the URL and enter the code
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Authentication failed: {result.get('error_description')}")

    _save_token_cache(cache)
    return result["access_token"]


# ── Graph API helpers ─────────────────────────────────────────────────────────

def _graph_get(token: str, path: str, params: dict | None = None) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_unread_emails(token: str) -> list[dict]:
    """Fetch unread emails from the Inbox received in the last 24 hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "$filter": f"isRead eq false and receivedDateTime ge {since}",
        "$select": "subject,from,receivedDateTime,bodyPreview,importance",
        "$orderby": "receivedDateTime desc",
        "$top": 50,
    }
    data = _graph_get(token, "/me/mailFolders/Inbox/messages", params)
    return data.get("value", [])


def fetch_today_events(token: str) -> list[dict]:
    """Fetch calendar events for today."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    params = {
        "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "$select": "subject,start,end,location,organizer,isOnlineMeeting,importance",
        "$orderby": "start/dateTime",
        "$top": 50,
    }
    data = _graph_get(token, "/me/calendarView", params)
    return data.get("value", [])


def send_email(token: str, subject: str, html_body: str) -> None:
    """Send the briefing email to the user's own mailbox."""
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": USER_EMAIL}}],
        },
        "saveToSentItems": True,
    }
    resp = requests.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


# ── Data formatting for the prompt ───────────────────────────────────────────

def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        local_offset = datetime.now().astimezone().utcoffset()
        dt = dt.astimezone(timezone(local_offset))
        return dt.strftime("%H:%M")
    except Exception:
        return iso


def format_events(events: list[dict]) -> str:
    if not events:
        return "No events scheduled for today."
    lines = []
    for e in events:
        start = _fmt_time(e.get("start", {}).get("dateTime", ""))
        end = _fmt_time(e.get("end", {}).get("dateTime", ""))
        location = e.get("location", {}).get("displayName", "")
        online = " [Online]" if e.get("isOnlineMeeting") else ""
        loc_str = f" @ {location}" if location else ""
        lines.append(f"- {start}–{end}: {e['subject']}{loc_str}{online}")
    return "\n".join(lines)


def format_emails(emails: list[dict]) -> str:
    if not emails:
        return "No unread emails in the last 24 hours."
    lines = []
    for e in emails:
        sender = e.get("from", {}).get("emailAddress", {})
        name = sender.get("name", sender.get("address", "Unknown"))
        importance = " [HIGH]" if e.get("importance") == "high" else ""
        received = e.get("receivedDateTime", "")[:16].replace("T", " ")
        preview = e.get("bodyPreview", "")[:200].replace("\n", " ")
        lines.append(
            f"From: {name}{importance}\n"
            f"Subject: {e['subject']}\n"
            f"Received: {received}\n"
            f"Preview: {preview}\n"
        )
    return "\n---\n".join(lines)


# ── Claude summary ────────────────────────────────────────────────────────────

def generate_briefing(events_text: str, emails_text: str) -> str:
    today = datetime.now().strftime("%A, %d %B %Y")

    prompt = f"""You are an executive assistant preparing a concise morning briefing for {USER_EMAIL} on {today}.

Below is today's calendar data and unread inbox data from the last 24 hours.

---CALENDAR---
{events_text}

---EMAILS---
{emails_text}

Produce a professional morning briefing with exactly these three sections:

## Today's Calendar
List each event with time, title, and any important details (location, online meeting).

## Email Summary
Group emails by priority/sender. Highlight high-importance or time-sensitive messages first. For each email note the sender, subject, and a one-sentence summary of the preview.

## Action Items
Extract clear action items or follow-ups implied by the emails. Be specific (e.g. "Reply to John Smith re: contract renewal" rather than "respond to email").

Keep the briefing concise, scannable, and formatted for email. Use Markdown."""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text")


# ── Markdown → basic HTML ─────────────────────────────────────────────────────

def markdown_to_html(md: str) -> str:
    """Minimal Markdown → HTML conversion sufficient for email display."""
    import re

    lines = md.split("\n")
    html_lines = []
    in_ul = False

    for line in lines:
        if line.startswith("## "):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            item = line[2:]
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            html_lines.append(f"<li>{item}</li>")
        elif line.strip() == "":
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("<br>")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            html_lines.append(f"<p>{line}</p>")

    if in_ul:
        html_lines.append("</ul>")

    body = "\n".join(html_lines)
    return f"""<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;color:#222;">
{body}
</body></html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Acquiring Microsoft Graph token…")
    token = acquire_token()

    print("Fetching calendar events…")
    events = fetch_today_events(token)
    print(f"  → {len(events)} event(s) found.")

    print("Fetching unread emails…")
    emails = fetch_unread_emails(token)
    print(f"  → {len(emails)} unread email(s) found.")

    print("Generating briefing with Claude…")
    briefing_md = generate_briefing(
        events_text=format_events(events),
        emails_text=format_emails(emails),
    )

    today_label = datetime.now().strftime("%A %d %B")
    subject = f"☀️ Morning Briefing — {today_label}"
    html_body = markdown_to_html(briefing_md)

    print("Sending briefing email…")
    send_email(token, subject, html_body)
    print(f"Briefing sent to {USER_EMAIL}.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)

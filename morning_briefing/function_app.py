"""Azure Function: timer-triggered morning briefing using app-only Graph auth."""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import anthropic
import azure.functions as func
import requests

app = func.FunctionApp()

USER_EMAIL = "ethan.yap@qualitas.com.au"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ── Auth (client credentials — no interactive login) ─────────────────────────

def _acquire_token() -> str:
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]

    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


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
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "$filter": f"isRead eq false and receivedDateTime ge {since}",
        "$select": "subject,from,receivedDateTime,bodyPreview,importance",
        "$orderby": "receivedDateTime desc",
        "$top": 50,
    }
    # App-only: /users/{email}/... instead of /me/...
    data = _graph_get(token, f"/users/{USER_EMAIL}/mailFolders/Inbox/messages", params)
    return data.get("value", [])


def fetch_today_events(token: str) -> list[dict]:
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
    data = _graph_get(token, f"/users/{USER_EMAIL}/calendarView", params)
    return data.get("value", [])


def send_email(token: str, subject: str, html_body: str) -> None:
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": USER_EMAIL}}],
        },
        "saveToSentItems": True,
    }
    resp = requests.post(
        f"{GRAPH_BASE}/users/{USER_EMAIL}/sendMail",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


# ── Data formatting ───────────────────────────────────────────────────────────

def _fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        # Render in AEST (UTC+10)
        aest = timezone(timedelta(hours=10))
        return dt.astimezone(aest).strftime("%H:%M")
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
    today = datetime.now(timezone(timedelta(hours=10))).strftime("%A, %d %B %Y")

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

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(b.text for b in response.content if b.type == "text")


# ── Markdown → HTML ───────────────────────────────────────────────────────────

def markdown_to_html(md: str) -> str:
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
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:])
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
    return (
        '<html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;color:#222;">\n'
        + body
        + "\n</body></html>"
    )


# ── Timer trigger: runs at 07:30 AEST (21:30 UTC) Mon–Fri ────────────────────

@app.timer_trigger(
    schedule="0 30 21 * * 1-5",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def morning_briefing(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("Timer is past due — running anyway.")

    logging.info("Acquiring Microsoft Graph token…")
    token = _acquire_token()

    logging.info("Fetching calendar events…")
    events = fetch_today_events(token)
    logging.info("%d event(s) found.", len(events))

    logging.info("Fetching unread emails…")
    emails = fetch_unread_emails(token)
    logging.info("%d unread email(s) found.", len(emails))

    logging.info("Generating briefing with Claude…")
    briefing_md = generate_briefing(
        events_text=format_events(events),
        emails_text=format_emails(emails),
    )

    today_label = datetime.now(timezone(timedelta(hours=10))).strftime("%A %d %B")
    subject = f"Morning Briefing — {today_label}"
    html_body = markdown_to_html(briefing_md)

    logging.info("Sending briefing email…")
    send_email(token, subject, html_body)
    logging.info("Briefing sent to %s.", USER_EMAIL)

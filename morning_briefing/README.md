# Morning Briefing

Fetches unread emails and today's calendar events from your Microsoft 365 account, generates a concise summary using Claude, and emails the briefing to you.

## Prerequisites

- Python 3.10+
- A Microsoft 365 / Outlook account (ethan.yap@qualitas.com.au)
- An Azure AD app registration (see below)
- An Anthropic API key

---

## 1. Register an Azure AD App

1. Sign in to [portal.azure.com](https://portal.azure.com) with an admin or developer account in your tenant.
2. Go to **Azure Active Directory → App registrations → New registration**.
   - Name: `Morning Briefing` (or anything you like)
   - Supported account types: **Accounts in this organizational directory only**
   - Redirect URI: leave blank (not needed for device code flow)
3. Click **Register**. Copy the **Application (client) ID** — this is `AZURE_CLIENT_ID`.
4. Copy the **Directory (tenant) ID** from the Overview page — this is `AZURE_TENANT_ID`.
5. Go to **Authentication** and enable **Allow public client flows** (toggle to Yes). Save.
6. Go to **API permissions → Add a permission → Microsoft Graph → Delegated permissions**.
   Add:
   - `Mail.Read`
   - `Mail.Send`
   - `Calendars.Read`
7. Click **Grant admin consent** (requires admin privileges), or have a tenant admin do this.

---

## 2. Set Up Environment Variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```
AZURE_CLIENT_ID=<your app's client ID>
AZURE_TENANT_ID=<your tenant ID>
ANTHROPIC_API_KEY=<your Anthropic API key>
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. First Run (Device Code Authentication)

On the first run the script will print a URL and a one-time code:

```
To sign in, use a web browser to open the page https://microsoft.com/devicelogin
and enter the code XXXXXXXXX to authenticate.
```

Open the URL in your browser, enter the code, and sign in with `ethan.yap@qualitas.com.au`. After successful authentication the token is cached at `~/.morning_briefing_token_cache.json` and subsequent runs skip the browser step.

```bash
python briefing.py
```

---

## 5. Schedule with Cron

To run the briefing automatically every weekday at 7:30 AM:

```bash
crontab -e
```

Add:

```cron
30 7 * * 1-5 /usr/bin/python3 /home/user/Work/morning_briefing/briefing.py >> /home/user/Work/morning_briefing/briefing.log 2>&1
```

Adjust the Python path as needed (`which python3` to find it). The script uses `.env` in its own directory, so make sure `python-dotenv` is installed in the environment that cron uses, or export the variables directly in your crontab:

```cron
30 7 * * 1-5 AZURE_CLIENT_ID=xxx AZURE_TENANT_ID=yyy ANTHROPIC_API_KEY=zzz /usr/bin/python3 /home/user/Work/morning_briefing/briefing.py
```

---

## Token Cache

The MSAL token cache is stored at `~/.morning_briefing_token_cache.json`. It contains refresh tokens that allow silent re-authentication without the device code flow. Protect this file:

```bash
chmod 600 ~/.morning_briefing_token_cache.json
```

If you ever need to force re-authentication (e.g. after changing API permissions), delete the cache file and run the script again.

---

## Output

The script sends an HTML email to `ethan.yap@qualitas.com.au` with three sections:

- **Today's Calendar** — all events for today with times and locations
- **Email Summary** — unread emails from the last 24 hours, grouped by priority
- **Action Items** — extracted follow-ups and tasks from your inbox

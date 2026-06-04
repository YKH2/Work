# Morning Briefing — Azure Function

Timer-triggered Azure Function that fetches your Outlook emails and calendar events, summarises them with Claude, and emails you a briefing at 7:30 AM AEST (Mon–Fri).

Uses **app-only (client credentials) auth** — no interactive login, runs fully unattended in the cloud.

---

## Prerequisites

- Azure subscription
- Microsoft 365 / Exchange Online mailbox
- Anthropic API key

---

## 1. Register an Azure AD App

1. Go to [Azure Portal → App registrations → New registration](https://portal.azure.com/#blade/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/RegisteredApps)
2. Name it `morning-briefing`, leave defaults, click **Register**
3. Note the **Application (client) ID** and **Directory (tenant) ID**
4. Go to **Certificates & secrets → New client secret**, set an expiry, copy the secret value

### API Permissions (Application, not Delegated)

Add these **Application** permissions and grant admin consent:

| Permission | Type | Purpose |
|---|---|---|
| `Mail.Read` | Application | Read inbox |
| `Mail.Send` | Application | Send briefing email |
| `Calendars.Read` | Application | Read calendar |

> **Admin consent required.** An M365 admin must click **Grant admin consent** for your tenant.

---

## 2. Create the Azure Function App

```bash
# Install Azure Functions Core Tools if needed
npm install -g azure-functions-core-tools@4

# Create a resource group and storage account
az group create --name morning-briefing-rg --location australiaeast
az storage account create --name mbriefstorage --resource-group morning-briefing-rg --sku Standard_LRS

# Create the Function App (Python 3.11)
az functionapp create \
  --resource-group morning-briefing-rg \
  --consumption-plan-location australiaeast \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name morning-briefing-fn \
  --storage-account mbriefstorage \
  --os-type linux
```

---

## 3. Configure Application Settings

```bash
az functionapp config appsettings set \
  --name morning-briefing-fn \
  --resource-group morning-briefing-rg \
  --settings \
    AZURE_CLIENT_ID="<your-client-id>" \
    AZURE_TENANT_ID="<your-tenant-id>" \
    AZURE_CLIENT_SECRET="<your-client-secret>" \
    ANTHROPIC_API_KEY="<your-anthropic-key>"
```

---

## 4. Deploy

```bash
cd morning_briefing
func azure functionapp publish morning-briefing-fn
```

---

## 5. Schedule

The function runs on cron schedule `0 30 21 * * 1-5` (UTC), which is **7:30 AM AEST Mon–Fri**.

To change the time, edit the `schedule` parameter in `function_app.py`:

```
"0 30 21 * * 1-5"
 |  |  |  |  |  +-- Mon-Fri
 |  |  |  +--------- every month
 |  |  +------------ 21:00 UTC = 07:00 AEST  (change this hour)
 |  +--------------- :30 minutes
 +------------------ :00 seconds
```

---

## Local development

```bash
pip install -r requirements.txt
```

Create `local.settings.json` (not committed):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_CLIENT_ID": "...",
    "AZURE_TENANT_ID": "...",
    "AZURE_CLIENT_SECRET": "...",
    "ANTHROPIC_API_KEY": "..."
  }
}
```

Then run:

```bash
func start
```

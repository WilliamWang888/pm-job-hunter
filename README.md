# pm-job-hunter

> Daily Senior+ PM AI/ML job hunter — fetches from Greenhouse, Lever, and Ashby public APIs, filters by level / location / AI signal, dedupes, LLM-reranks the top 30, exports a local Excel tracker, and emails an HTML digest every morning at 8 AM.

Built as an **Agency Copilot skill** (compatible with the [Agency Cowork](https://github.com/WilliamWang888/daily-ai-news) skill pattern). Designed to surface the **15 highest-fit Senior / Staff / Principal / Group / Director PM roles in AI / ML** every morning so you spend zero time scrolling job boards and all your time on tailored applications.

---

## Daily email digest

Lands in your Outlook inbox every morning at 8 AM, sorted by LLM fit score with one-sentence rationale, direct apply links, and color-coded scores (green ≥ 80, amber 60–79, gray < 60):

![Daily email digest](docs/screenshots/email-digest.png)

## Local Excel tracker

Auto-refreshed every run from the SQLite source of truth. Edit the **Status** column in Excel to track applications (`Matched` → `Applied` → `Interview` → `Offer`/`Rejected`/`Passed`); changes sync back via `sync_tracker.py`:

![Excel tracker](docs/screenshots/excel-tracker.png)

---

## What it does

Every morning at 8:00 AM local:

1. **Fetches** ~5,000+ open roles across **34 hand-picked AI companies** (frontier labs, AI product companies, AI infra, data platforms, dev tools, AI-forward fintech) from public ATS APIs — no scraping, no API keys required.
2. **Filters** to Senior / Staff / Principal / Group / Lead / Director / Head / VP **Product Manager** roles only, in **SF Bay / Seattle / NYC / Remote-US**, with **AI/ML signal** in the title or description.
3. **Dedupes** identical postings across multiple cities into a single row.
4. **LLM-reranks** the top 30 candidates against your `profile.yaml` (must-haves, nice-to-haves, target stage, etc.) and produces a 0–100 fit score plus a one-sentence rationale.
5. **Persists** everything to a local SQLite database and refreshes a clean **Excel tracker** with editable status columns (Applied / Interview / Offer / Rejected / Passed).
6. **Emails** you an HTML digest with a sortable table — score color-coded, direct apply links, why-it-matches blurbs.

Sample top 3 from a real run:

| # | Company    | Role                                  | Score | Why                                                                  |
|---|------------|---------------------------------------|-------|----------------------------------------------------------------------|
| 1 | Databricks | Staff PM, AI Platform                 | 94    | Core AI/ML platform role (MLflow, model serving, LLM infra)          |
| 2 | Anthropic  | Senior PM, Education Labs             | 90    | Senior PM owning AI-native learning product at a frontier lab         |
| 3 | Scale AI   | Staff PM, Agentic Platform            | 88    | Direct 0-to-1 agentic product leadership matches goals               |

---

## Why I built it

Job boards are a firehose of low-signal listings. As a Senior PM trying to move into AI-native product work, ~98% of "Product Manager" results were noise (Marketing PMs, Program Managers, Product Designers, Legal Counsel "Product"). I wanted a tool that respected my actual filters:

- **Seniority bar:** Senior+ only — no IC1/IC2 reposts
- **Domain:** must be **directly working on AI/ML products**, not "AI-adjacent" fintech
- **Geography:** SF / Seattle / NYC / Remote-US
- **No spam:** dedupe across multi-city listings, suppress jobs already seen yesterday

Existing aggregators don't get any of these right. This script does.

---

## Architecture

```
                ┌─────────────────────┐
                │   companies.yaml    │  ~34 companies × 1 ATS endpoint each
                └──────────┬──────────┘
                           │
                           ▼
         ┌─────────────────────────────────┐
         │   scripts/fetch_jobs.py         │  ThreadPool, 8 workers, 15s timeout
         │   greenhouse | lever | ashby    │
         └────────────────┬────────────────┘
                          │  raw_jobs.json (~5,600 jobs)
                          ▼
         ┌─────────────────────────────────┐
         │   scripts/pipeline.py           │  level + location + AI signal
         │   regex filter → fuzzy dedupe   │  rapidfuzz token_set_ratio ≥ 92
         │   → SQLite upsert               │  fingerprint = sha1(company|title)
         └────────────────┬────────────────┘
                          │  candidates.json (top 30)
                          ▼
         ┌─────────────────────────────────┐
         │   LLM rerank (Agency Copilot)   │  read profile.yaml + JD
         │   produces score 0–100 + why    │  → ranked.json (top 15)
         └────────────────┬────────────────┘
                          │
                          ▼
         ┌─────────────────────────────────┐
         │   scripts/finalize.py           │  persist scores, refresh Excel,
         │                                 │  emit digest.json
         └────────────────┬────────────────┘
                          │
                          ▼
         ┌─────────────────────────────────┐
         │   send-email skill              │  HTML digest → your Outlook inbox
         └─────────────────────────────────┘
```

**Why this split?** Heavy lifting (5,600+ HTTP calls, regex filtering, fuzzy dedupe, SQLite I/O, openpyxl) runs in deterministic Python — fast, debuggable, no LLM cost. The LLM only sees the **30 pre-filtered candidates** for nuanced ranking + email composition. End-to-end runs in **~7.5 min** scheduled.

---

## Repository layout

```
pm-job-hunter/
├── README.md
├── skill.json                          # Skill metadata (Agency Copilot)
└── skills/pm-job-hunter/
    ├── SKILL.md                        # 6-step workflow the agent follows
    ├── config/
    │   ├── companies.yaml              # 34 companies × ATS source + board_id
    │   └── profile.yaml                # Your must-haves, locations, AI keywords
    ├── scripts/
    │   ├── fetch_jobs.py               # Parallel ATS fetchers
    │   ├── pipeline.py                 # Filter + dedupe + SQLite persist
    │   ├── finalize.py                 # Score persist + Excel refresh + digest
    │   ├── sync_tracker.py             # Excel status → SQLite (manual sync)
    │   └── probe_boards.py             # Discover correct board_ids
    └── data/                           # Generated, gitignored
        ├── tracker.db                  # SQLite source of truth
        ├── JobTracker.xlsx             # Your editable application log
        ├── raw_jobs.json               # Latest fetch
        ├── candidates.json             # Pre-rerank
        ├── ranked.json                 # LLM scores
        └── digest.json                 # Email payload
```

---

## Configuration

### `config/profile.yaml` — your matching criteria

```yaml
profile_summary: |
  Senior PM (10+ yrs) targeting Staff/Principal AI-native product roles.
  Must be directly working on AI/ML products — not AI-adjacent fintech.
  Strong preference for frontier labs and AI infra (model serving,
  agents, LLM tooling, dev platforms).

target_locations:
  - San Francisco
  - Bay Area
  - Seattle
  - New York
  - NYC
  - Remote

ai_signal_keywords:
  - llm
  - foundation model
  - generative ai
  - agentic
  - rag
  - inference
  - ml platform
  - model serving
  - fine-tun

master_resume_path: ""   # v0.2 — leave empty for v0.1
```

### `config/companies.yaml` — the watch list

Each company maps to **one** ATS source. All 34 board IDs in the default config have been **live-probed** and confirmed to return jobs. To add a company:

1. Find its careers page → check the URL pattern:
   - `boards.greenhouse.io/<slug>` → `source: greenhouse`, `board_id: <slug>`
   - `jobs.lever.co/<slug>` → `source: lever`, `board_id: <slug>`
   - `jobs.ashbyhq.com/<slug>` → `source: ashby`, `board_id: <slug>`
2. Or run the probe utility:
   ```powershell
   python scripts/probe_boards.py "Stripe" "Notion" "Some New Co"
   ```
3. Add to `companies.yaml`. Done.

> **Big Tech (Google / Meta / MSFT / Amazon)** uses Workday, which doesn't expose a public list endpoint. Coverage of those is planned for v0.3.

---

## Usage

### Daily (scheduled — set this up once)

The skill registers itself with the Agency Copilot **task-scheduler**:

```
Task ID:  daily-pm-job-hunter
Schedule: 0 15 * * *   (UTC = 8 AM PDT)
Timeout:  15 minutes
```

Just leave your laptop on. The full pipeline runs and the digest lands in your inbox at 8 AM.

### On-demand (run it any time)

Invoke via Agency Copilot:

> *"run job hunter"* / *"find me PM jobs"* / *"refresh jobs"*

Or directly:

```powershell
& "<path>/task-scheduler/scripts/task-manager.ps1" run -Id daily-pm-job-hunter
```

### Sync your Excel edits back to SQLite

After you mark statuses (Applied / Interview / etc.) in `data/JobTracker.xlsx`, push them back:

> *"sync job tracker"*

Or:

```powershell
python scripts/sync_tracker.py --excel data/JobTracker.xlsx --db data/tracker.db
```

---

## Setup on your own machine

Works on **macOS, Linux, and Windows**. The fetch / filter / dedupe / Excel /
SQLite pipeline is pure Python and is fully cross-platform. The only piece
that differs by OS is **how the email gets sent**:

| Platform | Default email backend | Requirements |
|---|---|---|
| **Windows + Outlook desktop** | `outlook` (COM automation) | Outlook installed and signed in |
| **macOS / Linux / Windows w/o Outlook** | `smtp` | Any SMTP account (Gmail, iCloud, Outlook.com, Fastmail, your own…) |

### 1. Clone the repo

```bash
git clone https://github.com/WilliamWang888/pm-job-hunter.git
cd pm-job-hunter
```

> If you use **Agency Copilot CLI**, clone it into your skills directory
> instead so it auto-registers as a skill:
> `git clone … "<Agency-Cowork>/skills/pm-job-hunter"`

### 2. Install Python dependencies (Python 3.11+)

```bash
# macOS / Linux
python3 -m pip install --user openpyxl rapidfuzz pyyaml requests

# Windows (PowerShell)
python -m pip install --user openpyxl rapidfuzz pyyaml requests
```

### 3. Edit your profile

Open `skills/pm-job-hunter/config/profile.yaml` and customize:

- `target_locations` — your city / region preferences
- `ai_signal_keywords` — the AI/ML terms that signal a real AI role for you
- `must_haves`, `nice_to_haves`, `profile_summary` — used by the LLM reranker
- `email:` block (see step 4)

### 4. Configure your email delivery

Add an `email:` block at the top of `profile.yaml`. Pick **one** of the two
recipes below.

**Recipe A — SMTP (works on Mac, Linux, Windows; recommended for non-Microsoft accounts):**

```yaml
email:
  backend: smtp
  to: "you@example.com"            # where the digest is delivered
  smtp_host: "smtp.gmail.com"      # your provider
  smtp_port: 587                   # 587 = STARTTLS, 465 = implicit SSL
  smtp_starttls: true
  smtp_user: "you@gmail.com"
  smtp_from: "you@gmail.com"       # usually same as smtp_user
  # smtp_pass: leave blank — set via env var (see below)
```

Set the password as an environment variable so it never lands in git:

```bash
# macOS / Linux (add to ~/.zshrc or ~/.bashrc to persist)
export PMJH_SMTP_PASS="your-app-password-here"

# Windows (PowerShell — persists for this user)
[Environment]::SetEnvironmentVariable("PMJH_SMTP_PASS","your-app-password","User")
```

**Common providers:**

| Provider | Host | Port | Notes |
|---|---|---|---|
| Gmail | `smtp.gmail.com` | 587 | Requires an [App Password](https://myaccount.google.com/apppasswords) (2FA must be on). Don't use your normal password. |
| Outlook.com / Hotmail | `smtp-mail.outlook.com` | 587 | Use an [app password](https://account.live.com/proofs/AppPassword). |
| iCloud Mail | `smtp.mail.me.com` | 587 | Requires an [app-specific password](https://support.apple.com/en-us/102654). |
| Fastmail | `smtp.fastmail.com` | 465 | Set `smtp_port: 465` and `smtp_starttls: false`. |
| Your company SMTP | ask IT | usually 587 | |

**Recipe B — Outlook desktop (Windows only):**

```yaml
email:
  backend: outlook
  to: "you@yourcompany.com"        # any address you want it sent to
```

The skill will drive your local Outlook via COM and send from the
currently-signed-in profile. No password needed — Outlook handles auth.

> **All settings can also be passed as env vars** if you'd rather not put
> them in YAML: `PMJH_RECIPIENT`, `PMJH_EMAIL_BACKEND`, `PMJH_SMTP_HOST`,
> `PMJH_SMTP_PORT`, `PMJH_SMTP_USER`, `PMJH_SMTP_PASS`, `PMJH_SMTP_FROM`,
> `PMJH_SMTP_STARTTLS` (`1`/`0`). Env vars override YAML.

### 5. Smoke-test the pipeline (no LLM, no email)

```bash
cd skills/pm-job-hunter
python scripts/fetch_jobs.py --config config/companies.yaml --out data/raw_jobs.json
python scripts/pipeline.py --raw data/raw_jobs.json --profile config/profile.yaml \
    --db data/tracker.db --out data/candidates.json
```

You should see ~5,000+ raw jobs collapsed to 20–40 candidates.

### 6. Send a test email

After a real run produces `data/digest.json`:

```bash
python scripts/_send_digest.py
```

If the email lands, you're done. If SMTP fails, the script prints the exact
missing variable.

### 7. Schedule the daily run

**Option A — Agency Copilot task-scheduler (cross-platform, the same way the author runs it):**

```powershell
# Windows
& "<Agency-Cowork>/skills/task-scheduler/scripts/task-manager.ps1" create `
    -Id daily-pm-job-hunter `
    -Name "Daily PM Job Hunter" `
    -Schedule "0 15 * * *" `
    -Timeout 15 `
    -Prompt "<see SKILL.md for the recommended scheduled prompt>"
& "<Agency-Cowork>/skills/task-scheduler/scripts/task-manager.ps1" ensure-running
```

> ⚠️ **Cron strings are interpreted in UTC**, not local time. For 8 AM PDT
> use `0 15 * * *`; for 8 AM PST use `0 16 * * *`. You'll need to flip this
> at DST changeover.

**Option B — macOS `launchd`:**

Create `~/Library/LaunchAgents/com.user.pmjobhunter.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.user.pmjobhunter</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd ~/code/pm-job-hunter/skills/pm-job-hunter &amp;&amp; \
      python3 scripts/fetch_jobs.py --config config/companies.yaml --out data/raw_jobs.json &amp;&amp; \
      python3 scripts/pipeline.py --raw data/raw_jobs.json --profile config/profile.yaml --db data/tracker.db --out data/candidates.json &amp;&amp; \
      python3 scripts/finalize.py &amp;&amp; \
      python3 scripts/_send_digest.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>/tmp/pmjobhunter.log</string>
  <key>StandardErrorPath</key><string>/tmp/pmjobhunter.err</string>
</dict>
</plist>
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/com.user.pmjobhunter.plist
launchctl start com.user.pmjobhunter   # test fire
```

> Note: Option B skips the LLM rerank step (which requires an Agency Copilot
> session). You'll still get filtered + deduped matches in your Excel
> tracker, but without LLM scores. To get LLM scoring on Mac/Linux, swap the
> `_send_digest.py` step for an LLM API call of your choice.

**Option C — Linux `cron`:**

```cron
0 15 * * * cd ~/code/pm-job-hunter/skills/pm-job-hunter && \
  python3 scripts/fetch_jobs.py --config config/companies.yaml --out data/raw_jobs.json && \
  python3 scripts/pipeline.py --raw data/raw_jobs.json --profile config/profile.yaml --db data/tracker.db --out data/candidates.json && \
  python3 scripts/finalize.py && python3 scripts/_send_digest.py >> ~/pmjobhunter.log 2>&1
```

**Option D — Windows Task Scheduler (no Agency Copilot required):**

```powershell
$action = New-ScheduledTaskAction -Execute "python.exe" `
  -Argument "scripts\_run_all.py" `
  -WorkingDirectory "C:\path\to\pm-job-hunter\skills\pm-job-hunter"
$trigger = New-ScheduledTaskTrigger -Daily -At 8am
Register-ScheduledTask -TaskName "PM Job Hunter" -Action $action -Trigger $trigger
```

(You'd write a tiny `_run_all.py` that chains fetch → pipeline → finalize →
send. ~10 lines.)

---

## Design decisions worth knowing

- **SQLite is the source of truth; Excel is a regenerated export.** If you have the Excel file open when the scheduler runs, the export is skipped (your edits are preserved) and the email notes "Excel will refresh next run". Status edits sync back via `sync_tracker.py`.
- **One ATS source per company** — we don't query Greenhouse + Lever + Ashby for everyone. Cuts HTTP volume by ~70%.
- **Fingerprint excludes location** so Brex's "Group Product Manager" listed in NYC + SF + Seattle + Vancouver collapses to one row with `"NYC | SF | SEA | YVR"`.
- **LLM only on the final 30** — never asked to score 5,600 raw jobs. Keeps each run cheap and fast.
- **No auto-submission. No scraping. No CAPTCHAs.** Hard-coded refusals in the skill rules. ToS compliance + your account safety > convenience.
- **No daily resume tailoring (v0.1).** Doc generation per match would blow the 15-min timeout and most generated docs go unused. v0.2 adds **on-demand** tailoring (`tailor <company>`) for the matches you actually want to apply to.

---

## Roadmap

**v0.2 (next):**
- On-demand `tailor <company>` → generates a tailored resume + cover letter for one match
- Click-tracking on apply links so you don't re-apply by mistake
- Optional Slack/Teams delivery in addition to email

**v0.3:**
- Workday adapter → Google, Meta, Microsoft, Amazon, Salesforce
- Compensation extraction (where disclosed)
- "Re-rank reasons changed" alerts for jobs you've already seen if the JD was edited

---

## License

MIT — use freely, fork happily.

---

## Credits

Built with help from **GitHub Copilot CLI (Claude Opus 4.7)** in an Agency Copilot session.
Inspired by the cognitive cost of repeated daily job-board scrolling.

Co-authored-by: Copilot &lt;223556219+Copilot@users.noreply.github.com&gt;

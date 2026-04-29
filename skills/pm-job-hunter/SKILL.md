---
name: pm-job-hunter
description: Use this skill when the user asks to "find PM jobs", "run job hunter", "refresh jobs", "search for product manager openings", "daily PM job digest", "any new PM jobs", "find me Senior PM roles", "check for new job matches", or wants to search and rank AI/ML Senior+ PM roles. Also manages the recurring 8am daily schedule. Triggers include "job hunter", "pm jobs", "find jobs", "run job search", "pm digest".
---

# PM Job Hunter Skill

Curate and email a daily digest of Senior+ PM AI/ML role matches. Fetches from public ATS APIs (Greenhouse, Lever, Ashby), filters by level/location/AI-signal, scores via LLM against the user's profile, and emails the top 10–15 matches every morning at 8 AM.

## Scope (v0.1)

- **Roles:** Senior / Staff / Principal / Group / Lead / Director+ PM in AI/ML
- **Locations:** SF Bay Area, Seattle, NYC, Remote-US
- **Companies:** ~40 AI-heavy Series B+ startups on Greenhouse / Lever / Ashby (Big Tech via Workday is v0.3)
- **Delivery:** Daily HTML email digest at 8:00 AM local time
- **No doc generation in v0.1** — tailoring is on-demand via v0.2 (not yet built)

## Workflow (on-demand or scheduled)

When triggered (daily 8am or on-demand), execute these steps IN ORDER. **You MUST run every Python step every time** — do not skip the fetch or pipeline steps even if `data/` already contains files from a previous run. The pipeline reads today's fresh ATS fetch, refreshes the SQLite mirror, marks new vs returning roles, and prunes closed listings. Skipping any step causes the digest to be reconstructed from stale data.

### Step 1: Fetch jobs
Run the fetch script which pulls from each company's configured ATS:
```powershell
python scripts\fetch_jobs.py --config config\companies.yaml --out data\raw_jobs.json
```

### Step 2: Filter + dedupe + persist
Apply keyword/level/location heuristic filter, fuzzy-dedupe against SQLite history:
```powershell
python scripts\pipeline.py --raw data\raw_jobs.json --db data\tracker.db --profile config\profile.yaml --out data\candidates.json
```

Output: `candidates.json` with up to 30 new candidates to score.

### Step 3: LLM rerank
Read `data\candidates.json` and `config\profile.yaml`. Each candidate now carries an `is_new` flag — score every candidate fairly, but in the email surface NEW postings first (the digest sender already sorts new-first). For each candidate, score 0–100 for fit with the profile. Focus on: AI/ML product experience directly relevant; seniority match; startup/stage fit; location compatibility.

For EACH candidate, produce:
- `score`: integer 0–100
- `why_match`: one concise sentence (≤ 20 words) explaining the match

Output must be valid JSON written to `data\ranked.json` as an array:
```json
[{"id": "...", "score": 87, "why_match": "..."}, ...]
```

Keep only the top 15.

### Step 4: Persist scores + export Excel
```powershell
python scripts\finalize.py --ranked data\ranked.json --db data\tracker.db --excel data\JobTracker.xlsx --out data\digest.json
```

This script:
- Writes scores + why_match back to SQLite
- Attempts to refresh `data\JobTracker.xlsx` (skips if locked, notes in digest.json)
- Produces `digest.json` with the ordered top-15 for email rendering

The Excel file lives inside the skill's `data/` directory so the scheduled run (sandboxed) can always write to it. Open it directly from there to review and edit statuses.

### Step 5: Send email via send-email skill
Read `data\digest.json`. Compose an HTML email:

- **Subject:** `🎯 PM Job Matches — <today's date in Month Day, Year>`
- **Recipient:** signed-in Outlook user (self only)
- **Body:** HTML table with columns: `#`, `Company`, `Role`, `Location`, `Score`, `Why it matches`, `Job page`, `Apply`
- Include a header line with total-matches-today and link to the local Excel tracker path
- If Excel was locked during export, include a note: "Excel tracker was open — SQLite updated, Excel will refresh on next run"
- Footer: "Reply 'tailor <company>' to generate a tailored resume + cover letter for that match (v0.2, coming soon)"

Use the send-email skill's `SendEmailWithAttachments` MCP tool. Do NOT attach files (all data is in the email body and local tracker).

### Step 6: Confirm
Report to the user: number of new matches, top 3 headlines, path to Excel tracker.

## Scheduled run

Registered as `daily-pm-job-hunter` via the `task-scheduler` skill. Runs every day at 8:00 AM local time.

### Managing the schedule

Via `task-scheduler` task id `daily-pm-job-hunter`:
- **Run now:** `task-manager.ps1 run -Id daily-pm-job-hunter`
- **Pause:** `task-manager.ps1 pause -Id daily-pm-job-hunter`
- **Logs:** `task-manager.ps1 logs -Id daily-pm-job-hunter -Tail 40`

## On-demand trigger phrases

- "run job hunter"
- "find me PM jobs"
- "refresh jobs"
- "check for new PM jobs"
- "run daily PM digest"

When triggered on-demand, execute the full workflow immediately.

## Status tracking

The user's Excel file at `skills\pm-job-hunter\skills\pm-job-hunter\data\JobTracker.xlsx` mirrors the SQLite state. User can edit the **Status** column directly in Excel (values: `Matched`, `Applied`, `Interview`, `Offer`, `Rejected`, `Passed`). To sync changes back into SQLite, the user can trigger:
- "sync job tracker" → runs `scripts\sync_tracker.py` (reads Excel → updates SQLite status + applied_at)

## Rules

- **NEVER** auto-submit applications (ToS risk, account bans, recruiter filtering)
- **NEVER** scrape LinkedIn beyond the official RSS (currently not in sources)
- **NEVER** bypass CAPTCHAs
- **ALWAYS** send email only to the signed-in user (self), no other recipients
- **ALWAYS** dedupe against SQLite to avoid surfacing the same job multiple days
- **ALWAYS** respect the lock state of the Excel file — skip export if user has it open
- Keep daily run under 10 minutes — scheduler timeout is 15 min

## Related skills

- **send-email** — used for daily digest delivery
- **task-scheduler** — manages the 8am daily run
- **excel** — can inspect/edit the tracker workbook on demand

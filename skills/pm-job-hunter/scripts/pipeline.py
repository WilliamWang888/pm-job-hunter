"""Filter + dedupe + persist to SQLite. Emits candidates.json for LLM rerank."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    source TEXT NOT NULL,
    source_job_id TEXT,
    url TEXT,
    apply_url TEXT,
    description TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    posted_at TEXT,
    score INTEGER,
    why_match TEXT,
    status TEXT NOT NULL DEFAULT 'matched',
    applied_at TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);
"""

ROLE_REGEX = re.compile(
    r"\b(senior|staff|principal|group|lead)\s+product\s+manager\b|"
    r"\b(director|head|vp)(?:\s+of)?,?\s+product(?:\s+management)?\b|"
    r"\bgroup\s+product\s+manager\b|"
    r"\bhead\s+of\s+product\b",
    re.IGNORECASE,
)

NEGATIVE_TITLES = re.compile(
    r"\b(intern|associate|junior|apprentice|designer|engineer|marketing|"
    r"partner manager|program manager|project manager|operations|business development|"
    r"customer success|account manager|sales|recruiter|data scien|analyst|researcher|"
    r"technical writer|ux|ui|brand|content|people|counsel|legal|accounting|tax|"
    r"finance|compensation|hr |human resources|partnerships)\b",
    re.IGNORECASE,
)


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def fingerprint(company: str, title: str, location: str = "") -> str:
    # Location excluded so multi-city postings of the same role collapse to one row.
    key = f"{normalize(company)}|{normalize(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def level_match(title: str) -> bool:
    if NEGATIVE_TITLES.search(title):
        # allow if also has senior PM signal e.g. "Senior Product Manager, Partner Engineering"
        if not re.search(r"\b(senior|staff|principal|group|lead|director|head|vp)\b.*\bproduct manager\b", title, re.IGNORECASE):
            return False
    return bool(ROLE_REGEX.search(title))


def location_match(location: str, targets: list[str]) -> bool:
    if not location:
        return False
    loc_norm = normalize(location)
    for t in targets:
        if normalize(t) in loc_norm:
            return True
    # remote US fallback heuristics
    if "remote" in loc_norm and ("us" in loc_norm or "united states" in loc_norm or "usa" in loc_norm or "america" in loc_norm):
        return True
    return False


def ai_signal(text: str, keywords: list[str]) -> bool:
    if not text:
        return False
    tlow = text.lower()
    hits = 0
    for kw in keywords:
        if kw.lower() in tlow:
            hits += 1
            if hits >= 2:
                return True
    # single strong signal is enough for tight keywords
    strong = {"llm", "foundation model", "generative ai", "genai", "agentic", "ml", " ai "}
    for s in strong:
        if s in tlow:
            return True
    return False


def is_fuzzy_dup(candidate: dict[str, Any], seen: list[dict[str, Any]]) -> bool:
    """Collapse same company+title across multiple city listings into one row.
    When matched, merge the candidate's location into the seen row's locations list."""
    ct = normalize(candidate["title"])
    cc = normalize(candidate["company"])
    cl = candidate.get("location", "") or ""
    for s in seen:
        if normalize(s["company"]) != cc:
            continue
        if fuzz.token_set_ratio(ct, normalize(s["title"])) >= 92:
            # merge locations
            locs = s.setdefault("locations", [s.get("location", "")])
            if cl and cl not in locs:
                locs.append(cl)
            return True
    return False


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    # Migrate older DBs that predate the posted_at column.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "posted_at" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN posted_at TEXT")
        conn.commit()
    return conn


def upsert_job(conn: sqlite3.Connection, job: dict[str, Any], now: str) -> bool:
    """Returns True if newly inserted, False if already existed (last_seen updated)."""
    posted_at = job.get("updated_at", "") or ""
    cur = conn.execute("SELECT id FROM jobs WHERE id = ?", (job["id"],))
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE jobs SET last_seen_at = ?, location = ?, url = ?, apply_url = ?, description = ?, posted_at = COALESCE(NULLIF(?, ''), posted_at) WHERE id = ?",
            (now, job["location"], job["url"], job["apply_url"], job["description"], posted_at, job["id"]),
        )
        return False
    conn.execute(
        """INSERT INTO jobs (id, company, title, location, source, source_job_id, url, apply_url,
            description, first_seen_at, last_seen_at, posted_at, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'matched')""",
        (
            job["id"], job["company"], job["title"], job["location"], job["source"],
            job.get("source_job_id", ""), job["url"], job["apply_url"], job["description"],
            now, now, posted_at,
        ),
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-candidates", type=int, default=30)
    args = ap.parse_args()

    with open(args.profile, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)
    with open(args.raw, "r", encoding="utf-8") as f:
        raw_jobs = json.load(f)

    targets = profile.get("target_locations", [])
    ai_kws = profile.get("ai_signal_keywords", [])

    # Stage 1: level + location + AI signal filter
    stage1: list[dict[str, Any]] = []
    for job in raw_jobs:
        title = job.get("title", "")
        if not level_match(title):
            continue
        if not location_match(job.get("location", ""), targets):
            continue
        if not ai_signal(job.get("title", "") + " " + job.get("description", ""), ai_kws):
            continue
        job["id"] = fingerprint(job.get("company", ""), title, job.get("location", ""))
        stage1.append(job)

    print(f"[filter] {len(raw_jobs)} raw -> {len(stage1)} after filter", file=sys.stderr)

    # Stage 2: fuzzy dedupe within today's fetch
    deduped: list[dict[str, Any]] = []
    for job in stage1:
        if not is_fuzzy_dup(job, deduped):
            deduped.append(job)
    print(f"[dedupe] {len(stage1)} -> {len(deduped)} after fuzzy dedupe", file=sys.stderr)

    # Flatten merged location lists into the location field for display & storage.
    for job in deduped:
        locs = job.get("locations")
        if locs and len(locs) > 1:
            job["location"] = " | ".join(locs)

    # Stage 3: persist into SQLite — track which fingerprints we saw today so we can
    # mark anything missing as 'closed'. Every deduped job becomes a candidate (not
    # just newly-inserted ones) so the LLM re-evaluates the full set of currently
    # open roles each run. This catches: (a) JD edits, (b) profile changes, and
    # (c) the common case where no genuinely new postings appeared but the open
    # set shifted.
    now = datetime.now(timezone.utc).isoformat()
    conn = init_db(Path(args.db))
    new_count = 0
    seen_today_ids: set[str] = set()
    for job in deduped:
        is_new = upsert_job(conn, job, now)
        if is_new:
            new_count += 1
        seen_today_ids.add(job["id"])
        job["is_new"] = is_new

    # Mark jobs not seen in this fetch as closed (they were removed from the ATS).
    # Only flip jobs whose status is still in the "open" set so we don't clobber
    # user-edited statuses like Applied/Interview/Offer.
    # Safety: if the fetch was clearly degraded (very small raw set), skip the
    # close pass — otherwise a transient network issue would silently mark every
    # tracked role as closed.
    closed_ids: list[str] = []
    SAFE_CLOSE_MIN_RAW = 500
    if len(raw_jobs) >= SAFE_CLOSE_MIN_RAW:
        cur = conn.execute(
            "SELECT id FROM jobs WHERE status IN ('matched', 'new', 'open')"
        )
        for (jid,) in cur.fetchall():
            if jid not in seen_today_ids:
                closed_ids.append(jid)
        if closed_ids:
            conn.executemany(
                "UPDATE jobs SET status = 'closed' WHERE id = ?",
                [(jid,) for jid in closed_ids],
            )
    else:
        print(
            f"[persist] WARNING: only {len(raw_jobs)} raw jobs (<{SAFE_CLOSE_MIN_RAW}) — "
            f"skipping close-pass to avoid false positives.",
            file=sys.stderr,
        )
    conn.commit()
    conn.close()
    print(
        f"[persist] {new_count} new, {len(deduped) - new_count} refreshed, "
        f"{len(closed_ids)} marked closed",
        file=sys.stderr,
    )

    # Stage 4: cap candidates to max for LLM rerank.
    # Sort: new postings first (so they bubble up), then by ATS updated_at desc.
    deduped.sort(
        key=lambda j: (0 if j.get("is_new") else 1, -1 * len(j.get("updated_at") or "")),
    )
    deduped.sort(key=lambda j: j.get("updated_at") or "", reverse=True)
    deduped.sort(key=lambda j: 0 if j.get("is_new") else 1)
    candidates = deduped[: args.max_candidates]

    # Trim description for LLM context (keep concise excerpts)
    for c in candidates:
        desc = c.get("description", "") or ""
        if len(desc) > 2000:
            c["description_excerpt"] = desc[:2000] + "..."
        else:
            c["description_excerpt"] = desc

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"candidates": candidates, "stats": {
            "raw": len(raw_jobs), "filtered": len(stage1), "deduped": len(deduped),
            "new": new_count, "refreshed": len(deduped) - new_count,
            "closed": len(closed_ids), "to_score": len(candidates),
        }}, f, ensure_ascii=False, indent=2)
    print(f"[OK] wrote {len(candidates)} candidates to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

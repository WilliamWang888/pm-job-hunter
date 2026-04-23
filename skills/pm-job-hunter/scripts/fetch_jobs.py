"""Fetch jobs from Greenhouse / Lever / Ashby public APIs per company."""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests
import yaml

TIMEOUT = 15
HEADERS = {"User-Agent": "pm-job-hunter/0.1"}


def strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_greenhouse(board_id: str) -> list[dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs?content=true"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    jobs = []
    for job in r.json().get("jobs", []):
        offices = job.get("offices") or []
        loc_parts = []
        if job.get("location", {}).get("name"):
            loc_parts.append(job["location"]["name"])
        for o in offices:
            if o.get("name"):
                loc_parts.append(o["name"])
        jobs.append({
            "source": "greenhouse",
            "source_job_id": str(job.get("id", "")),
            "title": job.get("title", ""),
            "location": " | ".join(dict.fromkeys(loc_parts)),
            "url": job.get("absolute_url", ""),
            "apply_url": job.get("absolute_url", ""),
            "description": strip_html(job.get("content", ""))[:15000],
            "updated_at": job.get("updated_at", ""),
        })
    return jobs


def fetch_lever(board_id: str) -> list[dict[str, Any]]:
    url = f"https://api.lever.co/v0/postings/{board_id}?mode=json"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    jobs = []
    for job in r.json():
        cats = job.get("categories") or {}
        loc = cats.get("location", "") or ""
        jobs.append({
            "source": "lever",
            "source_job_id": job.get("id", ""),
            "title": job.get("text", ""),
            "location": loc,
            "url": job.get("hostedUrl", ""),
            "apply_url": (job.get("applyUrl") or job.get("hostedUrl") or ""),
            "description": strip_html(job.get("descriptionPlain") or job.get("description") or "")[:15000],
            "updated_at": str(job.get("createdAt", "")),
        })
    return jobs


def fetch_ashby(board_id: str) -> list[dict[str, Any]]:
    # Ashby public API
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_id}?includeCompensation=true"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return []
    data = r.json()
    jobs = []
    for job in data.get("jobs", []):
        loc_parts = []
        if job.get("locationName"):
            loc_parts.append(job["locationName"])
        for sec in (job.get("secondaryLocations") or []):
            if sec.get("locationName"):
                loc_parts.append(sec["locationName"])
        if job.get("isRemote"):
            loc_parts.append("Remote")
        jobs.append({
            "source": "ashby",
            "source_job_id": job.get("id", ""),
            "title": job.get("title", ""),
            "location": " | ".join(dict.fromkeys(loc_parts)),
            "url": job.get("jobUrl") or job.get("applyUrl", ""),
            "apply_url": job.get("applyUrl", "") or job.get("jobUrl", ""),
            "description": strip_html(job.get("descriptionHtml") or job.get("descriptionPlain") or "")[:15000],
            "updated_at": job.get("publishedAt", ""),
        })
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def fetch_company(company: dict[str, Any]) -> list[dict[str, Any]]:
    source = company.get("source")
    board_id = company.get("board_id")
    name = company.get("name")
    if not source or not board_id:
        return []
    fetcher = FETCHERS.get(source)
    if not fetcher:
        return []
    try:
        jobs = fetcher(board_id)
    except Exception as e:
        print(f"[WARN] {name} ({source}/{board_id}): {e}", file=sys.stderr)
        return []
    for j in jobs:
        j["company"] = name
    return jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-workers", type=int, default=8)
    args = ap.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        companies = yaml.safe_load(f)

    all_jobs: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(fetch_company, c): c for c in companies}
        for fut in cf.as_completed(futures):
            c = futures[fut]
            try:
                jobs = fut.result()
            except Exception as e:
                print(f"[WARN] {c.get('name')} failed: {e}", file=sys.stderr)
                jobs = []
            print(f"  {c.get('name'):<25} {c.get('source'):<12} -> {len(jobs)} jobs", file=sys.stderr)
            all_jobs.extend(jobs)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, ensure_ascii=False, indent=2)
    print(f"[OK] wrote {len(all_jobs)} total jobs to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

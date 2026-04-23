"""Probe Greenhouse/Lever/Ashby for candidate board IDs for a given company name."""
import sys
import requests
from urllib.parse import quote

UA = {"User-Agent": "Mozilla/5.0 pm-job-hunter-probe"}

def try_greenhouse(bid):
    url = f"https://boards-api.greenhouse.io/v1/boards/{bid}/jobs"
    try:
        r = requests.get(url, headers=UA, timeout=8)
        if r.status_code == 200:
            n = len(r.json().get("jobs", []))
            return n
    except Exception:
        pass
    return None

def try_lever(bid):
    url = f"https://api.lever.co/v0/postings/{bid}?mode=json"
    try:
        r = requests.get(url, headers=UA, timeout=8)
        if r.status_code == 200:
            return len(r.json())
    except Exception:
        pass
    return None

def try_ashby(bid):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{bid}"
    try:
        r = requests.get(url, headers=UA, timeout=8)
        if r.status_code == 200:
            return len(r.json().get("jobs", []))
    except Exception:
        pass
    return None

def variants(name):
    base = name.lower()
    out = set()
    out.add(base.replace(" ", "").replace(".", "").replace("&", "and"))
    out.add(base.replace(" ", "-").replace(".", "").replace("&", "and"))
    out.add(base.replace(" ", "").replace(".", "").replace("&", ""))
    out.add(base.split()[0])
    out.add(base.replace(" ai", "").replace(" ", ""))
    out.add(base.replace(" ", "") + "ai")
    out.add(base.replace(" ", "") + "io")
    out.add(base.replace(" ", "") + "inc")
    out.add(base.replace(" ", "") + "hq")
    return [v for v in out if v]

def probe(name):
    print(f"\n=== {name} ===")
    for v in variants(name):
        for src, fn in [("greenhouse", try_greenhouse), ("lever", try_lever), ("ashby", try_ashby)]:
            n = fn(v)
            if n is not None and n > 0:
                print(f"  HIT: {src:11} / {v:25} -> {n} jobs")

if __name__ == "__main__":
    for name in sys.argv[1:]:
        probe(name)

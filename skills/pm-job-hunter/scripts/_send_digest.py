"""Compose HTML digest email body and send it.

Cross-platform: defaults to Outlook COM on Windows; falls back to SMTP on
macOS / Linux (or when ``PMJH_EMAIL_BACKEND=smtp`` is set).

Configuration precedence (highest first):
  1. Environment variables: ``PMJH_RECIPIENT``, ``PMJH_EMAIL_BACKEND``,
     ``PMJH_SMTP_HOST``, ``PMJH_SMTP_PORT``, ``PMJH_SMTP_USER``,
     ``PMJH_SMTP_PASS``, ``PMJH_SMTP_FROM``, ``PMJH_SMTP_STARTTLS`` (1/0).
  2. ``email:`` block in ``config/profile.yaml`` (see README).
  3. Built-in defaults (Outlook COM on Windows).
"""
from __future__ import annotations
import json
import os
import platform
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DIGEST = SKILL_ROOT / "data" / "digest.json"
PROFILE_YAML = SKILL_ROOT / "config" / "profile.yaml"

DEFAULT_RECIPIENT = "williwang@microsoft.com"
EXCEL_DISPLAY_PATH = (
    r"%USERPROFILE%\JobHunter\JobTracker.xlsx"
    if platform.system() == "Windows"
    else "~/JobHunter/JobTracker.xlsx"
)
TARGET_EMOJI = "\U0001F3AF"  # 🎯


def _load_email_config() -> dict:
    """Load email config from profile.yaml (best-effort)."""
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not PROFILE_YAML.exists():
        return {}
    try:
        data = yaml.safe_load(PROFILE_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data.get("email", {}) or {}


def esc(s: str) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_html(digest: dict) -> str:
    items = digest.get("items", [])
    # Sort: new jobs first, then by score desc within each group.
    items = sorted(items, key=lambda x: (0 if x.get("is_new") else 1, -1 * (x.get("score") or 0)))
    total = len(items)
    new_count = sum(1 for i in items if i.get("is_new"))
    date_label = digest.get("date_label", "")
    excel_info = digest.get("excel", {})
    excel_locked_note = ""
    if not excel_info.get("refreshed", True):
        excel_locked_note = (
            "<p style='background:#fff3cd;border:1px solid #ffe08a;padding:10px;"
            "border-radius:4px;color:#663c00;margin:12px 0'>"
            "<strong>Note:</strong> Excel tracker was not refreshed this run — "
            "SQLite was updated. Excel will refresh on the next run when the "
            "target path is writable.</p>"
        )

    rows = []
    for i, item in enumerate(items, start=1):
        is_new = bool(item.get("is_new"))
        first_seen = (item.get("first_seen_at") or "")[:10]
        posted_raw = item.get("posted_at") or ""
        # ATS sources hand back ISO strings (greenhouse/ashby) or millisecond
        # epoch strings (lever). Normalize both to YYYY-MM-DD for the email.
        posted_display = ""
        if posted_raw:
            s = str(posted_raw)
            if s.isdigit() and len(s) >= 10:
                try:
                    from datetime import datetime, timezone
                    posted_display = datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    posted_display = s[:10]
            else:
                posted_display = s[:10]
        new_badge = (
            "<span style='background:#1a7f37;color:#fff;font-size:10px;font-weight:bold;"
            "padding:2px 6px;border-radius:3px;margin-left:6px;vertical-align:middle'>NEW</span>"
            if is_new else ""
        )
        first_seen_cell = (
            f"<span style='color:#1a7f37;font-weight:bold'>{esc(first_seen)}</span>"
            if is_new else f"<span style='color:#57606a'>{esc(first_seen)}</span>"
        )
        rows.append(
            "<tr>"
            f"<td style='text-align:center;padding:6px 10px;border:1px solid #e1e4e8'>{i}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><strong>{esc(item.get('company'))}</strong>{new_badge}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'>{esc(item.get('title'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;font-size:12px;color:#57606a'>{esc(item.get('location'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;font-size:12px;color:#57606a'>{esc(posted_display)}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;font-size:12px'>{first_seen_cell}</td>"
            f"<td style='text-align:center;padding:6px 10px;border:1px solid #e1e4e8;font-weight:bold;color:{'#1a7f37' if (item.get('score') or 0) >= 80 else ('#9a6700' if (item.get('score') or 0) >= 60 else '#57606a')}'>{esc(item.get('score'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;max-width:360px'>{esc(item.get('why_match'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><a href='{esc(item.get('url'))}'>Job page</a></td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><a href='{esc(item.get('apply_url'))}'>Apply</a></td>"
            "</tr>"
        )

    new_phrase = (
        f" — <span style='color:#1a7f37;font-weight:bold'>{new_count} new</span>"
        if new_count > 0 else " — no brand-new postings; full list refreshed against today's open roles"
    )
    header = (
        f"<p style='font-size:15px;margin:0 0 8px 0'><strong>{total}</strong> matches today{new_phrase} "
        f"({esc(date_label)}).</p>"
        f"<p style='font-size:13px;color:#57606a;margin:0 0 12px 0'>"
        f"Local Excel tracker: <code>{esc(EXCEL_DISPLAY_PATH)}</code></p>"
    )

    table = (
        "<table cellspacing='0' cellpadding='0' style='border-collapse:collapse;"
        "font-family:Segoe UI, Arial, sans-serif;font-size:13px;width:100%'>"
        "<thead>"
        "<tr style='background:#305496;color:#ffffff'>"
        "<th style='padding:8px 10px;border:1px solid #305496'>#</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Company</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Role</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Location</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Posted</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>First seen</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Score</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Why it matches</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Job page</th>"
        "<th style='padding:8px 10px;border:1px solid #305496'>Apply</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    footer = (
        "<p style='font-size:12px;color:#57606a;margin-top:16px'>"
        "Reply 'tailor &lt;company&gt;' to generate a tailored resume + cover letter "
        "for that match (v0.2, coming soon).</p>"
        "<p style='font-size:12px;color:#57606a;margin-top:6px'>—<br>Sent by Agency Cowork</p>"
    )

    body = (
        "<html><body style='font-family:Segoe UI, Arial, sans-serif'>"
        f"{header}{excel_locked_note}{table}{footer}"
        "</body></html>"
    )
    return body


def send_via_com(recipient: str, subject: str, html_body: str) -> None:
    """Windows / Outlook desktop. Sends from the signed-in profile."""
    data_dir = SKILL_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    body_file = data_dir / "_email_body.html"
    body_file.write_text(html_body, encoding="utf-8")

    ps_script = r"""
param([string]$Recipient, [string]$Subject, [string]$BodyFile)
$body = Get-Content -LiteralPath $BodyFile -Raw -Encoding UTF8
$outlook = New-Object -ComObject Outlook.Application
$mail = $outlook.CreateItem(0)
$mail.To = $Recipient
$mail.Subject = $Subject
$mail.BodyFormat = 2  # olFormatHTML
$mail.HTMLBody = $body
$mail.Send()
Write-Output "Sent to $Recipient"
"""
    ps_file = data_dir / "_send_email.ps1"
    ps_file.write_text(ps_script, encoding="utf-8")

    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(ps_file),
        "-Recipient", recipient,
        "-Subject", subject,
        "-BodyFile", str(body_file.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    if result.returncode != 0:
        sys.exit(result.returncode)


def send_via_smtp(recipient: str, subject: str, html_body: str, cfg: dict) -> None:
    """Cross-platform (Mac, Linux, Windows). Uses SMTP credentials from env or profile.yaml."""
    host = os.environ.get("PMJH_SMTP_HOST") or cfg.get("smtp_host")
    port = int(os.environ.get("PMJH_SMTP_PORT") or cfg.get("smtp_port") or 587)
    user = os.environ.get("PMJH_SMTP_USER") or cfg.get("smtp_user")
    pwd = os.environ.get("PMJH_SMTP_PASS") or cfg.get("smtp_pass")
    sender = os.environ.get("PMJH_SMTP_FROM") or cfg.get("smtp_from") or user
    starttls_env = os.environ.get("PMJH_SMTP_STARTTLS")
    starttls = (
        starttls_env not in ("0", "false", "False", "no")
        if starttls_env is not None
        else cfg.get("smtp_starttls", True)
    )

    if not (host and user and pwd and sender):
        print(
            "ERROR: SMTP backend requires PMJH_SMTP_HOST, PMJH_SMTP_USER, "
            "PMJH_SMTP_PASS, and PMJH_SMTP_FROM (or matching keys under "
            "`email:` in profile.yaml).",
            file=sys.stderr,
        )
        sys.exit(2)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content("This message requires an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as s:
            s.ehlo()
            if starttls:
                s.starttls(context=context)
                s.ehlo()
            s.login(user, pwd)
            s.send_message(msg)
    print(f"Sent (SMTP {host}:{port}) to {recipient}")


def _resolve_backend(cfg: dict) -> str:
    backend = (
        os.environ.get("PMJH_EMAIL_BACKEND")
        or cfg.get("backend")
        or ("outlook" if platform.system() == "Windows" else "smtp")
    )
    return backend.lower()


def _resolve_recipient(cfg: dict) -> str:
    return (
        os.environ.get("PMJH_RECIPIENT")
        or cfg.get("to")
        or DEFAULT_RECIPIENT
    )


def main() -> int:
    digest = json.loads(DIGEST.read_text(encoding="utf-8"))
    date_label = digest.get("date_label", "")
    subject = f"{TARGET_EMOJI} PM Job Matches \u2014 {date_label}"
    html = build_html(digest)

    cfg = _load_email_config()
    recipient = _resolve_recipient(cfg)
    backend = _resolve_backend(cfg)

    if backend == "outlook":
        if platform.system() != "Windows":
            print(
                "ERROR: backend=outlook only works on Windows with Outlook "
                "desktop installed. Set PMJH_EMAIL_BACKEND=smtp (or "
                "email.backend: smtp in profile.yaml).",
                file=sys.stderr,
            )
            return 2
        send_via_com(recipient, subject, html)
    elif backend == "smtp":
        send_via_smtp(recipient, subject, html, cfg)
    else:
        print(f"ERROR: unknown backend '{backend}'. Use 'outlook' or 'smtp'.",
              file=sys.stderr)
        return 2

    print(f"Subject: {subject}")
    print(f"Recipient: {recipient}")
    print(f"Backend: {backend}")
    print(f"Matches: {len(digest.get('items', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

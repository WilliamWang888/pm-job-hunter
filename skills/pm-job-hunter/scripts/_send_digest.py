"""Compose HTML digest email body and send via Outlook COM to signed-in user only."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

DIGEST = Path(r"skills\pm-job-hunter\skills\pm-job-hunter\data\digest.json")
RECIPIENT = "williwang@microsoft.com"
EXCEL_DISPLAY_PATH = r"%USERPROFILE%\JobHunter\JobTracker.xlsx"
TARGET_EMOJI = "\U0001F3AF"  # 🎯


def esc(s: str) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_html(digest: dict) -> str:
    items = digest.get("items", [])
    total = len(items)
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
        rows.append(
            "<tr>"
            f"<td style='text-align:center;padding:6px 10px;border:1px solid #e1e4e8'>{i}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><strong>{esc(item.get('company'))}</strong></td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'>{esc(item.get('title'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;font-size:12px;color:#57606a'>{esc(item.get('location'))}</td>"
            f"<td style='text-align:center;padding:6px 10px;border:1px solid #e1e4e8;font-weight:bold;color:{'#1a7f37' if (item.get('score') or 0) >= 80 else ('#9a6700' if (item.get('score') or 0) >= 60 else '#57606a')}'>{esc(item.get('score'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8;max-width:360px'>{esc(item.get('why_match'))}</td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><a href='{esc(item.get('url'))}'>Job page</a></td>"
            f"<td style='padding:6px 10px;border:1px solid #e1e4e8'><a href='{esc(item.get('apply_url'))}'>Apply</a></td>"
            "</tr>"
        )

    header = (
        f"<p style='font-size:15px;margin:0 0 8px 0'><strong>{total}</strong> matches today — "
        f"{esc(date_label)}.</p>"
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
    # Write body to temp file to avoid quoting chaos
    body_file = Path("data") / "_email_body.html"
    body_file.parent.mkdir(parents=True, exist_ok=True)
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
    ps_file = Path("data") / "_send_email.ps1"
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


def main() -> int:
    digest = json.loads(DIGEST.read_text(encoding="utf-8"))
    date_label = digest.get("date_label", "")
    subject = f"{TARGET_EMOJI} PM Job Matches \u2014 {date_label}"
    html = build_html(digest)
    os.chdir(Path(r"skills\pm-job-hunter\skills\pm-job-hunter"))
    send_via_com(RECIPIENT, subject, html)
    print(f"Subject: {subject}")
    print(f"Recipient: {RECIPIENT}")
    print(f"Matches: {len(digest.get('items', []))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

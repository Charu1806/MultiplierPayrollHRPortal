"""Outgoing employee reminder email via Gmail SMTP (smtplib)."""

from __future__ import annotations

import re
import smtplib
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple

from server.services.env_config import env


def smtp_configured() -> bool:
    return bool(env("SMTP_USER") and env("SMTP_PASS") and env("DEMO_INBOX") and env("APP_BASE_URL"))


def app_base_url() -> str:
    return env("APP_BASE_URL", "http://localhost:5173").rstrip("/")


def _slug_first(name: str) -> str:
    first = (name or "employee").split()[0]
    normalized = unicodedata.normalize("NFKD", first)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]", "", ascii_only.lower())
    return slug or "employee"


def demo_personal_email(employee_name: str, personal_email: Optional[str] = None) -> str:
    """Plus-alias of DEMO_INBOX, e.g. you+priya@gmail.com for Priya Nair."""
    if personal_email:
        return personal_email
    inbox = env("DEMO_INBOX")
    if not inbox or "@" not in inbox:
        return f"{_slug_first(employee_name)}@example.com"
    local, _, domain = inbox.partition("@")
    return f"{local}+{_slug_first(employee_name)}@{domain}"


def employee_details_mail(
    *,
    first: str,
    label: str,
    deadline: str,
    month: str,
    when_note: str = "",
    detail: str = "",
) -> Tuple[str, str]:
    """Subject and body: what is missing, by when, why, and how."""
    subject = f"Add your {label} by {deadline} or {month} payroll will be missed"
    when = f"{deadline} · {when_note}" if when_note else deadline
    what = f"your {label}."
    if detail:
        what = f"your {label}. {detail}"
    body = (
        f"Hi {first},\n\n"
        f"What: {what}\n"
        f"By when: {when}.\n"
        f"Why: {month} payroll will be missed if this is still missing.\n"
        f"How: use Add my details below. It takes about a minute. You don't need to reply to this email."
    )
    return subject, body


def build_reminder_email(
    *,
    employee_name: str,
    fields_label: str,
    form_url: str,
    cutoff_label: str = "Oct 15",
    month: str = "October",
    detail: str = "",
) -> Tuple[str, str, str]:
    first = employee_name.split()[0]
    subject, text_body = employee_details_mail(
        first=first,
        label=fields_label,
        deadline=cutoff_label,
        month=month,
        detail=detail,
    )
    text = (
        text_body.replace(
            "How: use Add my details below.",
            f"How: add your details here: {form_url}",
        )
        + "\n\n— Acme Tech Payroll (via Multiplier)\n"
    )
    html = f"""\
<html><body style="font-family:system-ui,sans-serif;color:#111;line-height:1.5">
  <p style="margin:0 0 16px;font-size:13px;font-weight:500;color:#863bff">
    <span style="vertical-align:middle">◆</span> From Multiplier Payroll
  </p>
  <p>Hi {first},</p>
  <p><strong>What:</strong> your {fields_label}.{f" {detail}" if detail else ""}</p>
  <p><strong>By when:</strong> {cutoff_label}.</p>
  <p><strong>Why:</strong> {month} payroll will be missed if this is still missing.</p>
  <p><strong>How:</strong> use the button. It takes about a minute.</p>
  <p>
    <a href="{form_url}"
       style="display:inline-block;padding:10px 16px;background:#863bff;color:#fff;
              text-decoration:none;border-radius:4px;font-weight:600">
      Add my details →
    </a>
  </p>
  <p style="color:#666;font-size:13px">You don't need to reply to this email.</p>
  <p style="color:#666;font-size:12px">— Acme Tech Payroll (via Multiplier)</p>
</body></html>
"""
    return subject, text, html


def send_employee_note(*, to_address: str, subject: str, text: str) -> Dict[str, Any]:
    """Send a short employee note. Returns {sent, error?}."""
    user = env("SMTP_USER")
    password = env("SMTP_PASS")
    if not (user and password and env("DEMO_INBOX") and env("APP_BASE_URL")):
        return {"sent": False, "error": "smtp_not_configured"}
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_address
    msg.attach(MIMEText(text, "plain", "utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, [to_address], msg.as_string())
        return {"sent": True, "to": to_address, "subject": subject}
    except Exception as exc:  # noqa: BLE001 — surface to caller / Notifications
        return {"sent": False, "error": str(exc), "to": to_address, "subject": subject}


def send_reminder_email(
    *,
    to_address: str,
    employee_name: str,
    fields_label: str,
    form_url: str,
    cutoff_label: str = "Oct 15",
    month: str = "October",
    detail: str = "",
) -> Dict[str, Any]:
    """Send via Gmail SMTP. Returns {sent, error?}."""
    user = env("SMTP_USER")
    password = env("SMTP_PASS")
    if not (user and password and env("DEMO_INBOX") and env("APP_BASE_URL")):
        return {"sent": False, "error": "smtp_not_configured"}

    subject, text, html = build_reminder_email(
        employee_name=employee_name,
        fields_label=fields_label,
        form_url=form_url,
        cutoff_label=cutoff_label,
        month=month,
        detail=detail,
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_address
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, [to_address], msg.as_string())
        return {"sent": True, "to": to_address, "subject": subject}
    except Exception as exc:  # noqa: BLE001 — surface to caller / Notifications
        return {"sent": False, "error": str(exc), "to": to_address, "subject": subject}

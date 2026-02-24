"""
Email notification service — sends lead alerts to listing agents via SMTP/SSL.

Usage (fire-and-forget):
    import asyncio
    asyncio.create_task(send_lead_notification_email(agent_email, agent_name, lead_data, summary))
"""

import asyncio
import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── SMTP config from environment ──────────────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(label: str, value: Optional[str]) -> str:
    """Return an HTML table row only when value is non-empty."""
    if not value:
        return ""
    safe = str(value).replace("<", "&lt;").replace(">", "&gt;")
    return f"""
        <tr>
          <td style="padding:6px 12px;font-weight:600;color:#555;white-space:nowrap;">{label}</td>
          <td style="padding:6px 12px;color:#222;">{safe}</td>
        </tr>"""


def _build_html(
    agent_name:   str,
    lead:         Dict[str, Any],
    summary:      str,
    property_name: Optional[str] = None,
) -> str:
    """Build a styled HTML email body."""

    # Personal info rows — only include non-null fields
    info_rows = (
        _row("Name",          lead.get("name") or lead.get("tenant_name"))
        + _row("Email",         lead.get("email"))
        + _row("Phone",         lead.get("phone"))
        + _row("Nationality",   lead.get("nationality"))
        + _row("Pass Type",     lead.get("pass_type"))
        + _row("Gender",        lead.get("gender"))
        + _row("Profession",    lead.get("profession"))
        + _row("Age Group",     lead.get("age_group"))
        + _row("Budget (max)",  f"SGD {lead['budget_max']}/mo" if lead.get("budget_max") else None)
        + _row("Location",      lead.get("location"))
        + _row("Move-in Date",  lead.get("move_in_date"))
        + _row("Lease Duration", f"{lead['lease_months']} months" if lead.get("lease_months") else None)
        + _row("Property Type", lead.get("last_target_table", "").replace("_", " ").title() or None)
    )

    prop_line = f"<p style='margin:0 0 8px'><strong>Property enquired:</strong> {property_name}</p>" if property_name else ""

    summary_html = str(summary).replace("\n", "<br>") if summary else "—"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1a3c5e;padding:24px 32px;">
            <h2 style="margin:0;color:#ffffff;font-size:20px;">
              🏠 New Lead Notification — Proppanda
            </h2>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 32px;">
            <p style="margin:0 0 16px;font-size:15px;color:#333;">
              Hi <strong>{agent_name}</strong>,
            </p>
            <p style="margin:0 0 20px;font-size:14px;color:#555;">
              A prospect has shown interest in one of your listings. Here are their details:
            </p>

            {prop_line}

            <!-- Prospect info table -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border:1px solid #e0e0e0;border-radius:6px;font-size:14px;
                          border-collapse:collapse;margin-bottom:24px;">
              {info_rows if info_rows.strip() else
               '<tr><td style="padding:12px;color:#888;">No personal details collected yet.</td></tr>'}
            </table>

            <!-- Conversation summary -->
            <h3 style="margin:0 0 10px;font-size:15px;color:#1a3c5e;">Conversation Summary</h3>
            <div style="background:#f8f9fb;border-left:4px solid #1a3c5e;
                        padding:14px 18px;border-radius:4px;font-size:14px;
                        color:#333;line-height:1.6;">
              {summary_html}
            </div>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f4f6f8;padding:16px 32px;text-align:center;
                     font-size:12px;color:#999;">
            This email was sent automatically by the Proppanda AI chatbot.
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ── Public API ────────────────────────────────────────────────────────────────

async def send_lead_notification_email(
    agent_email:   str,
    agent_name:    str,
    lead_data:     Dict[str, Any],
    summary:       str,
    property_name: Optional[str] = None,
) -> None:
    """
    Send a lead-notification email to the listing agent.

    Runs the blocking SMTP call in a thread-pool so it never blocks the event loop.
    All errors are caught and logged — this must never crash the chat flow.
    """
    if not agent_email:
        logger.warning("send_lead_notification_email: agent_email is empty — skipping")
        return
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("send_lead_notification_email: SMTP credentials not configured — skipping")
        return

    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            _send_blocking,
            agent_email,
            agent_name,
            lead_data,
            summary,
            property_name,
        )
        logger.info(f"✉️  Lead notification email sent to {agent_email}")
    except Exception as exc:
        logger.error(f"send_lead_notification_email failed: {exc}")


def _send_blocking(
    agent_email:   str,
    agent_name:    str,
    lead_data:     Dict[str, Any],
    summary:       str,
    property_name: Optional[str],
) -> None:
    """Blocking SMTP/SSL send — called from thread-pool."""
    prospect_name = lead_data.get("name") or "A prospect"
    subject = f"[Proppanda] New Lead: {prospect_name} is enquiring about your listing"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Proppanda Leads <{SMTP_USERNAME}>"
    msg["To"]      = agent_email

    html_body = _build_html(agent_name, lead_data, summary, property_name)
    msg.attach(MIMEText(html_body, "html"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, agent_email, msg.as_string())

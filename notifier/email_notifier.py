"""
notifier/email_notifier.py
Sends job alerts via SMTP email (Gmail, Outlook, or any SMTP server).

v4: Now sends a single digest email per run, skipping if there are 0 jobs.

Setup (.env):
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=you@gmail.com
    SMTP_PASS=your-app-password
    ALERT_EMAIL_TO=you@gmail.com
"""

from __future__ import annotations

import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from notifier.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """
    SMTP email notifier — works with Gmail, Outlook, SendGrid, etc.
    v4: sends a single digest email.
    """

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        from_addr: str | None = None,
        to_addrs: list[str] | None = None,
    ):
        self.smtp_host = smtp_host or os.environ.get("SMTP_HOST", os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com"))
        self.smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", os.environ.get("EMAIL_SMTP_PORT", "587")))
        self.username = username or os.environ.get("SMTP_USER", os.environ.get("EMAIL_USERNAME", ""))
        self.password = password or os.environ.get("SMTP_PASS", os.environ.get("EMAIL_PASSWORD", ""))
        self.from_addr = from_addr or os.environ.get("SMTP_FROM", self.username)

        to_env = os.environ.get("ALERT_EMAIL_TO", os.environ.get("EMAIL_TO", ""))
        self.to_addrs = to_addrs or [addr.strip() for addr in to_env.split(",") if addr.strip()]

        if not (self.username and self.password and self.to_addrs):
            logger.warning(
                "[Email] SMTP_USER, SMTP_PASS, or ALERT_EMAIL_TO not set. "
                "Email notifications will be skipped."
            )

    @property
    def enabled(self) -> bool:
        return bool(self.username and self.password and self.to_addrs)

    def send_digest(self, jobs: list[dict]) -> bool:
        """
        Sends a single digest email for a list of jobs.
        If the list is empty, does nothing and returns True.
        """
        if not jobs:
            logger.info("[Email] 0 new jobs to notify — skipping digest email.")
            return True
            
        if not self.enabled:
            logger.warning("[Email] Skipping digest (not configured). %d jobs missed.", len(jobs))
            return False

        now_date = datetime.now().strftime("%Y-%m-%d")
        subject = f"🚀 {len(jobs)} New AI/DS/SDE Openings — {now_date}"
        
        text_body = self._build_text_digest(jobs, now_date)
        html_body = self._build_html_digest(jobs, now_date)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        
        if len(self.to_addrs) == 1:
            msg["To"] = self.to_addrs[0]
        else:
            msg["To"] = self.from_addr  # Bcc is handled by sendmail envelope

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        for attempt in range(3):
            try:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
                    logger.info("[Email] Sent digest of %d jobs to %s", len(jobs), self.to_addrs)
                    return True
            except smtplib.SMTPAuthenticationError as exc:
                logger.error("[Email] Auth failed: %s", exc)
                return False  # Don't retry auth failures
            except Exception as exc:
                wait = 2 ** attempt
                logger.warning("[Email] Attempt %d failed: %s — retry in %ds", attempt + 1, exc, wait)
                time.sleep(wait)

        logger.error("[Email] All retries failed for digest of %d jobs", len(jobs))
        return False

    def _build_text_digest(self, jobs: list[dict], date_str: str) -> str:
        lines = [f"Subject: 🚀 {len(jobs)} New AI/DS/SDE Openings — {date_str}", ""]
        for i, job in enumerate(jobs, 1):
            lines.append(self.format_job_text(job, i))
        return "\n".join(lines)

    def _build_html_digest(self, jobs: list[dict], date_str: str) -> str:
        job_blocks = "\n".join(self.format_job_html(job) for job in jobs)
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>New Job Alerts</title></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;background:#f5f5f5">
  <div style="background:white;border-radius:12px;padding:30px;box-shadow:0 2px 8px rgba(0,0,0,.1)">
    <h2 style="color:#6c63ff;margin-top:0">🚀 {len(jobs)} New Job Openings</h2>
    <p style="color:#555;font-size:14px;margin-bottom:24px;">Found on {date_str}</p>
    
    {job_blocks}
    
    <p style="color:#aaa;font-size:12px;margin-top:24px;text-align:center">
      Sent by AI Job Hunter Agent
    </p>
  </div>
</body>
</html>"""

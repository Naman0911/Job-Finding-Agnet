"""
notifier/base_notifier.py
Abstract base for all notification channels.
Every notifier must implement send_digest(jobs).

v4 changes:
  - Changed interface from `send(job)` to `send_digest(jobs)` for single digest email per run.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone


class BaseNotifier(abc.ABC):
    """
    Abstract notification interface.
    All notifiers receive a list of normalised job dicts and format them.
    """

    @abc.abstractmethod
    def send_digest(self, jobs: list[dict]) -> bool:
        """
        Send a batch digest of job alerts.

        Args:
            jobs: List of normalised job dicts from the database.

        Returns:
            True if the notification was sent successfully, False otherwise.
        """
        ...

    @staticmethod
    def format_job_text(job: dict, index: int = 1) -> str:
        """
        Format a single job as text for the digest.
        """
        ts = job.get("first_seen_at", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                # Convert to IST (UTC+5:30)
                from datetime import timedelta
                ist = dt + timedelta(hours=5, minutes=30)
                ts = ist.strftime("%Y-%m-%d %H:%M IST")
            except ValueError:
                pass

        source = job.get("source", "Company careers page")

        lines = [
            f"{index}) Company:    {job.get('company', 'N/A')}",
            f"   Role:       {job.get('title', 'N/A')}",
            f"   Location:   {job.get('location', 'N/A')}",
            f"   Source:     {source}",
            f"   Link:       {job.get('url', 'N/A')}",
            f"   First seen: {ts}",
            ""
        ]
        return "\n".join(lines)

    @staticmethod
    def format_job_html(job: dict) -> str:
        """HTML version of a single job for the digest email."""
        ts = job.get("first_seen_at", "")
        if ts:
            try:
                from datetime import timedelta
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ist = dt + timedelta(hours=5, minutes=30)
                ts = ist.strftime("%Y-%m-%d %H:%M IST")
            except ValueError:
                pass

        url = job.get("url", "#")
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        location = job.get("location", "N/A")
        source = job.get("source", "Company careers page")

        return f"""
        <div style="margin-bottom: 24px; padding-bottom: 24px; border-bottom: 1px solid #eee;">
            <table style="width:100%;border-collapse:collapse">
              <tr><td style="padding:4px 0;color:#555;width:110px"><b>Company</b></td>
                  <td style="padding:4px 0;color:#222">{company}</td></tr>
              <tr><td style="padding:4px 0;color:#555"><b>Role</b></td>
                  <td style="padding:4px 0;color:#222"><a href="{url}" style="color:#6c63ff;text-decoration:none;"><b>{title}</b></a></td></tr>
              <tr><td style="padding:4px 0;color:#555"><b>Location</b></td>
                  <td style="padding:4px 0;color:#222">{location}</td></tr>
              <tr><td style="padding:4px 0;color:#555"><b>Source</b></td>
                  <td style="padding:4px 0;color:#222">{source}</td></tr>
              <tr><td style="padding:4px 0;color:#555"><b>First seen</b></td>
                  <td style="padding:4px 0;color:#888;font-size:13px">{ts}</td></tr>
            </table>
            <div style="margin-top:16px;">
              <a href="{url}" style="background:#6c63ff;color:white;padding:8px 20px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block">
                Apply Now →
              </a>
            </div>
        </div>
        """

"""
tests/test_notifier.py
Tests for Telegram and Email notifiers (mocked — no real API calls).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock

from notifier.base_notifier import BaseNotifier
from notifier.telegram_notifier import TelegramNotifier
from notifier.email_notifier import EmailNotifier


# ── Sample job dict ───────────────────────────────────────────────────────────

SAMPLE_JOB = {
    "id": 1,
    "company": "Persistent Systems",
    "title": "Machine Learning Engineer",
    "location": "Pune",
    "url": "https://example.com/job/123",
    "posted_date": "2026-07-09",
    "first_seen_at": "2026-07-09T09:00:00+00:00",
    "dedup_hash": "abc123",
    "notified": 0,
}


# ── BaseNotifier message format ───────────────────────────────────────────────

class ConcreteNotifier(BaseNotifier):
    def send(self, job: dict) -> bool:
        return True


class TestBaseNotifierFormat:

    def test_plain_text_format(self):
        n = ConcreteNotifier()
        msg = n.format_message(SAMPLE_JOB)
        assert "🚀 New AI/DS Opening" in msg
        assert "Persistent Systems" in msg
        assert "Machine Learning Engineer" in msg
        assert "Pune" in msg
        assert "https://example.com/job/123" in msg
        assert "IST" in msg

    def test_html_format_contains_link(self):
        n = ConcreteNotifier()
        html = n.format_html(SAMPLE_JOB)
        assert "<b>" in html
        assert "href=" in html
        assert "Persistent Systems" in html
        assert "Machine Learning Engineer" in html

    def test_send_batch_calls_send_per_job(self):
        n = ConcreteNotifier()
        jobs = [SAMPLE_JOB, {**SAMPLE_JOB, "title": "Data Scientist"}]
        results = n.send_batch(jobs)
        assert results == [True, True]


# ── Telegram notifier ─────────────────────────────────────────────────────────

class TestTelegramNotifier:

    def test_disabled_without_config(self):
        notifier = TelegramNotifier(token="", chat_id="")
        assert not notifier.enabled

    def test_enabled_with_config(self):
        notifier = TelegramNotifier(token="fake_token", chat_id="123456")
        assert notifier.enabled

    def test_send_success(self):
        notifier = TelegramNotifier(token="fake_token", chat_id="123456")
        with patch("notifier.telegram_notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            result = notifier.send(SAMPLE_JOB)
        assert result is True

    def test_send_api_error_returns_false(self):
        notifier = TelegramNotifier(token="fake_token", chat_id="123456")
        with patch("notifier.telegram_notifier.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            mock_post.return_value = mock_resp

            result = notifier.send(SAMPLE_JOB)
        assert result is False

    def test_send_skips_when_disabled(self):
        notifier = TelegramNotifier(token="", chat_id="")
        result = notifier.send(SAMPLE_JOB)
        assert result is False

    def test_rate_limit_retry(self):
        notifier = TelegramNotifier(token="fake_token", chat_id="123456")
        responses = [
            MagicMock(status_code=429, json=lambda: {"parameters": {"retry_after": 0}}),
            MagicMock(status_code=200),
        ]
        with patch("notifier.telegram_notifier.requests.post", side_effect=responses):
            with patch("notifier.telegram_notifier.time.sleep"):
                result = notifier.send(SAMPLE_JOB)
        assert result is True


# ── Email notifier ────────────────────────────────────────────────────────────

class TestEmailNotifier:

    def test_disabled_without_config(self):
        notifier = EmailNotifier(username="", password="", to_addrs=[])
        assert not notifier.enabled

    def test_enabled_with_config(self):
        notifier = EmailNotifier(
            username="test@gmail.com",
            password="app-password",
            to_addrs=["recipient@gmail.com"],
        )
        assert notifier.enabled

    def test_send_success(self):
        notifier = EmailNotifier(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            username="test@gmail.com",
            password="app-password",
            from_addr="test@gmail.com",
            to_addrs=["recipient@gmail.com"],
        )
        with patch("notifier.email_notifier.smtplib.SMTP") as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__ = lambda s: mock_server
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            result = notifier.send(SAMPLE_JOB)
        assert result is True

    def test_html_email_body(self):
        notifier = EmailNotifier(
            username="a@b.com", password="pw", to_addrs=["c@d.com"]
        )
        html = notifier._build_html_email(SAMPLE_JOB)
        assert "Persistent Systems" in html
        assert "Machine Learning Engineer" in html
        assert "Apply Now" in html
        assert "Pune" in html

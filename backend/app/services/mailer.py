"""Outgoing account email over SMTP. Not configured → nothing is sent and callers say so.

The message body never contains financial data. Credentials come from environment variables only.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger("vitram.mail")


class MailNotConfigured(Exception):
    pass


def send(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.email_configured:
        raise MailNotConfigured()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        if s.smtp_starttls:
            smtp.starttls()
        username = s.smtp_username or s.smtp_user
        if username:
            smtp.login(username, s.smtp_password or "")
        smtp.send_message(msg)
    log.info("account email sent")

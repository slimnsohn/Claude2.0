"""Email alert sender (optional, lower priority)."""

import logging
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email_alert(
    subject: str,
    body: str,
    to_addr: str,
    from_addr: str = None,
    smtp_host: str = "localhost",
    smtp_port: int = 587,
    smtp_user: str = None,
    smtp_pass: str = None,
):
    """Send a plain-text email alert. Configure SMTP via params or env vars."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr or smtp_user or "mismatch-detector@localhost"
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            if smtp_port == 587:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info(f"Email sent to {to_addr}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

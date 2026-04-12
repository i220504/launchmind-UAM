from __future__ import annotations

import smtplib
from email.message import EmailMessage

import requests

from config import settings
from utils.logger import get_logger
from utils.retry import retry_call


class EmailClient:
    def __init__(self) -> None:
        self.logger = get_logger("email_client")

    def validate(self) -> None:
        if settings.sendgrid_api_key and settings.email_from and settings.email_to:
            self.logger.info("Email client configured for SendGrid")
            return
        if all([settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.email_from, settings.email_to]):
            self.logger.info("Email client configured for SMTP")
            return
        raise ValueError("Email environment variables are incomplete")

    def send_email(self, subject: str, body: str) -> dict[str, str]:
        if settings.sendgrid_api_key:
            return self._send_with_sendgrid(subject, body)
        return self._send_with_smtp(subject, body)

    def _send_with_sendgrid(self, subject: str, body: str) -> dict[str, str]:
        payload = {
            "personalizations": [{"to": [{"email": settings.email_to}]}],
            "from": {"email": settings.email_from},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }

        def _do() -> dict[str, str]:
            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {settings.sendgrid_api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=45,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"SendGrid API error {response.status_code}: {response.text}")
            return {"provider": "sendgrid", "status": str(response.status_code)}

        return retry_call(_do, retry_on=(requests.RequestException, RuntimeError))

    def _send_with_smtp(self, subject: str, body: str) -> dict[str, str]:
        def _do() -> dict[str, str]:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = settings.email_from
            msg["To"] = settings.email_to
            msg.set_content(body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=45) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg)
            return {"provider": "smtp", "status": "sent"}

        return retry_call(_do, retry_on=(smtplib.SMTPException, OSError, RuntimeError))

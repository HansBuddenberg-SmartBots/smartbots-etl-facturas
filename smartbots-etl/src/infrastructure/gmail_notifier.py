"""Notificador via Gmail API con soporte de templates HTML."""

from __future__ import annotations

import base64
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import structlog
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = structlog.get_logger()

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailNotifier:
    """Envía notificaciones HTML por email via Gmail API con soporte de templates."""

    def __init__(
        self,
        credentials_path: str,
        delegated_user: str,
        sender: str,
        templates_dir: Path,
    ) -> None:
        creds = Credentials.from_service_account_file(credentials_path, scopes=GMAIL_SCOPES)
        delegated = creds.with_subject(delegated_user)
        self._service = build("gmail", "v1", credentials=delegated)
        self._sender = sender
        self._templates_dir = templates_dir

    def send(
        self,
        subject: str,
        template_name: str,
        template_vars: dict[str, Any],
        recipients: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[Path] | None = None,
    ) -> None:
        """Envía un email HTML usando un template."""
        html_body = self._render_template(template_name, template_vars)

        msg = MIMEMultipart("mixed")
        msg["From"] = self._sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        # HTML + plain text alternativo
        alternative = MIMEMultipart("alternative")
        text_fallback = self._html_to_plain(html_body)
        alternative.attach(MIMEText(text_fallback, "plain"))
        alternative.attach(MIMEText(html_body, "html"))
        msg.attach(alternative)

        # Attachments
        for path in attachments or []:
            if path.exists():
                part = MIMEBase("application", "octet-stream")
                part.set_payload(path.read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={path.name}",
                )
                msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        result = self._service.users().messages().send(userId="me", body={"raw": raw}).execute()

        message_id = result.get("id", "unknown")
        logger.info(
            "gmail_sent",
            message_id=message_id,
            recipients=recipients,
            cc=cc,
            subject=subject,
        )

    def _render_template(self, template_name: str, variables: dict[str, Any]) -> str:
        """Carga y renderiza un template HTML con sustitución de variables.

        Usa regex para reemplazar solo placeholders {word_chars}, lo que permite
        que las llaves CSS ({ margin: 0; }) no sean afectadas.
        """
        template_path = self._templates_dir / template_name
        if not template_path.exists():
            msg = f"Template no encontrado: {template_path}"
            raise FileNotFoundError(msg)

        html = template_path.read_text(encoding="utf-8")

        def _replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            return match.group(0)

        return re.sub(r"\{(\w+)\}", _replacer, html)

    @staticmethod
    def _html_to_plain(html: str) -> str:
        """Conversión básica de HTML a texto plano para fallback."""
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

"""OAuth-based Gmail notifier."""

from __future__ import annotations

import base64
import json
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = structlog.get_logger()

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class OAuthGmailNotifier:
    def __init__(
        self,
        credentials_path: str,
        token_path: str,
        sender: str,
        templates_dir: Path,
    ) -> None:
        creds_path = Path(credentials_path)
        token_file = Path(token_path)

        with open(creds_path) as f:
            client_config = json.load(f).get("installed", {})

        with open(token_file) as f:
            token_data = json.load(f)

        self._creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id", client_config.get("client_id")),
            client_secret=token_data.get("client_secret", client_config.get("client_secret")),
            scopes=token_data.get("scopes", GMAIL_SCOPES),
        )

        self._token_path = token_file
        self._service = build("gmail", "v1", credentials=self._creds)
        self._sender = sender
        self._templates_dir = templates_dir

    def _save_token(self) -> None:
        token_data = {
            "token": self._creds.token,
            "refresh_token": self._creds.refresh_token,
            "token_uri": self._creds.token_uri,
            "client_id": self._creds.client_id,
            "client_secret": self._creds.client_secret,
            "scopes": self._creds.scopes,
        }
        self._token_path.write_text(json.dumps(token_data, indent=2))

    def _ensure_valid_token(self) -> None:
        if self._creds.expired:
            self._creds.refresh(None)
            self._save_token()
            logger.info("oauth_gmail_token_refreshed")

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
        self._ensure_valid_token()
        html_body = self._render_template(template_name, template_vars)

        msg = MIMEMultipart("mixed")
        msg["From"] = self._sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        alternative = MIMEMultipart("alternative")
        text_fallback = self._html_to_plain(html_body)
        alternative.attach(MIMEText(text_fallback, "plain"))
        alternative.attach(MIMEText(html_body, "html"))
        msg.attach(alternative)

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
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

from typing import Any, Protocol
from pathlib import Path


class Notifier(Protocol):
    def send(
        self,
        subject: str,
        template_name: str,
        template_vars: dict[str, Any],
        recipients: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[Path] | None = None,
    ) -> None: ...

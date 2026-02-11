import re
from pathlib import Path

import pytest

from src.infrastructure.gmail_notifier import GmailNotifier


class _FakeNotifier:
    def __init__(self, templates_dir: Path):
        self._templates_dir = templates_dir

    _render_template = GmailNotifier._render_template


class TestRenderTemplate:
    def test_substitutes_placeholders(self, tmp_path):
        template = tmp_path / "test.html"
        template.write_text("<p>{run_id} - {timestamp}</p>", encoding="utf-8")

        notifier = _FakeNotifier(tmp_path)
        result = notifier._render_template(
            "test.html", {"run_id": "abc-123", "timestamp": "2026-02-11"}
        )
        assert "abc-123" in result
        assert "2026-02-11" in result

    def test_preserves_css_braces(self, tmp_path):
        template = tmp_path / "css.html"
        template.write_text(
            "<style>body { margin: 0; color: #333; }</style><p>{run_id}</p>",
            encoding="utf-8",
        )

        notifier = _FakeNotifier(tmp_path)
        result = notifier._render_template("css.html", {"run_id": "xyz"})
        assert "{ margin: 0; color: #333; }" in result
        assert "xyz" in result

    def test_missing_template_raises(self, tmp_path):
        notifier = _FakeNotifier(tmp_path)
        with pytest.raises(FileNotFoundError, match="no_existe.html"):
            notifier._render_template("no_existe.html", {})

    def test_unknown_placeholder_preserved(self, tmp_path):
        template = tmp_path / "partial.html"
        template.write_text("<p>{known} {unknown_var}</p>", encoding="utf-8")

        notifier = _FakeNotifier(tmp_path)
        result = notifier._render_template("partial.html", {"known": "YES"})
        assert "YES" in result
        assert "{unknown_var}" in result


class TestHtmlToPlain:
    def test_strips_tags(self):
        result = GmailNotifier._html_to_plain("<p>Hello <b>World</b></p>")
        assert result == "Hello World"

    def test_converts_br_to_newline(self):
        result = GmailNotifier._html_to_plain("Line1<br/>Line2<br>Line3")
        assert "Line1\nLine2\nLine3" in result

    def test_collapses_multiple_newlines(self):
        result = GmailNotifier._html_to_plain("<p>A</p>\n\n\n\n<p>B</p>")
        assert "\n\n\n" not in result

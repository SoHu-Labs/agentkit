"""Tests for agentkit.gmail — mock googleapiclient, test payload decoding and body cleaning."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentkit.gmail import (
    GmailApiBackend,
    GmailBackend,
    GmailFacade,
    GmailError,
    GmailAuthError,
    GmailMessageNotFoundError,
    clean_email_body,
    resolve_spec_to_message,
)
from agentkit.gmail._client import _extract_body_from_payload, _strip_html


class TestPayloadDecoding:
    def test_extract_plain_text(self):
        payload = {
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQ="},  # "Hello World"
        }
        assert "Hello World" in _extract_body_from_payload(payload)

    def test_extract_html_converts_to_text(self):
        payload = {
            "mimeType": "text/html",
            "body": {"data": "PHA-SGk8L3A-"},
        }
        result = _extract_body_from_payload(payload)
        assert result is not None

    def test_extract_from_parts(self):
        payload = {
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "SGVsbG8="}},
                {"mimeType": "text/html", "body": {"data": "PHAtQnllPC9wPg=="}},
            ]
        }
        result = _extract_body_from_payload(payload)
        assert "Hello" in result

    def test_extract_returns_empty_for_no_body(self):
        assert _extract_body_from_payload({}) == ""


class TestStripHtml:
    def test_removes_tags(self):
        assert "Hello World" in _strip_html("<html><body><p>Hello World</p></body></html>")

    def test_converts_br_to_newline(self):
        result = _strip_html("Line1<br>Line2")
        assert "Line1" in result
        assert "Line2" in result

    def test_removes_style_and_script(self):
        result = _strip_html("<style>body{}</style><script>x()</script>Clean")
        assert "Clean" in result
        assert "body{}" not in result


class TestCleanEmailBody:
    def test_removes_quoted_lines(self):
        body = "Hello\n> quoted text\n> more quoted\nWorld"
        cleaned = clean_email_body(body)
        assert "Hello" in cleaned
        assert "World" in cleaned
        assert "quoted text" not in cleaned

    def test_removes_german_sign_off(self):
        body = "Invoice attached\nMit freundlichen Gr\u00fc\u00dfen\nJohn Doe"
        cleaned = clean_email_body(body)
        assert "Invoice attached" in cleaned
        assert "Mit freundlichen" not in cleaned

    def test_removes_forwarded_blocks(self):
        body = "Here is the mail\n--- Forwarded message ---\nOriginal text"
        cleaned = clean_email_body(body)
        assert "Original text" not in cleaned

    def test_collapses_whitespace(self):
        body = "Line1\n\n\n\nLine2"
        cleaned = clean_email_body(body)
        assert cleaned.count("\n\n") == 1


class TestGmailFacade:
    def test_get_message_delegates_to_backend(self):
        backend = MagicMock(spec=GmailBackend)
        backend.fetch_message_body.return_value = "message body"
        facade = GmailFacade(backend)
        assert facade.get_message("msg1") == "message body"

    def test_get_message_wraps_error(self):
        backend = MagicMock(spec=GmailBackend)
        backend.fetch_message_body.side_effect = RuntimeError("boom")
        facade = GmailFacade(backend)
        with pytest.raises(GmailError, match="boom"):
            facade.get_message("msg1")

    def test_search_delegates(self):
        backend = MagicMock(spec=GmailBackend)
        backend.search_messages.return_value = [{"id": "1", "threadId": "t1"}]
        facade = GmailFacade(backend)
        assert facade.search("test") == [{"id": "1", "threadId": "t1"}]


class TestGmailApiBackend:
    def test_constructor_accepts_custom_path(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text('{"token": "test"}')
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_file") as m:
            mock_creds = MagicMock()
            mock_creds.valid = True
            m.return_value = mock_creds
            backend = GmailApiBackend(credentials_path=token)
            assert backend._creds is not None


class TestResolveSpecToMessage:
    def test_resolves_message_id_like_spec(self):
        client = MagicMock(spec=GmailFacade)
        client.get_message.return_value = "email body"
        msg_id, body = resolve_spec_to_message(client, "msg@example.com")
        assert body == "email body"

    def test_falls_back_to_search(self):
        client = MagicMock(spec=GmailFacade)
        client.get_message.side_effect = GmailError("nope")
        client.search.return_value = [{"id": "abc", "threadId": "t1"}]
        client.get_message.side_effect = None
        client.get_message.return_value = "found via search"
        msg_id, body = resolve_spec_to_message(client, "some query")
        assert body == "found via search"

    def test_raises_when_no_results(self):
        client = MagicMock(spec=GmailFacade)
        client.get_message.side_effect = GmailError("nope")
        client.search.return_value = []
        with pytest.raises(GmailError, match="No messages found"):
            resolve_spec_to_message(client, "nothing")


class TestExceptions:
    def test_gmail_error_hierarchy(self):
        assert issubclass(GmailAuthError, GmailError)
        assert issubclass(GmailMessageNotFoundError, GmailError)

    def test_auth_error_message(self):
        with pytest.raises(GmailAuthError):
            GmailApiBackend(credentials_path=Path("/nonexistent.json"))

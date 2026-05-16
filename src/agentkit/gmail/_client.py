"""Gmail API client — Protocol-based backend, facade, payload decoding, body cleaning."""
from __future__ import annotations

import base64
import json
import os
import re
from html import unescape
from pathlib import Path
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class GmailBackend(Protocol):
    """Pluggable Gmail read-only backend."""

    def fetch_message_body(self, message_id: str) -> str: ...
    def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, str]]: ...


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class GmailFacade:
    """Wraps a GmailBackend with error handling and payload decoding."""

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    def get_message(self, message_id: str) -> str:
        try:
            return self._backend.fetch_message_body(message_id)
        except GmailError:
            raise
        except Exception as e:
            raise GmailError(f"Failed to fetch message {message_id}: {e}") from e

    def search(self, query: str, max_results: int = 10) -> list[dict[str, str]]:
        try:
            return self._backend.search_messages(query, max_results=max_results)
        except GmailError:
            raise
        except Exception as e:
            raise GmailError(f"Search failed for '{query}': {e}") from e


# ---------------------------------------------------------------------------
# Gmail API Backend
# ---------------------------------------------------------------------------


class GmailApiBackend:
    """GmailBackend using googleapiclient (the standard Gmail REST API)."""

    def __init__(
        self,
        credentials_path: Path | str | None = None,
        *,
        token_env_var: str = "GOOGLE_OAUTH_TOKEN",
        scopes: tuple[str, ...] = ("https://www.googleapis.com/auth/gmail.readonly",),
    ) -> None:
        self._creds = self._load_credentials(credentials_path, token_env_var, scopes)
        self._service = None

    @staticmethod
    def _load_credentials(
        credentials_path: Path | str | None,
        token_env_var: str,
        scopes: tuple[str, ...],
    ) -> Any:
        from google.oauth2.credentials import Credentials

        path = Path(credentials_path) if credentials_path else None

        if path and path.is_file():
            creds = Credentials.from_authorized_user_file(str(path), scopes=list(scopes))
            if creds and creds.valid:
                return creds
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                return creds

        env_path = os.environ.get(token_env_var, "").strip()
        if env_path:
            token_file = Path(env_path).expanduser()
            if token_file.is_file():
                creds = Credentials.from_authorized_user_file(str(token_file), scopes=list(scopes))
                if creds and creds.valid:
                    return creds

        default_path = Path.home() / ".config" / "gmail_token.json"
        if default_path.is_file():
            creds = Credentials.from_authorized_user_file(str(default_path), scopes=list(scopes))
            if creds and creds.valid:
                return creds

        raise GmailAuthError(
            "No valid Gmail credentials found. Set GOOGLE_OAUTH_TOKEN env var, "
            f"or place a token at {default_path}."
        )

    def _get_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build
            self._service = build("gmail", "v1", credentials=self._creds)
        return self._service

    def fetch_message_body(self, message_id: str) -> str:
        from googleapiclient.errors import HttpError

        try:
            service = self._get_service()
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
        except HttpError as e:
            if e.resp.status == 404:
                raise GmailMessageNotFoundError(f"Message {message_id} not found") from e
            raise GmailError(str(e)) from e

        payload = msg.get("payload", {})
        body = _extract_body_from_payload(payload)
        if not body:
            body = _extract_body_from_payload(payload)
        return body


    def search_messages(self, query: str, max_results: int = 10) -> list[dict[str, str]]:
        from googleapiclient.errors import HttpError

        try:
            service = self._get_service()
            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )
        except HttpError as e:
            raise GmailError(str(e)) from e

        return [
            {"id": m["id"], "threadId": m.get("threadId", "")}
            for m in results.get("messages", [])
        ]


# ---------------------------------------------------------------------------
# Payload decoding
# ---------------------------------------------------------------------------


def _extract_body_from_payload(payload: dict) -> str:
    """Extract plaintext or HTML body from a Gmail message payload part."""
    if "parts" in payload:
        for part in payload["parts"]:
            result = _extract_body_from_payload(part)
            if result:
                return result
        return ""

    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data", "")
    if not data:
        return ""

    try:
        decoded = base64.urlsafe_b64decode(data + "===").decode("utf-8", errors="replace")
    except Exception:
        return ""

    if mime == "text/plain":
        return decoded
    if mime == "text/html":
        return _strip_html(decoded)

    return ""


def _strip_html(html: str) -> str:
    """Convert HTML email body to plaintext."""
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    text = unescape(html)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Body cleaning
# ---------------------------------------------------------------------------


def clean_email_body(raw: str) -> str:
    """Remove quoted replies, forwarded blocks, signatures, and excess whitespace.

    Handles German sign-offs (Mit freundlichen Grüßen, Viele Grüße, etc.).
    """
    cleaned = re.sub(r"^>.*$", "", raw, flags=re.MULTILINE)

    cleaned = re.sub(
        r"(?i)-+ ?forwarded message ?-+.*$",
        "",
        cleaned,
        flags=re.DOTALL,
    )

    sign_offs = [
        r"Mit freundlichen Gr(ü|u)(ß|ss)en.*$",
        r"Viele Gr(ü|u)(ß|ss)e.*$",
        r"Liebe Gr(ü|u)(ß|ss)e.*$",
        r"Herzliche Gr(ü|u)(ß|ss)e.*$",
        r"Beste Gr(ü|u)(ß|ss)e.*$",
        r"Best regards.*$",
        r"Kind regards.*$",
        r"Cheers.*$",
        r"Thanks.*$",
        r"Sent from my.*$",
        r"Get Outlook for.*$",
    ]
    for pattern in sign_offs:
        cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE | re.MULTILINE)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Message resolution
# ---------------------------------------------------------------------------


def resolve_spec_to_message(
    client: GmailFacade,
    spec: str,
    *,
    pick_index: int = 0,
) -> tuple[str, str]:
    """Resolve a message ID or Gmail search query to (message_ref, body).

    If *spec* looks like a message ID (contains '@'), fetch directly.
    Otherwise, treat it as a Gmail search query and return the first result.
    *pick_index* selects which search result to use (0 = first).
    """
    if "@" in spec and "." in spec.split("@")[-1]:
        try:
            body = client.get_message(spec)
            return spec, body
        except GmailError:
            pass

    results = client.search(spec, max_results=max(pick_index + 1, 5))
    if not results:
        raise GmailError(f"No messages found for query: {spec}")

    if pick_index >= len(results):
        raise GmailError(
            f"Query returned {len(results)} results, but pick_index={pick_index}"
        )

    msg = results[pick_index]
    body = client.get_message(msg["id"])
    return msg["id"], body


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GmailError(Exception):
    """Base for Gmail-related errors."""


class GmailAuthError(GmailError):
    """Authentication/credentials failure."""


class GmailMessageNotFoundError(GmailError):
    """Requested message not found in mailbox."""

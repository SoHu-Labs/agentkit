#!/usr/bin/env python3
"""Fetch + clean one Gmail message. Usage: gmail_fetch.py "<spec>".

resolve_spec_to_message returns (message_ref, body) — a tuple, not an object,
and subject is not available from this API. Verified against
src/agentkit/gmail/_client.py:245.
"""
from __future__ import annotations

import os
import sys

from agentkit.gmail import GmailApiBackend, clean_email_body, resolve_spec_to_message


def main() -> int:
    token = os.environ.get("GOOGLE_OAUTH_TOKEN", "").strip()
    if not token:
        print("Set GOOGLE_OAUTH_TOKEN to your OAuth token file path.", file=sys.stderr)
        return 1
    spec = sys.argv[1] if len(sys.argv) > 1 else "is:unread"
    backend = GmailApiBackend(credentials_path=token)
    msg_ref, body = resolve_spec_to_message(backend, spec)
    print(f"message: {msg_ref}")
    print(clean_email_body(body)[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

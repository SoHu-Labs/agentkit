#!/usr/bin/env python3
"""Start Brave with remote debugging and attach a Selenium driver (macOS).

chrome_driver_attach builds its own options internally and takes keyword-only
args; debugger_address is required. Verified against
src/agentkit/browser/_browser.py:112.
"""
from __future__ import annotations

from agentkit.browser import chrome_driver_attach, ensure_brave_running

_ADDR = "127.0.0.1:9222"  # matches ensure_brave_running's default


def main() -> int:
    ensure_brave_running(_ADDR)
    driver = chrome_driver_attach(debugger_address=_ADDR)
    print(f"attached. current_url={driver.current_url!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

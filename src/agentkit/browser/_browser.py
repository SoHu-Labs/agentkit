"""Browser helpers — Selenium/Brave attach and Chrome options for macOS automation."""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

_BRAVE_PATH_MACOS = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
_IS_MACOS = sys.platform == "darwin"


def _brave_cdp_ready(address: str, timeout_s: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(f"http://{address}/json/version")
        urllib.request.urlopen(req, timeout=timeout_s)
        return True
    except Exception:
        return False


def ensure_brave_running(
    address: str = "127.0.0.1:9222",
    *,
    launch_timeout_s: float = 30.0,
) -> None:
    if _brave_cdp_ready(address):
        return

    binary = _BRAVE_PATH_MACOS
    if not Path(binary).exists():
        if not _IS_MACOS:
            return
        raise RuntimeError(
            f"Brave not found at {binary!r} and is not listening on {address}. "
            "Start Brave manually with --remote-debugging-port first."
        )

    host, _, port_str = address.partition(":")
    port = int(port_str)

    with open(os.devnull, "w") as devnull:
        subprocess.Popen(
            [binary, f"--remote-debugging-port={port}", "--no-first-run", "--disable-extensions"],
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,
        )

    print(f"Launched Brave (port {port}), waiting up to {launch_timeout_s:.0f}s...", file=sys.stderr)
    deadline = time.monotonic() + launch_timeout_s
    while time.monotonic() < deadline:
        if _brave_cdp_ready(address):
            print("Brave ready.", file=sys.stderr)
            return
        time.sleep(0.5)
    raise RuntimeError(f"Brave did not become ready on {address} within {launch_timeout_s:.0f}s.")


def build_chrome_options(
    *,
    download_dir: Path,
    user_data_dir: Path | None = None,
    binary_location: str | None = None,
    headless: bool = False,
) -> Options:
    opts = Options()
    dl = str(download_dir.resolve())
    prefs: dict[str, object] = {
        "download.default_directory": dl,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "plugins.always_open_pdf_externally": True,
    }
    opts.add_experimental_option("prefs", prefs)
    if user_data_dir is not None:
        opts.add_argument(f"--user-data-dir={user_data_dir.resolve()}")
    if binary_location:
        opts.binary_location = binary_location
    if headless:
        opts.add_argument("--headless=new")
    return opts


def chrome_options_for_debugger(
    *,
    debugger_address: str,
    download_dir: Path | None = None,
) -> Options:
    opts = Options()
    opts.add_experimental_option("debuggerAddress", debugger_address.strip())
    if download_dir is not None:
        dl = str(download_dir.resolve())
        prefs: dict[str, object] = {
            "download.default_directory": dl,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
        }
        opts.add_experimental_option("prefs", prefs)
    return opts


def chrome_driver_attach(
    *,
    debugger_address: str,
    download_dir: Path | None = None,
) -> webdriver.Chrome:
    opts = chrome_options_for_debugger(
        debugger_address=debugger_address,
        download_dir=download_dir,
    )
    return webdriver.Chrome(options=opts)

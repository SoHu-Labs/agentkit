---
name: brave-attach
description: Start Brave with remote debugging and attach a Selenium driver on macOS. Use before any browser-automation task (email-digest unsubscribe, invoice-admin Google Ads download) or to debug "cannot connect to Brave / chromedriver" errors.
---

# agentkit Brave attach check

## Steps
1. `python skills/brave-attach/scripts/brave_attach.py`.
2. On success it prints `attached. current_url=...`. If it fails, the printed
   error tells you whether Brave failed to launch or the debugging port was not
   reachable.

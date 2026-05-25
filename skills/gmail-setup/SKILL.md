---
name: gmail-setup
description: Authenticate Gmail via agentkit and fetch one test message. Use when wiring up or debugging Gmail access (GOOGLE_OAUTH_TOKEN), or to confirm credentials work before running an email pipeline.
---

# agentkit Gmail setup check

## Steps
1. Set `GOOGLE_OAUTH_TOKEN` to the path of your OAuth token/credentials file.
2. `python skills/gmail-setup/scripts/gmail_fetch.py "<gmail-search-spec>"`
   (default spec: `is:unread`).
3. A subject line and a cleaned body excerpt print on success. An auth error
   means the token path or scopes are wrong.

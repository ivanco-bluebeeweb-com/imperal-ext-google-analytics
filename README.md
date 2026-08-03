# Google Analytics

Read-only GA4 reporting for Imperal. The MVP connects through Google OAuth, lists the GA4 properties the account can read, stores a local default property, and reads headline Overview metrics through the Google Analytics Admin and Data APIs. It does not change GA4 settings, events, audiences, data, or access.

> **Brand asset note:** `icon.svg` embeds the unmodified official Google-hosted product asset and is sourced from Google-hosted product branding; its provenance is recorded in `assets/ATTRIBUTION.md`.

## Current boundary

- Requests only `analytics.readonly` plus OIDC identity scopes.
- A `gmail.readonly` workaround was tried and reverted: Imperal's OAuth callback resolves a
  connected Google account's email via a Gmail-specific profile call for the "google"
  provider on every extension, not just Mail, and without any Gmail scope that lookup fails
  and the account is saved with an "unknown" email placeholder. Adding `gmail.readonly` did
  not fix that — it made the grant fail outright (0 accounts saved instead of 1 with
  "unknown"), because it's a Google *restricted* scope that needs app verification. Root
  cause is still open; it needs a platform-side fix or a verified Google app, not a scope
  change here.
- Does not modify Google Analytics properties, events, audiences, conversions or data.
- A connected account must later be verified and its accessible GA4 properties loaded before reports are shown.

## OAuth setup

1. Create a Google OAuth **Web application** client.
2. Add this redirect URI:

   `https://panel.imperal.io/v1/ext/google-analytics-bluebee/oauth/google/callback`

3. Save the client ID and secret in this application's Imperal secrets as `google_client_id` and `google_client_secret`.
4. Do not put OAuth credentials in source files, tests or chat.

## Local checks

```bash
imperal build .
imperal validate .
pytest
```

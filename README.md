# Google Analytics

Read-only GA4 reporting for Imperal. The MVP connects through Google OAuth, lists the GA4 properties the account can read, stores a local default property, and reads headline Overview metrics through the Google Analytics Admin and Data APIs. It does not change GA4 settings, events, audiences, data, or access.

> **Brand asset note:** `icon.svg` embeds the unmodified official Google-hosted product asset and is sourced from Google-hosted product branding; its provenance is recorded in `assets/ATTRIBUTION.md`.

## Current boundary

- Requests only `analytics.readonly` plus OIDC identity scopes.
- A `gmail.readonly` workaround was tried and reverted after root-causing the issue: Imperal's
  OAuth callback resolves a connected Google account's email via a Gmail-specific
  `getProfile` call for the "google" provider, on every extension, not just Mail. With
  `gmail.readonly` granted the Gmail call does succeed (the saved record gains an
  `unread_count` field), but email still lands as an "unknown" placeholder -- most likely
  because the platform reads a field named `email` out of that response, when Gmail actually
  returns the address under `emailAddress`. This is a platform bug outside this app's
  control; no scope choice here fixes it. This app correctly refuses to treat an
  "unknown"-email record as a usable connection rather than fabricate a status.
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

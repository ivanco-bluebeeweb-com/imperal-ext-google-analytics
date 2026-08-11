# Google Analytics

GA4 reporting for Imperal through the Google Analytics Admin and Data APIs,
plus optional property editing (Part D). Parts A (custom/canned reports), B
(account/property structure) and C (alert rules) only ever read from Google.
Part D (`handlers_admin_write.py`) writes to the user's actual GA4 property:
custom dimensions/metrics, key events (conversions), Google Ads links,
property settings, and data streams.

> **Brand asset note:** `icon.svg` embeds the unmodified official Google-hosted product asset and is sourced from Google-hosted product branding; its provenance is recorded in `assets/ATTRIBUTION.md`.

## Current boundary

- Requests `analytics.readonly` (Parts A/B/C) and `analytics.edit` (Part D) plus OIDC identity scopes.
- A `gmail.readonly` workaround was tried and reverted after root-causing the issue: Imperal's
  OAuth callback resolves a connected Google account's email via a Gmail-specific
  `getProfile` call for the "google" provider, on every extension, not just Mail. With
  `gmail.readonly` granted the Gmail call does succeed (the saved record gains an
  `unread_count` field), but email still lands as an "unknown" placeholder -- most likely
  because the platform reads a field named `email` out of that response, when Gmail actually
  returns the address under `emailAddress`. This is a platform bug outside this app's
  control; no scope choice here fixes it. This app correctly refuses to treat an
  "unknown"-email record as a usable connection rather than fabricate a status.
- Parts A/B/C never modify Google Analytics properties, events, audiences, conversions or data.
- Part D functions change real GA4 property configuration. Nothing in Part D is scheduled;
  every call is explicit.
- A connected account must later be verified and its accessible GA4 properties loaded before reports are shown.

## UI context refresh rule

Any action that changes the GA4 reporting context must refresh the surface that
can now be stale:

- **Account connected, disconnected, or switched:** refresh both the sidebar and
  the central reporting panel, because account choices and all report content may
  have changed.
- **Property selected:** refresh both surfaces, because the selected property is
  the global reporting context.
- **Period selected or report loaded:** refresh the central reporting panel; also
  refresh the sidebar when it owns the automatic initial-load action or displays
  related context.

Every new connect/switch/select flow must be checked against this rule in code
review and regression tests. The Overview header uses the GA4 property's display
name and the Google-style `Property ID: <id>` label; it must never present an ID
as if it were the site's name.

## Panel flow

- With no usable Google account, both the sidebar and main area offer only **Connect Google Account**.
- Once connected, the sidebar shows the account list, **Add another Google account**, then one GA4 property selector spanning every connected account.
- Report navigation appears only after a property is selected. Every visible section is backed by a live handler: Overview, Explore, Real-time, Site reports and Alerts.
- **Settings** stays as a separate secondary button at the bottom of the sidebar for account management.
- The property selector records the owning Google account, so selecting a property from a non-active account still routes reports to the right account.

## Part D: what the OWNER must do before write functions actually work

Code alone cannot make Part D work. Three things are outside this app's
control and must be done by the developer/owner:

1. **Add the `analytics.edit` scope in Google Cloud Console**, on the same
   OAuth client already used for `analytics.readonly`. It is a Google
   "sensitive" scope (not "restricted" -- no annual security assessment),
   but once the app serves more than Google's ~100-user OAuth testing cap,
   Google requires an app verification review (a form plus a short screen
   recording showing the scope in actual use) before every user can grant it.
2. **Every already-connected Google account must reconnect.** Old tokens were
   issued with only `analytics.readonly` and cannot write no matter what this
   code does. Reconnect flow: `disconnect_google_account` then
   `connect_google_analytics` again, and accept the new consent screen that
   now also asks for edit access.
3. **The account's role on the GA4 property itself must be Editor or
   Administrator**, set inside Google Analytics (Admin > Property Access
   Management), not inside Imperal. A Viewer/Analyst role gets
   `PERMISSION_DENIED` even with the right OAuth scope granted.

Until all three are true, Part D calls fail with the ordinary
`TOKEN_REJECTED` / `PERMISSION_DENIED` error codes -- that is Google's own
authorization stack refusing the call, not a bug in this app.

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

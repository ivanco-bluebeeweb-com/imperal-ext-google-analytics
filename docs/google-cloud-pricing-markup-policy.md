# Google Cloud pricing markup policy (standing rule)

**Status:** Standing policy — applies to every Imperal extension built by this
developer that calls a Google Cloud / Google Workspace API (Google Analytics,
Google Drive, Gmail, Google Search Console, Google Ads, and any future
Google-backed connector).

## Why this exists

Most Google Workspace/Cloud APIs (GA4 Data API, GA4 Admin API, Gmail API,
Drive API, etc.) do **not** charge a direct per-call fee — Google meters them
in request-quota units, not money. So there is no literal Google Cloud
invoice line to "pass through" per call.

The real cost to the developer is diffuse and not per-call: the Google Cloud
project itself, OAuth consent/verification overhead, ongoing engineering and
support liability, and the risk of eventually needing paid infrastructure
(BigQuery Export, quota increases, etc.) as usage grows. Because Imperal's
standard token tiers (0/8/12/16/20) were designed for zero-external-cost
extensions, any extension that depends on a Google Cloud-backed API should
carry a standing margin/risk buffer above that standard scale — paid by the
app's own users through slightly higher token prices, not absorbed by the
developer.

## The rule

For any Imperal extension whose tools call a Google Cloud / Google Workspace
API, **every tool price must be marked up from the platform's standard tier
scale by the same ratio used for Google Analytics**, established 2026-08-12:

| Standard tier | Google Cloud-backed price | Markup |
|---:|---:|---:|
| 0  | 0  | stays free (never gate onboarding) |
| 8  | 15 | ×1.875 |
| 12 | 22 | ×1.83 |
| 16 | 30 | ×1.875 |
| 20 | 35 | ×1.75 |

Rounded rule of thumb: **take the standard tier price and multiply by ~1.8x,
rounding to the nearest 5.** Tier 0 (onboarding/account plumbing: connect,
disconnect, switch account, select resource, pause/resume/delete a purely
local automation) always stays free regardless of this markup, so users are
never blocked from getting started.

## What counts as "uses Google Cloud"

Apply this markup if the extension's tools:
- call any `googleapis.com` REST API (Analytics, Drive, Gmail, Ads, Search
  Console, Calendar, Sheets, etc.), **or**
- depend on a Google OAuth client / Google Cloud project the developer
  provisions and maintains, **or**
- could plausibly grow into a billed Google service (e.g. BigQuery Export)
  as a natural next step for that extension.

Do not apply it to extensions with no Google dependency — their tools keep
the plain standard scale (0/8/12/16/20).

## How to apply it when pricing a new or existing Google-backed extension

1. Classify every tool into the extension's standard-scale tier the same way
   you would for a non-Google extension (0 = onboarding/local, 8 = light
   read, 12 = standard read, 16 = heavier/mutating, 20 = heaviest).
2. Convert each tier through the table above (0→0, 8→15, 12→22, 16→30,
   20→35).
3. If a tool doesn't cleanly fit an existing standard tier, price it at the
   nearest justified point on the *marked-up* scale (15/22/30/35) rather
   than inventing an ad hoc number.
4. Keep `pricing.notes` in `imperal.json` honest: state plainly that this is
   a standing margin/risk buffer, not a literal per-call Google Cloud bill,
   because most Google APIs used this way have no such bill.
5. Sync via `developer.update_pricing` while the app is `suspended`, same as
   any other pricing change; resubmit for review afterward.

## Precedent

First applied to `google-analytics-bluebee` (Google Analytics) on
2026-08-12: standard tiers 8/12/16/20 → marked-up tiers 15/22/30/35, tier 0
(connect/disconnect/switch/select/diagnostics/pause/resume/delete-of-local-
alert) left free. See that app's `tests/test_pricing.py` and
`imperal.json`'s `pricing.notes` for the worked example.

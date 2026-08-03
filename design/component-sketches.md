# Google Analytics MVP component sketches

## Connect Google Analytics

- Page title and official product icon (official asset must be added before release)
- Read-only access explanation
- `Connect Google account` external OAuth action
- Setup state with redirect URI and secrets link when credentials are missing

## Overview

- Implemented: metric cards (active users, sessions, views, conversions, revenue) from the cached last-loaded report
- Implemented: "Updated <timestamp>" caption per the plan's cache-transparency rule
- Implemented: empty state routes to the property picker; loaded state offers "Change property"
- Not yet implemented: period selector / comparison control beyond the fixed 7-day default, chart, top-changes and channel/landing-page tables

## Explore

- Not yet implemented — placeholder screen only

## Realtime

- Not yet implemented — placeholder screen only

## Properties (picker)

- Implemented: one card per GA4 property across every connected account, grouped by account email
- Implemented: "Selected" badge + disabled "Use this property" on the active pick; "Open in Google Analytics" deep link
- Implemented: empty states for "no usable account" and "no GA4 properties/insufficient access"

## Settings

- Implemented: list of connected accounts with live status (Connected / Reconnect needed / Insufficient access / Error), property count, and connected date
- Implemented: per-account "Check access" (read-only re-check), "Reconnect" (back to OAuth), "Disconnect" (destructive, confirmed, removes local account + selection + alert records; never revokes Google's own OAuth grant and never touches GA4 data)

## Alerts

- Implemented: notify-only rule creation form (account, property, metric, condition, threshold, daily/weekly schedule) and a list of existing rules with delete
- Implemented: daily scheduled evaluator (`evaluate_alerts`) that reads GA4, compares against the threshold, and sends an Imperal notification on trigger — never writes to Google, never touches budgets or campaigns
- Not yet implemented: editing an existing rule (delete + recreate for now)

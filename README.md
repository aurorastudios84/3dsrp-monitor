# 3DSRP Project Pulse

A public, static dashboard for aurorastudios84/3dsrp. No AI, paid APIs, backend, or JavaScript dependencies. Python uses only the standard library.

## Run locally

```sh
python3 -m unittest discover -s tests -v
python3 collect.py
python3 -m http.server 8080 --directory site
```

Open http://localhost:8080. The initial snapshot contains real GitHub data and three manually verified Reddit links. Missing access is explicitly shown as setup needed, never zero activity.

## Daily hosting

The included workflow runs at 06:23 UTC, on main pushes, or manually. GitHub schedules may be delayed. Enable Settings → Pages → GitHub Actions. Standard public-repository Actions runners and Pages are free. Daily snapshot commits keep the repository active; if collection stops for 60 days, GitHub may disable scheduling. The dashboard flags snapshots older than 36 hours. GitHub workflow notifications report failed runs; individual source failures appear in source status and preserve previous data.

The dashboard and its saved GitHub aggregates are PUBLIC. Secrets belong in repository Actions secrets, never config.json or browser code. GitHub stars/downloads work without extra setup. Automatic access to other sources must be configured:

| Secret | Purpose |
| --- | --- |
| `GH_METRICS_TOKEN` | Optional fine-grained GitHub token limited to `aurorastudios84/3dsrp`, with repository Administration: read. Enables repository views/clones. The dashboard's built-in token cannot read another repository's traffic. |
| `YOUTUBE_API_KEY` | Google Cloud API key with YouTube Data API v3 enabled, restricted to that API. Uses free quota; no paid search or AI service. |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_REFRESH_TOKEN` | Approved Reddit Data API app and permanent OAuth refresh token with read scope. Approval/eligibility are required; free availability is not guaranteed. |
| `MONITOR_FEEDS` | Optional JSON list: `[{"name":"3DSRP alerts","url":"https://..."}]`. Supports RSS/Atom, including a Google Alert RSS URL if available in your account. Feed URLs stay secret; discovered links are published. |

Google Alerts must be created manually for the queries in config.json. Choose RSS delivery if available. Without configured feeds, there is NO automatic general web/social search. Do not put private feed content into a public dashboard. Publisher feeds are ingested in full; use topic-specific feeds.

## Coverage and meaning

- GitHub: paginates all releases; records per-asset downloads, total application downloads, stars and forks daily. Source archives and checksums excluded from application totals. Totals are files, not users. Replaced/deleted assets can reduce counters. Daily snapshots overwrite the current day, not append duplicate dates.
- GitHub traffic: merges the rolling 14-day daily windows by timestamp, updating partial days. Daily uniques cannot be summed into unique people over a period. No historical traffic before the available window can be recovered.
- YouTube: up to 25 recent videos per configured query, then refreshes all discovered videos. Broad search candidates can be unrelated. Unavailable videos are removed. API-derived mention records expire after 30 days without a successful refresh.
- Reddit: up to 50 recent search results per query. Refreshes every known thread to show current scores, comment counts and net comment-count changes. This is not exhaustive Reddit search, global comment search, or a feed of individual replies. No comment bodies or post view counts are collected. Removed/unavailable threads are removed from the current snapshot. Seed links are manually verified, not automatically live metrics.
- Web: optional RSS/Atom. X, Instagram and Facebook are search shortcuts, not automatic scrapers. Login may be needed for native searches.
- Reading/bookmark/hide controls persist only in the current browser. All external text is escaped; only HTTP(S) links are rendered.

Only GitHub historical aggregates are committed to Git. Current mention data is loaded from the previous published snapshot and replaced at each deployment; it is excluded from Git history. Deployment artifacts expire after one day. No claim of unique audience, complete coverage, installs, active usage or causation is made.

## Configuration

Edit config.json for queries, public topic feeds, and verified seed links. Legacy Orbit terms can be added for historical discovery. Current queries prioritize 3DSRP and 3DS Remote Play. Repository references use the current aurorastudios84 account.

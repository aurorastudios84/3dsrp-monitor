#!/usr/bin/env python3
"""No paid services or AI. Fetch on the runner; publish only sanitized public data."""
import base64
import copy
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NOW = dt.datetime.now(dt.timezone.utc).isoformat()
TODAY = NOW[:10]


def request(url, headers=None, form=None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "3DSRP-Monitor/1.0", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def api(url, headers=None, form=None):
    return json.loads(request(url, headers, form))


def canonical(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Unsupported link")
    if p.hostname in ("www.google.com", "google.com") and p.path == "/url":
        target = urllib.parse.parse_qs(p.query).get("url", urllib.parse.parse_qs(p.query).get("q", [None]))[0]
        if target:
            return canonical(target)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.startswith("utm_") and k not in ("fbclid", "gclid")]
    host = p.hostname.lower().removeprefix("www.")
    match = re.search(r"/comments/([a-z0-9]+)", p.path) if host.endswith("reddit.com") else None
    if match:
        return "https://reddit.com/comments/" + match[1]
    return urllib.parse.urlunsplit(("https", host, p.path.rstrip("/"), urllib.parse.urlencode(query), ""))


def asset_group(name):
    name = name.lower()
    if name.endswith((".cia", ".3dsx")):
        return "Relay" if "relay" in name else "New 3DS"
    if name.endswith(".apk"):
        return "Android companion"
    if name.endswith(".exe"):
        return "Windows companion"
    return "Other / source"


def merge_mention(state, item):
    key = canonical(item["url"])
    prior = state["mentions"].get(key, {})
    state["mentions"][key] = {**prior, **item, "first_seen": prior.get("first_seen", NOW)}


def source(state, name, callback):
    previous = state["sources"].get(name, {})
    backup = copy.deepcopy(state)
    try:
        message = callback()
        state["sources"][name] = {"status": "ok", "message": message, "last_success": NOW, "checked_at": NOW}
    except Exception as exc:
        state.clear()
        state.update(backup)
        # Never expose exception URLs: query strings can contain API keys.
        reason = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
        state["sources"][name] = {**previous, "status": "error", "message": f"Refresh failed ({reason}); previous data retained.", "checked_at": NOW}


def unconfigured(state, name, message):
    state["sources"][name] = {**state["sources"].get(name, {}), "status": "setup", "message": message, "checked_at": NOW}


def collect_github(state, config):
    token = os.environ.get("GH_METRICS_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    base = "https://api.github.com/repos/" + config["repository"]
    repo = api(base, headers)
    assets = []
    page = 1
    while True:
        releases = api(f"{base}/releases?per_page=100&page={page}", headers)
        for release in releases:
            for a in release["assets"]:
                assets.append({"id": a["id"], "name": a["name"], "release": release["tag_name"], "downloads": a["download_count"], "group": asset_group(a["name"]), "url": a["browser_download_url"]})
        if len(releases) < 100:
            break
        page += 1
    summary = {"date": TODAY, "stars": repo["stargazers_count"], "forks": repo["forks_count"], "downloads": sum(a["downloads"] for a in assets if a["group"] != "Other / source")}
    history = {s["date"]: s for s in state.get("history", [])}
    history[TODAY] = summary
    state.update(repository=config["repository"], history=sorted(history.values(), key=lambda s: s["date"]), assets=assets)
    return "Stars, forks and release assets refreshed. Downloads are files, not unique users."


def collect_traffic(state, config, kind):
    token = os.environ.get("GH_METRICS_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        unconfigured(state, "GitHub " + kind, "Needs GH_METRICS_TOKEN with target repository Administration: read.")
        return
    def fetch():
        payload = api("https://api.github.com/repos/" + config["repository"] + "/traffic/" + kind, {"Authorization": "Bearer " + token})
        days = {x["timestamp"]: x for x in state.get("traffic", {}).get(kind, [])}
        for x in payload[kind]:
            days[x["timestamp"]] = x
        state.setdefault("traffic", {})[kind] = sorted(days.values(), key=lambda x: x["timestamp"])
        return "Daily counts saved; unique counts are per day, not additive."
    source(state, "GitHub " + kind, fetch)


def collect_youtube(state, config):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        unconfigured(state, "YouTube", "Add a free YOUTUBE_API_KEY to enable video discovery and metrics.")
        return
    def fetch():
        def yt(endpoint, params):
            return api("https://www.googleapis.com/youtube/v3/" + endpoint + "?" + urllib.parse.urlencode({**params, "key": key}))
        ids = {m["video_id"] for m in state["mentions"].values() if m.get("video_id")}
        for q in config["queries"]:
            found = yt("search", {"part": "snippet", "q": q, "type": "video", "order": "date", "maxResults": 25})
            ids.update(x["id"]["videoId"] for x in found.get("items", []))
        ids = sorted(ids)
        refreshed = set()
        for i in range(0, len(ids), 50):
            results = yt("videos", {"part": "snippet,statistics", "id": ",".join(ids[i:i+50])})
            for video in results.get("items", []):
                snippet, stats = video["snippet"], video.get("statistics", {})
                refreshed.add(video["id"])
                merge_mention(state, {"url": "https://www.youtube.com/watch?v=" + video["id"], "video_id": video["id"], "title": snippet["title"], "author": snippet["channelTitle"], "published_at": snippet["publishedAt"], "platform": "YouTube", "metrics": {k: int(stats[v]) for k, v in {"views": "viewCount", "likes": "likeCount", "comments": "commentCount"}.items() if v in stats}, "updated_at": NOW, "discovery": "API search"})
        for url, item in list(state["mentions"].items()):
            if item.get("video_id") and item["video_id"] not in refreshed:
                del state["mentions"][url]
        return "Up to 25 recent results per query; discovered videos refreshed daily. Search coverage is partial."
    source(state, "YouTube", fetch)


def collect_reddit(state, config):
    client, secret, refresh = (os.environ.get(n) for n in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_REFRESH_TOKEN"))
    if not all((client, secret, refresh)):
        unconfigured(state, "Reddit", "Seed threads available. Automatic discovery/comments require approved Reddit API access and OAuth secrets.")
        return
    def fetch():
        auth = base64.b64encode((client + ":" + secret).encode()).decode()
        token = api("https://www.reddit.com/api/v1/access_token", {"Authorization": "Basic " + auth}, {"grant_type": "refresh_token", "refresh_token": refresh})["access_token"]
        headers = {"Authorization": "Bearer " + token, "User-Agent": "web:3dsrp-monitor:1.0 (by /u/stepcach)"}
        def reddit(path):
            return api("https://oauth.reddit.com" + path, headers)
        posts = {}
        for q in config["queries"]:
            listing = reddit("/search?" + urllib.parse.urlencode({"q": q, "sort": "new", "limit": 50, "t": "all", "type": "link"}))
            for child in listing["data"]["children"]:
                posts[child["data"]["id"]] = child["data"]
        tracked = set(posts)
        for item in state["mentions"].values():
            if item.get("platform") == "Reddit":
                match = re.search(r"/comments/([a-z0-9]+)", item["url"])
                if match:
                    tracked.add(match[1])
        # Refresh all known posts, including older announcements; no comment bodies stored.
        tracked = sorted(tracked)
        found = set()
        for i in range(0, len(tracked), 100):
            listing = reddit("/api/info?" + urllib.parse.urlencode({"id": ",".join("t3_" + x for x in tracked[i:i+100])}))
            for child in listing["data"]["children"]:
                p = child["data"]
                if p.get("removed_by_category"):
                    continue
                found.add(p["id"])
                url = "https://www.reddit.com" + p["permalink"]
                old = state["mentions"].get(canonical(url), {}).get("metrics", {}).get("comments")
                merge_mention(state, {"url": url, "platform": "Reddit", "title": p["title"], "author": p.get("author"), "community": "r/" + p["subreddit"], "published_at": dt.datetime.fromtimestamp(p["created_utc"], dt.timezone.utc).isoformat(), "metrics": {"score": p["score"], "comments": p["num_comments"]}, "comment_change": p["num_comments"] - old if old is not None else None, "updated_at": NOW, "discovery": "Reddit API"})
        for url, item in list(state["mentions"].items()):
            if item.get("platform") == "Reddit":
                match = re.search(r"/comments/([a-z0-9]+)", item["url"])
                if match and match[1] not in found:
                    del state["mentions"][url]
        return "Up to 50 posts per query; known threads refreshed. Comment changes are net changes since the previous run. No global comment search or post views."
    source(state, "Reddit", fetch)


def collect_feed(state, feed):
    root = ET.fromstring(request(feed["url"]))
    count = 0
    for entry in list(root.findall(".//item")) + list(root.findall("{http://www.w3.org/2005/Atom}entry")):
        def value(name):
            el = entry.find(name)
            if el is None:
                el = entry.find("{http://www.w3.org/2005/Atom}" + name)
            return "" if el is None else "".join(el.itertext()).strip()
        link = value("link")
        if not link:
            el = entry.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        try:
            url = canonical(link)
        except ValueError:
            continue
        # Store plain titles and links only; no feed HTML is injected in the browser.
        merge_mention(state, {"url": url, "title": value("title"), "platform": "Web", "discovery": feed["name"], "updated_at": NOW})
        count += 1
    return f"{count} feed links processed; search-index coverage is partial."


def main():
    config = json.loads((ROOT / "config.json").read_text())
    path = ROOT / "site/data/dashboard.json"
    if path.exists():
        state = json.loads(path.read_text())
    elif os.environ.get("PREVIOUS_SNAPSHOT_URL"):
        try:
            state = api(os.environ["PREVIOUS_SNAPSHOT_URL"])
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            state = {"mentions": {}, "sources": {}, "history": [], "assets": []}
    else:
        state = {"mentions": {}, "sources": {}, "history": [], "assets": []}
    history_path = ROOT / "site/data/history.json"
    if history_path.exists():
        saved = json.loads(history_path.read_text())
        state["history"] = saved.get("history", [])
        state["traffic"] = saved.get("traffic", {})
    for item in config["seed_mentions"]:
        if not state.get("seeded") and canonical(item["url"]) not in state["mentions"]:
            merge_mention(state, {**item, "discovery": "Manually verified link"})
    state["seeded"] = True
    source(state, "GitHub", lambda: collect_github(state, config))
    for kind in ("views", "clones"):
        collect_traffic(state, config, kind)
    collect_youtube(state, config)
    collect_reddit(state, config)
    feeds = config["feeds"] + json.loads(os.environ.get("MONITOR_FEEDS", "[]"))
    for feed in feeds:
        source(state, "Feed: " + feed["name"], lambda f=feed: collect_feed(state, f))
    if not feeds:
        unconfigured(state, "Web alerts", "No RSS/Atom feeds configured. Add Google Alerts RSS feeds or relevant publisher feeds.")
    unconfigured(state, "X / Instagram / Facebook", "Search shortcuts only. No automatic collection or engagement metrics configured.")
    # Do not retain stale API content indefinitely when a connection fails.
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
    state["mentions"] = {k: m for k, m in state["mentions"].items() if m.get("discovery") not in ("API search", "Reddit API") or m.get("updated_at", "") >= cutoff}
    state["generated_at"] = NOW
    state["queries"] = config["queries"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)
    history_path.write_text(json.dumps({"history": state.get("history", []), "traffic": state.get("traffic", {})}, indent=2) + "\n")
    for name, status in state["sources"].items():
        print(f"{name}: {status['status']} — {status['message']}")


if __name__ == "__main__":
    main()

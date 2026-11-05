#!/usr/bin/env python3
"""Render the profile terminal from public GitHub data; Python stdlib only."""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOGIN = "hudbeard"
TEXT = "#c6d2db"
FONT_SIZE = 12.5
CELL = 7.53


def github(path, payload=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hudbeard-profile"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    data = None if payload is None else json.dumps(payload).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urlopen(Request(f"https://api.github.com/{path}", headers=headers, data=data), timeout=30) as response:
        body = response.read()
        return json.loads(body) if body else None


def public_data():
    profile = github(f"users/{LOGIN}")
    repos = []
    page = 1
    while True:
        batch = github(f"users/{LOGIN}/repos?type=owner&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return profile, repos


def collect_activity(profile, repos):
    """Count public default-branch authorship, deduplicated by commit SHA."""
    names = {repo["full_name"] for repo in repos if not repo.get("private")}
    first_year = int(profile["created_at"][:4])
    now = datetime.now(timezone.utc)
    for year in range(first_year, now.year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = f"{year}-12-31T23:59:59Z" if year < now.year else now.strftime("%Y-%m-%dT%H:%M:%SZ")
        query = '''query($login:String!, $from:DateTime!, $to:DateTime!) {
          user(login:$login) { contributionsCollection(from:$from,to:$to) {
            commitContributionsByRepository(maxRepositories:100) {
              repository { nameWithOwner isPrivate }
            }
          } }
        }'''
        result = github("graphql", {"query": query, "variables": {"login": LOGIN, "from": start, "to": end}})
        if result.get("errors"):
            raise RuntimeError("GitHub could not return the full contribution history")
        collection = result["data"]["user"]["contributionsCollection"]["commitContributionsByRepository"]
        if len(collection) == 100:
            raise RuntimeError("Contribution history exceeded GitHub's repository limit; refusing partial totals")
        # Never publish or request commit details for private repositories.
        names.update(item["repository"]["nameWithOwner"] for item in collection if not item["repository"]["isPrivate"])

    def authored_commits(name):
        commits = []
        page = 1
        while True:
            try:
                batch = github(f"repos/{name}/commits?per_page=100&page={page}")
            except HTTPError as error:
                if error.code == 409:  # Empty repositories have no commit history.
                    error.close()
                    return commits
                raise
            for commit in batch:
                linked = (commit.get("author") or {}).get("login", "").lower() == LOGIN
                unlinked = commit.get("author") is None and name.split("/")[0].lower() == LOGIN and commit["commit"]["author"]["name"].lower() == LOGIN
                if (linked or unlinked) and len(commit["parents"]) <= 1:
                    commits.append((commit["sha"], name))
            if len(batch) < 100:
                return commits
            page += 1

    commits = {}
    contributed = set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for batch in pool.map(authored_commits, sorted(names)):
            for sha, name in batch:
                commits.setdefault(sha, name)
                contributed.add(name)
    cache_path = ROOT / "assets/activity-cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def changes(item):
        sha, name = item
        if sha in cache:
            return sha, cache[sha]
        stats = github(f"repos/{name}/commits/{sha}")["stats"]
        return sha, {"added": stats["additions"], "deleted": stats["deletions"]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        current = dict(pool.map(changes, commits.items()))
    # Only cache immutable, public commit totals; no author names or email addresses.
    cache_path.write_text(json.dumps(current, sort_keys=True, indent=2) + "\n")
    added = sum(item["added"] for item in current.values())
    deleted = sum(item["deleted"] for item in current.values())
    return {"commits": len(commits), "contributed": len(contributed), "added": added, "deleted": deleted, "net": added - deleted}


def facts(profile, repos, activity):
    original = [repo for repo in repos if not repo.get("fork") and not repo.get("private")]
    joined = datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00")).strftime("%b %Y")
    return [
        ("OS", "HudbeardOS x86_64"),
        ("Kernel", "Linux"),
        ("Host", "Hudson"),
        ("Uptime (age)", "19 years"),
        ("Joined", joined),
        ("Age Started Coding", "8 years"),
        None,
        ("Langs", "Python / Java / C++"),
        ("Experience", "3 years CrownQuest / 1 year Cosee Home"),
        None,
        ("Repos", str(profile["public_repos"])),
        ("Stars", f"{sum(repo['stargazers_count'] for repo in original):,}"),
        ("Contributed", str(activity["contributed"])),
        ("Commits", f"{activity['commits']:,}"),
        ("Lines of Code", f"{activity['net']:,}"),
        ("Lines Added", f"{activity['added']:,}+"),
        ("Lines Removed", f"{activity['deleted']:,}-"),
        None,
        ("Locale", "en_US"),
    ]


def text(x, y, value, color=TEXT, size=14, weight="normal", **attrs):
    if weight != "normal":
        attrs["font_weight"] = weight
    extra = " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}"{(" " + extra) if extra else ""}>{escape(value)}</text>'


def leaders(parts, label, value_length, x, y, right):
    start = x + (len(label) + 1) * CELL
    end = right - (value_length + 1) * CELL
    dots = "." * max(0, int((end - start) / CELL))
    parts.append(text(start, y, dots, "#605e72", FONT_SIZE))


def field(parts, label, value, x, y, right, color, value_color="#d1cede"):
    parts.append(text(x, y, label, color, FONT_SIZE))
    leaders(parts, label, len(value), x, y, right)
    parts.append(text(right, y, value, value_color, FONT_SIZE, text_anchor="end"))


def section(parts, title, top, bottom, accent):
    left, right, center = 438, 1088, 763
    gap = len(title) * 3.5 + 13
    parts.append(f'<path d="M{left} {top+7}V{top}H{center-gap}M{center+gap} {top}H{right}V{top+7}M{left} {bottom-7}V{bottom}H{right}V{bottom-7}" fill="none" stroke="#4f4d60"/>')
    parts.append(text(center, top + 4, title, "#a5a0b7", 11, text_anchor="middle"))
    parts.append(f'<path d="M{left+3} {top+19}H{left}V{bottom-15}H{left+3}" fill="none" stroke="{accent}"/>')


def render(profile, repos, activity):
    rows = json.loads((ROOT / "assets/avatar-ascii.json").read_text())
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="570" viewBox="0 0 1120 570" role="img" aria-labelledby="title description">',
        '<title id="title">hudbeard@github</title>',
        '<desc id="description">Hudson’s terminal profile, with a cyan ASCII avatar and System, Software, Uptime / Age, and GitHub Stats sections. GitHub stats show public repositories, stars, contributed repositories, commits, and net line changes.</desc>',
        '<rect width="1120" height="570" fill="#0d1117"/>',
        '<g font-family="DejaVu Sans Mono, Liberation Mono, Consolas, monospace">',
        text(30, 36, "hudbeard@github", "#c8c5dc", 13),
        text(157, 36, "~", "#a6b4cf", 13),
        text(30, 59, "❯", "#a6d8bd", 14),
        text(49, 59, "fastfetch", "#a8b9cf", 12),
    ]
    # Contiguous color runs preserve real monospace text in browsers and SVG renderers.
    for row_index, row in enumerate(rows):
        spans = [f'<text x="34" y="{173 + row_index * 12.5}" font-size="12" xml:space="preserve">']
        start = 0
        while start < len(row["text"]):
            color = row["colors"][start]
            end = start + 1
            while end < len(row["text"]) and row["colors"][end] == color:
                end += 1
            spans.append(f'<tspan fill="{color}">{escape(row["text"][start:end])}</tspan>')
            start = end
        spans.append('</text>')
        parts.append(''.join(spans))
    values = dict(fact for fact in facts(profile, repos, activity) if fact)
    groups = [
        ("System", 92, ["OS", "Kernel", "Host", "Locale"], ["#b2d7ab", "#a6d5bc", "#95d1c1", "#a8cfb0"]),
        ("Software", 226, ["Langs", "Experience"], ["#e0c795", "#deb49b"]),
        ("Uptime / Age", 316, ["Uptime (age)", "Joined", "Age Started Coding"], ["#acc5ed", "#aab4df", "#bfb1e0"]),
    ]
    for title, top, keys, colors in groups:
        bottom = top + 22 + len(keys) * 23
        section(parts, title, top, bottom, colors[0])
        for index, label in enumerate(keys):
            y = top + 29 + index * 23
            field(parts, label, values[label], 465, y, 1070, colors[index])
    section(parts, "GitHub Stats", 428, 537, "#c7b2d8")
    gold, blue = "#e0b58a", "#9fc6e6"
    for label, x, y, right in [
        ("Repos", 465, 458, 725), ("Stars", 770, 458, 1070),
        ("Contributed", 465, 482, 725), ("Commits", 770, 482, 1070),
    ]:
        field(parts, label, values[label], x, y, right, gold, blue)
    # Keep the net, additions, and deletions together in one right-aligned text run.
    changes = [
        (values["Lines of Code"], blue), (" ( ", TEXT),
        ("+" + f"{activity['added']:,}", "#a6da95"), (" / ", TEXT),
        ("-" + f"{activity['deleted']:,}", "#ed8796"), (" )", TEXT),
    ]
    parts.append(text(465, 512, "Lines of Code", gold, FONT_SIZE))
    leaders(parts, "Lines of Code", sum(len(value) for value, _ in changes), 465, 512, 1070)
    spans = ''.join(f'<tspan fill="{color}">{escape(value)}</tspan>' for value, color in changes)
    parts.append(f'<text x="1070" y="512" font-size="{FONT_SIZE}" text-anchor="end" xml:space="preserve">{spans}</text>')
    parts.append('</g></svg>\n')
    (ROOT / "assets/profile.svg").write_text("\n".join(parts), encoding="utf-8")
    # Accessible text keeps the profile useful without image rendering.
    summary = "\n".join(
        f"{fact[0]} {'.' * max(1, 69 - len(fact[0]) - len(fact[1]))} {fact[1]}" if fact else ""
        for fact in facts(profile, repos, activity)
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    start, end = "<!-- profile:stats:start -->", "<!-- profile:stats:end -->"
    before, rest = readme.split(start, 1)
    _, after = rest.split(end, 1)
    (ROOT / "README.md").write_text(f"{before}{start}\n\n```text\n{summary}\n```\n\n{end}{after}", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, help="Directory containing profile.json and repos.json for offline previews")
    args = parser.parse_args()
    if args.fixtures:
        profile = json.loads((args.fixtures / "profile.json").read_text())
        repos = json.loads((args.fixtures / "repos.json").read_text())
        activity = json.loads((args.fixtures / "activity.json").read_text())
    else:
        profile, repos = public_data()
        activity = collect_activity(profile, repos)
    render(profile, repos, activity)


if __name__ == "__main__":
    main()

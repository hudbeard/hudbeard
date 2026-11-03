#!/usr/bin/env python3
"""Render the profile terminal from public GitHub data; Python stdlib only."""

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOGIN = "hudbeard"
CYAN = "#63e6dd"
TEXT = "#c6d2db"
MUTED = "#8294a4"


def github(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "hudbeard-profile"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urlopen(Request(f"https://api.github.com/{path}", headers=headers), timeout=30) as response:
        return json.load(response)


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


def facts(profile, repos):
    original = [repo for repo in repos if not repo.get("fork") and not repo.get("private")]
    languages = Counter(repo["language"] for repo in original if repo.get("language"))
    joined = datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00")).strftime("%b %Y")
    return [
        ("OS", "Linux"),
        ("Language", "Python"),
        ("Work", "CrownQuest"),
        ("Projects", "Desktop tools / graphics / robotics"),
        ("Writing", "medium.com/@hudbeard"),
        ("Joined", joined),
        None,
        ("Repos", f"{profile['public_repos']} public"),
        ("Stars", f"{sum(repo['stargazers_count'] for repo in original):,} on original repos"),
        ("Followers", str(profile["followers"])),
        ("Following", str(profile["following"])),
        ("Repo langs", " / ".join(name for name, _ in languages.most_common(3)) or "Getting started"),
    ]


def text(x, y, value, color=TEXT, size=14, weight="normal", **attrs):
    extra = " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" {extra}>{escape(value)}</text>'


def render(profile, repos, updated):
    rows = json.loads((ROOT / "assets/avatar-ascii.json").read_text())
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="630" viewBox="0 0 1040 630" role="img" aria-labelledby="title description">',
        '<title id="title">hudbeard@github — Python on Linux</title>',
        '<desc id="description">A fastfetch-inspired terminal with a colored ASCII rendering of hudbeard’s geometric avatar on the left. Linux, Python, CrownQuest, and public GitHub stats appear on the right.</desc>',
        '<rect x="1" y="1" width="1038" height="628" rx="14" fill="#0d141c" stroke="#2a3946"/>',
        '<path d="M15 1H1025Q1039 1 1039 15V45H1V15Q1 1 15 1Z" fill="#16212c"/>',
        '<path d="M1 45H1039" stroke="#2a3946"/>',
        '<circle cx="25" cy="24" r="5" fill="#f07883"/><circle cx="44" cy="24" r="5" fill="#e5c07b"/><circle cx="63" cy="24" r="5" fill="#70c997"/>',
        '<g font-family="DejaVu Sans Mono, Liberation Mono, Consolas, monospace">',
        text(520, 28, "hudbeard — ~/", MUTED, 12, text_anchor="middle"),
        text(30, 86, "❯", CYAN, 19),
        text(54, 85, "fastfetch", TEXT, 17),
        text(156, 85, "--config me.jsonc", MUTED, 15),
        text(30, 119, "A little Python. A lot of curiosity.", MUTED, 13),
        '<path d="M464 150V548" stroke="#22313e"/>',
    ]
    # Contiguous color runs preserve real monospace text in browsers and SVG renderers.
    for row_index, row in enumerate(rows):
        spans = [f'<text x="31" y="{160 + row_index * 14}" font-size="13.5" xml:space="preserve">']
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
    parts.extend([
        text(495, 161, "hudbeard", CYAN, 19, "bold"),
        text(587, 161, "@", MUTED, 19),
        text(600, 161, "github", TEXT, 19),
        text(495, 184, "────────────────────────────────────", MUTED, 14),
    ])
    for index, fact in enumerate(facts(profile, repos)):
        if fact is None:
            continue
        label, value = fact
        y = 215 + index * 25
        parts.append(text(495, y, label, CYAN, 14, "bold"))
        parts.append(text(590, y, value, TEXT, 13))
    for index, color in enumerate(["#233342", "#f07883", "#70c997", "#e5c07b", "#7aa2f7", "#bb9af7", CYAN, "#c6d2db"]):
        parts.append(f'<rect x="{495 + index * 25}" y="530" width="25" height="15" fill="{color}"/>')
    parts.extend([
        '<path d="M30 575H1010" stroke="#22313e"/>',
        text(30, 602, "~/build • tinker • repeat", CYAN, 12),
        text(1010, 602, f"public stats · {updated} UTC", MUTED, 11, text_anchor="end"),
        '</g></svg>\n',
    ])
    (ROOT / "assets/profile.svg").write_text("\n".join(parts), encoding="utf-8")
    # Accessible text keeps the profile useful without image rendering.
    summary = "\n".join(f"{label}: {value}" for fact in facts(profile, repos) if fact for label, value in [fact])
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
    else:
        profile, repos = public_data()
    render(profile, repos, datetime.now(timezone.utc).strftime("%Y-%m-%d"))


if __name__ == "__main__":
    main()

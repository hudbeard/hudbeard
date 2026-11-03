#!/usr/bin/env python3
"""Render the profile terminal from public GitHub data; Python stdlib only."""

import argparse
import json
import os
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
        ("Followers", str(profile["followers"])),
        ("Following", str(profile["following"])),
        None,
        ("Locale", "en_US"),
    ]


def text(x, y, value, color=TEXT, size=14, weight="normal", **attrs):
    extra = " ".join(f'{key.replace("_", "-")}="{escape(str(value), quote=True)}"' for key, value in attrs.items())
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" {extra}>{escape(value)}</text>'


def render(profile, repos, updated):
    rows = json.loads((ROOT / "assets/avatar-ascii.json").read_text())
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="650" viewBox="0 0 1120 650" role="img" aria-labelledby="title description">',
        '<title id="title">hudbeard@github</title>',
        '<desc id="description">A quiet Linux terminal with a cyan ASCII avatar on the left and thin bordered System, Software, Uptime / Age, and GitHub sections on the right. Colored keys have dotted leaders and right-aligned values.</desc>',
        '<defs><radialGradient id="ambient" cx="75%" cy="15%" r="90%"><stop stop-color="#29283d"/><stop offset="0.6" stop-color="#1e1e2e"/><stop offset="1" stop-color="#191a28"/></radialGradient></defs>',
        '<rect width="1120" height="650" rx="7" fill="url(#ambient)"/>',
        '<path d="M0 490L125 345L215 425L365 215L515 445L660 390L815 215L1010 450L1120 340V650H0Z" fill="#111322" opacity="0.16"/>',
        '<path d="M0 570L185 465L335 555L470 405L640 560L825 435L970 535L1120 460V650H0Z" fill="#10121e" opacity="0.2"/>',
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
    values = dict(fact for fact in facts(profile, repos) if fact)
    groups = [
        ("System", 92, ["OS", "Kernel", "Host", "Locale"], ["#b2d7ab", "#a6d5bc", "#95d1c1", "#a8cfb0"]),
        ("Software", 226, ["Langs", "Experience"], ["#e0c795", "#deb49b"]),
        ("Uptime / Age", 316, ["Uptime (age)", "Joined", "Age Started Coding"], ["#acc5ed", "#aab4df", "#bfb1e0"]),
        ("GitHub", 428, ["Repos", "Stars", "Followers", "Following"], ["#c7b2d8", "#e2c099", "#d6adc8", "#bea8d7"]),
    ]
    for title, top, keys, colors in groups:
        left, right, center = 438, 1088, 763
        bottom = top + 22 + len(keys) * 23
        title_half = len(title) * 3.5 + 13
        parts.append(f'<path d="M{left} {top+7}V{top}H{center-title_half}M{center+title_half} {top}H{right}V{top+7}M{left} {bottom-7}V{bottom}H{right}V{bottom-7}" fill="none" stroke="#555369" stroke-opacity="0.65" stroke-width="1"/>')
        parts.append(text(center, top + 4, title, "#858199", 11, text_anchor="middle"))
        parts.append(f'<path d="M{left+3} {top+19}H{left}V{bottom-15}H{left+3}" fill="none" stroke="{colors[0]}" stroke-opacity="0.8"/>')
        for index, label in enumerate(keys):
            value = values[label]
            color = colors[index]
            y = top + 29 + index * 23
            cell = 7.53
            leader_x = 465 + (len(label) + 1) * cell
            value_x = 1070 - len(value) * cell
            dots = "." * max(0, int((value_x - cell - leader_x) / cell))
            parts.append(text(449, y, "›", color, 12.5))
            parts.append(text(465, y, label, color, 12.5))
            parts.append(text(leader_x, y, dots, color, 12.5, opacity="0.25"))
            parts.append(text(1070, y, value, "#d1cede", 12.5, text_anchor="end"))
    for index, color in enumerate(["#cdd6f4", "#a6e3a1", "#94e2d5", "#89dceb", "#89b4fa", "#b4befe", "#cba6f7", "#f9e2af", "#f5c2e7"]):
        parts.append(f'<circle cx="{452 + index * 15}" cy="561" r="3.6" fill="{color}"/>')
    parts.extend([
        text(30, 608, "λ ~/", "#a6d8d2", 13),
        text(79, 608, "·" * 129, "#555367", 7.2),
        text(1088, 608, updated + " UTC", "#747187", 10, text_anchor="end"),
        text(30, 631, "❯", "#c8b8db", 14),
        '</g></svg>\n',
    ])
    (ROOT / "assets/profile.svg").write_text("\n".join(parts), encoding="utf-8")
    # Accessible text keeps the profile useful without image rendering.
    summary = "\n".join(
        f"{fact[0]} {'.' * max(1, 69 - len(fact[0]) - len(fact[1]))} {fact[1]}" if fact else ""
        for fact in facts(profile, repos)
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
    else:
        profile, repos = public_data()
    render(profile, repos, datetime.now(timezone.utc).strftime("%Y-%m-%d"))


if __name__ == "__main__":
    main()

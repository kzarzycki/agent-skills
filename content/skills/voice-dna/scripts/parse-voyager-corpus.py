#!/usr/bin/env python3
"""Convert raw Voyager API JSON output into a formatted corpus markdown file."""

import argparse
import json
import sys
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser(description="Convert Voyager JSON to corpus markdown.")
    p.add_argument("input", help="JSON file path, or '-' for stdin")
    p.add_argument("output", nargs="?", help="Output markdown file (default: stdout)")
    return p.parse_args()


def load_posts(path):
    src = sys.stdin if path == "-" else open(path, "r", encoding="utf-8")
    try:
        data = json.load(src)
    finally:
        if src is not sys.stdin:
            src.close()
    return data if isinstance(data, list) else data.get("posts", data.get("results", []))


def dedup(posts):
    seen = set()
    unique = []
    for p in posts:
        urn = p.get("activityUrn", "")
        if urn and urn in seen:
            continue
        if urn:
            seen.add(urn)
        unique.append(p)
    return unique


def format_engagement(eng):
    if not eng:
        return "0 likes, 0 comments"
    parts = []
    likes = eng.get("likes", 0)
    comments = eng.get("comments", 0)
    shares = eng.get("shares", 0)
    parts.append(f"{likes} likes")
    parts.append(f"{comments} comments")
    if shares:
        parts.append(f"{shares} shares")
    return ", ".join(parts)


def format_post(n, post):
    date = post.get("date", "unknown")[:10]
    ptype = post.get("type", "original").capitalize()
    engagement = format_engagement(post.get("engagement"))
    text = post.get("text", "").strip()
    url = post.get("url", "")

    lines = [
        f"## Post {n}",
        "",
        f"**Date:** {date}",
        f"**Type:** {ptype}",
        f"**Engagement:** {engagement}",
    ]
    if url:
        lines.append(f"**URL:** {url}")
    lines += ["", text, "", "---", ""]
    return "\n".join(lines)


def summary(posts, originals, reposts, date_range):
    return (
        f"Total raw posts: {date_range['raw']}  |  "
        f"Unique after dedup: {len(posts)}  |  "
        f"Date range: {date_range['earliest']} to {date_range['latest']}  |  "
        f"Originals: {originals}, Reposts: {reposts}"
    )


def main():
    args = parse_args()
    raw = load_posts(args.input)
    raw_count = len(raw)
    posts = dedup(raw)
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)

    originals = sum(1 for p in posts if p.get("type", "original").lower() != "repost")
    reposts = len(posts) - originals
    dates = sorted(p.get("date", "")[:10] for p in posts if p.get("date"))
    earliest = dates[0] if dates else "?"
    latest = dates[-1] if dates else "?"

    print(
        summary(posts, originals, reposts, {"raw": raw_count, "earliest": earliest, "latest": latest}),
        file=sys.stderr,
    )

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        for i, post in enumerate(posts, 1):
            out.write(format_post(i, post))
    finally:
        if out is not sys.stdout:
            out.close()


if __name__ == "__main__":
    main()

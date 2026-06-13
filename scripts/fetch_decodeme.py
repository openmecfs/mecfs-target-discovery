#!/usr/bin/env python3
"""Fetch the public DecodeME OSF project (node rgqs3).

The OSF node is PUBLIC — no authentication/token required. This script walks the
osfstorage tree recursively, preserving folder layout, and either lists it
(`--list`) or downloads everything into ./data/decodeme/ with a manifest.csv.

Usage:
    python scripts/fetch_decodeme.py --list      # verify: print tree + sizes, no download
    python scripts/fetch_decodeme.py             # download all into data/decodeme/
    python scripts/fetch_decodeme.py --only "DecodeME Summary Statistics"  # one subtree

Stdlib only (urllib/json/csv) — no third-party deps.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

NODE = "rgqs3"
API = "https://api.osf.io/v2"
OUT = Path("data/decodeme")
HEADERS = {"User-Agent": "mecfs-target-discovery/0.1 (+https://openmecfs.org)"}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def list_folder(url: str) -> list[dict]:
    """Return all items in an OSF folder, following pagination."""
    items: list[dict] = []
    while url:
        data = get_json(url)
        items.extend(data["data"])
        url = data["links"].get("next")
    return items


def walk(folder_url: str, rel: Path = Path(".")):
    """Yield (relative_path, attributes, download_url) for every file in the tree."""
    for item in list_folder(folder_url):
        a = item["attributes"]
        name = a["name"]
        if a["kind"] == "folder":
            sub = item["relationships"]["files"]["links"]["related"]["href"]
            yield from walk(sub, rel / name)
        else:
            yield rel / name, a, item["links"]["download"]


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):  # 1 MB chunks
            f.write(chunk)


def human(n) -> str:
    if not n:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list files only, no download")
    ap.add_argument("--only", help="restrict to a top-level folder name")
    args = ap.parse_args()

    root = f"{API}/nodes/{NODE}/files/osfstorage/"
    manifest = []
    total = 0
    for relpath, attrs, dl in walk(root):
        if args.only and relpath.parts[0] != args.only:
            continue
        size = attrs.get("size") or 0
        total += size
        print(f"{'·' if args.list else '↓'} {relpath}  ({human(size)})")
        if not args.list:
            download(dl, OUT / relpath)
        manifest.append(
            {
                "path": str(relpath),
                "size": size,
                "md5": attrs.get("extra", {}).get("hashes", {}).get("md5"),
                "download": dl,
            }
        )

    print(f"\n{len(manifest)} files, {human(total)} total.")
    if not args.list:
        OUT.mkdir(parents=True, exist_ok=True)
        with open(OUT / "manifest.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["path", "size", "md5", "download"])
            w.writeheader()
            w.writerows(manifest)
        print(f"Downloaded into {OUT}/  (manifest.csv written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
List files in a Hugging Face repo with sizes and download URLs.

Uses the huggingface_hub API to list repository contents, determines
file sizes via HTTP HEAD requests (falling back to a ranged GET
request if Content-Length is missing), and prints either plain URLs
or ready-to-use aria2c command lines (--aria2). Sizes are shown in a
human-readable unit scale (B/KB/MB/GB/TB).
"""

import argparse
import os

import requests
from huggingface_hub import HfApi, hf_hub_url


def human(value):
    """
    Convert bytes to a human-readable string.
    For values < 1 KB, no decimal is shown.
    For values >= 1 KB, one decimal is shown.
    """
    value = int(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            if unit == "B":
                return f"{value}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}PB"


def get_file_size(url):
    """
    Try to determine the remote file size via HTTP HEAD request.
    Falls back to a ranged GET request if HEAD doesn't provide a size.
    Returns the size in bytes as an int, or None if unavailable.
    """
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        size = resp.headers.get("Content-Length")
        if size:
            return int(size)
    except Exception:
        pass

    try:
        resp = requests.get(
            url,
            headers={"Range": "bytes=0-0"},
            allow_redirects=True,
            timeout=10,
        )
        content_range = resp.headers.get("Content-Range")
        if content_range and "/" in content_range:
            total = content_range.split("/")[-1]
            if total.isdigit():
                return int(total)
    except Exception:
        pass

    return None


def main():
    parser = argparse.ArgumentParser(
        description="List files in a Hugging Face repo with sizes and download URLs"
    )
    parser.add_argument(
        "repo",
        help="Repository ID, e.g. Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    )
    parser.add_argument(
        "--revision",
        default="main",
        help="Revision / branch / tag (default: main)",
    )
    parser.add_argument(
        "--hf-token",
        help="Hugging Face access token (optional, required for private repos)",
    )
    parser.add_argument(
        "--aria2",
        action="store_true",
        help="Print aria2c command lines instead of plain URLs",
    )
    args = parser.parse_args()

    # Set Hugging Face token via environment variable if provided
    if args.hf_token:
        os.environ["HF_HUB_TOKEN"] = args.hf_token

    api = HfApi()

    try:
        files = api.list_repo_files(
            repo_id=args.repo,
            revision=args.revision,
        )
    except Exception as e:
        print(f"Error accessing repository {args.repo}: {e}")
        return

    if not files:
        print("No files found in repository.")
        return

    print(f"\nFiles in repository {args.repo} (revision: {args.revision}):\n")

    for f in files:
        url = hf_hub_url(
            repo_id=args.repo,
            filename=f,
            revision=args.revision,
        )
        size_bytes = get_file_size(url)
        size_str = human(size_bytes) if size_bytes is not None else "unknown"
        if args.aria2:
            print(f"{f} ({size_str})")
            print(f"aria2c -o '{f}' '{url}'\n")
        else:
            print(f"{f} ({size_str}) -> {url}")


if __name__ == "__main__":
    main()

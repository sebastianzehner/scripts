#!/usr/bin/env python3
"""
Query aria2 RPC and print a short download status summary.

This script connects to the aria2 JSON-RPC interface and shows:
- number of active downloads
- number of waiting downloads
- number of finished downloads
- progress and speed of active downloads

Authentication is done via --rpc-secret.
"""

import argparse
from pathlib import Path

import requests


def rpc_call(host, method, params):
    """
    Perform a JSON-RPC call to aria2.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": method,
        "method": f"aria2.{method}",
        "params": params,
    }

    r = requests.post(
        f"http://{host}:6800/jsonrpc",
        json=payload,
        timeout=5,
    )
    r.raise_for_status()
    return r.json()["result"]


def calc_eta(d):
    """
    Calculate estimated time remaining in seconds, based on
    remaining bytes and current download speed. Returns None if
    speed is 0 or data is missing.
    """
    try:
        total = int(d.get("totalLength", 0))
        done = int(d.get("completedLength", 0))
        speed = int(d.get("downloadSpeed", 0))
        if speed <= 0 or total <= 0:
            return None
        remaining = total - done
        return remaining // speed
    except (ValueError, TypeError):
        return None


def format_eta(seconds):
    """
    Format a duration in seconds as a human-readable string,
    e.g. 536 -> "8m 56s", 45 -> "45s", 7325 -> "2h 2m 5s".
    """
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


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


def read_rpc_secret(path):
    try:
        return Path(path).read_text().strip()
    except Exception as e:
        print(f"❌ Failed to read RPC secret from {path}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="aria2 RPC status overview")
    parser.add_argument(
        "--rpc-secret-file",
        default="~/.aria2_rpc_secret",
        help="Path to file containing aria2 RPC secret",
    )
    parser.add_argument(
        "--host",
        default="nas.lan",
        help="aria2 host (default: nas.lan)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove all finished downloads after showing status",
    )
    args = parser.parse_args()

    rpc_secret = read_rpc_secret(Path(args.rpc_secret_file).expanduser())
    if not rpc_secret:
        print("❌ No RPC secret found. Exiting.")
        return

    active = rpc_call(args.host, "tellActive", [f"token:{rpc_secret}"])
    waiting = rpc_call(args.host, "tellWaiting", [f"token:{rpc_secret}", 0, 1000])
    stopped = rpc_call(args.host, "tellStopped", [f"token:{rpc_secret}", 0, 1000])

    print("📊 aria2 RPC Status")
    print("-------------------")
    print(f"Active   : {len(active)}")
    print(f"Waiting  : {len(waiting)}")
    print(f"Finished : {len(stopped)}\n")

    if active:
        print("🔽 Active downloads:")
        for d in active:
            name = d["files"][0]["path"].split("/")[-1]
            done = human(d["completedLength"])
            total = human(d["totalLength"])
            speed = human(d["downloadSpeed"]) + "/s"
            eta = calc_eta(d)
            eta_str = format_eta(eta) if eta is not None else "unknown"
            print(f"- {name}: {done} / {total} @ {speed} (ETA: {eta_str})")

    if waiting:
        print("\n⏳ Waiting downloads:")
        for d in waiting:
            name = d["files"][0]["path"].split("/")[-1]
            total = human(d["totalLength"])
            print(f"- {name} (Total: {total})")

    if stopped:
        print("\n✅ Finished downloads:")
        for d in stopped:
            name = d["files"][0]["path"].split("/")[-1]
            total = human(d["totalLength"])
            status = d.get("status", "unknown")
            print(f"- {name}: {status} ({total})")

    if args.clean and stopped:
        print("\n🧹 Cleaning finished downloads...")
        for d in stopped:
            gid = d["gid"]
            rpc_call(args.host, "removeDownloadResult", [f"token:{rpc_secret}", gid])
            print(f"- Removed: {d['files'][0]['path']}")


if __name__ == "__main__":
    main()

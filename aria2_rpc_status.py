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
import requests
from pathlib import Path


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
            eta = d.get("eta", 0)
            print(f"- {name}: {done} / {total} @ {speed} (ETA: {eta}s)")

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

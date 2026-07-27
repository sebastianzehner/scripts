#!/usr/bin/env python3
"""
Queue a Hugging Face repo for download on a NAS via aria2 RPC.

Lists all files in a Hugging Face repo and queues them as downloads
on a remote aria2 instance (e.g. running on a NAS), placing them in
a per-repo subdirectory. The NAS SSH user is resolved automatically
from ~/.ssh/config (via 'ssh -G'), unless overridden with --nas-user.

Before running any SSH commands, the script waits for the local SSH
agent (e.g. provided by KeePassXC) to have at least one identity
loaded, so it doesn't fail if KeePassXC is still locked.
"""

import argparse
import fnmatch
import os
import posixpath
import subprocess
import time
from pathlib import Path

import requests
from huggingface_hub import HfApi, hf_hub_url


def aria2_rpc(rpc_url, method, params):
    payload = {
        "jsonrpc": "2.0",
        "id": "hf-download",
        "method": f"aria2.{method}",
        "params": params,
    }
    r = requests.post(rpc_url, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def read_rpc_secret(path):
    try:
        return Path(path).read_text().strip()
    except Exception as e:
        print(f"❌ Failed to read RPC secret from {path}: {e}")
        return None


def get_ssh_user(host):
    """
    Resolve the effective SSH user for a given host, the same way
    OpenSSH itself would (respecting ~/.ssh/config, Match blocks,
    wildcards, etc.). Returns None if resolution fails.
    """
    try:
        result = subprocess.run(
            ["ssh", "-G", host],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("user "):
                return line.split(" ", 1)[1].strip()
    except Exception:
        pass
    return None


def filter_files(files, patterns):
    """
    Filter a list of repo file paths by one or more glob patterns
    (e.g. "*.safetensors", "config.json"). A file is kept if it
    matches ANY of the given patterns. If patterns is empty, all
    files are returned unchanged.
    """
    if not patterns:
        return files
    return [
        f for f in files if any(fnmatch.fnmatch(f, pattern) for pattern in patterns)
    ]


def wait_for_ssh_agent(timeout=120):
    """
    Wait until the SSH agent (e.g. provided by KeePassXC) has at
    least one identity loaded. Notifies the user if the agent is
    locked and polls until it becomes available or timeout is hit.
    """
    notified = False
    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True,
            text=True,
        )
        # returncode 0 = identities available
        if result.returncode == 0:
            return True

        if not notified:
            print("🔒 SSH agent has no keys (KeePassXC locked?). Waiting for unlock...")
            subprocess.run(
                [
                    "notify-send",
                    "-u",
                    "critical",
                    "HF Download",
                    "Please unlock KeePassXC to continue.",
                ],
                capture_output=True,
            )
            notified = True

        time.sleep(2)

    print("❌ Timed out waiting for SSH agent to become available.")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Download HF repo on NAS via aria2 RPC"
    )
    parser.add_argument("repo", help="Hugging Face repo ID, e.g. Comfy-Org/SCAIL-2")
    parser.add_argument(
        "--revision", default="main", help="Revision / branch / tag (default: main)"
    )

    # Tokens (explicit & unambiguous)
    parser.add_argument(
        "--hf-token",
        help="Hugging Face access token (optional, required for private/gated repos)",
    )
    parser.add_argument(
        "--rpc-secret-file",
        default="~/.aria2_rpc_secret",
        help="Path to file containing aria2 RPC secret (default: ~/.aria2_rpc_secret)",
    )

    # NAS / aria2
    parser.add_argument(
        "--nas-host", required=True, help="NAS hostname or IP (required)"
    )
    parser.add_argument(
        "--nas-user",
        default=None,
        help="NAS SSH username (default: resolved from ~/.ssh/config via 'ssh -G')",
    )
    parser.add_argument(
        "--rpc-port", type=int, default=6800, help="aria2 RPC port (default: 6800)"
    )
    parser.add_argument(
        "--nas-dir",
        default="/volume1/Downloads",
        help="Base download directory on the NAS (default: /volume1/Downloads)",
    )

    # Download behaviour
    parser.add_argument(
        "--limit",
        default=8000000,
        type=int,
        help="Max overall download speed in bytes/s (default: 8000000 = ~64 Mbit/s, use 0 for unlimited)",
    )
    parser.add_argument(
        "--include",
        nargs="+",
        default=None,
        metavar="PATTERN",
        help=(
            "Only queue files matching one or more glob patterns "
            '(e.g. --include "*.safetensors" config.json). '
            "Default: include all files."
        ),
    )
    args = parser.parse_args()

    rpc_secret = read_rpc_secret(Path(args.rpc_secret_file).expanduser())
    if not rpc_secret:
        print("❌ No RPC secret found. Exiting.")
        return

    nas_user = args.nas_user or get_ssh_user(args.nas_host)
    if not nas_user:
        print(f"❌ Could not determine SSH user for {args.nas_host}. Use --nas-user.")
        return

    if not wait_for_ssh_agent():
        print("❌ Aborting: no SSH agent identities available.")
        return

    # HF auth
    if args.hf_token:
        os.environ["HF_HUB_TOKEN"] = args.hf_token

    rpc_url = f"http://{args.nas_host}:{args.rpc_port}/jsonrpc"
    repo_dirname = args.repo.split("/")[-1]
    target_dir = posixpath.join(args.nas_dir, repo_dirname)

    # Base folder on NAS
    try:
        subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                f"{nas_user}@{args.nas_host}",
                "mkdir",
                "-p",
                target_dir,
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to reach NAS or create directory on {args.nas_host}: {e}")
        return

    api = HfApi()
    try:
        all_files = api.list_repo_files(repo_id=args.repo, revision=args.revision)
    except Exception as e:
        print(f"❌ Failed to access repository {args.repo}: {e}")
        return
    files = filter_files(all_files, args.include)

    if not files:
        print("❌ No files match the given --include pattern(s). Nothing to queue.")
        return

    if args.include:
        skipped = len(all_files) - len(files)
        print(
            f"🔎 Filtered by pattern {args.include}: {len(files)} matched, {skipped} skipped\n"
        )

    print(f"📦 Queue downloads via aria2 RPC → {target_dir}\n")

    for f in files:
        remote_path = posixpath.join(target_dir, f)
        remote_dir = posixpath.dirname(remote_path)
        if remote_dir:
            subprocess.run(
                [
                    "ssh",
                    "-o",
                    "ConnectTimeout=10",
                    f"{nas_user}@{args.nas_host}",
                    "mkdir",
                    "-p",
                    remote_dir,
                ],
                check=True,
            )

        url = hf_hub_url(
            repo_id=args.repo,
            filename=f,
            revision=args.revision,
        )

        options = {
            "dir": remote_dir,
            "out": posixpath.basename(f),
            "continue": "true",
            "file-allocation": "trunc",
            "max-overall-download-limit": str(args.limit),
            "remove-control-file": "true",
        }

        params = [f"token:{rpc_secret}", [url], options]
        aria2_rpc(rpc_url, "addUri", params)
        print(f"→ queued: {f}")


if __name__ == "__main__":
    main()

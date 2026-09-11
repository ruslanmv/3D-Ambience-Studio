#!/usr/bin/env python3
"""Clone pinned upstream repositories for local research/integration.

By design, upstream code is not bundled into the 3D-Ambience-Studio repository.
This script creates ./upstream/<Name> and checks out the revision recorded in
upstreams.lock.json.
"""
from pathlib import Path
import argparse, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "upstreams.lock.json").read_text())


def run(cmd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=["core", "v2", "reference", "all"], default="core")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    target_root = ROOT / "upstream"
    target_root.mkdir(exist_ok=True)
    repos = [r for r in LOCK["repositories"] if args.group == "all" or r["group"] == args.group]
    if not repos:
        print("No repositories in selected group")
        return
    for item in repos:
        target = target_root / item["name"]
        if target.exists() and not args.force:
            print(f"skip {target} (exists; use --force to replace)")
            continue
        if target.exists():
            import shutil; shutil.rmtree(target)
        run(["git", "clone", "--filter=blob:none", "--no-checkout", item["url"], str(target)])
        run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", item["ref"]])
        run(["git", "-C", str(target), "checkout", "--detach", item["ref"]])
        print(f"checked out {item['name']} @ {item['ref']} ({item['strategy']})")
        print(f"license note: {item['licenseNote']}")

if __name__ == "__main__":
    try: main()
    except subprocess.CalledProcessError as exc:
        print(f"Upstream clone failed: {exc}", file=sys.stderr); sys.exit(exc.returncode)

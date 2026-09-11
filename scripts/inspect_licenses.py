#!/usr/bin/env python3
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / "upstreams.lock.json").read_text())
for item in lock["repositories"]:
    repo = ROOT / "upstream" / item["name"]
    print(f"\n## {item['name']}\n{item['url']}\nPinned: {item['ref']}\nRecorded note: {item['licenseNote']}")
    if not repo.exists():
        print("not cloned")
        continue
    candidates = list(repo.glob("LICENSE*")) + list(repo.glob("COPYING*"))
    for path in candidates:
        print(f"- {path.relative_to(ROOT)}")

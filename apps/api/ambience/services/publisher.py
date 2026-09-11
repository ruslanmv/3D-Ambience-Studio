from __future__ import annotations
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from ..config import settings
from ..models import ProjectRecord


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def build_manifest(project: ProjectRecord, published_dir: Path, panorama_meta: dict, audio_meta: dict | None) -> dict:
    desktop = published_dir / "panorama-desktop.webp"
    quest = published_dir / "panorama-quest.webp"
    preview = published_dir / "panorama-preview.webp"
    manifest = {
        "schemaVersion": 1,
        "id": project.id,
        "version": project.version,
        "name": project.name,
        "description": project.description,
        "category": project.category,
        "tags": project.tags,
        "preview": {"src": preview.name},
        "orientation": {"yawDegrees": project.yawDegrees, "floorY": 0.0},
        "variants": {
            "desktop": {"type": "panorama", "background": desktop.name, "width": panorama_meta["desktop"]["width"], "height": panorama_meta["desktop"]["height"], "bytes": desktop.stat().st_size},
            "quest": {"type": "panorama", "background": quest.name, "width": panorama_meta["quest"]["width"], "height": panorama_meta["quest"]["height"], "bytes": quest.stat().st_size},
            "companion": {"type": project.companionMode, "preset": project.companionPreset}
        },
        "audio": None,
        "lighting": project.lighting.model_dump(),
        "effects": project.effects,
        "geometry": [],
        "compatibility": {"minRuntime": "0.1.0", "passthrough": "hidden"}
    }
    if audio_meta:
        manifest["audio"] = {"ambient": Path(audio_meta["path"]).name, "loop": True, "defaultVolume": 0.45}
    return manifest


def publish_project(project: ProjectRecord, work_dir: Path, public_root: Path | None = None, featured: bool = False) -> dict:
    public_root = public_root or (settings.data_dir / "public")
    env_root = public_root / "environments" / project.id
    final_dir = env_root / project.version
    temp_dir = env_root / f".{project.version}.tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    panorama_meta = json.loads((work_dir / "panorama-meta.json").read_text(encoding="utf-8"))
    for key in ("desktop", "quest", "preview"):
        src = Path(panorama_meta[key]["path"])
        shutil.copy2(src, temp_dir / f"panorama-{key}.webp")
        panorama_meta[key]["path"] = str(temp_dir / f"panorama-{key}.webp")

    audio_meta = None
    audio_meta_file = work_dir / "audio-meta.json"
    if audio_meta_file.exists():
        audio_meta = json.loads(audio_meta_file.read_text(encoding="utf-8"))
        audio_src = Path(audio_meta["path"])
        audio_dst = temp_dir / audio_src.name
        shutil.copy2(audio_src, audio_dst)
        audio_meta["path"] = str(audio_dst)

    manifest = build_manifest(project, temp_dir, panorama_meta, audio_meta)
    (temp_dir / "environment.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if final_dir.exists():
        raise FileExistsError(f"Published environment version already exists: {final_dir}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_dir, final_dir)

    base = settings.ambience_public_base_url.rstrip("/")
    entry = {
        "id": project.id,
        "version": project.version,
        "name": project.name,
        "description": project.description,
        "category": project.category,
        "tags": project.tags,
        "preview": f"{base}/environments/{project.id}/{project.version}/panorama-preview.webp",
        "manifest": f"{base}/environments/{project.id}/{project.version}/environment.json",
        "featured": featured,
        "bytes": sum(p.stat().st_size for p in final_dir.rglob("*") if p.is_file())
    }
    update_catalog(public_root, entry)
    return {"directory": str(final_dir), "entry": entry, "manifest": manifest}


def update_catalog(public_root: Path, entry: dict) -> None:
    public_root.mkdir(parents=True, exist_ok=True)
    path = public_root / "catalog.json"
    catalog = {"schemaVersion": 1, "generatedAt": "", "environments": []}
    if path.exists():
        catalog = json.loads(path.read_text(encoding="utf-8"))
    items = [x for x in catalog.get("environments", []) if not (x.get("id") == entry["id"] and x.get("version") == entry["version"])]
    items.append(entry)
    items.sort(key=lambda x: (x["category"], x["name"], x["version"]))
    catalog["schemaVersion"] = 1
    catalog["generatedAt"] = datetime.now(timezone.utc).isoformat()
    catalog["environments"] = items
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

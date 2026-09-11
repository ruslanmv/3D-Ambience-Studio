from __future__ import annotations
import json
from pathlib import Path
from .repository import ProjectRepository
from .providers.registry import get_panorama_provider
from .services.image_pipeline import optimize_panorama
from .services.audio_pipeline import optimize_audio
from .services.validator import validate_project_assets, validate_json, load_schema
from .services.publisher import publish_project


class Workflow:
    def __init__(self, repo: ProjectRepository | None = None, repo_root: Path | None = None):
        self.repo = repo or ProjectRepository()
        self.repo_root = repo_root or Path.cwd()
        self.work_root = self.repo.data_dir / "work"
        self.work_root.mkdir(parents=True, exist_ok=True)

    async def generate_panorama(self, project_id: str, provider_name: str, seed: int | None = None):
        project = self.repo.get(project_id)
        project_dir = self.repo.project_dir(project_id)
        output = project_dir / "source-panorama.png"
        provider = get_panorama_provider(provider_name)
        provenance = await provider.generate(prompt=project.prompt or project.name, output=output, seed=seed)
        (project_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
        project.sourcePanorama = output.name
        project.panoramaProvider = provider_name
        project.status = "generated"
        return self.repo.save(project)

    def optimize(self, project_id: str) -> dict:
        project = self.repo.get(project_id)
        project_dir = self.repo.project_dir(project_id)
        source_panorama = project_dir / project.sourcePanorama if project.sourcePanorama else None
        source_audio = project_dir / project.sourceAudio if project.sourceAudio else None
        errors = validate_project_assets(source_panorama, source_audio)
        if errors:
            raise ValueError(" ".join(errors))
        work_dir = self.work_root / project_id
        work_dir.mkdir(parents=True, exist_ok=True)
        panorama_meta = optimize_panorama(source_panorama, work_dir)
        serializable = {k: {**v, "path": str(v["path"])} for k, v in panorama_meta.items()}
        (work_dir / "panorama-meta.json").write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")
        audio_meta = None
        if source_audio:
            audio_meta = optimize_audio(source_audio, work_dir)
            audio_meta["path"] = str(audio_meta["path"])
            (work_dir / "audio-meta.json").write_text(json.dumps(audio_meta, indent=2) + "\n", encoding="utf-8")
        project.status = "optimized"
        self.repo.save(project)
        return {"panorama": serializable, "audio": audio_meta}

    def validate(self, project_id: str) -> dict:
        project = self.repo.get(project_id)
        project_dir = self.repo.project_dir(project_id)
        source_panorama = project_dir / project.sourcePanorama if project.sourcePanorama else None
        source_audio = project_dir / project.sourceAudio if project.sourceAudio else None
        errors = validate_project_assets(source_panorama, source_audio)
        work_dir = self.work_root / project_id
        errors += [] if (work_dir / "panorama-meta.json").exists() else ["Project has not been optimized yet."]
        return {"valid": not errors, "errors": errors}

    def publish(self, project_id: str, featured: bool = False) -> dict:
        result = self.validate(project_id)
        if not result["valid"]:
            raise ValueError(" ".join(result["errors"]))
        project = self.repo.get(project_id)
        work_dir = self.work_root / project_id
        publication = publish_project(project, work_dir, featured=featured)
        schema = load_schema(self.repo_root, "environment.schema.json")
        schema_errors = validate_json(publication["manifest"], schema)
        if schema_errors:
            raise ValueError("Published manifest did not satisfy schema: " + "; ".join(schema_errors))
        project.status = "published"
        self.repo.save(project)
        return publication

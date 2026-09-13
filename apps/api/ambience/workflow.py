from __future__ import annotations

import json
from pathlib import Path

from .providers.registry import get_backplate_provider, get_panorama_provider
from .repository import ProjectRepository
from .services.audio_pipeline import optimize_audio
from .services.backplate_guide import build_prompt, get_profile, load_contract, render_guide
from .services.image_pipeline import optimize_backplate, optimize_panorama
from .services.publisher import publish_project
from .services.validator import load_schema, validate_json, validate_project_assets


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

    async def generate_backplate(
        self,
        project_id: str,
        provider_name: str,
        contract_path: Path,
        profile: str = "landscape",
        seed: int | None = None,
    ):
        """Route 2: generate a flat backplate directly, against a runtime's camera contract.

        Every pixel ends up in the final image, and the generator is handed a picture of where
        the horizon and the floor have to be — neither of which the panorama route can offer.
        See docs/BACKPLATE_ROUTE.md for why that matters and what it costs.

        The guide is written into the project directory and kept. It is the strongest evidence
        available when a backplate turns out not to line up: the question becomes whether the
        guide was wrong or the worker ignored it, and without the artefact neither is answerable.
        """
        project = self.repo.get(project_id)
        project_dir = self.repo.project_dir(project_id)

        contract = load_contract(Path(contract_path))
        camera = get_profile(contract, profile)
        guide_path = project_dir / f"guide-{profile}.png"
        guide_path.parent.mkdir(parents=True, exist_ok=True)
        render_guide(camera).save(guide_path)

        prompt = build_prompt(camera, project.prompt or project.name)
        negative = build_prompt(camera, "", negative=True)
        output = project_dir / f"source-backplate-{profile}.png"

        provider = get_backplate_provider(provider_name)
        provenance = await provider.generate(
            prompt=prompt,
            output=output,
            width=int(camera["master"]["width"]),
            height=int(camera["master"]["height"]),
            guide=guide_path,
            negative_prompt=negative,
            seed=seed,
        )
        provenance["cameraContract"] = {"id": contract.get("id"), "runtime": contract.get("runtime"), "profile": profile}
        (project_dir / f"provenance-backplate-{profile}.json").write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
        project.sourceBackplate = output.name
        project.backplateProvider = provider_name
        project.backplateProfile = profile
        project.status = "generated"
        return self.repo.save(project)

    def optimize_backplate_asset(self, project_id: str, profile: str | None = None) -> dict:
        """Crop and resize the generated backplate to its profile's exact master size."""
        project = self.repo.get(project_id)
        project_dir = self.repo.project_dir(project_id)
        if not project.sourceBackplate:
            raise ValueError("Project has no generated backplate.")
        source = project_dir / project.sourceBackplate
        if not source.exists():
            raise ValueError(f"Backplate source is missing: {source.name}")
        work_dir = self.work_root / project_id
        work_dir.mkdir(parents=True, exist_ok=True)
        meta = optimize_backplate(source, work_dir, profile or project.backplateProfile or "landscape")
        serializable = {k: {**v, "path": str(v["path"])} for k, v in meta.items()}
        (work_dir / "backplate-meta.json").write_text(json.dumps(serializable, indent=2) + "\n", encoding="utf-8")
        project.status = "optimized"
        self.repo.save(project)
        return serializable

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

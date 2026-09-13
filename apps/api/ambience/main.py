import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .models import GeneratePlateRequest, GenerateRequest, ProjectCreate, PublishRequest
from .providers.registry import backplate_provider_summary, provider_summary
from .repository import ProjectRepository
from .services.backplate_guide import ContractError, build_prompt, get_profile, load_contract
from .workflow import Workflow

app = FastAPI(title="3D-Ambience-Studio API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

repo = ProjectRepository()
workflow = Workflow(repo=repo, repo_root=Path.cwd())
public_dir = settings.data_dir / "public"
public_dir.mkdir(parents=True, exist_ok=True)
app.mount("/public", StaticFiles(directory=public_dir), name="public")


@app.get("/health")
def health():
    return {"ok": True, "service": "3D-Ambience-Studio", "version": "0.1.0"}


@app.get("/api/providers")
def providers():
    return provider_summary()


@app.post("/api/projects")
def create_project(payload: ProjectCreate):
    return repo.create(payload)


@app.get("/api/projects")
def list_projects():
    return repo.list()


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        return repo.get(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")


@app.post("/api/projects/{project_id}/generate")
async def generate(project_id: str, payload: GenerateRequest):
    try:
        return await workflow.generate_panorama(project_id, payload.provider, payload.seed)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/projects/{project_id}/assets/panorama")
async def upload_panorama(project_id: str, file: UploadFile = File(...)):
    try:
        project = repo.get(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")
    suffix = Path(file.filename or "panorama.jpg").suffix.lower() or ".jpg"
    target = repo.project_dir(project_id) / f"source-panorama{suffix}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    project.sourcePanorama = target.name
    project.panoramaProvider = "manual"
    project.status = "generated"
    return repo.save(project)


@app.post("/api/projects/{project_id}/assets/audio")
async def upload_audio(project_id: str, file: UploadFile = File(...)):
    try:
        project = repo.get(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")
    suffix = Path(file.filename or "ambience.wav").suffix.lower() or ".wav"
    target = repo.project_dir(project_id) / f"source-audio{suffix}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    project.sourceAudio = target.name
    return repo.save(project)


@app.post("/api/projects/{project_id}/optimize")
def optimize(project_id: str):
    try:
        return workflow.optimize(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/projects/{project_id}/validate")
def validate(project_id: str):
    try:
        return workflow.validate(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")


@app.post("/api/projects/{project_id}/publish")
def publish(project_id: str, payload: PublishRequest):
    try:
        project = repo.get(project_id)
        if payload.version:
            project.version = payload.version
            repo.save(project)
        return workflow.publish(project_id, featured=payload.featured)
    except KeyError:
        raise HTTPException(404, "Project not found")
    except (ValueError, FileExistsError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/catalog")
def catalog():
    path = public_dir / "catalog.json"
    if not path.exists():
        return {"schemaVersion": 1, "generatedAt": "", "environments": []}
    import json
    return json.loads(path.read_text(encoding="utf-8"))


# ── Plate route (the fixed-camera backgrounds 3D-Avatar-Chatbot consumes) ────────────────────
#
# Separate endpoints rather than a mode flag on the panorama ones. The two produce different
# shapes, take different arguments and fail for different reasons, and a single endpoint that
# branched on a flag would report a panorama's errors for a plate.


def _contracts_dir() -> Path:
    return Path.cwd() / "examples" / "backplate-camera"


@app.get("/api/camera-contracts")
def camera_contracts():
    """The runtimes a plate can be generated for, and the profiles each offers.

    The wizard reads this rather than hard-coding "landscape" and "portrait": a second consuming
    runtime with its own camera should appear in the list without a front-end change.
    """
    out = []
    for path in sorted(_contracts_dir().glob("*.json")):
        try:
            contract = load_contract(path)
        except (ContractError, ValueError):
            # A malformed contract is skipped with the rest still listed — one bad file should
            # not empty the dropdown.
            continue
        out.append(
            {
                "file": path.name,
                "id": contract.get("id"),
                "runtime": contract.get("runtime"),
                "profiles": [
                    {
                        "name": name,
                        "width": profile["master"]["width"],
                        "height": profile["master"]["height"],
                        "fovDeg": profile.get("fovDeg"),
                        "horizonY": profile.get("horizonY"),
                        "footAnchor": profile.get("footAnchor"),
                        "safeZone": profile.get("safeZone"),
                    }
                    for name, profile in contract.get("profiles", {}).items()
                ],
            }
        )
    return out


@app.get("/api/backplate-providers")
def backplate_providers():
    return backplate_provider_summary()


@app.post("/api/projects/{project_id}/preview-prompt")
def preview_prompt(project_id: str, payload: GeneratePlateRequest):
    """What will actually be sent, before anything is generated.

    The wizard shows this. A designer writing "moonlit terrace" should be able to see the
    technical paragraph the Studio appends on their behalf — both so the constraints are
    inspectable and so a surprising result has somewhere to be explained.
    """
    try:
        project = repo.get(project_id)
        contract = load_contract(_contracts_dir() / payload.contract)
        camera = get_profile(contract, payload.profile)
    except (KeyError, ContractError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {
        "prompt": build_prompt(camera, project.prompt or project.name),
        "negativePrompt": build_prompt(camera, "", negative=True),
        "profile": payload.profile,
        "master": camera["master"],
    }


@app.post("/api/projects/{project_id}/generate-plate")
async def generate_plate(project_id: str, payload: GeneratePlateRequest):
    try:
        return await workflow.generate_backplate(
            project_id,
            payload.provider,
            _contracts_dir() / payload.contract,
            payload.profile,
            payload.seed,
        )
    except (KeyError, ContractError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/projects/{project_id}/optimize-plate")
def optimize_plate(project_id: str, payload: GeneratePlateRequest):
    try:
        return workflow.optimize_backplate_asset(project_id, payload.profile)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/projects/{project_id}/guide/{profile}")
def plate_guide(project_id: str, profile: str):
    """The conditioning image, so the wizard can show what the generator was told."""
    from fastapi.responses import FileResponse

    path = repo.project_dir(project_id) / f"guide-{profile}.png"
    if not path.exists():
        raise HTTPException(404, "No guide for that profile yet — generate first.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/projects/{project_id}/plate/{profile}")
def plate_image(project_id: str, profile: str):
    """The generated plate itself, for the wizard's preview."""
    from fastapi.responses import FileResponse

    for candidate in (
        settings.data_dir / "work" / project_id / f"backplate-{profile}.webp",
        repo.project_dir(project_id) / f"source-backplate-{profile}.png",
    ):
        if candidate.exists():
            return FileResponse(candidate)
    raise HTTPException(404, "No plate for that profile yet.")

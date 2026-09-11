from pathlib import Path
import shutil
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import settings
from .models import ProjectCreate, GenerateRequest, PublishRequest
from .repository import ProjectRepository
from .providers.registry import provider_summary
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

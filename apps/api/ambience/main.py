import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .models import GeneratePlateRequest, GenerateRequest, ProjectCreate, PublishRequest
from .providers.huggingface import list_text_to_image_models as list_hf_models
from .providers.openai_images import list_models, pair_with_bridge
from .providers.registry import backplate_provider_summary, provider_from_settings, provider_summary
from .repository import ProjectRepository
from .services import generation_settings as gen_settings
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


# ── Image generation settings (the SYSTEM CONFIGURATION panel) ───────────────────────────────


class SettingsPatch(BaseModel):
    """A partial update. Omitted fields keep their stored value; an empty string clears one.

    Partial on purpose — pairing must not have to resend the API key, and a form that does not
    render the key field must not wipe it on save.
    """

    provider: str | None = None
    auth_mode: str | None = None
    api_key: str | None = None
    pair_token: str | None = None
    base_url: str | None = None
    model: str | None = None
    hf_routing: str | None = None
    hf_use_guide: bool | None = None


class PairRequest(BaseModel):
    code: str
    label: str = "3d-ambience-studio"


def _refuse_if_locked() -> None:
    """A shared deployment configures itself; a visitor does not get to reconfigure it.

    Refused loudly with 403 rather than accepted-and-ignored: a panel whose save appears to work
    and changes nothing is worse than one that says it is read-only, and the reason travels with
    the refusal so it can be shown.

    What this prevents is not only a surprise bill. A writable base URL on a public instance is a
    credential-exfiltration route — point the provider at a host you control and the deployment's
    own key arrives in your logs on the next generate.
    """
    state = gen_settings.deployment()
    if state["locked"]:
        raise HTTPException(403, state["reason"])


@app.get("/api/image-providers")
def image_providers():
    """Everything the panel needs to render itself: icons, auth modes, defaults, caveats."""
    return gen_settings.PROVIDERS


@app.get("/api/settings/generation")
def get_generation_settings():
    # Redacted: the panel shows that a key is stored, never the key.
    return gen_settings.redact(gen_settings.load())


@app.put("/api/settings/generation")
def put_generation_settings(patch: SettingsPatch):
    _refuse_if_locked()
    payload = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "provider" in payload and payload["provider"] not in gen_settings.PROVIDER_IDS:
        raise HTTPException(400, f"Unknown provider: {payload['provider']}")
    return gen_settings.redact(gen_settings.save(payload))


@app.post("/api/settings/generation/pair")
async def pair_device(payload: PairRequest):
    """Exchange a pairing code for a device token and store it.

    Proxied through the API rather than called from the browser because the bridge would
    otherwise need CORS configured for the Studio's origin — the same reason the avatar app
    offers a proxy path.
    """
    _refuse_if_locked()
    config = gen_settings.load()
    result = await pair_with_bridge(config.get("base_url", ""), payload.code, payload.label)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Pairing failed."))
    gen_settings.save(
        {"pair_token": result["token"], "device_id": result.get("device_id") or "", "auth_mode": "pairing"}
    )
    return {"ok": True, "device_id": result.get("device_id")}


@app.post("/api/settings/generation/unpair")
def unpair_device():
    _refuse_if_locked()
    gen_settings.save({"pair_token": "", "device_id": ""})
    return {"ok": True}


@app.get("/api/settings/generation/models")
async def fetch_models():
    """What the configured provider can actually draw with.

    Two catalogues, because the two routes have nothing in common: an OpenAI-compatible endpoint
    answers GET /v1/models, while Hugging Face's router is a filtered view of the Hub. Asking the
    wrong one returns a plausible empty list rather than an error, which is the failure mode this
    branch exists to avoid.
    """
    config = gen_settings.load()
    auth_mode = config.get("auth_mode", "apikey")
    credential, _source = gen_settings.credential_for(config)
    try:
        if gen_settings.provider_spec(config["provider"])["kind"] == "huggingface":
            return {"models": await list_hf_models(credential)}
        return {"models": await list_models(config.get("base_url", ""), credential or "", auth_mode)}
    except (RuntimeError, OSError, KeyError) as exc:
        # Raised rather than returned empty: "no models" and "could not ask" look identical in
        # a dropdown, and one of them sends somebody to check their billing for no reason.
        raise HTTPException(400, str(exc))


@app.post("/api/settings/generation/test")
async def test_connection():
    """One small generation against the configured provider, reported honestly.

    Cheap enough to run freely and real enough to prove the credential, the base URL and the
    model all work together — which is the whole point of testing before a full-size plate.
    """
    import tempfile

    config = gen_settings.load()
    try:
        provider = provider_from_settings(config)
    except KeyError as exc:
        raise HTTPException(400, str(exc))
    _credential, source = gen_settings.credential_for(config)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "probe.png"
        try:
            provenance = await provider.generate(
                prompt="a plain grey test square, no detail",
                output=out,
                width=256,
                height=256,
            )
        except Exception as exc:  # noqa: BLE001 - any upstream failure is the answer here
            return {
                "ok": False,
                "provider": config["provider"],
                "credentialSource": source,
                "error": str(exc)[:600],
            }
        return {
            "ok": True,
            "provider": config["provider"],
            "credentialSource": source,
            "bytes": out.stat().st_size if out.exists() else 0,
            "detail": provenance,
        }


# ── Serving the web app from the API (single-process deployments) ─────────────────────────────
#
# Two processes locally — Vite on :5173, this on :8000 — but a Hugging Face Space exposes exactly
# one port, so there the built bundle has to come from here. Mounted last, after every route
# above, because a StaticFiles mount at "/" matches everything: declared earlier it would shadow
# /api and /health and the Space would serve index.html in answer to every request.
#
# Gated on the directory existing so a development checkout that has never run `npm run build`
# starts exactly as before instead of dying on a missing path.


def _web_dist() -> Path:
    """Where the built front-end lands, overridable for a container that puts it elsewhere."""
    import os

    configured = os.environ.get("AMBIENCE_WEB_DIST")
    if configured:
        return Path(configured)
    return Path.cwd() / "apps" / "web" / "dist"


_dist = _web_dist()
if (_dist / "index.html").is_file():
    # html=True so "/" resolves to index.html. The wizard has no client-side router, so no
    # deep-link fallback is needed beyond that.
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")

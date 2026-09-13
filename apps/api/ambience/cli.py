from pathlib import Path
import asyncio
import json
import shutil
import typer
from .models import ProjectCreate
from .repository import ProjectRepository
from .workflow import Workflow

app = typer.Typer(help="3D-Ambience-Studio CLI")


def _ctx(root: Path):
    data = root / "data"
    repo = ProjectRepository(data)
    return repo, Workflow(repo=repo, repo_root=root)


@app.command()
def demo(root: Path = Path(".")):
    """Run the complete V1 pipeline using tiny fixture media."""
    root = root.resolve()
    repo, workflow = _ctx(root)
    project = repo.create(ProjectCreate(
        name="Sunset Beach Demo",
        prompt="A peaceful tropical beach at sunset, no people, seamless 360 panorama",
        description="Tiny local fixture proving Studio → package → catalog.",
        category="relax",
        tags=["beach", "sunset", "demo"],
    ))
    project_dir = repo.project_dir(project.id)
    shutil.copy2(root / "fixtures" / "demo-panorama.webp", project_dir / "source-panorama.webp")
    shutil.copy2(root / "fixtures" / "demo-audio.wav", project_dir / "source-audio.wav")
    project.sourcePanorama = "source-panorama.webp"
    project.sourceAudio = "source-audio.wav"
    project.panoramaProvider = "fixture"
    repo.save(project)
    result = workflow.optimize(project.id)
    check = workflow.validate(project.id)
    if not check["valid"]:
        raise typer.Exit(code=1)
    publication = workflow.publish(project.id, featured=True)
    typer.echo(json.dumps({"project": project.id, "optimized": result, "publication": publication["entry"]}, indent=2))


@app.command()
def create(name: str, prompt: str = "", category: str = "relax", root: Path = Path(".")):
    repo, _ = _ctx(root.resolve())
    project = repo.create(ProjectCreate(name=name, prompt=prompt, category=category))
    typer.echo(project.model_dump_json(indent=2))


@app.command()
def generate(project_id: str, provider: str = "mock", seed: int | None = None, root: Path = Path(".")):
    _, workflow = _ctx(root.resolve())
    result = asyncio.run(workflow.generate_panorama(project_id, provider, seed))
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def optimize(project_id: str, root: Path = Path(".")):
    _, workflow = _ctx(root.resolve())
    typer.echo(json.dumps(workflow.optimize(project_id), indent=2))


@app.command()
def validate(project_id: str, root: Path = Path(".")):
    _, workflow = _ctx(root.resolve())
    typer.echo(json.dumps(workflow.validate(project_id), indent=2))


@app.command()
def publish(project_id: str, featured: bool = False, root: Path = Path(".")):
    _, workflow = _ctx(root.resolve())
    typer.echo(json.dumps(workflow.publish(project_id, featured=featured)["entry"], indent=2))


# ── The plate route: one scene, both cameras, one package ────────────────────────────────────
#
# Its own command rather than a flag on `generate`, because it does a different thing: `generate`
# makes one panorama for a project, this makes a complete two-variant environment package and
# publishes it. A flag would have made every argument conditional on the other.

SCENES: dict[str, dict] = {
    # The art direction lives here and the geometry does not — every number in the prompt comes
    # from the camera contract. Adding a scene is adding a paragraph, which is the point.
    "coastal-moonlight": {
        "id": "coastal-moonlight",
        "version": "0.1.0",
        "name": "Coastal Terrace — Moonlight",
        "description": "A quiet Mediterranean terrace above a calm sea, under a clear moonlit sky.",
        "category": "chill",
        "tags": ["water", "coast", "calm", "night", "moonlight", "mediterranean", "outdoor"],
        "fallbackColor": "#071525",
        "lighting": {"preset": "cool-moonlight-left", "exposure": 1.0},
        "subject": (
            "A peaceful cinematic Mediterranean coastal terrace at night. A calm dark blue sea "
            "extends toward distant low mountains. A clear moonlit sky with subtle thin clouds and "
            "restrained stars. The immediate foreground is an elegant, simple natural stone terrace. "
            "Sparse vegetation and low architecture at the far left and far right edges only. "
            "Photorealistic and cinematic, slightly idealised, believable scale, atmospheric depth, "
            "quiet and relaxing. Cool moonlight from the upper left, soft blue ambient fill, no blown "
            "highlights and no pitch-black areas in the centre. An original place, not a real or "
            "fictional location"
        ),
    }
}


@app.command("plate")
def plate(
    scene: str = typer.Option("coastal-moonlight", help="Which scene in SCENES to build."),
    contract: str = typer.Option("avatar-chatbot.json", help="Camera contract in examples/backplate-camera/."),
    provider: str = typer.Option("openai", help="openai or mock-backplate."),
    live: bool = typer.Option(False, "--live", help="Actually call the provider. Costs money."),
    root: Path = Path("."),
):
    """Build a two-variant plate package. Dry run unless --live is given.

    Dry run is the default on purpose: a live run spends real credit and returns a different
    picture each time, so the reviewable step and the expensive step are separated. Without
    --live this prints the compiled prompts, the model, the sizes that will be requested and
    where the files would land, and makes no network call at all.
    """
    from .providers.backplate import MockBackplateProvider
    from .providers.openai_plate import OpenAIPlateProvider
    from .services.backplate_guide import ContractError, load_contract
    from .services.plate_package import PlatePackageError, build, plan

    root = root.resolve()
    if scene not in SCENES:
        raise typer.BadParameter(f"Unknown scene {scene!r}. Known: {', '.join(sorted(SCENES))}")
    spec = SCENES[scene]

    contract_path = root / "examples" / "backplate-camera" / contract
    try:
        contract_data = load_contract(contract_path)
    except (ContractError, FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    contract_meta = {
        "id": contract_data.get("id", ""),
        "runtime": contract_data.get("runtime", ""),
        "file": contract_path.name,
    }

    engine = OpenAIPlateProvider() if provider == "openai" else MockBackplateProvider()
    out_dir = root / "data" / "public" / "environments" / spec["id"] / spec["version"]
    work_dir = root / "data" / "work" / spec["id"]

    if not live:
        report = plan(contract_data, spec, engine, out_dir)
        typer.echo(json.dumps(report, indent=2))
        typer.echo("\nDry run — nothing was generated and nothing was billed. Add --live to run it.")
        return

    if out_dir.exists() and any(out_dir.iterdir()):
        # Published versions are immutable here, and a silent overwrite of a package somebody has
        # already looked at is the kind of thing that is noticed much later.
        raise typer.BadParameter(f"{out_dir} already exists. Bump the version or remove it first.")

    if provider == "openai":
        engine.require_key()

    try:
        result = asyncio.run(build(contract_data, contract_meta, spec, engine, out_dir, work_dir))
    except (PlatePackageError, RuntimeError) as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    assets = result["assets"]
    typer.echo("")
    typer.echo("FIRST AI AMBIENCE ARTIFACT")
    typer.echo("==========================")
    typer.echo("")
    typer.echo(f"Scene:     {spec['id']} {spec['version']}")
    typer.echo(f"Provider:  {getattr(engine, 'name', provider)}")
    typer.echo(f"Model:     {getattr(engine, 'model', '-')}")
    typer.echo("")
    for variant in ("desktop", "mobile"):
        item = assets[variant]
        typer.echo(f"  OK  {variant}/background.webp  {item['width']}x{item['height']}  {item['bytes']} bytes")
    preview = result["preview"]
    with __import__("PIL.Image", fromlist=["Image"]).open(preview) as image:
        typer.echo(f"  OK  preview.webp  {image.width}x{image.height}  {preview.stat().st_size} bytes")
    typer.echo("  OK  environment.json")
    typer.echo("  OK  provenance.json")
    typer.echo("")
    typer.echo(f"Published: {result['dir']}")


if __name__ == "__main__":
    app()

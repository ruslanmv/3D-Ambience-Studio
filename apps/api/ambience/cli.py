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

@app.command("plate")
def plate(
    scene: str = typer.Option("coastal-moonlight", help="Which scene in ambience.scenes to build."),
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
    from .scenes import ALL_SCENES

    if scene not in ALL_SCENES:
        raise typer.BadParameter(f"Unknown scene {scene!r}. Known: {', '.join(sorted(ALL_SCENES))}")
    spec = ALL_SCENES[scene]

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


@app.command("generate-presets")
def generate_presets(
    contract: str = typer.Option("avatar-chatbot.json", help="Camera contract in examples/backplate-camera/."),
    provider: str = typer.Option("openai", help="openai or mock-backplate."),
    live: bool = typer.Option(False, "--live", help="Actually call the provider. Costs money."),
    force: bool = typer.Option(False, "--force", help="Regenerate variants that are already complete."),
    yes: bool = typer.Option(False, "--yes", help="Skip the one confirmation before the batch."),
    only: str = typer.Option("", help="Comma-separated scene ids, for re-running a few."),
    root: Path = Path("."),
):
    """Build every built-in preset: ten scenes, two plates each.

    Three properties matter more here than in the single-scene command, because this one spends
    real money twenty times.

    **Resumable.** A variant already generated by this model, from this prompt, against this
    camera is skipped. A failure at image fourteen must not buy the first thirteen again.

    **One confirmation, not twenty.** The batch is described in full — scenes, calls, model,
    quality, where it lands — and approved once. Asking again before every image trains people to
    stop reading.

    **No partial publish.** A scene publishes only when both its plates exist and pass structural
    validation. A package with a desktop plate and no portrait one validates, publishes, and
    breaks on a phone.
    """
    from .providers.backplate import MockBackplateProvider
    from .providers.openai_plate import OpenAIPlateProvider
    from .scenes import PRESETS
    from .services import preflight
    from .services.backplate_guide import ContractError, get_profile, load_contract
    from .services.plate_package import PlatePackageError, build, calibration_fingerprint
    from .services.plate_qa import composite

    root = root.resolve()
    wanted = [s.strip() for s in only.split(",") if s.strip()] or list(PRESETS)
    unknown = [s for s in wanted if s not in PRESETS]
    if unknown:
        raise typer.BadParameter(f"Unknown scene(s): {', '.join(unknown)}. Known: {', '.join(sorted(PRESETS))}")

    contract_path = root / "examples" / "backplate-camera" / contract
    try:
        contract_data = load_contract(contract_path)
    except (ContractError, FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    contract_meta = {
        "id": contract_data.get("id", ""),
        "runtime": contract_data.get("runtime", ""),
        "file": contract_path.name,
        "calibration": calibration_fingerprint(contract_data),
    }

    engine = OpenAIPlateProvider() if provider == "openai" else MockBackplateProvider()
    public_root = root / "data" / "public" / "environments"
    work_root = root / "data" / "work"

    typer.echo("")
    typer.echo("PRODUCTION AMBIENCE BATCH")
    typer.echo("=========================")
    typer.echo("")
    typer.echo(f"  Scenes:      {len(wanted)}")
    typer.echo(f"  Plates:      {len(wanted) * 2}  (desktop + portrait, composed separately)")
    typer.echo(f"  Provider:    {getattr(engine, 'name', provider)}")
    typer.echo(f"  Model:       {getattr(engine, 'model', '-')}")
    typer.echo(f"  Quality:     {getattr(engine, 'quality', '-')}")
    typer.echo(f"  Calibration: {contract_meta['calibration']} ({contract_meta['file']})")
    typer.echo(f"  Publish to:  {public_root}")
    typer.echo(f"  Work dir:    {work_root}")
    typer.echo("")
    for name in wanted:
        typer.echo(f"    {name}  →  {public_root / name / PRESETS[name]['version']}")
    typer.echo("")

    if not live:
        typer.echo("Dry run — nothing generated, nothing billed. Add --live to run the batch.")
        return

    problems = preflight.check(root, require_key=(provider == "openai"))
    if problems:
        typer.echo("Refusing to start a paid run:", err=True)
        for problem in problems:
            typer.echo(f"  - {problem}", err=True)
        raise typer.Exit(code=2)

    if not yes and not typer.confirm(f"Generate {len(wanted) * 2} images at {getattr(engine, 'quality', '?')} quality?"):
        typer.echo("Cancelled. Nothing was billed.")
        raise typer.Exit(code=1)

    done: list[str] = []
    failed: list[tuple[str, str]] = []
    for name in wanted:
        spec = PRESETS[name]
        out_dir = public_root / spec["id"] / spec["version"]
        work_dir = work_root / spec["id"]
        if out_dir.exists() and any(out_dir.iterdir()) and not force:
            typer.echo(f"  = {name}: already published at {spec['version']}, skipping.")
            done.append(name)
            continue
        typer.echo(f"  … {name}")
        try:
            result = asyncio.run(build(contract_data, contract_meta, spec, engine, out_dir, work_dir, force=force))
        except (PlatePackageError, RuntimeError, OSError) as exc:
            # Recorded and carried on. One scene's safety refusal must not abandon the other
            # nine, and the ledger means the next run resumes rather than restarts.
            failed.append((name, str(exc)[:300]))
            typer.echo(f"  ✗ {name}: {str(exc)[:200]}", err=True)
            continue

        for variant, profile_name in (("desktop", "landscape"), ("mobile", "portrait")):
            composite(
                result["assets"][variant]["path"],
                get_profile(contract_data, profile_name),
                work_dir / f"qa-{variant}.png",
            )
        reused = f"  (reused {', '.join(result['reused'])})" if result.get("reused") else ""
        typer.echo(f"  ✓ {name}{reused}")
        done.append(name)

    typer.echo("")
    typer.echo(f"Published {len(done)}/{len(wanted)}.")
    if failed:
        typer.echo("")
        typer.echo("Failed — re-run to resume, nothing already generated will be paid for twice:")
        for name, reason in failed:
            typer.echo(f"  {name}: {reason}")
        raise typer.Exit(code=1)
    typer.echo(f"QA composites for human inspection: {work_root}/<scene>/qa-*.png")


if __name__ == "__main__":
    app()

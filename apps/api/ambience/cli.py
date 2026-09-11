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


if __name__ == "__main__":
    app()

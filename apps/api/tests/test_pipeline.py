from pathlib import Path
from ambience.models import ProjectCreate
from ambience.repository import ProjectRepository
from ambience.workflow import Workflow
import shutil

ROOT = Path(__file__).resolve().parents[3]


def test_manual_pipeline(tmp_path):
    repo = ProjectRepository(tmp_path / "data")
    workflow = Workflow(repo=repo, repo_root=ROOT)
    project = repo.create(ProjectCreate(name="Forest Test", category="relax"))
    pdir = repo.project_dir(project.id)
    shutil.copy2(ROOT / "fixtures/demo-panorama.webp", pdir / "source-panorama.webp")
    project.sourcePanorama = "source-panorama.webp"
    repo.save(project)
    result = workflow.optimize(project.id)
    assert result["panorama"]["quest"]["width"] > 0
    assert workflow.validate(project.id)["valid"] is True

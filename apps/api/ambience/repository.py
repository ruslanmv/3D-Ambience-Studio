import json
import re
import secrets
from pathlib import Path
from .config import settings
from .models import ProjectCreate, ProjectRecord, utcnow


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "environment"


class ProjectRepository:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or settings.data_dir
        self.root = self.data_dir / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, project_id: str) -> Path:
        return self.root / project_id

    def _meta(self, project_id: str) -> Path:
        return self._dir(project_id) / "project.json"

    def create(self, payload: ProjectCreate) -> ProjectRecord:
        base = slugify(payload.name)
        project_id = f"{base}-{secrets.token_hex(3)}"
        record = ProjectRecord(id=project_id, **payload.model_dump())
        self.save(record)
        return record

    def save(self, record: ProjectRecord) -> ProjectRecord:
        record.updatedAt = utcnow()
        directory = self._dir(record.id)
        directory.mkdir(parents=True, exist_ok=True)
        self._meta(record.id).write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return record

    def get(self, project_id: str) -> ProjectRecord:
        path = self._meta(project_id)
        if not path.exists():
            raise KeyError(project_id)
        return ProjectRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[ProjectRecord]:
        records = []
        for path in sorted(self.root.glob("*/project.json")):
            records.append(ProjectRecord.model_validate_json(path.read_text(encoding="utf-8")))
        return records

    def project_dir(self, project_id: str) -> Path:
        path = self._dir(project_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

import json
from pathlib import Path
from jsonschema import Draft202012Validator
from .image_pipeline import validate_panorama_shape


def load_schema(repo_root: Path, name: str) -> dict:
    return json.loads((repo_root / "schemas" / name).read_text(encoding="utf-8"))


def validate_json(document: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [err.message for err in sorted(validator.iter_errors(document), key=lambda e: list(e.path))]


def validate_project_assets(source_panorama: Path | None, source_audio: Path | None) -> list[str]:
    errors = []
    if source_panorama is None or not source_panorama.exists():
        errors.append("A source panorama is required.")
    else:
        errors.extend(validate_panorama_shape(source_panorama))
    if source_audio is not None and not source_audio.exists():
        errors.append("Configured source audio file does not exist.")
    return errors

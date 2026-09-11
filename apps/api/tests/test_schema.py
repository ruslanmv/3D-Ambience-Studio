import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]


def test_example_environment_matches_schema():
    schema = json.loads((ROOT / "schemas/environment.schema.json").read_text())
    doc = json.loads((ROOT / "examples/sunset-beach/environment.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert errors == [], [e.message for e in errors]


def test_example_catalog_matches_schema():
    schema = json.loads((ROOT / "schemas/catalog.schema.json").read_text())
    doc = json.loads((ROOT / "examples/catalog.json").read_text())
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert errors == [], [e.message for e in errors]

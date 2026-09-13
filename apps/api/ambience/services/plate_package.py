"""One scene, both cameras, as a package the runtime can consume.

The panorama path publishes one image and lets every device crop it. A plate cannot work that
way: it is composed for exactly one projection, so a phone in portrait needs its own picture,
composed for *its* camera, not a crop of the desktop one. A crop moves the horizon, and the
horizon is the whole contract.

So this builds both, from the same art direction and two different camera profiles:

    scene spec ─┬─ landscape profile ─► prompt ─► provider ─► desktop/background.webp
                └─ portrait profile  ─► prompt ─► provider ─► mobile/background.webp
                                                    ↓
                                    environment.json · provenance.json · preview.webp

## Where the numbers come from

Not from here. Every geometric figure in the prompt and the manifest is read out of the camera
contract in `examples/backplate-camera/`, which is generated from the consuming runtime's own
camera. Writing "feet at 76%" into this file would be a guess, and a plausible one: the measured
value is 89.7% in landscape and 88.2% in portrait, because the camera is tilted about 1.72
degrees down and frames a 1.6 m figure from four metres. A guess that close is worse than no
number at all, because the art it produces looks nearly right.

## Dry run is the default

A live call costs money and produces a different picture every time. `plan()` builds everything
that does not need the network — the prompts, the sizes, the output paths — so the expensive step
is something a person asks for on purpose, once they have read what it would send.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from ..scenes import PROMPT_VERSION
from .backplate_guide import build_prompt, get_profile, render_guide
from .image_pipeline import BACKPLATE_TARGETS, optimize_backplate

#: Which runtime variant each camera profile produces. The runtime names a device; the contract
#: names a projection; this is the only place the two vocabularies meet.
VARIANT_PROFILES = {"desktop": "landscape", "mobile": "portrait"}

#: The scene card thumbnail. Derived from the desktop plate — a card is a wide crop everywhere.
PREVIEW_SIZE = (640, 360)
PREVIEW_QUALITY = 82


class PlatePackageError(RuntimeError):
    """A package that cannot be built, with the reason a person can act on."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compile_prompts(contract: dict, spec: dict) -> dict[str, dict]:
    """The art direction plus each profile's geometry, one compiled prompt per variant.

    Separated from generation so the expensive step and the reviewable step are different
    functions: the dry run prints exactly what a live call would send, because it is the same
    string, built by the same code.
    """
    out: dict[str, dict] = {}
    for variant, profile_name in VARIANT_PROFILES.items():
        try:
            camera = get_profile(contract, profile_name)
        except (KeyError, ValueError) as exc:
            raise PlatePackageError(f"Camera contract has no {profile_name!r} profile: {exc}") from exc
        master = camera["master"]
        out[variant] = {
            "variant": variant,
            "profile": profile_name,
            "prompt": build_prompt(camera, spec["subject"]),
            "negativePrompt": build_prompt(camera, "", negative=True),
            "master": {"width": int(master["width"]), "height": int(master["height"])},
            "camera": camera,
        }
    return out


def calibration_fingerprint(contract: dict) -> str:
    """A short hash of the camera geometry a plate was composed against.

    Recorded per variant so a resumed batch can tell "already generated" from "generated against
    a camera that has since moved". Without it, re-exporting the contract would leave twenty
    plates that look finished and no longer fit — the expensive kind of stale.
    """
    profiles = contract.get("profiles", {})
    payload = json.dumps(profiles, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def variant_state_path(work_dir: Path, variant: str) -> Path:
    return work_dir / f"state-{variant}.json"


def record_variant(work_dir: Path, variant: str, state: dict) -> None:
    """Written the moment a generation succeeds, not at the end of the batch.

    The whole point of resuming is that a crash at image fourteen keeps the first thirteen. A
    ledger written after everything succeeds would only ever describe runs that did not need it.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    variant_state_path(work_dir, variant).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def completed_variant(work_dir: Path, variant: str, expected: dict) -> dict | None:
    """The recorded state if this variant is genuinely done, otherwise None.

    "Done" means four things agree: a source image exists and opens, and the scene, the prompt and
    the calibration it was made for are the ones being asked for now. Any disagreement means
    regenerate — a skipped variant that does not match is a silent wrong answer, and the money
    saved by skipping it is the cheapest part of this.
    """
    path = variant_state_path(work_dir, variant)
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    source = work_dir / state.get("source", "")
    if not source.exists() or source.stat().st_size == 0:
        return None
    try:
        with Image.open(source) as image:
            image.verify()
    except (OSError, ValueError):
        # A half-written PNG from an interrupted run. Regenerate rather than publish it.
        return None

    for field in ("scene", "promptSha256", "calibration", "model"):
        if state.get(field) != expected.get(field):
            return None
    return state


def plan(contract: dict, spec: dict, provider: Any, out_dir: Path) -> dict:
    """Everything a live run would do, without doing any of it."""
    compiled = compile_prompts(contract, spec)
    steps = []
    for variant, item in compiled.items():
        master = item["master"]
        request = (
            provider.plan(master["width"], master["height"])
            if hasattr(provider, "plan")
            else {"provider": getattr(provider, "name", "?"), "masterSize": f"{master['width']}x{master['height']}"}
        )
        steps.append(
            {
                "variant": variant,
                "profile": item["profile"],
                "output": str(out_dir / variant / "background.webp"),
                "prompt": item["prompt"],
                "negativePrompt": item["negativePrompt"],
                "request": request,
            }
        )
    return {
        "scene": {"id": spec["id"], "version": spec["version"], "name": spec["name"]},
        "outputDir": str(out_dir),
        "steps": steps,
        "manifest": str(out_dir / "environment.json"),
    }


async def build(
    contract: dict,
    contract_meta: dict,
    spec: dict,
    provider: Any,
    out_dir: Path,
    work_dir: Path,
    *,
    force: bool = False,
) -> dict:
    """Generate, optimise and package. Raises rather than publishing something half-built.

    Nothing is written into `out_dir` until both variants have been generated and optimised. A
    package with a desktop plate and no mobile one is worse than no package: it validates, it
    publishes, and it breaks on a phone.
    """
    compiled = compile_prompts(contract, spec)
    work_dir.mkdir(parents=True, exist_ok=True)
    calibration = calibration_fingerprint(contract)
    model = getattr(provider, "model", "") or getattr(provider, "name", "")

    staged: dict[str, dict] = {}
    reused: list[str] = []
    for variant, item in compiled.items():
        profile_name = item["profile"]
        if profile_name not in BACKPLATE_TARGETS:
            raise PlatePackageError(f"No optimise target for profile {profile_name!r}.")

        # Kept beside the output: when a plate does not line up, the question is whether the
        # guide was wrong or the generator ignored it, and without the artefact neither is
        # answerable.
        guide_path = work_dir / f"guide-{profile_name}.png"
        render_guide(item["camera"]).save(guide_path)

        raw = work_dir / f"source-{variant}.png"
        expected = {
            "scene": spec["id"],
            "promptSha256": hashlib.sha256(item["prompt"].encode("utf-8")).hexdigest(),
            "calibration": calibration,
            "model": model,
        }

        existing = None if force else completed_variant(work_dir, variant, expected)
        if existing:
            # Already generated, by this model, from this prompt, against this camera. Twenty
            # paid requests is enough that re-running after a failure at image fourteen must not
            # buy the first thirteen again.
            provenance = existing.get("provenance", {})
            reused.append(variant)
        else:
            provenance = await provider.generate(
                prompt=item["prompt"],
                output=raw,
                width=item["master"]["width"],
                height=item["master"]["height"],
                guide=guide_path,
                negative_prompt=item["negativePrompt"],
                metadata={"scene": spec["id"], "variant": variant, "profile": profile_name},
            )
            if not raw.exists() or raw.stat().st_size == 0:
                raise PlatePackageError(f"{variant}: provider reported success but wrote no image.")
            record_variant(
                work_dir,
                variant,
                {**expected, "source": raw.name, "provenance": provenance, "recordedAt": _now()},
            )

        meta = optimize_backplate(raw, work_dir, profile_name)
        staged[variant] = {"optimised": meta[profile_name], "provenance": provenance, "guide": guide_path}

    # Both halves exist. Only now does anything land in the package directory.
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict] = {}
    for variant, item in staged.items():
        target = out_dir / variant / "background.webp"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(item["optimised"]["path"]).read_bytes())
        written[variant] = {
            "path": target,
            "width": item["optimised"]["width"],
            "height": item["optimised"]["height"],
            "bytes": target.stat().st_size,
        }

    preview = out_dir / "preview.webp"
    with Image.open(written["desktop"]["path"]) as image:
        image.convert("RGB").resize(PREVIEW_SIZE, Image.Resampling.LANCZOS).save(
            preview, "WEBP", quality=PREVIEW_QUALITY, method=6
        )

    manifest = build_manifest(spec, compiled, written, preview, contract_meta)
    # Validated before it is written, not after. A manifest that fails the schema is not a
    # publishing problem to notice later — it is a package the runtime will refuse, sitting in an
    # immutable versioned directory looking finished. The tests validated; the production path did
    # not, and a batch of ten shipped with `keyDirection` the schema had never been taught about.
    problems = validate_manifest(manifest)
    if problems:
        raise PlatePackageError(f"manifest does not satisfy the schema: {'; '.join(problems)}")
    (out_dir / "environment.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    provenance = build_provenance(spec, compiled, staged, written, contract_meta)
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    return {
        "dir": out_dir,
        "manifest": manifest,
        "provenance": provenance,
        "assets": written,
        "preview": preview,
        "reused": reused,
    }


def validate_manifest(manifest: dict) -> list[str]:
    """Check a manifest against the published schema, returning problems rather than raising.

    Soft on a missing validator — `jsonschema` is a dependency, but a packaging accident should
    not stop a batch that is otherwise correct — and hard on a real violation.
    """
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - the dependency is declared
        return []
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / "environment.schema.json"
    if not schema_path.exists():
        return []
    try:
        jsonschema.validate(manifest, json.loads(schema_path.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as exc:
        return [f"{'/'.join(str(p) for p in exc.absolute_path) or '(root)'}: {exc.message}"]
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not read the schema: {exc}"]
    return []


def build_manifest(spec: dict, compiled: dict, written: dict, preview: Path, contract_meta: dict) -> dict:
    """The environment manifest, in the schema this repository already publishes.

    Two departures from the shape a first sketch tends to take, both deliberate.

    `avatarAnchor` and `safeZone` live *inside each variant*, not once at the top level, because
    they genuinely differ: the character spans 39.8%–60.2% of a landscape frame and 25.2%–74.8%
    of a portrait one. A single top-level safe zone would be wrong for one of the two, and which
    one would depend on who wrote it.

    `cameraContract` names the projection the plate was composed for. A plate is not reusable
    across arbitrary views — that is the trade it makes for fitting one of them exactly — so a
    consumer has to be able to tell whether this picture is for its camera.
    """
    variants: dict[str, Any] = {}
    for variant, item in compiled.items():
        asset = written[variant]
        camera = item["camera"]
        safe = camera["safeZone"]
        variants[variant] = {
            "type": "plate",
            "background": f"{variant}/background.webp",
            "width": asset["width"],
            "height": asset["height"],
            "bytes": asset["bytes"],
            "cameraContract": {
                "id": contract_meta.get("id", ""),
                "runtime": contract_meta.get("runtime", ""),
                "profile": item["profile"],
            },
            "fovY": float(camera["fovDeg"]),
            "avatarAnchor": {"x": float(camera["footAnchor"]["x"]), "feetY": float(camera["footAnchor"]["y"])},
            "safeZone": {
                "xMin": float(safe["x0"]),
                "xMax": float(safe["x1"]),
                "yMin": float(safe["y0"]),
                "yMax": float(safe["y1"]),
            },
        }
    variants["companion"] = {"type": "inherit"}

    return {
        "schemaVersion": 1,
        "id": spec["id"],
        "version": spec["version"],
        "name": spec["name"],
        "description": spec.get("description", ""),
        "category": spec["category"],
        "tags": list(spec.get("tags", [])),
        "preview": {"src": preview.name},
        "variants": variants,
        "audio": None,
        "lighting": spec.get("lighting", {"preset": "cool-moonlight-left", "exposure": 1.0}),
        "effects": [],
        "fallbackColor": spec.get("fallbackColor", "#071525"),
        "compatibility": {"minRuntime": "0.1.0", "passthrough": "hidden"},
    }


def build_provenance(spec: dict, compiled: dict, staged: dict, written: dict, contract_meta: dict) -> dict:
    """How this was made, in enough detail to make it again — and nothing that must stay secret.

    The prompts are here because a surprising picture needs somewhere to be explained, and the
    prompt hash because that is what makes two runs comparable at a glance. What is not here, and
    is never here, is the credential: no key, no Authorization header, no account identifier. A
    package is published; a key is not.
    """
    entries = {}
    for variant, item in staged.items():
        record = dict(item["provenance"])
        record.pop("apiKey", None)
        entries[variant] = {
            "profile": compiled[variant]["profile"],
            "request": record,
            "promptSha256": hashlib.sha256(compiled[variant]["prompt"].encode("utf-8")).hexdigest(),
            "finalSize": f"{written[variant]['width']}x{written[variant]['height']}",
            "bytes": written[variant]["bytes"],
        }
    return {
        "schemaVersion": 1,
        "scene": {"id": spec["id"], "version": spec["version"]},
        "generatedAt": _now(),
        "promptVersion": PROMPT_VERSION,
        "cameraContract": contract_meta,
        "subject": spec["subject"],
        "variants": entries,
    }

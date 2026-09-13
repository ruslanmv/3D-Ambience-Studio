"""Route 2: generating a flat backplate against a consuming runtime's camera contract.

The panorama route is lossy and uncontrolled for a flat-background runtime — a 30° view at 16:9
takes about a seventh of a 4096-wide panorama and upscales it, and a 360° sky has no reason to
keep the middle of any particular view clear. This route generates the final image directly and
conditions the generator on a picture of where the horizon and floor must be.

That only works if the numbers survive the trip. The chain is:

    runtime camera → contract JSON → guide image → provider → backplate

and the tests that matter are the ones that check a figure entering one end comes out the other.
`test_horizon_survives_the_whole_chain` is the point of this file; the rest guard its edges.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from ambience.models import ProjectCreate
from ambience.providers.backplate import MockBackplateProvider
from ambience.providers.registry import get_backplate_provider
from ambience.repository import ProjectRepository
from ambience.services.backplate_guide import (
    ContractError,
    build_prompt,
    get_profile,
    load_contract,
    render_guide,
)
from ambience.services.image_pipeline import (
    BACKPLATE_TARGETS,
    optimize_backplate,
    validate_backplate_shape,
)
from ambience.workflow import Workflow
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "examples/backplate-camera/avatar-chatbot.json"


@pytest.fixture
def landscape() -> dict:
    return get_profile(load_contract(CONTRACT), "landscape")


def _horizon_row(image: Image.Image) -> int:
    """The row where sky becomes ground, found by the largest vertical jump down the centre."""
    rgb = image.convert("RGB")
    column = rgb.width // 2
    previous = rgb.getpixel((column, 0))
    best, best_delta = 0, 0
    for y in range(1, rgb.height):
        current = rgb.getpixel((column, y))
        delta = sum(abs(a - b) for a, b in zip(current, previous))
        if delta > best_delta:
            best, best_delta = y, delta
        previous = current
    return best


class TestContract:
    def test_the_shipped_contract_loads(self):
        contract = load_contract(CONTRACT)
        assert contract["schemaVersion"] == 1
        assert "landscape" in contract["profiles"]
        assert "portrait" in contract["profiles"]

    def test_the_camera_is_tilted_and_the_horizon_is_not_mid_frame(self, landscape):
        # The single most important number in the contract. A consumer that assumed a level
        # camera would put its horizon at 50% and be 60px out on a 1080 master.
        assert landscape["horizonY"] < 0.5
        assert landscape["horizonY"] == pytest.approx(0.444, abs=0.002)
        assert landscape["pitchDeg"] == pytest.approx(1.718, abs=0.01)

    def test_a_missing_profile_is_refused_rather_than_defaulted(self):
        # Guessing would produce a guide that looks authoritative and is wrong, which is worse
        # than refusing — nobody is supposed to estimate these.
        with pytest.raises(ContractError, match="no profile"):
            get_profile(load_contract(CONTRACT), "isometric")

    def test_an_unversioned_contract_is_refused(self, tmp_path):
        bad = tmp_path / "c.json"
        bad.write_text(json.dumps({"profiles": {}}), encoding="utf-8")
        with pytest.raises(ContractError):
            load_contract(bad)

    def test_a_contract_with_a_profile_missing_its_horizon_is_refused(self, tmp_path):
        bad = tmp_path / "c.json"
        bad.write_text(
            json.dumps({"schemaVersion": 1, "profiles": {"landscape": {"master": {"width": 1, "height": 1}}}}),
            encoding="utf-8",
        )
        with pytest.raises(ContractError, match="horizonY"):
            get_profile(load_contract(bad), "landscape")


class TestGuide:
    def test_it_renders_at_the_master_size(self, landscape):
        guide = render_guide(landscape)
        assert guide.size == (1920, 1080)

    def test_the_horizon_is_drawn_where_the_contract_puts_it(self, landscape):
        guide = render_guide(landscape).convert("RGB")
        expected = round(landscape["horizonY"] * guide.height)
        rows = [y for y in range(guide.height) if guide.getpixel((5, y))[0] > 200 and guide.getpixel((5, y))[1] < 110]
        assert rows, "no horizon line drawn"
        assert min(rows) <= expected <= max(rows)

    def test_the_floor_lines_converge_on_a_vanishing_point(self, landscape):
        # Parallel horizontals say how far apart things are; convergence is what makes a floor
        # read as a floor, and it is the cue a generator most needs.
        guide = render_guide(landscape).convert("RGB")
        horizon = round(landscape["horizonY"] * guide.height)

        def spread(row: int) -> int:
            xs = [x for x in range(guide.width) if guide.getpixel((x, row))[2] > 120 and guide.getpixel((x, row))[0] < 80]
            return max(xs) - min(xs) if len(xs) > 1 else 0

        near = spread(guide.height - 40)
        far = spread(horizon + 40)
        assert near > far > 0, f"lines do not converge: {near} near vs {far} far"

    def test_the_prompt_carries_the_numbers_a_text_only_worker_needs(self, landscape):
        prompt = build_prompt(landscape, "a quiet coastal terrace at dusk")
        assert "44.4%" in prompt
        assert "30 degree vertical field of view" in prompt
        assert "1.7 degrees down" in prompt
        assert "no people" in prompt

    def test_the_negative_prompt_forbids_what_has_no_positive_phrasing(self, landscape):
        negative = build_prompt(landscape, "", negative=True)
        # A painted person duplicates the avatar; a painted shadow will not match where she
        # stands. Neither can be expressed as something to include.
        assert "person" in negative
        assert "cast shadow of a person" in negative


class TestPipeline:
    def test_a_16_9_backplate_passes_its_own_validator(self, tmp_path):
        path = tmp_path / "b.png"
        Image.new("RGB", (1920, 1080), (10, 20, 30)).save(path)
        assert validate_backplate_shape(path, 16 / 9) == []

    def test_a_panorama_fails_the_backplate_validator(self, tmp_path):
        # The obvious way to waste an afternoon: running one through the other's check.
        path = tmp_path / "p.png"
        Image.new("RGB", (2048, 1024), (10, 20, 30)).save(path)
        errors = validate_backplate_shape(path, 16 / 9)
        assert errors and "1.778:1" in errors[0]

    def test_a_quantised_generator_output_is_accepted_and_cropped(self, tmp_path):
        # Models quantise to multiples of 8 or 64, so 1920x1088 is a rounding artefact rather
        # than a wrong shape. It is cropped, never resized: resizing would move the horizon off
        # the row the contract put it on, which is the one thing that must not move.
        source = tmp_path / "b.png"
        Image.new("RGB", (1920, 1088), (10, 20, 30)).save(source)
        result = optimize_backplate(source, tmp_path / "out", "landscape")
        assert (result["landscape"]["width"], result["landscape"]["height"]) == (1920, 1080)

    def test_an_undersized_backplate_is_upscaled_to_the_master(self, tmp_path):
        # Unlike the panorama path, which never upscales. A backplate is the final image, so
        # delivering it small only moves the upscale into the browser.
        source = tmp_path / "b.png"
        Image.new("RGB", (960, 540), (10, 20, 30)).save(source)
        result = optimize_backplate(source, tmp_path / "out", "landscape")
        assert (result["landscape"]["width"], result["landscape"]["height"]) == (1920, 1080)

    def test_a_preview_is_written_beside_the_master(self, tmp_path):
        source = tmp_path / "b.png"
        Image.new("RGB", (1920, 1080), (10, 20, 30)).save(source)
        result = optimize_backplate(source, tmp_path / "out", "landscape")
        assert Path(result["landscape-preview"]["path"]).exists()
        assert result["landscape-preview"]["width"] < result["landscape"]["width"]

    def test_portrait_uses_its_own_master(self, tmp_path):
        source = tmp_path / "b.png"
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(source)
        result = optimize_backplate(source, tmp_path / "out", "portrait")
        assert (result["portrait"]["width"], result["portrait"]["height"]) == (1080, 1920)

    def test_an_unknown_profile_is_refused(self, tmp_path):
        source = tmp_path / "b.png"
        Image.new("RGB", (1920, 1080), (10, 20, 30)).save(source)
        with pytest.raises(ValueError, match="Unknown backplate profile"):
            optimize_backplate(source, tmp_path / "out", "square")

    def test_both_masters_match_the_contract(self):
        contract = load_contract(CONTRACT)
        for name, (width, height, _quality) in BACKPLATE_TARGETS.items():
            master = contract["profiles"][name]["master"]
            assert (master["width"], master["height"]) == (width, height)


class TestProvider:
    def test_the_registry_is_separate_from_the_panorama_one(self):
        assert get_backplate_provider("mock-backplate") is not None
        with pytest.raises(KeyError):
            get_backplate_provider("panfusion")

    def test_the_mock_says_it_is_not_ai_generated(self, tmp_path, landscape):
        out = tmp_path / "b.png"
        provenance = asyncio.run(
            MockBackplateProvider().generate(prompt="x", output=out, width=640, height=360)
        )
        assert "not AI generated" in provenance["note"]

    def test_it_generates_at_exactly_the_size_asked_for(self, tmp_path):
        out = tmp_path / "b.png"
        asyncio.run(MockBackplateProvider().generate(prompt="x", output=out, width=1920, height=1080))
        with Image.open(out) as image:
            assert image.size == (1920, 1080)

    def test_no_guide_still_produces_a_usable_image(self, tmp_path):
        # A worker or a caller without a guide must degrade, not fail.
        out = tmp_path / "b.png"
        asyncio.run(MockBackplateProvider().generate(prompt="x", output=out, width=640, height=360, guide=None))
        with Image.open(out) as image:
            assert _horizon_row(image) == pytest.approx(180, abs=4)


def test_horizon_survives_the_whole_chain(tmp_path, landscape):
    """contract → guide → provider → backplate, with the horizon landing where it started.

    This is the assertion the route exists for. Every other test here guards one edge of it; if
    this one passes, a backplate built through this pipeline agrees with the camera that will
    render the avatar in front of it.
    """
    guide_path = tmp_path / "guide.png"
    render_guide(landscape).save(guide_path)

    out = tmp_path / "backplate.png"
    width = landscape["master"]["width"]
    height = landscape["master"]["height"]
    asyncio.run(
        MockBackplateProvider().generate(prompt="x", output=out, width=width, height=height, guide=guide_path)
    )

    with Image.open(out) as image:
        actual = _horizon_row(image) / image.height

    assert actual == pytest.approx(landscape["horizonY"], abs=0.003)


def test_workflow_generates_and_optimizes_a_backplate(tmp_path):
    repo = ProjectRepository(tmp_path / "data")
    workflow = Workflow(repo=repo, repo_root=ROOT)
    project = repo.create(ProjectCreate(name="Terrace", prompt="a quiet coastal terrace", category="relax"))

    asyncio.run(workflow.generate_backplate(project.id, "mock-backplate", CONTRACT, "landscape"))
    saved = repo.get(project.id)
    assert saved.sourceBackplate == "source-backplate-landscape.png"
    assert saved.backplateProvider == "mock-backplate"

    project_dir = repo.project_dir(project.id)
    # The guide is kept: when a backplate does not line up, it is the only evidence that
    # distinguishes "the guide was wrong" from "the worker ignored it".
    assert (project_dir / "guide-landscape.png").exists()
    provenance = json.loads((project_dir / "provenance-backplate-landscape.json").read_text())
    assert provenance["cameraContract"]["profile"] == "landscape"
    assert provenance["cameraContract"]["runtime"] == "3D-Avatar-Chatbot"

    result = workflow.optimize_backplate_asset(project.id)
    assert (result["landscape"]["width"], result["landscape"]["height"]) == (1920, 1080)


def test_the_panorama_route_is_untouched(tmp_path):
    """Route 2 is additive. The existing pipeline must behave exactly as it did."""
    import shutil

    repo = ProjectRepository(tmp_path / "data")
    workflow = Workflow(repo=repo, repo_root=ROOT)
    project = repo.create(ProjectCreate(name="Pano", category="relax"))
    pdir = repo.project_dir(project.id)
    shutil.copy2(ROOT / "fixtures/demo-panorama.webp", pdir / "source-panorama.webp")
    project.sourcePanorama = "source-panorama.webp"
    repo.save(project)
    assert workflow.optimize(project.id)["panorama"]["quest"]["width"] > 0
    assert workflow.validate(project.id)["valid"] is True


class TestPlateCompatibility:
    """The `plate` vocabulary, made compatible rather than renamed into.

    "Plate" is the standard term and what the environment schema accepts; "backplate" is what
    the working code and its tests are written against. Exporting both, as one class, costs a
    line and avoids churning code that works.
    """

    def test_plate_provider_is_the_same_class(self):
        from ambience.providers.backplate import BackplateProvider, PlateProvider

        assert PlateProvider is BackplateProvider

    def test_an_adapter_written_against_either_name_satisfies_both(self):
        from ambience.providers.backplate import BackplateProvider, PlateProvider

        assert issubclass(MockBackplateProvider, PlateProvider)
        assert isinstance(MockBackplateProvider(), BackplateProvider)

    def test_the_schema_accepts_both_spellings(self):
        import jsonschema

        schema = json.loads((ROOT / "schemas/environment.schema.json").read_text())
        for spelling in ("backplate", "plate"):
            manifest = {
                "schemaVersion": 1,
                "id": "x",
                "version": "1.0.0",
                "name": "X",
                "category": "relax",
                "preview": {"src": "p.webp"},
                "variants": {
                    "desktop": {
                        "type": spelling,
                        "background": "b.webp",
                        "width": 1920,
                        "height": 1080,
                        "cameraContract": {"id": "avatar-chatbot", "profile": "landscape"},
                        "fovY": 30,
                        "avatarAnchor": {"x": 0.5, "feetY": 0.897},
                        "safeZone": {"xMin": 0.398, "xMax": 0.602, "yMin": 0.158, "yMax": 0.897},
                    },
                    "quest": {"type": "panorama", "background": "q.webp"},
                    "companion": {"type": "gradient"},
                },
                "lighting": {"preset": "n"},
                "effects": [],
            }
            jsonschema.validate(manifest, schema)

    def test_the_panorama_manifest_still_validates(self):
        # The compatibility claim in one assertion: nothing about the existing format moved.
        import jsonschema

        schema = json.loads((ROOT / "schemas/environment.schema.json").read_text())
        jsonschema.validate(json.loads((ROOT / "examples/sunset-beach/environment.json").read_text()), schema)

    def test_the_wider_signature_is_optional_everywhere(self, tmp_path):
        # reference_images, mask and metadata are in the ABC so that adding them later would not
        # break third-party adapters. Every one must be omittable.
        out = tmp_path / "b.png"
        asyncio.run(MockBackplateProvider().generate(prompt="x", output=out, width=64, height=36))
        assert out.exists()

    def test_and_is_accepted_when_supplied(self, tmp_path):
        out = tmp_path / "b.png"
        provenance = asyncio.run(
            MockBackplateProvider().generate(
                prompt="x",
                output=out,
                width=64,
                height=36,
                reference_images=[],
                mask=None,
                metadata={"scene_id": "coastal-night", "profile": "mobile-fullbody-v1"},
            )
        )
        assert provenance["metadata"]["scene_id"] == "coastal-night"


class TestHomePilotAdapter:
    """Written against a stated contract, not a running service — so the tests pin the shape.

    What can be checked without HomePilot: that the request carries what the contract says, that
    polling terminates on both outcomes and on a deadline, and that no model identifier is
    hard-coded. Model names change faster than adapters do.
    """

    def test_it_hard_codes_no_model_names(self):
        # Read the code, not the prose. The module docstring names FLUX and SDXL while
        # *explaining* that neither is hard-coded, and an assertion over the raw text fails on
        # the documentation — which is the fourth time that trap has caught this project.
        source = (ROOT / "apps/api/ambience/providers/homepilot.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', "", source)
        code = re.sub(r"#.*$", "", code, flags=re.MULTILINE)
        for invented in ("gpt-image", "flux", "sdxl", "dall-e", "stable-diffusion"):
            assert invented not in code.lower(), f"{invented!r} should be configuration, not code"

    def test_provider_and_model_are_configuration(self):
        from ambience.providers.homepilot import HomePilotPlateProvider

        provider = HomePilotPlateProvider("http://x", provider="openai", model="anything-at-all")
        assert provider.provider == "openai"
        assert provider.model == "anything-at-all"

    def test_the_registry_exposes_it(self):
        assert get_backplate_provider("homepilot") is not None

    def test_it_submits_then_polls_then_downloads(self, tmp_path):
        import httpx
        from ambience.providers.homepilot import HomePilotPlateProvider

        calls: list[str] = []
        png = Image.new("RGB", (8, 8), (1, 2, 3))
        buffer = tmp_path / "a.png"
        png.save(buffer)

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(f"{request.method} {request.url.path}")
            if request.url.path.endswith("/v1/images/generate"):
                return httpx.Response(200, json={"job_id": "img_1", "status": "queued"})
            if request.url.path.endswith("/v1/jobs/img_1"):
                # Running first, so the poll loop is genuinely exercised.
                if calls.count("GET /v1/jobs/img_1") == 1:
                    return httpx.Response(200, json={"status": "running"})
                return httpx.Response(
                    200,
                    json={
                        "status": "succeeded",
                        "assets": [{"url": "/media/a.png", "width": 8, "height": 8}],
                        "generation": {"provider": "local", "model": "whatever"},
                    },
                )
            return httpx.Response(200, content=buffer.read_bytes(), headers={"content-type": "image/png"})

        provider = HomePilotPlateProvider("http://homepilot", poll_seconds=0)
        out = tmp_path / "plate.png"

        async def run():
            transport = httpx.MockTransport(handler)
            original = httpx.AsyncClient

            class Patched(original):
                def __init__(self, *args, **kwargs):
                    kwargs["transport"] = transport
                    super().__init__(*args, **kwargs)

            httpx.AsyncClient = Patched
            try:
                return await provider.generate(prompt="p", output=out, width=8, height=8)
            finally:
                httpx.AsyncClient = original

        provenance = asyncio.run(run())
        assert out.exists()
        assert calls[0] == "POST /v1/images/generate"
        assert calls.count("GET /v1/jobs/img_1") == 2, "it must poll until the job leaves 'running'"
        # A relative /media path is the documented shape and has to resolve against the base.
        assert calls[-1] == "GET /media/a.png"
        assert provenance["jobId"] == "img_1"
        assert provenance["routedProvider"] == "local"

    def test_a_failed_job_raises_with_the_reason(self, tmp_path):
        import httpx
        from ambience.providers.homepilot import HomePilotPlateProvider

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/v1/images/generate"):
                return httpx.Response(200, json={"job_id": "j", "status": "queued"})
            return httpx.Response(200, json={"status": "failed", "error": "out of memory"})

        provider = HomePilotPlateProvider("http://homepilot", poll_seconds=0)

        async def run():
            transport = httpx.MockTransport(handler)
            original = httpx.AsyncClient

            class Patched(original):
                def __init__(self, *args, **kwargs):
                    kwargs["transport"] = transport
                    super().__init__(*args, **kwargs)

            httpx.AsyncClient = Patched
            try:
                return await provider.generate(prompt="p", output=tmp_path / "x.png", width=8, height=8)
            finally:
                httpx.AsyncClient = original

        with pytest.raises(RuntimeError, match="out of memory"):
            asyncio.run(run())

    def test_an_endless_job_times_out_rather_than_hanging(self, tmp_path):
        import httpx
        from ambience.providers.homepilot import HomePilotPlateProvider

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/v1/images/generate"):
                return httpx.Response(200, json={"job_id": "j", "status": "queued"})
            return httpx.Response(200, json={"status": "running"})

        provider = HomePilotPlateProvider("http://homepilot", poll_seconds=0, timeout_seconds=0)

        async def run():
            transport = httpx.MockTransport(handler)
            original = httpx.AsyncClient

            class Patched(original):
                def __init__(self, *args, **kwargs):
                    kwargs["transport"] = transport
                    super().__init__(*args, **kwargs)

            httpx.AsyncClient = Patched
            try:
                return await provider.generate(prompt="p", output=tmp_path / "x.png", width=8, height=8)
            finally:
                httpx.AsyncClient = original

        with pytest.raises(TimeoutError):
            asyncio.run(run())

    def test_an_unknown_status_is_treated_as_still_running(self):
        # A worker inventing a new in-progress name should slow us down, not fail the job.
        from ambience.providers.homepilot import _FAILURE, _SUCCESS

        assert "queued" not in _SUCCESS and "queued" not in _FAILURE
        assert "running" not in _SUCCESS and "running" not in _FAILURE

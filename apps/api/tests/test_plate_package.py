"""The OpenAI plate route, tested without spending a cent.

Every test here mocks the transport. That is not only thrift: a live image model returns a
different picture every time, so anything asserted against a real response would either be
trivially true or flaky. What is worth pinning is the part that is deterministic — the request
shape, the exact final dimensions, the manifest, and what happens when the provider fails
half-way.

The request-shape tests are the ones that earn their keep. Verified against the live API on
2026-09-13, `gpt-image-2.5-sunburst` rejects `response_format` outright and refuses any size whose
edges are not multiples of 16. Both facts are invisible until a real call fails, and both are
cheap to hold here.
"""

from __future__ import annotations

import asyncio
import io
import json

import httpx
import jsonschema
import pytest
from ambience.providers.openai_plate import MAX_EDGE, OpenAIPlateProvider, snap_size
from ambience.services import plate_package
from PIL import Image

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
SCHEMA = json.loads((REPO_ROOT / "schemas" / "environment.schema.json").read_text(encoding="utf-8"))
CONTRACT_PATH = REPO_ROOT / "examples" / "backplate-camera" / "avatar-chatbot.json"


def png_bytes(width: int, height: int) -> bytes:
    """A real image of the requested size, made here rather than committed as a fixture."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 40, 60)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def contract():
    from ambience.services.backplate_guide import load_contract

    return load_contract(CONTRACT_PATH)


@pytest.fixture
def spec():
    return {
        "id": "coastal-moonlight",
        "version": "0.1.0",
        "name": "Coastal Terrace — Moonlight",
        "description": "Test scene.",
        "category": "chill",
        "tags": ["water", "night"],
        "fallbackColor": "#071525",
        "lighting": {"preset": "cool-moonlight-left", "exposure": 1.0},
        "subject": "A quiet coastal terrace at night",
    }


class FakeProvider:
    """Returns an image of exactly the size it was asked for, and records the asks."""

    name = "fake"
    model = "fake-model"

    def __init__(self, fail_on: str | None = None):
        self.calls: list[dict] = []
        self.fail_on = fail_on

    async def generate(self, *, prompt, output, width, height, **kwargs):
        self.calls.append({"prompt": prompt, "width": width, "height": height, **kwargs})
        if self.fail_on and kwargs.get("metadata", {}).get("variant") == self.fail_on:
            raise RuntimeError("provider exploded")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately not the master size: a real generator returns what its quantiser allows,
        # and the optimise step is what makes the final file exact.
        output.write_bytes(png_bytes(round(width * 0.8 / 16) * 16, round(height * 0.8 / 16) * 16))
        return {"provider": self.name, "model": self.model, "prompt": prompt}



def build_package(contract, spec, provider, out, work, meta=None):
    """The house pattern: asyncio.run in a synchronous test.

    No pytest-asyncio in the dev extras, and adding a dependency for syntax sugar when the rest of
    the suite already does this would be the wrong trade.
    """
    return asyncio.run(
        plate_package.build(contract, meta or {"id": "avatar-chatbot", "runtime": "3D-Avatar-Chatbot"}, spec, provider, out, work)
    )


def generate(provider, tmp_path, **kwargs):
    kwargs.setdefault("prompt", "x")
    kwargs.setdefault("output", tmp_path / "o.png")
    kwargs.setdefault("width", 512)
    kwargs.setdefault("height", 512)
    return asyncio.run(provider.generate(**kwargs))


def install_transport(monkeypatch, handler):
    """Point every httpx.AsyncClient in this process at a mock transport."""
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)


class TestSizeRules:
    """Measured from the API, not remembered from documentation."""

    def test_the_master_sizes_are_not_requestable_as_they_stand(self):
        # 1080 is not a multiple of 16, so neither master can be asked for directly. That is the
        # whole reason the provider snaps and the pipeline crops.
        assert 1080 % 16 != 0
        assert snap_size(1920, 1080) == (1920, 1088)
        assert snap_size(1080, 1920) == (1088, 1920)

    def test_both_edges_always_land_on_a_multiple_of_sixteen(self):
        for width, height in ((1920, 1080), (1080, 1920), (1080, 2400), (999, 333)):
            out_w, out_h = snap_size(width, height)
            assert out_w % 16 == 0 and out_h % 16 == 0, (width, height)

    def test_nothing_exceeds_the_longest_edge_the_api_allows(self):
        for width, height in ((8192, 8192), (4096, 2048), (1024, 6000)):
            assert max(snap_size(width, height)) <= MAX_EDGE

    def test_the_snapped_aspect_stays_inside_the_crop_tolerance(self):
        # validate_backplate_shape allows 2%. Exceed it and the optimise step would reject the
        # provider's own output.
        for width, height in ((1920, 1080), (1080, 1920), (1600, 900)):
            out_w, out_h = snap_size(width, height)
            assert abs((out_w / out_h) - (width / height)) / (width / height) < 0.02


class TestCredential:
    def test_a_missing_key_is_a_clear_instruction_not_a_stack_trace(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError) as error:
            OpenAIPlateProvider().require_key()
        assert "OPENAI_API_KEY" in str(error.value)

    def test_the_key_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
        assert OpenAIPlateProvider().api_key == "sk-from-env"

    def test_the_plan_reports_whether_a_key_exists_without_showing_it(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
        report = OpenAIPlateProvider().plan(1920, 1080)
        assert report["hasKey"] is True
        assert "sk-secret-value" not in json.dumps(report)


class TestRequestShape:
    """What actually goes on the wire."""

    @pytest.fixture
    def captured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_IMAGE_MODEL", raising=False)
        monkeypatch.delenv("OPENAI_IMAGE_QUALITY", raising=False)
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import base64

            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png_bytes(64, 64)).decode()}]})

        install_transport(monkeypatch, handler)
        return seen

    def test_it_never_sends_response_format(self, captured, tmp_path):
        # The live API answers `Unknown parameter: 'response_format'` — which is exactly why this
        # is not the OpenAI-compatible adapter, which always sends it.
        generate(OpenAIPlateProvider(), tmp_path, width=1920, height=1080)
        assert "response_format" not in captured["payload"]

    def test_it_asks_for_a_legal_size_and_records_both(self, captured, tmp_path):
        result = generate(OpenAIPlateProvider(), tmp_path, width=1920, height=1080)
        assert captured["payload"]["size"] == "1920x1088"
        assert result["requestedSize"] == "1920x1088"
        assert result["masterSize"] == "1920x1080"

    def test_quality_and_model_are_configuration(self, captured, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
        monkeypatch.setenv("OPENAI_IMAGE_QUALITY", "medium")
        generate(OpenAIPlateProvider(), tmp_path)
        assert captured["payload"]["model"] == "gpt-image-2.5-flare"
        assert captured["payload"]["quality"] == "medium"

    def test_an_invalid_quality_falls_back_rather_than_failing_upstream(self, captured, tmp_path):
        generate(OpenAIPlateProvider(quality="cinematic"), tmp_path)
        assert captured["payload"]["quality"] == "high"

    def test_the_negative_prompt_rides_in_the_prompt(self, captured, tmp_path):
        # There is no negative-prompt field on this endpoint, and dropping "no people" from a
        # plate that will have a real person standing in front of it is not an option.
        generate(OpenAIPlateProvider(), tmp_path, prompt="a terrace", negative_prompt="people")
        assert "people" in captured["payload"]["prompt"]

    def test_the_key_travels_as_a_bearer_header_and_nowhere_else(self, captured, tmp_path):
        generate(OpenAIPlateProvider(), tmp_path)
        assert captured["headers"]["authorization"] == "Bearer sk-test"
        assert "sk-test" not in json.dumps(captured["payload"])

    def test_the_bytes_are_written(self, captured, tmp_path):
        output = tmp_path / "nested" / "o.png"
        generate(OpenAIPlateProvider(), tmp_path, output=output)
        assert output.exists() and output.stat().st_size > 0


class TestFailures:
    def test_a_client_error_is_terminal_and_not_retried(self, monkeypatch, tmp_path):
        # A refusal, a bad key or an empty balance fails identically the second time, and
        # confirming that costs money.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(400, json={"error": {"message": "your prompt was rejected"}})

        install_transport(monkeypatch, handler)
        with pytest.raises(RuntimeError) as error:
            generate(OpenAIPlateProvider(), tmp_path)
        assert attempts["n"] == 1
        assert "rejected" in str(error.value)

    def test_a_server_error_is_retried_exactly_once(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        attempts = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["n"] += 1
            return httpx.Response(503, text="upstream busy")

        install_transport(monkeypatch, handler)
        with pytest.raises(RuntimeError):
            generate(OpenAIPlateProvider(), tmp_path)
        assert attempts["n"] == 2

    def test_a_response_without_an_image_is_an_error_not_an_empty_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        install_transport(monkeypatch, lambda request: httpx.Response(200, json={"data": []}))
        output = tmp_path / "o.png"
        with pytest.raises(RuntimeError):
            generate(OpenAIPlateProvider(), tmp_path, output=output)
        assert not output.exists()


class TestPackage:
    def test_both_variants_land_at_exactly_their_master_size(self, contract, spec, tmp_path):
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        assert (result["assets"]["desktop"]["width"], result["assets"]["desktop"]["height"]) == (1920, 1080)
        assert (result["assets"]["mobile"]["width"], result["assets"]["mobile"]["height"]) == (1080, 1920)

    def test_the_preview_is_the_card_size(self, contract, spec, tmp_path):
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        with Image.open(result["preview"]) as image:
            assert image.size == plate_package.PREVIEW_SIZE

    def test_the_manifest_validates(self, contract, spec, tmp_path):
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        jsonschema.validate(result["manifest"], SCHEMA)

    def test_a_panorama_manifest_still_validates_after_the_schema_change(self):
        # Relaxing `variants.required` for plates must not stop requiring a Quest variant of a
        # panorama — that requirement is what keeps a skybox from shipping without one.
        panorama = json.loads((REPO_ROOT / "examples" / "sunset-beach" / "environment.json").read_text())
        jsonschema.validate(panorama, SCHEMA)
        del panorama["variants"]["quest"]
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(panorama, SCHEMA)

    def test_the_two_variants_are_composed_for_different_cameras(self, contract, spec, tmp_path):
        # Not one image cropped twice. A crop moves the horizon, and the horizon is the contract.
        provider = FakeProvider()
        build_package(contract, spec, provider, tmp_path / "out", tmp_path / "work")
        prompts = [call["prompt"] for call in provider.calls]
        assert len(prompts) == 2
        assert prompts[0] != prompts[1]
        assert "44.4%" in prompts[0] and "46.1%" in prompts[1]

    def test_the_manifest_carries_each_profile_s_own_safe_zone(self, contract, spec, tmp_path):
        # One top-level safe zone would be wrong for one of the two: she spans a fifth of a
        # landscape frame and half a portrait one.
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        desktop = result["manifest"]["variants"]["desktop"]["safeZone"]
        mobile = result["manifest"]["variants"]["mobile"]["safeZone"]
        assert (mobile["xMax"] - mobile["xMin"]) > (desktop["xMax"] - desktop["xMin"]) * 2

    def test_a_failure_half_way_publishes_nothing(self, contract, spec, tmp_path):
        # A package with a desktop plate and no mobile one validates, publishes, and breaks on a
        # phone. Worse than no package at all.
        out = tmp_path / "out"
        with pytest.raises(RuntimeError):
            build_package(contract, spec, FakeProvider(fail_on="mobile"), out, tmp_path / "work")
        assert not out.exists() or not any(out.iterdir())

    def test_no_credential_reaches_the_manifest_or_the_provenance(self, contract, spec, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-must-never-appear")
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        written = (tmp_path / "out" / "environment.json").read_text() + (
            tmp_path / "out" / "provenance.json"
        ).read_text()
        assert "sk-must-never-appear" not in written
        assert "sk-" not in json.dumps(result["provenance"])

    def test_the_provenance_records_what_makes_a_run_reproducible(self, contract, spec, tmp_path):
        result = build_package(contract, spec, FakeProvider(), tmp_path / "out", tmp_path / "work")
        provenance = result["provenance"]
        assert provenance["scene"]["id"] == "coastal-moonlight"
        assert provenance["generatedAt"].endswith("Z")
        for variant in ("desktop", "mobile"):
            assert len(provenance["variants"][variant]["promptSha256"]) == 64
            assert provenance["variants"][variant]["request"]["prompt"]

    def test_the_guide_is_kept_for_each_profile(self, contract, spec, tmp_path):
        # The evidence that answers "was the guide wrong, or did the generator ignore it".
        work = tmp_path / "work"
        build_package(contract, spec, FakeProvider(), tmp_path / "out", work)
        assert (work / "guide-landscape.png").exists()
        assert (work / "guide-portrait.png").exists()

    def test_a_dry_run_touches_nothing(self, contract, spec, tmp_path):
        out = tmp_path / "out"
        report = plate_package.plan(contract, spec, FakeProvider(), out)
        assert not out.exists()
        assert len(report["steps"]) == 2

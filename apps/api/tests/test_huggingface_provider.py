"""The Hugging Face plate adapter.

No network here. What is worth pinning is not that an HTTP call happens but the three decisions
around it: what size gets asked for, which of the two Hugging Face calls is made, and what happens
when the conditioned one fails — because that last answer is the difference between a plate that
is wrong and a plate that is wrong *and looks fine*.
"""

from __future__ import annotations

import asyncio

import pytest
from ambience.providers.huggingface import (
    DEFAULT_MODEL,
    ROUTING,
    SUGGESTED_MODELS,
    HuggingFacePlateProvider,
    fit_to_model,
)
from PIL import Image


class FakeClient:
    """Stands in for InferenceClient, recording what it was asked for."""

    def __init__(self, *, fail_image_to_image: bool = False):
        self.calls: list[tuple[str, dict]] = []
        self.fail_image_to_image = fail_image_to_image

    def text_to_image(self, prompt, **kwargs):
        self.calls.append(("text_to_image", {"prompt": prompt, **kwargs}))
        return Image.new("RGB", (kwargs.get("width", 8), kwargs.get("height", 8)), (10, 20, 30))

    def image_to_image(self, image, **kwargs):
        self.calls.append(("image_to_image", {"bytes": len(image), **kwargs}))
        if self.fail_image_to_image:
            raise RuntimeError("provider does not support image-to-image for this model")
        size = kwargs.get("target_size")
        width = getattr(size, "width", None) or (size or {}).get("width", 8)
        height = getattr(size, "height", None) or (size or {}).get("height", 8)
        return Image.new("RGB", (width, height), (30, 20, 10))


@pytest.fixture
def provider_with(monkeypatch):
    def build(fake: FakeClient, **kwargs):
        provider = HuggingFacePlateProvider("hf-token", **kwargs)
        monkeypatch.setattr(provider, "_client", lambda: fake)
        return provider

    return build


class TestSizeFitting:
    def test_the_master_size_is_scaled_down_at_the_same_aspect(self):
        # 1920 is frequently refused or silently re-quantised. The optimise step resizes to the
        # master anyway — and upscales — so asking for a size models accept costs nothing that
        # matters, as long as the aspect is exact. The aspect is the part that must not move.
        assert fit_to_model(1920, 1080) == (1536, 864)
        assert 1536 / 864 == 1920 / 1080

    def test_portrait_too(self):
        assert fit_to_model(1080, 1920) == (864, 1536)

    def test_both_edges_land_on_a_multiple_of_sixteen(self):
        for width, height in ((1920, 1080), (1080, 1920), (1000, 700), (333, 777)):
            out_w, out_h = fit_to_model(width, height)
            assert out_w % 16 == 0 and out_h % 16 == 0, (width, height)

    def test_a_size_already_small_enough_is_left_alone(self):
        assert fit_to_model(1024, 1024) == (1024, 1024)

    def test_the_result_stays_inside_the_shape_validator_tolerance(self):
        # validate_backplate_shape allows 2%; rounding to a multiple of 16 must not exceed it or
        # the optimise step would reject the adapter's own output.
        for width, height in ((1920, 1080), (1080, 1920), (1600, 900), (1234, 567)):
            out_w, out_h = fit_to_model(width, height)
            assert abs((out_w / out_h) - (width / height)) / (width / height) < 0.02


class TestTextToImage:
    def test_it_is_the_default_route(self, provider_with, tmp_path):
        fake = FakeClient()
        provider = provider_with(fake)
        guide = tmp_path / "guide.png"
        Image.new("RGB", (32, 18)).save(guide)

        result = asyncio.run(
            provider.generate(
                prompt="a terrace", output=tmp_path / "out.png", width=1920, height=1080, guide=guide
            )
        )
        assert [c[0] for c in fake.calls] == ["text_to_image"]
        assert result["mode"] == "text-to-image"
        assert result["guideSent"] is False

    def test_it_passes_the_negative_prompt_and_seed_through(self, provider_with, tmp_path):
        fake = FakeClient()
        provider = provider_with(fake)
        asyncio.run(
            provider.generate(
                prompt="a terrace",
                output=tmp_path / "out.png",
                width=1024,
                height=1024,
                negative_prompt="people, text",
                seed=7,
            )
        )
        _, kwargs = fake.calls[0]
        assert kwargs["negative_prompt"] == "people, text"
        assert kwargs["seed"] == 7
        assert kwargs["model"] == DEFAULT_MODEL

    def test_an_empty_negative_prompt_is_sent_as_nothing(self, provider_with, tmp_path):
        # Not as "". Some routes treat an empty string as a real, meaningless condition.
        fake = FakeClient()
        asyncio.run(
            provider_with(fake).generate(
                prompt="p", output=tmp_path / "o.png", width=512, height=512, negative_prompt=""
            )
        )
        assert fake.calls[0][1]["negative_prompt"] is None

    def test_the_written_file_is_the_returned_image(self, provider_with, tmp_path):
        output = tmp_path / "out.png"
        asyncio.run(
            provider_with(FakeClient()).generate(prompt="p", output=output, width=1920, height=1080)
        )
        with Image.open(output) as image:
            assert image.size == (1536, 864)


class TestImageToImage:
    def test_the_guide_is_only_sent_when_asked_for(self, provider_with, tmp_path):
        fake = FakeClient()
        provider = provider_with(fake, use_guide=True)
        guide = tmp_path / "guide.png"
        Image.new("RGB", (64, 36), (255, 0, 64)).save(guide)

        result = asyncio.run(
            provider.generate(
                prompt="a terrace", output=tmp_path / "out.png", width=1920, height=1080, guide=guide
            )
        )
        assert [c[0] for c in fake.calls] == ["image_to_image"]
        assert result["mode"] == "image-to-image"
        assert result["guideSent"] is True
        assert fake.calls[0][1]["bytes"] == guide.stat().st_size

    def test_asking_for_the_guide_without_one_falls_back_to_text(self, provider_with, tmp_path):
        # Not an error: the operator turned the switch on and this particular call has no guide.
        fake = FakeClient()
        provider = provider_with(fake, use_guide=True)
        asyncio.run(provider.generate(prompt="p", output=tmp_path / "o.png", width=512, height=512))
        assert fake.calls[0][0] == "text_to_image"

    def test_a_failure_is_raised_not_quietly_downgraded(self, provider_with, tmp_path):
        """The rule this adapter exists to enforce.

        Falling back to text_to_image would return a handsome plate with the horizon in the wrong
        place. That is not a degraded success — it is a failure that survives review and is found
        by a character standing in mid-air, which is exactly the bug the guide was built to stop.
        """
        fake = FakeClient(fail_image_to_image=True)
        provider = provider_with(fake, use_guide=True)
        guide = tmp_path / "guide.png"
        Image.new("RGB", (64, 36)).save(guide)

        with pytest.raises(RuntimeError) as error:
            asyncio.run(
                provider.generate(
                    prompt="p", output=tmp_path / "o.png", width=1920, height=1080, guide=guide
                )
            )
        assert [c[0] for c in fake.calls] == ["image_to_image"]
        assert "image-to-image" in str(error.value)
        assert not (tmp_path / "o.png").exists()


class TestConfiguration:
    def test_an_unknown_routing_target_falls_back_to_auto(self):
        # Rather than passing a value the client would reject at generation time, minutes later.
        assert HuggingFacePlateProvider("t", routing="not-a-provider").routing == "auto"

    def test_every_offered_routing_target_is_accepted(self):
        for routing in ROUTING:
            assert HuggingFacePlateProvider("t", routing=routing).routing == routing

    def test_no_model_means_the_default_model(self):
        assert HuggingFacePlateProvider("t", model="").model == DEFAULT_MODEL

    def test_the_shortlist_is_openly_licensed(self):
        # A default model is a licence decision made for the operator. The FLUX "dev" weights are
        # non-commercial, so nothing on this list may be one.
        assert [m["licence"] for m in SUGGESTED_MODELS] == ["Apache-2.0", "Apache-2.0"]

    def test_no_token_is_a_clear_error_not_an_auth_failure(self):
        provider = HuggingFacePlateProvider("")
        with pytest.raises(RuntimeError) as error:
            provider._client()
        assert "HF_TOKEN" in str(error.value)

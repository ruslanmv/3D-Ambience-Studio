"""Hugging Face Inference Providers as a plate generator.

One token, many inference companies. Hugging Face routes a single request to fal.ai, Replicate,
Together, Nscale, WaveSpeed or its own inference stack, so this adapter buys access to a set of
open-weight image models without the Studio hosting a GPU or holding an account with any of them.
That makes it the natural cloud default when the Studio itself runs on a Hugging Face Space,
where the token is already present as a Space Secret.

## Why this is not the OpenAI-compatible adapter

Hugging Face does expose an OpenAI-compatible endpoint, and it is tempting to point
`OpenAICompatibleImageProvider` at it and be done. That endpoint is for chat completions; its
documentation states it does not cover image generation. So the compatibility is real and
irrelevant here, and a shared adapter would fail at runtime in a way that reads like a bad
credential.

## Why the guide is opt-in

`text_to_image` carries the camera constraints as words only — the same weakness as the
OllaBridge route. `image_to_image` can take the rendered guide as an actual spatial condition,
which is the whole reason the guide exists, but only some provider/model combinations implement
it and only some of those honour `target_size`.

So `use_guide` is a choice, not a guess, and a failure on that path is **raised, never retried as
text-to-image**. A silent fallback would produce a perfectly attractive plate whose horizon is in
the wrong place, which is the specific failure this repository keeps warning about: it looks like
success and is discovered in the runtime, by a character standing in mid-air.

## Model defaults and licences

The default is `black-forest-labs/FLUX.1-schnell`, whose weights are Apache-2.0 and may be used
commercially. `Qwen/Qwen-Image` is offered as the second option on the same terms. Models under
the FLUX non-commercial "dev" licence can produce better plates and are deliberately **not**
defaults: a default is a licence choice made on the operator's behalf, and that one is not ours
to make. The model field is free text, so choosing one remains possible and deliberate.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .backplate import BackplateProvider

logger = logging.getLogger(__name__)

#: Apache-2.0 weights, fast enough to iterate with. See the licence note above before changing.
DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"

#: Offered in the panel. Both Apache-2.0; the field accepts anything, this is only the shortlist.
SUGGESTED_MODELS = [
    {"id": "black-forest-labs/FLUX.1-schnell", "licence": "Apache-2.0", "role": "Fast default"},
    {"id": "Qwen/Qwen-Image", "licence": "Apache-2.0", "role": "Composition and layout"},
]

#: Routing targets. "auto" lets Hugging Face pick and fail over, which is what its own
#: documentation recommends; the rest pin one company when a model is known to behave better on it.
ROUTING = ["auto", "hf-inference", "fal-ai", "replicate", "together", "nscale", "wavespeed"]

#: The longest edge to ask a model for. 1920 is frequently refused or quietly re-quantised, and
#: the plate is resized to its master size by `optimize_backplate` anyway — which upscales, so
#: asking for 1536x864 and letting the pipeline finish the job is not a loss of resolution worth
#: the failures. Aspect is preserved exactly; that is the part that must not move.
MAX_EDGE = 1536


def fit_to_model(width: int, height: int, max_edge: int = MAX_EDGE, multiple: int = 16) -> tuple[int, int]:
    """The nearest size a diffusion model will accept, at the same aspect ratio.

    Two constraints at once: no edge longer than `max_edge`, and both edges a multiple of
    `multiple` — nearly every latent-space model quantises to 8 or 16 and either rounds silently
    or refuses. Ratio is preserved to within that rounding, which `validate_backplate_shape`
    tolerates at 2%; 1920x1080 becomes 1536x864, exactly 16:9.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    scale = min(1.0, max_edge / max(width, height))
    out_w = max(multiple, round(width * scale / multiple) * multiple)
    out_h = max(multiple, round(height * scale / multiple) * multiple)
    return out_w, out_h


class HuggingFacePlateProvider(BackplateProvider):
    """text-to-image (and optionally image-to-image) through Hugging Face's router."""

    name = "huggingface"

    def __init__(
        self,
        token: str,
        *,
        model: str = "",
        routing: str = "auto",
        use_guide: bool = False,
        timeout_seconds: float = 300.0,
        max_edge: int = MAX_EDGE,
    ):
        self.token = (token or "").strip()
        self.model = (model or "").strip() or DEFAULT_MODEL
        self.routing = routing if routing in ROUTING else "auto"
        self.use_guide = use_guide
        self.timeout_seconds = timeout_seconds
        self.max_edge = max_edge

    def _client(self):
        """Built per call, lazily imported.

        Lazy because `huggingface_hub` is only needed by operators who choose this provider, and
        an import error at module scope would take down every other route with it — including the
        mock, which is what a first run is meant to use.
        """
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:  # pragma: no cover - exercised only without the dependency
            raise RuntimeError(
                "huggingface_hub is not installed. Add it to the environment to use the "
                "Hugging Face provider (it is in this project's dependencies)."
            ) from exc
        if not self.token:
            raise RuntimeError(
                "No Hugging Face token. Set the HF_TOKEN Space Secret, or add a token in "
                "SYSTEM CONFIGURATION."
            )
        return InferenceClient(provider=self.routing, token=self.token, timeout=self.timeout_seconds)

    async def generate(
        self,
        *,
        prompt: str,
        output: Path,
        width: int,
        height: int,
        guide: Path | None = None,
        negative_prompt: str = "",
        seed: int | None = None,
        reference_images: list[Path] | None = None,
        mask: Path | None = None,
        metadata: dict | None = None,
    ) -> dict:
        ask_w, ask_h = fit_to_model(width, height, self.max_edge)
        guide_used = bool(self.use_guide and guide is not None and Path(guide).exists())

        # The client is synchronous and does blocking HTTP. Run it off the event loop rather than
        # reaching for AsyncInferenceClient: one call, one code path, and the generation is
        # minutes long — the thread hop costs nothing next to it.
        image = await asyncio.to_thread(
            self._generate_sync,
            prompt,
            negative_prompt,
            ask_w,
            ask_h,
            seed,
            Path(guide) if guide_used else None,
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output)
        return {
            "provider": self.name,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "seed": seed,
            "model": self.model,
            "routing": self.routing,
            "width": image.width,
            "height": image.height,
            "requestedSize": [ask_w, ask_h],
            "masterSize": [int(width), int(height)],
            "guideSent": guide_used,
            "mode": "image-to-image" if guide_used else "text-to-image",
            "metadata": metadata or {},
            "note": (
                "Generated below master size and resized by the optimise step; aspect preserved."
                if (ask_w, ask_h) != (int(width), int(height))
                else ""
            ),
        }

    def _generate_sync(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        seed: int | None,
        guide: Path | None,
    ):
        client = self._client()
        if guide is None:
            return client.text_to_image(
                prompt,
                model=self.model,
                width=width,
                height=height,
                negative_prompt=negative_prompt or None,
                seed=seed,
            )

        target_size = _target_size(width, height)
        try:
            return client.image_to_image(
                guide.read_bytes(),
                prompt=prompt,
                model=self.model,
                negative_prompt=negative_prompt or None,
                target_size=target_size,
            )
        except Exception as exc:
            # Deliberately not a fallback to text_to_image. Conditioning is the reason this path
            # was chosen; producing an unconditioned plate instead would hide the failure until
            # somebody notices the horizon is wrong in the runtime.
            raise RuntimeError(
                f"image-to-image failed on {self.model} via {self.routing}: {exc}. "
                "Not every provider/model supports it — pick an image-to-image model, or turn "
                "the guide image off to send the camera constraints as text."
            ) from exc


def _target_size(width: int, height: int):
    """The typed size object when the installed hub has one, a plain dict otherwise."""
    try:
        from huggingface_hub.inference._generated.types.image_to_image import ImageToImageTargetSize

        return ImageToImageTargetSize(width=width, height=height)
    except ImportError:
        return {"width": width, "height": height}


async def list_text_to_image_models(token: str = "", limit: int = 60) -> list[str]:
    """Models the router can actually serve, rather than a hard-coded list that goes stale.

    Filtered to text-to-image models with an inference provider behind them: the Hub holds
    hundreds of thousands of models and all but a few hundred would 404 at generation time,
    which is a worse dropdown than none.
    """

    def _fetch() -> list[str]:
        from huggingface_hub import HfApi

        api = HfApi(token=token or None)
        models = api.list_models(
            pipeline_tag="text-to-image",
            inference_provider="all",
            sort="likes",
            limit=limit,
        )
        return [m.id for m in models]

    try:
        return await asyncio.to_thread(_fetch)
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is not installed.") from exc
    except Exception as exc:  # noqa: BLE001 - the Hub's failures are many and all mean the same
        # Raised rather than returned empty, for the reason the OpenAI adapter gives: "no models"
        # and "could not ask" look identical in a dropdown.
        raise RuntimeError(f"Could not list Hugging Face models: {exc}") from exc

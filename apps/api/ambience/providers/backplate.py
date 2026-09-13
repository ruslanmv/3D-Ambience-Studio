"""Providers that generate a flat backplate rather than a 360° panorama.

The Studio's original path produces 2:1 equirectangular panoramas, which suit a skybox. A
consuming runtime that draws a *flat* background — 3D-Avatar-Chatbot assigns one to
`scene.background` and crops it — gets a poor deal from that path twice over.

It is lossy: a 30° vertical view at 16:9 is 50.9° horizontal, so a 4096-wide panorama contributes
about 580 px to an image stretched to 1920. A seventh of the source, upscaled three times.

And it is uncontrolled: a panorama generated as a 360° sky has no reason to keep the middle of
any particular view clear, so the character ends up with a tree through her head.

Generating the backplate directly fixes both. Every pixel is in the final image, and the
generator can be conditioned on the guide from `backplate_guide` — the horizon, the converging
floor and the region that must stay empty, drawn from the runtime's own camera contract.

The provider contract mirrors `PanoramaProvider` so the workflow treats the two symmetrically,
with one addition: `guide` and `negative_prompt`, because a backplate worker that ignores the
spatial condition has thrown away the reason to prefer this route.
"""

from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


class BackplateProvider(ABC):
    name: str

    @abstractmethod
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
    ) -> dict:
        """Generate a flat backplate at exactly width×height and return provenance metadata."""
        raise NotImplementedError


class MockBackplateProvider(BackplateProvider):
    """Deterministic stand-in, so the pipeline is testable with no GPU and no network.

    It draws what the guide asks for rather than an arbitrary gradient: sky above the horizon,
    ground below, and the floor lines where the contract puts them. That makes it useful beyond
    "the code ran" — the output can be dropped into the runtime to check that a backplate built
    to the contract really does line up with the avatar's feet, before any model is involved.

    Not AI generated, and the provenance says so.
    """

    name = "mock-backplate"

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
    ) -> dict:
        horizon = _horizon_from_guide(guide, height)
        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)
        for y in range(height):
            if y < horizon:
                t = y / max(1, horizon)
                draw.line([(0, y), (width, y)], fill=(int(60 + 120 * t), int(90 + 110 * t), int(150 + 80 * t)))
            else:
                t = (y - horizon) / max(1, height - horizon)
                draw.line([(0, y), (width, y)], fill=(int(120 - 50 * t), int(105 - 45 * t), int(90 - 40 * t)))
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=92)
        return {
            "provider": self.name,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
            "guide": guide.name if guide else None,
            "note": "Synthetic test backplate built to the camera contract; not AI generated.",
        }


def _horizon_from_guide(guide: Path | None, height: int) -> int:
    """Find the guide's horizon row, so the mock agrees with the contract it was handed.

    Reads the drawn image rather than taking the number as an argument, which is the point: it
    exercises the same artefact a real worker receives. If the guide ever stops carrying a
    legible horizon, the mock notices — and falls back to mid-frame with the scene still usable,
    rather than failing the run.
    """
    if guide is None or not Path(guide).exists():
        return height // 2
    try:
        with Image.open(guide) as img:
            rgb = img.convert("RGB")
            column = rgb.width // 2
            for y in range(rgb.height):
                r, g, b = rgb.getpixel((column, y))
                if r > 200 and g < 110 and b < 130:
                    return round(y * height / rgb.height)
    except (OSError, ValueError) as error:
        # A truncated or unreadable guide. Say so and carry on with mid-frame rather than
        # failing the run: a stand-in image at the wrong horizon is still a usable stand-in,
        # and swallowing this silently would make a mis-set horizon impossible to explain.
        logger.warning("could not read horizon from guide %s: %s", guide, error)
    return height // 2


class HTTPBackplateProvider(BackplateProvider):
    """Adapter for an external GPU worker.

    Expected contract:

        POST {base_url}/generate
          {prompt, negative_prompt, width, height, seed, guide_png_base64?}
        response = image bytes, or JSON with download_url

    The guide is sent inline as base64 rather than as a URL, because the worker is typically on a
    private network with no route back to the Studio — and a conditioning image that fails to
    fetch would degrade silently into an unconditioned generation that looks fine and does not
    line up.

    A worker is free to ignore `guide_png_base64`; the prompt carries the same constraints in
    words. It will produce worse results, which is the trade `docs/BACKPLATE_ROUTE.md` describes.
    """

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")

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
    ) -> dict:
        payload: dict = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "seed": seed,
        }
        if guide is not None and Path(guide).exists():
            payload["guide_png_base64"] = base64.b64encode(Path(guide).read_bytes()).decode("ascii")

        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(f"{self.base_url}/generate", json=payload)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("image/"):
                data = response.content
            else:
                body = response.json()
                url = body.get("download_url")
                if not url:
                    raise RuntimeError(f"{self.name} worker returned neither image bytes nor download_url")
                download = await client.get(url)
                download.raise_for_status()
                data = download.content

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        return {
            "provider": self.name,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
            "guideSent": "guide_png_base64" in payload,
        }

"""OpenAI's image models as a plate generator.

Separate from `OpenAICompatibleImageProvider` despite both posting to
``/v1/images/generations``, because the two are not in fact compatible. Verified against the live
API on 2026-09-13:

    response_format: "b64_json"   →  400  Unknown parameter: 'response_format'

The shared adapter sends that field on every request, so pointing it at a `gpt-image-*` model
fails before an image is ever made — and fails with a message that reads like a client bug rather
than a model mismatch. That is the whole argument for a second adapter: the wire format is the
same shape and a different dialect.

## The size rules, measured rather than assumed

The same session established, by asking the API with deliberately invalid values so that nothing
was generated and nothing was billed:

    'Width and height must both be divisible by 16'
    'The longest edge must be less than or equal to 3840'
    'Requested resolution is below the current minimum pixel budget'
    quality ∈ low | medium | high | auto

1920x1080 is therefore **not** requestable: 1080 is not a multiple of 16. Nor is 1080x1920. So
the provider asks for the nearest legal size at the same aspect — 1920x1088, 1088x1920 — and the
existing `optimize_backplate` crops the surplus away. That is the case `_centre_crop_to_ratio`
was written for: it only ever removes pixels, so the horizon stays on the row the camera contract
put it on, which is the one thing that must not move.

## Retries

At most one, and only for a timeout or a 5xx. A safety refusal, a bad request, an auth failure or
an exhausted balance will fail identically the second time and cost money to confirm it.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import httpx

from .backplate import BackplateProvider

logger = logging.getLogger(__name__)

#: Measured, not documented-from-memory. See the header.
SIZE_MULTIPLE = 16
MAX_EDGE = 3840
QUALITIES = ("low", "medium", "high", "auto")

DEFAULT_MODEL = "gpt-image-2.5-sunburst"
DEFAULT_QUALITY = "high"


def snap_size(width: int, height: int, multiple: int = SIZE_MULTIPLE, max_edge: int = MAX_EDGE) -> tuple[int, int]:
    """The nearest size the API will accept, at the same aspect ratio.

    Aspect is preserved to within one rounding step, which `validate_backplate_shape` tolerates at
    2%; a master of 1920x1080 becomes a request for 1920x1088, an aspect error of 0.7%, and the
    optimise step takes the eight surplus rows off the top and bottom.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    scale = min(1.0, max_edge / max(width, height))
    out_w = max(multiple, round(width * scale / multiple) * multiple)
    out_h = max(multiple, round(height * scale / multiple) * multiple)
    return out_w, out_h


class OpenAIPlateProvider(BackplateProvider):
    """POST /v1/images/generations against OpenAI's image models."""

    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        *,
        model: str = "",
        quality: str = "",
        base_url: str = "https://api.openai.com",
        timeout_seconds: float = 300.0,
    ):
        # Environment first and never a literal: the key reaches this process from the shell or a
        # .env the repository ignores, and nothing writes it back out — not the provenance, not
        # the manifest, not a log line.
        self.api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.model = (model or os.environ.get("OPENAI_IMAGE_MODEL") or DEFAULT_MODEL).strip()
        quality = (quality or os.environ.get("OPENAI_IMAGE_QUALITY") or DEFAULT_QUALITY).strip()
        self.quality = quality if quality in QUALITIES else DEFAULT_QUALITY
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def require_key(self) -> None:
        """Fail before doing any work, with the fix in the message."""
        if not self.api_key:
            raise RuntimeError(
                "No OPENAI_API_KEY. Export it, or put it in .env (which this repository ignores):\n"
                "    OPENAI_API_KEY=sk-...\n"
                "It is never read from a manifest, a project file or the settings store."
            )

    def plan(self, width: int, height: int) -> dict:
        """What a live call would send. The dry run prints this; no request is made."""
        ask_w, ask_h = snap_size(width, height)
        return {
            "provider": self.name,
            "model": self.model,
            "quality": self.quality,
            "endpoint": f"{self.base_url}/v1/images/generations",
            "requestedSize": f"{ask_w}x{ask_h}",
            "masterSize": f"{int(width)}x{int(height)}",
            "hasKey": bool(self.api_key),
        }

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
        self.require_key()
        ask_w, ask_h = snap_size(width, height)

        # No negative-prompt field on this endpoint, so the exclusions ride in the prompt. Crude,
        # and better than dropping the one rule that matters most here — that the plate must not
        # contain a person, when a real one will be standing in front of it.
        text = prompt
        if negative_prompt:
            text = f"{prompt} Do not include: {negative_prompt}."

        payload = {
            "model": self.model,
            "prompt": text[:32000],
            "n": 1,
            "size": f"{ask_w}x{ask_h}",
            "quality": self.quality,
        }

        data = await self._post_with_one_retry(payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)

        return {
            "provider": self.name,
            "model": self.model,
            "quality": self.quality,
            "endpoint": f"{self.base_url}/v1/images/generations",
            "prompt": text,
            "negativePrompt": negative_prompt,
            "requestedSize": payload["size"],
            "masterSize": f"{int(width)}x{int(height)}",
            "bytes": len(data),
            "seed": seed,
            # Honest, and the line that explains a plate whose horizon is off: this endpoint takes
            # no reference image, so the camera contract travelled as words.
            "guideSent": False,
            "guideNote": (
                "The generations endpoint accepts no reference image; the camera geometry was "
                "compiled into the prompt as text."
            ),
            "metadata": metadata or {},
        }

    async def _post_with_one_retry(self, payload: dict) -> bytes:
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._post(payload)
            except _Transient as exc:
                if attempt >= 2:
                    raise RuntimeError(f"{self.name}: {exc} (retried once)") from exc
                logger.warning("openai: transient failure, retrying once: %s", exc)

    async def _post(self, payload: dict) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/v1/images/generations", json=payload, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise _Transient(f"timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise _Transient(f"connection failed: {exc}") from exc

        if response.status_code >= 500:
            raise _Transient(f"{response.status_code} — {response.text[:300]}")
        if response.status_code >= 400:
            # Deliberately terminal. A refusal, a malformed request, a bad key and an empty
            # balance all fail the same way twice, and confirming that costs money.
            raise RuntimeError(f"{self.name}: {response.status_code} — {_message(response)}")

        body = response.json()
        items = body.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise RuntimeError(f"{self.name}: response carried no image data")
        return base64.b64decode(items[0]["b64_json"])


class _Transient(Exception):
    """A failure worth exactly one more attempt."""


def _message(response: httpx.Response) -> str:
    try:
        return str((response.json().get("error") or {}).get("message") or response.text[:300])
    except ValueError:
        return response.text[:300]

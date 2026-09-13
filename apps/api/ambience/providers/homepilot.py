"""Adapter for HomePilot as the image-inference layer.

The architecture this fits: the Studio owns scene specification, camera calibration, validation
and publication; HomePilot owns model management and inference, behind one interface, so a plate
can come from a cloud image API or a local FLUX/SDXL ComfyUI graph without the Studio knowing
which produced the pixels.

Unlike the direct worker adapter in `backplate.py`, this one is **asynchronous**: submit a job,
poll until it finishes, then download. Image generation takes tens of seconds to minutes, and a
request held open that long dies to a proxy timeout somewhere in the middle with no way to
recover the result.

## This is written against a stated contract, not a verified one

The endpoints and field names below come from the integration proposal, not from reading a
running HomePilot. Two consequences worth stating rather than discovering:

* the paths and keys are **configurable**, so a mismatch is a settings change rather than a code
  change;
* `model` is passed through untouched and this module hard-codes no model identifiers. Model
  names change faster than adapters do, and an adapter that shipped a list of them would be
  wrong by the time somebody read it.

Expected contract:

    POST {base}/v1/images/generate  {provider, model, prompt, width, height, ...}
      → {job_id, status}
    GET  {base}/v1/jobs/{job_id}
      → {status: queued|running|succeeded|failed, assets: [{url, width, height}], generation: {...}}
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx

from .backplate import BackplateProvider

#: Terminal states. Anything else is treated as still running, which is the forgiving choice: a
#: worker that invents a new in-progress name should slow us down, not fail the job.
_SUCCESS = {"succeeded", "success", "completed", "complete"}
_FAILURE = {"failed", "error", "cancelled", "canceled"}


class HomePilotPlateProvider(BackplateProvider):
    """Submit a plate job to HomePilot and wait for it.

    `provider` and `model` are HomePilot's own routing keys — "openai" and an image-model id, or
    a local backend and a ComfyUI graph. The Studio passes them through and forms no opinion.
    """

    def __init__(
        self,
        base_url: str,
        *,
        provider: str = "auto",
        model: str = "",
        name: str = "homepilot",
        poll_seconds: float = 3.0,
        timeout_seconds: float = 900.0,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.model = model
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

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
        payload: dict = {
            "provider": self.provider,
            "model": self.model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "seed": seed,
            # Lets HomePilot route or log by intent without parsing the prompt.
            "purpose": "ambience_plate",
            "metadata": dict(metadata or {}),
        }

        # The guide travels as a reference image because that is the field the contract defines.
        # Whether a backend uses it as a ControlNet hint or merely as a style reference is
        # HomePilot's business; the provenance below records that it was sent either way, which
        # is what matters when a plate comes back not lining up.
        references: list[str] = []
        if guide is not None and Path(guide).exists():
            references.append(_b64(guide))
            payload["metadata"]["guide"] = "camera-calibration"
        for reference in reference_images or []:
            if Path(reference).exists():
                references.append(_b64(reference))
        if references:
            payload["reference_images"] = references
        if mask is not None and Path(mask).exists():
            payload["mask"] = _b64(mask)

        async with httpx.AsyncClient(timeout=60) as client:
            submit = await client.post(f"{self.base_url}/v1/images/generate", json=payload)
            submit.raise_for_status()
            accepted = submit.json()
            job_id = accepted.get("job_id") or accepted.get("id")
            if not job_id:
                raise RuntimeError(f"{self.name} accepted the request without returning a job id")

            job = await self._await_job(client, job_id)
            assets = job.get("assets") or []
            if not assets:
                raise RuntimeError(f"{self.name} job {job_id} succeeded but returned no assets")

            url = assets[0].get("url")
            if not url:
                raise RuntimeError(f"{self.name} job {job_id} returned an asset with no url")
            # A relative /media/... path is the documented shape, so resolve against the base.
            if url.startswith("/"):
                url = f"{self.base_url}{url}"
            download = await client.get(url)
            download.raise_for_status()
            data = download.content

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        generation = job.get("generation") or {}
        return {
            "provider": self.name,
            "routedProvider": generation.get("provider", self.provider),
            "model": generation.get("model", self.model),
            "jobId": job_id,
            "prompt": prompt,
            "negativePrompt": negative_prompt,
            "seed": seed,
            "width": width,
            "height": height,
            "guideSent": guide is not None and Path(guide).exists(),
            "referenceImages": len(references),
        }

    async def _await_job(self, client: httpx.AsyncClient, job_id: str) -> dict:
        """Poll until the job finishes, fails, or outlives its budget.

        The deadline is measured against a monotonic clock rather than counting iterations: a
        slow worker and a slow network produce different iteration counts for the same wall
        time, and "give up after fifteen minutes" is the intent.
        """
        deadline = asyncio.get_event_loop().time() + self.timeout_seconds
        while True:
            response = await client.get(f"{self.base_url}/v1/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            status = str(job.get("status", "")).lower()
            if status in _SUCCESS:
                return job
            if status in _FAILURE:
                raise RuntimeError(f"{self.name} job {job_id} {status}: {job.get('error', 'no reason given')}")
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(
                    f"{self.name} job {job_id} still {status or 'unknown'} after {self.timeout_seconds:.0f}s"
                )
            await asyncio.sleep(self.poll_seconds)


def _b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")

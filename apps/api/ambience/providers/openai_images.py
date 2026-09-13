"""One adapter for every provider that speaks OpenAI's image API.

OpenAI, OllaBridge cloud and OllaBridge local all accept the same request at
``POST {base}/v1/images/generations`` and return the same ``{data: [{b64_json | url}]}``. They
differ in base URL and credential and in nothing else that matters here, so they share an
adapter rather than having three that drift apart.

That is the same bet 3D-Avatar-Chatbot makes for chat: it drives OllaBridge through its
OpenAI-compatible chat endpoint instead of writing a bridge-specific client.

## Three ways to authenticate, because OllaBridge has three

``apikey``       ``Authorization: Bearer <key>`` — OpenAI's only mode, and OllaBridge's default.
``pairing``      the same header carrying a device token obtained from ``POST {base}/pair``.
``local-trust``  no header at all. A bridge on localhost can be configured to trust its own
                 machine, and sending an empty Bearer there is worse than sending nothing: some
                 stacks reject the malformed header rather than ignoring it.

## What this route cannot do

It takes a prompt and a size. **No reference image** — OllaBridge's ``ImageGenerationRequest`` has
no field for one, and neither does the OpenAI generations endpoint (its *edits* endpoint does,
which is a different call with different semantics).

So on this route the camera guide travels as *text* only: the horizon percentage, the foot
anchor, the keep-clear band. That is weaker than conditioning on the guide image and it is
stated rather than hidden, because a plate that misses the horizon on this route is the expected
outcome, not a bug to chase. `supportsGuideImage` on the provider spec is False for exactly this
reason, and the wizard says so.
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx

from .backplate import BackplateProvider


class OpenAICompatibleImageProvider(BackplateProvider):
    """POST /v1/images/generations against any base URL that implements it."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        auth_mode: str = "apikey",
        model: str = "",
        name: str = "openai-compatible",
        timeout_seconds: float = 300.0,
    ):
        self.name = name
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = (api_key or "").strip()
        self.auth_mode = auth_mode
        self.model = model
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        # local-trust deliberately sends nothing: an empty Bearer is rejected by some stacks
        # rather than ignored, which surfaces as a confusing 401 against a bridge that was
        # configured not to need one.
        if self.auth_mode != "local-trust" and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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
        if not self.base_url:
            raise RuntimeError(f"{self.name}: no base URL configured")

        # The endpoint has no negative-prompt field, so it is folded into the prompt as an
        # exclusion clause. Crude, and better than dropping the two rules that stop a figure
        # being painted into a plate that already has a real one standing in front of it.
        text = prompt
        if negative_prompt:
            text = f"{prompt}. Do not include: {negative_prompt}"

        payload = {
            "model": self.model or "ollabridge:image",
            "prompt": text[:4000],
            "n": 1,
            "size": f"{width}x{height}",
            "response_format": "b64_json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/v1/images/generations", json=payload, headers=self._headers()
            )
            if response.status_code >= 400:
                # Pass the upstream message through. "402 free credit exhausted" and
                # "400 Hugging Face token not configured" are both actionable, and a generic
                # "generation failed" would throw away the only useful part.
                raise RuntimeError(f"{self.name}: {response.status_code} — {response.text[:400]}")
            body = response.json()

            items = body.get("data") or []
            if not items:
                raise RuntimeError(f"{self.name}: response carried no image data")
            item = items[0]

            if item.get("b64_json"):
                data = base64.b64decode(item["b64_json"])
            elif item.get("url"):
                download = await client.get(item["url"])
                download.raise_for_status()
                data = download.content
            else:
                raise RuntimeError(f"{self.name}: image had neither b64_json nor url")

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        return {
            "provider": self.name,
            "baseUrl": self.base_url,
            "authMode": self.auth_mode,
            "model": payload["model"],
            "prompt": text,
            "requestedSize": payload["size"],
            "seed": seed,
            # Recorded because it is the honest limitation of this route, and because a plate
            # whose horizon is off is explained by this line.
            "guideSent": False,
            "guideNote": "This endpoint accepts no reference image; the camera constraints were sent as text only.",
        }


async def pair_with_bridge(base_url: str, code: str, label: str = "3d-ambience-studio") -> dict:
    """Exchange a pairing code for a device token.

    Mirrors 3D-Avatar-Chatbot's client exactly, including the code normalisation — people read
    codes off a screen and type them with dashes, spaces and in lower case, and a pairing that
    fails on punctuation is a support ticket.
    """
    base = (base_url or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "No base URL configured."}
    clean = str(code or "").strip().upper().replace("-", "").replace(" ", "")
    if not clean:
        return {"ok": False, "error": "No pairing code given."}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{base}/pair", json={"code": clean, "label": label})
            text = response.text
            if response.status_code >= 400:
                return {"ok": False, "error": f"Pairing failed: {response.status_code} — {text[:300]}"}
            body = response.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Cannot reach OllaBridge at {base}: {exc}"}
    except ValueError:
        return {"ok": False, "error": "OllaBridge returned a non-JSON response to /pair."}

    if body.get("ok") and body.get("token"):
        return {"ok": True, "token": body["token"], "device_id": body.get("device_id")}
    return {"ok": False, "error": body.get("error") or f"Unexpected response: {body}"}


async def list_models(base_url: str, api_key: str = "", auth_mode: str = "apikey") -> list[str]:
    """GET /v1/models, for the wizard's model dropdown.

    Returns ids only. A failure raises rather than returning an empty list: "no models" and
    "could not ask" look identical in a dropdown and lead somebody to conclude their account is
    empty when the base URL is simply wrong.
    """
    base = (base_url or "").rstrip("/")
    if not base:
        raise RuntimeError("No base URL configured.")
    headers = {}
    if auth_mode != "local-trust" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base}/v1/models", headers=headers)
        if response.status_code >= 400:
            raise RuntimeError(f"{response.status_code} — {response.text[:300]}")
        body = response.json()
    entries = body.get("data") if isinstance(body, dict) else body
    ids = []
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(str(entry["id"]))
        elif isinstance(entry, str):
            ids.append(entry)
    return ids

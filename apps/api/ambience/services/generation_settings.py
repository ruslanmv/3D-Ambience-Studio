"""Where the image generator is configured, and how that survives a restart.

The Studio's own settings, deliberately separate from a project: a project is "a moonlit
terrace", and this is "who draws it". Changing the provider must not rewrite ten projects, and
publishing a project must not pin a provider.

## Why this mirrors the avatar app's shape

3D-Avatar-Chatbot stores provider, auth mode, key, pairing token, base URL and model in one
settings object, and its Settings panel is a view of that object. The Studio does the same, with
the same field names where they mean the same thing, so the two are legible side by side and a
person who has configured one can configure the other without relearning it.

## Secrets

API keys and pairing tokens live in this file on disk, in the Studio's data directory. That is
appropriate for a single-operator desk tool and **not** appropriate for a shared deployment: the
file has no encryption and the API returns the settings to any caller who can reach it. `redact`
exists so the read endpoint never hands a key back over HTTP; the value is only ever written.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..config import settings as app_settings
from ..providers.huggingface import ROUTING as HF_ROUTING
from ..providers.huggingface import SUGGESTED_MODELS as HF_SUGGESTED_MODELS

#: Every provider the Studio can draw with. `kind` is what actually varies: three of these speak
#: the same OpenAI-compatible wire format and differ only in base URL and credential, which is
#: why one adapter serves them.
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "huggingface",
        "label": "Hugging Face",
        "icon": "🤗",
        "kind": "huggingface",
        "defaultBaseUrl": "https://router.huggingface.co",
        "defaultModel": "black-forest-labs/FLUX.1-schnell",
        "auth": ["apikey"],
        "envVar": "HF_TOKEN",
        "supportsGuideImage": True,
        # Rendered by the panel as the routing radio group and the model shortlist. Taken from the
        # adapter rather than restated here, so the two cannot disagree about what routing values
        # are legal.
        "routing": HF_ROUTING,
        "suggestedModels": HF_SUGGESTED_MODELS,
        "notes": (
            "Inference Providers: one token routed to fal.ai, Replicate, Together, Nscale or HF's "
            "own stack. Open-weight models, no GPU to run. The guide can be sent as a real spatial "
            "condition, but only on an image-to-image model."
        ),
    },
    {
        "id": "openai",
        "envVar": "OPENAI_API_KEY",
        "label": "OpenAI",
        "icon": "🤖",
        # Its own kind, not "openai-compatible". The gpt-image family rejects `response_format`,
        # which the shared adapter always sends, so this card was a 400 waiting to happen.
        "kind": "openai-plate",
        "defaultBaseUrl": "https://api.openai.com",
        "defaultModel": "gpt-image-2.5-sunburst",
        "auth": ["apikey"],
        "supportsGuideImage": False,
        "notes": (
            "Direct to OpenAI's image API. Sizes must be multiples of 16 with the longest edge at "
            "most 3840; the adapter snaps and the optimise step crops. The generations endpoint "
            "takes no reference image, so the camera guide travels as text."
        ),
    },
    {
        "id": "gemini",
        "envVar": "GEMINI_API_KEY",
        "label": "Gemini",
        "icon": "💎",
        "kind": "gemini",
        "defaultBaseUrl": "https://generativelanguage.googleapis.com",
        "auth": ["apikey"],
        "supportsGuideImage": True,
        "notes": "Google's own wire format, not OpenAI-compatible — a separate adapter.",
    },
    {
        "id": "ollabridge",
        "envVar": "OLLABRIDGE_TOKEN",
        "label": "OllaBridge",
        "icon": "🌉",
        "kind": "openai-compatible",
        "defaultBaseUrl": "https://app.ollabridge.com",
        "auth": ["pairing", "apikey", "local-trust"],
        "supportsGuideImage": False,
        "notes": "Cloud gateway. POST /v1/images/generations, OpenAI-compatible. Takes no reference image, so the guide travels as text only.",
    },
    {
        "id": "ollabridge-local",
        "envVar": "OLLABRIDGE_LOCAL_TOKEN",
        "label": "OllaBridge Local",
        "icon": "🏠",
        "kind": "openai-compatible",
        "defaultBaseUrl": "http://localhost:11435",
        "auth": ["local-trust", "pairing", "apikey"],
        "supportsGuideImage": False,
        "notes": "The same gateway on your own machine, routing to a local ComfyUI graph.",
    },
    {
        "id": "homepilot",
        "envVar": "HOMEPILOT_TOKEN",
        "label": "HomePilot",
        "icon": "🚀",
        "kind": "homepilot",
        "defaultBaseUrl": "http://localhost:8105",
        "auth": ["apikey", "local-trust"],
        "supportsGuideImage": True,
        "notes": "Asynchronous job API in front of cloud and local models. Accepts the guide as a reference image.",
    },
    {
        "id": "mock-backplate",
        "envVar": "",
        "label": "Mock",
        "icon": "○",
        "kind": "mock",
        "defaultBaseUrl": "",
        "auth": ["local-trust"],
        "supportsGuideImage": True,
        "notes": "Draws sky and ground to the camera contract's horizon. No network, no GPU, not AI generated.",
    },
]

PROVIDER_IDS = [p["id"] for p in PROVIDERS]

#: Field names shared with the avatar app, so the two panels read the same.
DEFAULTS: dict[str, Any] = {
    "provider": "mock-backplate",
    "auth_mode": "local-trust",
    "api_key": "",
    "pair_token": "",
    "device_id": "",
    "base_url": "",
    "model": "",
    # Hugging Face routes one request to several inference companies; "auto" lets it choose and
    # fail over. Sending the guide as an actual image is off by default because only some
    # provider/model pairs implement image-to-image — see providers/huggingface.py.
    "hf_routing": "auto",
    "hf_use_guide": False,
}

#: Never returned over HTTP. Written only.
SECRET_FIELDS = ("api_key", "pair_token")


def provider_spec(provider_id: str) -> dict[str, Any]:
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p
    raise KeyError(f"Unknown image provider: {provider_id}")


# ── The deployment layer ─────────────────────────────────────────────────────────────────────
#
# Everything above is a desk tool's settings: one operator, one machine, a JSON file. A Hugging
# Face Space is neither — it is a shared, usually public URL where every visitor shares one
# configuration and one billing account. Two things follow, and both are handled here rather than
# in the API so the CLI and the tests see the same rules.
#
# Credentials come from the environment first. A Space Secret is the deployment's credential:
# it never passes through the browser, never lands in the settings file, and cannot be read back
# out by a visitor. The stored key stays as the desk-install path.
#
# And in a shared deployment the settings are read-only. Otherwise any visitor could point the
# backend at an expensive model and spend the deployer's credits, or repoint a provider's base
# URL at a host of their choosing — a credential-exfiltration route, not merely a billing one.


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_hosted_space() -> bool:
    """True inside a Hugging Face Space, which sets SPACE_ID for every container it runs."""
    return bool(_env("SPACE_ID"))


def deployment() -> dict[str, Any]:
    """Whether this instance is shared, and therefore whether its settings are writable.

    AMBIENCE_SETTINGS_LOCKED decides it when set — "0" or "false" unlocks a Space for someone
    running a private one who wants the panel back. Otherwise a Space is locked and a desk
    install is not, which is the safe default in both directions.
    """
    override = _env("AMBIENCE_SETTINGS_LOCKED").lower()
    if override in {"0", "false", "no"}:
        return {"locked": False, "reason": "", "space": is_hosted_space()}
    if override in {"1", "true", "yes"}:
        return {
            "locked": True,
            "reason": "This deployment's image generation is configured by its operator (AMBIENCE_SETTINGS_LOCKED).",
            "space": is_hosted_space(),
        }
    if is_hosted_space():
        return {
            "locked": True,
            "reason": (
                "Running as a hosted Space, where everyone shares one configuration and one "
                "billing account. The operator sets the provider and its credential as Space "
                "secrets and variables."
            ),
            "space": True,
        }
    return {"locked": False, "reason": "", "space": False}


def credential_for(data: dict[str, Any]) -> tuple[str, str]:
    """The credential to authenticate with, and where it came from.

    Environment first, then the stored field for the mode in use. Which stored field that is —
    `pair_token` in pairing mode, `api_key` otherwise — is the only difference between the two
    modes, and no adapter should have to know it.
    """
    try:
        spec = provider_spec(data.get("provider", ""))
    except KeyError:
        spec = {}
    from_env = _env(spec.get("envVar", "")) if spec.get("envVar") else ""
    if from_env:
        return from_env, "environment"
    stored = data.get("pair_token") if data.get("auth_mode") == "pairing" else data.get("api_key")
    stored = str(stored or "").strip()
    return stored, "stored" if stored else "none"


def _deployment_overrides() -> dict[str, Any]:
    """What the operator has insisted on, which the panel cannot overrule.

    Separate from the defaults below: these win over anything stored, because they are how a
    locked deployment is configured at all.
    """
    out: dict[str, Any] = {}
    if _env("AMBIENCE_IMAGE_PROVIDER") in PROVIDER_IDS:
        out["provider"] = _env("AMBIENCE_IMAGE_PROVIDER")
    if _env("AMBIENCE_IMAGE_MODEL"):
        out["model"] = _env("AMBIENCE_IMAGE_MODEL")
    if _env("AMBIENCE_HF_ROUTING"):
        out["hf_routing"] = _env("AMBIENCE_HF_ROUTING")
    if _env("AMBIENCE_HF_USE_GUIDE").lower() in {"1", "true", "yes"}:
        out["hf_use_guide"] = True
    return out


def _deployment_defaults() -> dict[str, Any]:
    """What to start from when nothing is stored yet.

    A Space with an HF token should draw with Hugging Face out of the box rather than with the
    mock: the credential is already there, the models are open-weight, and asking someone to
    configure a provider on a locked panel would be a dead end. It is only a default — a stored
    choice still wins, as does an explicit override.
    """
    if _env("HF_TOKEN") or _env("HUGGING_FACE_HUB_TOKEN") or is_hosted_space():
        return {"provider": "huggingface", "auth_mode": "apikey"}
    return {}


def _path() -> Path:
    return app_settings.data_dir / "generation-settings.json"


def load() -> dict[str, Any]:
    """Read the stored settings, filling anything absent from DEFAULTS.

    Merged rather than replaced so that a settings file written by an older build keeps working
    when a field is added — the alternative is a KeyError on somebody's machine months later.
    """
    data = dict(DEFAULTS)
    data.update(_deployment_defaults())
    path = _path()
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except (OSError, json.JSONDecodeError):
            # A corrupt settings file should not stop the Studio starting. Defaults are a
            # working configuration; the mock provider needs nothing.
            pass
    data.update(_deployment_overrides())
    try:
        spec = provider_spec(data["provider"])
    except KeyError:
        spec = {}
    if not data.get("base_url"):
        data["base_url"] = spec.get("defaultBaseUrl", "")
    if not data.get("model"):
        # A provider with no usable model is a generate button that fails; Hugging Face needs one
        # named. Derived on read so a deployment that has never been configured — no settings
        # file at all — still has something to generate with.
        data["model"] = spec.get("defaultModel", "")
    return data


def save(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial update and persist it.

    Partial on purpose: the UI sends only what changed, so pairing does not have to resend the
    API key and switching model does not have to resend the base URL. An empty string clears a
    field; omitting it leaves it alone. Without that distinction a form that does not render the
    key field would wipe the key on every save.
    """
    data = load()
    for key, value in (patch or {}).items():
        if key in DEFAULTS:
            data[key] = value
    if "provider" in (patch or {}):
        try:
            spec = provider_spec(data["provider"])
        except KeyError:
            spec = None
        if spec:
            if not (patch or {}).get("base_url"):
                # A provider change carries its own default base URL unless one was given, so
                # switching from OllaBridge to OpenAI does not silently keep pointing at the
                # bridge.
                data["base_url"] = spec["defaultBaseUrl"]
            if not (patch or {}).get("model"):
                # And its own model. A model id is provider-specific — "gpt-image-1" means
                # nothing to Hugging Face's router and a Hub repo id means nothing to OpenAI —
                # so carrying one across a switch guarantees a failing generate. Empty is then
                # filled from the new provider's default by load().
                data["model"] = spec.get("defaultModel", "")
            if not (patch or {}).get("auth_mode"):
                # And its own preferred auth mode — always, not only when the carried-over one
                # is invalid.
                #
                # Two reasons. The dangerous case: OllaBridge/pairing → OpenAI, which offers
                # only apikey, would leave the panel in pairing mode with no pairing box and no
                # key field, so there is no way to enter a credential at all.
                #
                # The merely-wrong case: a carried-over mode that happens to be valid is
                # coincidence rather than intent. Nobody chose local-trust *for OllaBridge*;
                # they chose it for the provider before. Picking OllaBridge should give its
                # normal setup — Device Pairing, as in 3D-Avatar-Chatbot — and the dropdown is
                # right there to change.
                #
                # `auth` is ordered by preference, not alphabetically, which is what makes
                # [0] meaningful.
                data["auth_mode"] = spec["auth"][0]
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def redact(data: dict[str, Any]) -> dict[str, Any]:
    """The shape the API returns: secrets replaced by whether one is set.

    The panel needs to show "a key is stored" without the key crossing the wire again, exactly
    as a password field does.
    """
    out = {k: v for k, v in data.items() if k not in SECRET_FIELDS}
    for field in SECRET_FIELDS:
        out[f"has_{field}"] = bool(str(data.get(field) or "").strip())
    credential, source = credential_for(data)
    out["has_credential"] = bool(credential)
    # Where it came from, never what it is. "environment" is what lets the panel say "configured
    # by deployment" instead of showing an empty key field over a working configuration — which
    # otherwise reads as broken and invites someone to paste a second key.
    out["credential_source"] = source
    try:
        out["env_var"] = provider_spec(data.get("provider", "")).get("envVar", "")
    except KeyError:
        out["env_var"] = ""
    state = deployment()
    out["locked"] = state["locked"]
    out["lock_reason"] = state["reason"]
    out["hosted_space"] = state["space"]
    return out

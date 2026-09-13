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
from pathlib import Path
from typing import Any

from ..config import settings as app_settings

#: Every provider the Studio can draw with. `kind` is what actually varies: three of these speak
#: the same OpenAI-compatible wire format and differ only in base URL and credential, which is
#: why one adapter serves them.
PROVIDERS: list[dict[str, Any]] = [
    {
        "id": "openai",
        "label": "OpenAI",
        "icon": "🤖",
        "kind": "openai-compatible",
        "defaultBaseUrl": "https://api.openai.com",
        "auth": ["apikey"],
        "supportsGuideImage": True,
        "notes": "Direct to OpenAI's image API. Model ids are configuration — set whichever your account has.",
    },
    {
        "id": "gemini",
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
}

#: Never returned over HTTP. Written only.
SECRET_FIELDS = ("api_key", "pair_token")


def provider_spec(provider_id: str) -> dict[str, Any]:
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p
    raise KeyError(f"Unknown image provider: {provider_id}")


def _path() -> Path:
    return app_settings.data_dir / "generation-settings.json"


def load() -> dict[str, Any]:
    """Read the stored settings, filling anything absent from DEFAULTS.

    Merged rather than replaced so that a settings file written by an older build keeps working
    when a field is added — the alternative is a KeyError on somebody's machine months later.
    """
    data = dict(DEFAULTS)
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
    if not data.get("base_url"):
        try:
            data["base_url"] = provider_spec(data["provider"])["defaultBaseUrl"]
        except KeyError:
            data["base_url"] = ""
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
    return out

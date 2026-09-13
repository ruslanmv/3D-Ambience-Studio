from ..config import settings
from .backplate import HTTPBackplateProvider, MockBackplateProvider
from .homepilot import HomePilotPlateProvider
from .http import HTTPPanoramaProvider
from .mock import MockPanoramaProvider
from .openai_images import OpenAICompatibleImageProvider


def get_panorama_provider(name: str):
    providers = {
        "mock": MockPanoramaProvider(),
        "panfusion": HTTPPanoramaProvider("panfusion", settings.panfusion_url),
        "text2vr": HTTPPanoramaProvider("text2vr", settings.text2vr_url),
    }
    if name not in providers:
        raise KeyError(f"Unknown panorama provider: {name}")
    return providers[name]


def provider_summary() -> list[dict]:
    return [
        {"id": "mock", "enabled": True, "role": "test", "notes": "Built-in deterministic panorama generator."},
        {"id": "panfusion", "enabled": True, "role": "panorama", "notes": "External HTTP worker adapter; recommended first open-source candidate after license/model audit."},
        {"id": "text2vr", "enabled": True, "role": "reference-adapter", "notes": "Optional external adapter. Do not assume bundled Text2VR dependencies are uniformly MIT."},
    ]


def get_backplate_provider(name: str):
    """Backplate providers are kept in their own registry, not merged into the panorama one.

    The two have different signatures — a backplate takes a size and a conditioning guide — so a
    single lookup would hand callers an object that may or may not accept the arguments they are
    about to pass. Two registries make the mismatch a KeyError at the call site instead.
    """
    providers = {
        "mock-backplate": MockBackplateProvider(),
        "backplate": HTTPBackplateProvider("backplate", settings.backplate_url),
        # HomePilot as the inference layer: one interface in front of cloud image APIs and local
        # ComfyUI graphs alike. provider/model are its routing keys and are configuration, not
        # constants — model names change faster than adapters do.
        "homepilot": HomePilotPlateProvider(
            settings.homepilot_url,
            provider=settings.homepilot_image_provider,
            model=settings.homepilot_image_model,
        ),
    }
    if name not in providers:
        raise KeyError(f"Unknown backplate provider: {name}")
    return providers[name]


def backplate_provider_summary() -> list[dict]:
    return [
        {
            "id": "mock-backplate",
            "enabled": True,
            "role": "test",
            "notes": "Draws sky and ground to the camera contract's horizon. Not AI generated.",
        },
        {
            "id": "backplate",
            "enabled": True,
            "role": "backplate",
            "notes": "External HTTP worker. Sends the guide image as a spatial condition; a worker may ignore it.",
        },
        {
            "id": "homepilot",
            "enabled": True,
            "role": "inference-layer",
            "notes": (
                "Asynchronous job API in front of cloud and local image models. "
                "Written against the stated contract; endpoints and model ids are configurable."
            ),
        },
    ]


def provider_from_settings(config: dict):
    """Build the configured image provider from the stored settings.

    One place that turns "what the operator chose in the panel" into an object, so the wizard,
    the test-connection endpoint and the generate endpoint cannot disagree about what
    `provider: "ollabridge"` means.
    """
    from ..services.generation_settings import provider_spec

    spec = provider_spec(config["provider"])
    kind = spec["kind"]
    auth_mode = config.get("auth_mode", "apikey")
    # Pairing and API-key modes both end up as a Bearer token; which field holds it is the
    # only difference, and the adapter should not have to know that.
    credential = config.get("pair_token") if auth_mode == "pairing" else config.get("api_key")

    if kind == "mock":
        return MockBackplateProvider()
    if kind == "openai-compatible":
        return OpenAICompatibleImageProvider(
            config.get("base_url") or spec["defaultBaseUrl"],
            api_key=credential or "",
            auth_mode=auth_mode,
            model=config.get("model", ""),
            name=config["provider"],
        )
    if kind == "homepilot":
        return HomePilotPlateProvider(
            config.get("base_url") or spec["defaultBaseUrl"],
            model=config.get("model", ""),
            name="homepilot",
        )
    raise KeyError(f"No adapter for provider kind {kind!r}")

from ..config import settings
from .backplate import HTTPBackplateProvider, MockBackplateProvider
from .http import HTTPPanoramaProvider
from .mock import MockPanoramaProvider


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
    ]

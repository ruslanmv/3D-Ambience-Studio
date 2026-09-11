from .mock import MockPanoramaProvider
from .http import HTTPPanoramaProvider
from ..config import settings


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

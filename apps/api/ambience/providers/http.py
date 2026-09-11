from pathlib import Path
import httpx
from .base import PanoramaProvider


class HTTPPanoramaProvider(PanoramaProvider):
    """Adapter for an external GPU worker.

    Expected contract:
      POST {base_url}/generate {prompt, seed}
      response body = panorama bytes OR JSON with download_url.

    Upstream-specific workers should normalize their own API to this contract.
    """

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")

    async def generate(self, *, prompt: str, output: Path, seed: int | None = None) -> dict:
        async with httpx.AsyncClient(timeout=900) as client:
            response = await client.post(f"{self.base_url}/generate", json={"prompt": prompt, "seed": seed})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("image/"):
                data = response.content
            else:
                payload = response.json()
                url = payload.get("download_url")
                if not url:
                    raise RuntimeError(f"{self.name} worker did not return image bytes or download_url")
                download = await client.get(url)
                download.raise_for_status()
                data = download.content
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        return {"provider": self.name, "prompt": prompt, "seed": seed}

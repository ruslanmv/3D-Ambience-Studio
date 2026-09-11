from pathlib import Path
from PIL import Image
from .base import PanoramaProvider


class MockPanoramaProvider(PanoramaProvider):
    name = "mock"

    async def generate(self, *, prompt: str, output: Path, seed: int | None = None) -> dict:
        width, height = 2048, 1024
        image = Image.new("RGB", (width, height))
        px = image.load()
        for y in range(height):
            t = y / max(1, height - 1)
            for x in range(width):
                u = x / max(1, width - 1)
                px[x, y] = (int(40 + 170 * (1 - t)), int(80 + 90 * (1 - abs(u - 0.5) * 2)), int(120 + 100 * t))
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, quality=92)
        return {"provider": self.name, "prompt": prompt, "seed": seed, "note": "Synthetic test panorama; not AI generated."}

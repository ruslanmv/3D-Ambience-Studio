from abc import ABC, abstractmethod
from pathlib import Path


class PanoramaProvider(ABC):
    name: str

    @abstractmethod
    async def generate(self, *, prompt: str, output: Path, seed: int | None = None) -> dict:
        """Generate a 2:1 equirectangular panorama and return provenance metadata."""
        raise NotImplementedError

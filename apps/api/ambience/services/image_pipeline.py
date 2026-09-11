from pathlib import Path
from PIL import Image

TARGETS = {
    "desktop": (4096, 2048, 88),
    "quest": (2048, 1024, 82),
    "preview": (768, 384, 80),
}


def inspect_panorama(path: Path) -> dict:
    with Image.open(path) as image:
        width, height = image.size
    ratio = width / height if height else 0
    return {"width": width, "height": height, "ratio": ratio, "bytes": path.stat().st_size}


def validate_panorama_shape(path: Path, tolerance: float = 0.01) -> list[str]:
    info = inspect_panorama(path)
    errors = []
    if abs(info["ratio"] - 2.0) > tolerance:
        errors.append(f"Panorama must be 2:1 equirectangular; got {info['width']}x{info['height']} ({info['ratio']:.3f}:1).")
    if info["width"] < 1024 or info["height"] < 512:
        errors.append("Panorama is below the recommended minimum 1024x512 source resolution.")
    return errors


def _fit_no_upscale(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    tw, th = target
    scale = min(1.0, tw / image.width, th / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    if size == image.size:
        return image.copy()
    return image.resize(size, Image.Resampling.LANCZOS)


def optimize_panorama(source: Path, output_dir: Path) -> dict:
    errors = validate_panorama_shape(source)
    if errors:
        raise ValueError(" ".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    with Image.open(source) as image:
        image = image.convert("RGB")
        for key, (w, h, quality) in TARGETS.items():
            out = output_dir / f"panorama-{key}.webp"
            variant = _fit_no_upscale(image, (w, h))
            variant.save(out, "WEBP", quality=quality, method=6)
            result[key] = {"path": out, "width": variant.width, "height": variant.height, "bytes": out.stat().st_size}
    return result

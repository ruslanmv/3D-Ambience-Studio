from pathlib import Path

from PIL import Image

TARGETS = {
    "desktop": (4096, 2048, 88),
    "quest": (2048, 1024, 82),
    "preview": (768, 384, 80),
}

# Backplates are flat, so they get their own targets and their own shape check. The panorama
# path above insists on 2:1 within 1%, which a 16:9 backplate fails by a mile — running one
# through the wrong validator is the obvious way to waste an afternoon.
BACKPLATE_TARGETS = {
    "landscape": (1920, 1080, 86),
    "portrait": (1080, 1920, 86),
}
BACKPLATE_PREVIEW = (384, 216, 80)


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


def validate_backplate_shape(path: Path, expected_ratio: float, tolerance: float = 0.02) -> list[str]:
    """Check a backplate against the aspect its profile renders at.

    Tolerance is wider than the panorama's 1% because a generator asked for 1920x1080 may return
    1920x1088 — some models quantise to a multiple of 8 or 64. That is a rounding artefact worth
    accepting and cropping, not a wrong-shaped image worth rejecting.
    """
    info = inspect_panorama(path)
    errors = []
    if abs(info["ratio"] - expected_ratio) > tolerance:
        errors.append(
            f"Backplate should be {expected_ratio:.3f}:1 for this profile; "
            f"got {info['width']}x{info['height']} ({info['ratio']:.3f}:1)."
        )
    return errors


def _centre_crop_to_ratio(image: Image.Image, ratio: float) -> Image.Image:
    """Trim to an exact aspect, centred.

    Only ever removes pixels. A generator's 1088-row output becomes 1080 by losing four rows top
    and bottom, which is invisible; resizing instead would shift the horizon off the row the
    contract put it on, which is the one thing that must not move.
    """
    current = image.width / image.height
    if abs(current - ratio) < 1e-6:
        return image.copy()
    if current > ratio:
        target_w = round(image.height * ratio)
        left = (image.width - target_w) // 2
        return image.crop((left, 0, left + target_w, image.height))
    target_h = round(image.width / ratio)
    top = (image.height - target_h) // 2
    return image.crop((0, top, image.width, top + target_h))


def optimize_backplate(source: Path, output_dir: Path, profile: str = "landscape") -> dict:
    """Crop to the profile's exact aspect, resize to its master, and write a thumbnail.

    Unlike the panorama path this *does* resize up when a generator returns something smaller
    than the master. A backplate is the final image; delivering it under-sized would push the
    upscale into the browser, where it happens on every load and looks no better.
    """
    if profile not in BACKPLATE_TARGETS:
        raise ValueError(f"Unknown backplate profile {profile!r}; expected one of {sorted(BACKPLATE_TARGETS)}.")
    width, height, quality = BACKPLATE_TARGETS[profile]
    ratio = width / height
    errors = validate_backplate_shape(source, ratio)
    if errors:
        raise ValueError(" ".join(errors))

    output_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    with Image.open(source) as image:
        image = image.convert("RGB")
        exact = _centre_crop_to_ratio(image, ratio)
        master = exact if exact.size == (width, height) else exact.resize((width, height), Image.Resampling.LANCZOS)
        out = output_dir / f"backplate-{profile}.webp"
        master.save(out, "WEBP", quality=quality, method=6)
        result[profile] = {"path": out, "width": master.width, "height": master.height, "bytes": out.stat().st_size}

        pw, ph, pq = BACKPLATE_PREVIEW
        if profile == "portrait":
            pw, ph = ph, pw
        thumb = master.resize((pw, ph), Image.Resampling.LANCZOS)
        thumb_out = output_dir / f"backplate-{profile}-preview.webp"
        thumb.save(thumb_out, "WEBP", quality=pq, method=6)
        result[f"{profile}-preview"] = {
            "path": thumb_out,
            "width": thumb.width,
            "height": thumb.height,
            "bytes": thumb_out.stat().st_size,
        }
    return result


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

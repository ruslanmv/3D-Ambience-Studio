"""Turn a camera contract into something an image model can be held to.

Route 1 — reprojecting a 360° panorama — throws away six sevenths of the source and upscales
what is left. Route 2 generates the backplate directly at the master size, which wastes nothing;
but only if the generator can be made to put the horizon and the floor where the camera expects
them.

Text alone is weak for that. "Thirty degree vertical field of view" is not a constraint a
diffusion model can satisfy — it has no notion of the number. A *picture* of the horizon, the
converging floor and the region that must stay clear is a constraint it can, which is the whole
finding behind ControlNet and T2I-Adapter: spatial conditions control structure, prose does not.

So this module produces two things from one contract:

    contract JSON  ──►  guide image  (the spatial condition: horizon, floor, safe zone)
                   └─►  prompt text  (the same facts in words, for the models that only read)

Neither computes a projection. Every number is read from the contract, which the consuming
runtime exported from its own live camera — see `schemas/backplate-camera.schema.json`. That is
deliberate: a second implementation of the projection is how the Studio and the runtime would
quietly stop agreeing.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw


class ContractError(ValueError):
    """A contract that cannot produce a usable guide. Raised rather than defaulted.

    Guessing a missing horizon would produce a guide that looks authoritative and is wrong,
    which is worse than refusing — the whole point of the contract is that nobody estimates.
    """


def load_contract(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise ContractError(f"unsupported contract schemaVersion: {data.get('schemaVersion')!r}")
    if not data.get("profiles"):
        raise ContractError("contract carries no profiles")
    return data


def get_profile(contract: dict, name: str) -> dict:
    profiles = contract.get("profiles", {})
    if name not in profiles:
        raise ContractError(f"contract has no profile {name!r}; it has {sorted(profiles)}")
    profile = profiles[name]
    for field in ("master", "horizonY", "footAnchor", "safeZone"):
        if field not in profile:
            raise ContractError(f"profile {name!r} is missing {field!r}")
    return profile


def _px(fraction: float, size: int) -> int:
    """A 0..1 fraction to a pixel index. `round` already returns an int."""
    return round(fraction * size)


def render_guide(profile: dict, *, labels: bool = True) -> Image.Image:
    """Draw the guide at the profile's master size.

    Deliberately flat colour on black: a conditioning image is read for its *edges*, so gradients
    and anti-aliased decoration are noise. The three signals are the horizon, the convergence of
    the floor, and the rectangle that must stay empty.
    """
    width = int(profile["master"]["width"])
    height = int(profile["master"]["height"])
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)

    horizon = _px(float(profile["horizonY"]), height)
    draw.line([(0, horizon), (width, horizon)], fill=(255, 64, 96), width=max(2, height // 400))

    # Ground lines. Their convergence is the perspective cue; without them a generator has a
    # horizon and no reason to agree about anything below it.
    for line in profile.get("groundLines", []):
        y = _px(float(line["y"]), height)
        draw.line([(0, y), (width, y)], fill=(0, 160, 190), width=max(1, height // 900))

    # Longitudinal lines — the ones that actually convey perspective.
    #
    # The depth lines above are parallel horizontals: correct, and they only say how far apart
    # things are. What makes a floor read as a floor is convergence, and every line running away
    # from the camera meets at the vanishing point.
    #
    # No projection maths is needed to draw them, which matters because this module deliberately
    # computes none. A straight line in the world projects to a straight line in the image, and
    # all of these pass through the vanishing point — so each is simply a segment from a point
    # along the bottom edge to (footAnchor.x, horizonY). Correct by the geometry of perspective
    # rather than by arithmetic anyone here could get wrong.
    vanish = (_px(float(foot_x := float(profile["footAnchor"]["x"])), width), horizon)
    for i in range(-4, 5):
        if i == 0:
            continue
        bottom_x = _px(foot_x + i * 0.42, width)
        draw.line([(bottom_x, height), vanish], fill=(0, 120, 150), width=max(1, height // 1100))

    zone = profile["safeZone"]
    box = [
        _px(float(zone["x0"]), width),
        _px(float(zone["y0"]), height),
        _px(float(zone["x1"]), width),
        _px(float(zone["y1"]), height),
    ]
    draw.rectangle(box, outline=(255, 209, 102), width=max(2, height // 400))

    foot = profile["footAnchor"]
    fx, fy = _px(float(foot["x"]), width), _px(float(foot["y"]), height)
    radius = max(4, height // 160)
    draw.ellipse([fx - radius, fy - radius, fx + radius, fy + radius], fill=(0, 229, 255))
    draw.line([(fx - radius * 4, fy), (fx + radius * 4, fy)], fill=(0, 229, 255), width=max(2, height // 500))

    # Quiet zones. Drawn as a hatched region rather than an outline, because they ask for something
    # different from the keep-clear box: not "put no object here" but "put no *contrast* here". A
    # marketing hero composites a headline over one of these, and a busy shoreline behind white
    # display type is unreadable however well the horizon lands.
    for quiet in profile.get("quietZones", []):
        qx0, qy0 = _px(float(quiet["x0"]), width), _px(float(quiet["y0"]), height)
        qx1, qy1 = _px(float(quiet["x1"]), width), _px(float(quiet["y1"]), height)
        draw.rectangle([qx0, qy0, qx1, qy1], outline=(150, 120, 255), width=max(2, height // 500))
        step = max(12, height // 40)
        for offset in range(0, (qx1 - qx0) + (qy1 - qy0), step):
            x_start, y_start = qx0 + offset, qy0
            if x_start > qx1:
                x_start, y_start = qx1, qy0 + (offset - (qx1 - qx0))
            x_end, y_end = qx0, qy0 + offset
            if y_end > qy1:
                x_end, y_end = qx0 + (offset - (qy1 - qy0)), qy1
            draw.line([(x_start, y_start), (x_end, y_end)], fill=(96, 76, 170), width=1)

    if labels:
        draw.text((8, max(0, horizon - 16)), f"HORIZON {float(profile['horizonY']) * 100:.1f}%", fill=(255, 64, 96))
        draw.text((box[0] + 8, box[1] + 8), "KEEP CLEAR", fill=(255, 209, 102))
        for quiet in profile.get("quietZones", []):
            draw.text(
                (_px(float(quiet["x0"]), width) + 8, _px(float(quiet["y0"]), height) + 8),
                f"QUIET: {quiet['id'].upper()}",
                fill=(150, 120, 255),
            )
    return image


def build_prompt(profile: dict, subject: str, *, negative: bool = False) -> str:
    """The same constraints in words, for a model that takes no image condition.

    Weaker than the guide and worth having anyway: some workers accept only text, and the
    negative prompt is where the two rules with no positive phrasing live — no characters, and
    no cast figure shadows. A painted person is a duplicate of the avatar, and a painted shadow
    will not match where she is standing.
    """
    if negative:
        return (
            "people, person, character, figure, human, silhouette, cast shadow of a person, "
            "text, watermark, signature, frame, border, fisheye, panorama, warped horizon"
        )

    horizon = float(profile["horizonY"]) * 100
    foot = profile["footAnchor"]
    zone = profile["safeZone"]
    pitch = float(profile.get("pitchDeg", 0.0))
    eye = profile.get("eyeHeightMetres")

    parts = [
        subject.strip().rstrip("."),
        f"horizon exactly at {horizon:.1f}% of image height",
        f"{float(profile['fovDeg']):.0f} degree vertical field of view",
    ]
    if eye is not None:
        parts.append(f"camera {float(eye):.2f} m above a level floor")
    if abs(pitch) > 0.01:
        parts.append(f"tilted {abs(pitch):.1f} degrees {'down' if pitch > 0 else 'up'}")
    parts += [
        "continuous unobstructed floor across the lower third",
        f"floor clearly readable at {float(foot['x']) * 100:.0f}% across and {float(foot['y']) * 100:.1f}% down",
        f"nothing prominent between {float(zone['x0']) * 100:.0f}% and {float(zone['x1']) * 100:.0f}% of the width",
    ]
    # A quiet zone is a contrast constraint, not an object constraint, so it is phrased that way:
    # "keep this area clear" gets an empty area with a hard-edged cloud bank in it, which is
    # exactly as unreadable behind display type as a shoreline would have been.
    for quiet in profile.get("quietZones", []):
        parts.append(
            f"smooth low-contrast gradient with no detail or hard edges from "
            f"{float(quiet['x0']) * 100:.0f}% to {float(quiet['x1']) * 100:.0f}% across and "
            f"{float(quiet['y0']) * 100:.0f}% to {float(quiet['y1']) * 100:.0f}% down"
        )
    parts += [
        "no people, no characters",
        "empty scene, photographic, soft natural light",
    ]
    return ", ".join(parts)

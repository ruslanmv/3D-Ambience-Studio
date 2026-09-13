"""Visual QA composites: the contract drawn on top of the finished plate.

There is no automated acceptance test for "does this picture work". An earlier attempt measured
the horizon by looking for the strongest horizontal edge and confidently reported a 27-point error
that did not exist — it had found the lit terrace lip, which is a far stronger edge than a hazy
sea meeting a hazy sky. Nothing here repeats that. Distinguishing a terrace from a shoreline from
a mountain ridge from a true horizon is a semantic problem, and an edge detector does not have the
vocabulary for it.

So this draws the numbers on the image and stops. A person looks at one composite per variant and
answers the questions `docs/BACKPLATE_ROUTE.md` lists — does the foot anchor land on continuous
ground, is the keep-clear band empty, is the sea/sky line near the contract line. That is slower
than a green tick and it is the difference between checking and pretending to.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HORIZON = (255, 40, 70)
KEEP_CLEAR = (60, 255, 150)
FOOT = (255, 210, 60)


def composite(plate: Path, camera: dict, output: Path) -> Path:
    """Draw the camera contract over a finished plate and save it for inspection."""
    with Image.open(plate) as source:
        image = source.convert("RGB")

    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size
    unit = max(2, round(width / 640))

    horizon_y = round(float(camera["horizonY"]) * height)
    draw.line([(0, horizon_y), (width, horizon_y)], fill=(*HORIZON, 255), width=unit * 2)
    draw.text((unit * 4, horizon_y - unit * 9), f"contract horizon {camera['horizonY'] * 100:.1f}%", fill=(*HORIZON, 255))

    safe = camera["safeZone"]
    foot_y = round(float(camera["footAnchor"]["y"]) * height)
    x0 = round(float(safe["x0"]) * width)
    x1 = round(float(safe["x1"]) * width)
    draw.rectangle((x0, round(float(safe["y0"]) * height), x1, foot_y), outline=(*KEEP_CLEAR, 220), width=unit * 2)
    draw.line([(x0, foot_y), (x1, foot_y)], fill=(*FOOT, 255), width=unit * 2)

    radius = unit * 4
    centre = round(float(camera["footAnchor"]["x"]) * width)
    draw.ellipse((centre - radius, foot_y - radius, centre + radius, foot_y + radius), fill=(*FOOT, 255))
    draw.text((x1 + unit * 3, foot_y - unit * 7), f"feet {camera['footAnchor']['y'] * 100:.1f}%", fill=(*FOOT, 255))

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")
    return output

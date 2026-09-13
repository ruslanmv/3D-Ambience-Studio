from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["relax", "meditation", "study", "sleep", "nature", "cozy", "fantasy", "focus", "chill", "seasonal"]


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class LightingConfig(BaseModel):
    preset: str = "neutral"
    exposure: float = Field(default=1.0, ge=0, le=4)
    keyIntensity: float = Field(default=0.8, ge=0, le=4)


class ProjectCreate(BaseModel):
    name: str
    prompt: str = ""
    description: str = ""
    category: Category = "relax"
    tags: list[str] = []
    style: str = "realistic"


class ProjectRecord(ProjectCreate):
    id: str
    version: str = "1.0.0"
    status: str = "draft"
    sourcePanorama: str | None = None
    sourceAudio: str | None = None
    panoramaProvider: str | None = None
    # Route 2. Kept alongside the panorama fields rather than replacing them: a project may be
    # published as a panorama, as a backplate, or as both for different consumers.
    sourceBackplate: str | None = None
    backplateProvider: str | None = None
    backplateProfile: str | None = None
    lighting: LightingConfig = LightingConfig()
    yawDegrees: float = 0.0
    companionMode: str = "gradient"
    companionPreset: str = "auto"
    effects: list[dict] = []
    createdAt: str = Field(default_factory=utcnow)
    updatedAt: str = Field(default_factory=utcnow)


class GenerateRequest(BaseModel):
    provider: str = "mock"
    seed: int | None = None


class GeneratePlateRequest(BaseModel):
    """A plate request names the camera it is for, which a panorama request never has to.

    `contract` is a filename under examples/backplate-camera rather than a path, so a request
    cannot reach outside that directory.
    """

    provider: str = "mock-backplate"
    contract: str = "avatar-chatbot.json"
    profile: str = "landscape"
    seed: int | None = None


class PublishRequest(BaseModel):
    version: str | None = None
    featured: bool = False

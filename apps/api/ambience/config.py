from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ambience_data_dir: str = "./data"
    ambience_public_base_url: str = "http://localhost:8000/public"
    ambience_cors_origins: str = "http://localhost:5173,http://localhost:8000"
    ambience_panorama_provider: str = "mock"
    panfusion_url: str = "http://localhost:8101"
    triposr_url: str = "http://localhost:8102"
    text2vr_url: str = "http://localhost:8103"
    backplate_url: str = "http://localhost:8104"

    @property
    def data_dir(self) -> Path:
        return Path(self.ambience_data_dir).resolve()

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.ambience_cors_origins.split(",") if x.strip()]


settings = Settings()

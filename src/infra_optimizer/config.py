"""Configuration centralisée — chargée depuis l'environnement."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres de l'application chargés via .env."""

    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    log_level: str = "INFO"

    # Seuils de détection d'anomalies (configurables)
    cpu_threshold: float = 85.0
    memory_threshold: float = 85.0
    latency_threshold_ms: float = 300.0
    disk_threshold: float = 85.0
    error_rate_threshold: float = 0.05
    temperature_threshold: float = 75.0
    io_wait_threshold: float = 10.0
    zscore_threshold: float = 2.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

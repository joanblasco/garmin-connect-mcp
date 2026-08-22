"""Authentication and configuration for the AEMET OpenData API."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AemetConfig(BaseSettings):
    """AEMET OpenData API configuration from environment variables.

    AEMET authenticates with a free API key (requested by email at
    https://opendata.aemet.es/centrodedescargas/inicio, delivered almost
    instantly) sent as an `api_key` request header. No OAuth, no login flow.
    """

    aemet_api_key: str = ""

    # extra="ignore": the .env is shared with GarminConfig/IntervalsConfig/etc.,
    # each declaring its own unrelated variables (see auth.GarminConfig for why
    # this matters).
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


def load_aemet_config() -> AemetConfig:
    """Load AEMET configuration from environment variables."""
    return AemetConfig()


def validate_aemet_credentials(config: AemetConfig) -> bool:
    """Check that the required AEMET credential is configured."""
    return bool(config.aemet_api_key.strip())

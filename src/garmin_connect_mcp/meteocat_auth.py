"""Authentication and configuration for the MeteoCat (Servei Meteorològic de
Catalunya) API."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class MeteocatConfig(BaseSettings):
    """MeteoCat API configuration from environment variables.

    MeteoCat authenticates with an API key sent as an `x-api-key` request
    header. Unlike AEMET, registration is free but slower: it requires a form
    with organization/contact info (NIF/CIF is mandatory even for individual
    citizens), choosing which data subscription(s) to request (this project
    only needs the "Predicció" forecast subscription), and can take up to ~7
    days for a confirmation email. See https://apidocs.meteocat.gencat.cat/.
    """

    meteocat_api_key: str = ""

    # extra="ignore": the .env is shared with GarminConfig/IntervalsConfig/etc.,
    # each declaring its own unrelated variables (see auth.GarminConfig for why
    # this matters).
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


def load_meteocat_config() -> MeteocatConfig:
    """Load MeteoCat configuration from environment variables."""
    return MeteocatConfig()


def validate_meteocat_credentials(config: MeteocatConfig) -> bool:
    """Check that the required MeteoCat credential is configured."""
    return bool(config.meteocat_api_key.strip())

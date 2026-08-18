"""Authentication and configuration for the Intervals.icu API."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class IntervalsConfig(BaseSettings):
    """Intervals.icu API configuration from environment variables.

    Intervals.icu authenticates with a plain API key (HTTP Basic auth: username
    "API_KEY", password the generated key) rather than OAuth, so unlike Garmin
    there's no login flow, MFA, or token storage to configure here — just the key
    and the athlete ID it applies to.
    """

    intervals_api_key: str = ""
    intervals_athlete_id: str = ""

    # extra="ignore": the same .env is shared with GarminConfig, which declares its
    # own unrelated variables (see auth.GarminConfig for why this matters).
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


def load_intervals_config() -> IntervalsConfig:
    """Load Intervals.icu configuration from environment variables."""
    return IntervalsConfig()


def validate_intervals_credentials(config: IntervalsConfig) -> bool:
    """Check that both required Intervals.icu credentials are configured."""
    return bool(config.intervals_api_key.strip()) and bool(config.intervals_athlete_id.strip())

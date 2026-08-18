"""Authentication and configuration for Garmin Connect API."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path.home() / ".garminconnect.env"
LOCAL_ENV_FILE = Path(".env")


class GarminConfig(BaseSettings):
    """Garmin Connect API configuration from environment variables."""

    garmin_email: str = ""
    garmin_password: str = ""
    garmintokens: str = str(Path.home() / ".garminconnect")
    garmintokens_base64: str = str(Path.home() / ".garminconnect_base64")
    # Serialised OAuth tokens supplied inline instead of via the filesystem. Needed on
    # hosts with an ephemeral disk (Render, Fly, Heroku) where a token directory cannot
    # be persisted and secrets arrive as environment variables.
    garmin_token_data: str = ""

    # extra="ignore": the .env file is shared with other tool sets (e.g. Intervals.icu,
    # see intervals_auth.IntervalsConfig) that declare their own unrelated variables in
    # the same file. pydantic-settings' dotenv-file source defaults to "forbid" and
    # would otherwise raise a ValidationError for every key GarminConfig doesn't itself
    # declare.
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


def get_env_file_path() -> Path:
    """Get the path where interactive setup should write credentials."""
    local_env = Path.cwd() / LOCAL_ENV_FILE
    if local_env.exists():
        return local_env
    return DEFAULT_ENV_FILE


def load_config() -> GarminConfig:
    """Load configuration from environment variables and env files."""
    settings_kwargs = {"_env_file": (str(DEFAULT_ENV_FILE), str(LOCAL_ENV_FILE))}
    return GarminConfig(**settings_kwargs)


def validate_credentials(config: GarminConfig) -> bool:
    """Check if credentials are properly configured.

    Inline token data is sufficient on its own: a remote deployment can authenticate
    from previously generated tokens without ever holding the account password.
    """
    if has_inline_tokens(config):
        return True
    if not config.garmin_email or config.garmin_email == "your_email@example.com":
        return False
    if not config.garmin_password or config.garmin_password == "your_password":
        return False
    return True


# garminconnect treats a tokenstore argument longer than this as literal token data
# rather than a filesystem path.
INLINE_TOKEN_MIN_LENGTH = 512


def has_inline_tokens(config: GarminConfig) -> bool:
    """Check whether usable inline token data was supplied via the environment."""
    return len(config.garmin_token_data.strip()) > INLINE_TOKEN_MIN_LENGTH


def get_token_store() -> str:
    """Get the token storage directory path."""
    config = load_config()
    token_dir = Path(config.garmintokens)
    token_dir.mkdir(parents=True, exist_ok=True)
    return str(token_dir)


def get_token_base64_path() -> str:
    """Get the base64 token file path."""
    config = load_config()
    return config.garmintokens_base64

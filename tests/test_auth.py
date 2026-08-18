"""Tests for GarminConfig/load_config, focused on the shared .env file boundary.

GarminConfig.load_config() reads from a real dotenv file (not just the process
environment), and that file is shared with other tool sets — e.g. Intervals.icu's
IntervalsConfig declares its own INTERVALS_* variables in the same .env (see
README's Intervals.icu Integration section). GarminConfig must tolerate variables
it doesn't itself declare, rather than treating them as validation errors.
"""

from garmin_connect_mcp.auth import GarminConfig, load_config


class TestGarminConfigToleratesUnrelatedEnvVars:
    def test_load_config_ignores_keys_from_other_tool_sets_in_the_local_env_file(
        self, tmp_path, monkeypatch
    ):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "GARMIN_EMAIL=athlete@example.com\n"
            "GARMIN_PASSWORD=hunter2\n"
            "INTERVALS_API_KEY=some-other-tool-set-key\n"
            "INTERVALS_ATHLETE_ID=i12345\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("garmin_connect_mcp.auth.LOCAL_ENV_FILE", env_file)
        monkeypatch.setattr("garmin_connect_mcp.auth.DEFAULT_ENV_FILE", tmp_path / "nonexistent")

        config = load_config()

        assert config.garmin_email == "athlete@example.com"
        assert config.garmin_password == "hunter2"

    def test_garmin_config_ignores_unrelated_kwargs_directly(self):
        # Passed via a dict, not literal kwargs: intervals_api_key isn't a field
        # GarminConfig declares, so pyright would (correctly) flag it as a literal kwarg.
        config = GarminConfig(
            **{"garmin_email": "athlete@example.com", "intervals_api_key": "unrelated"}
        )

        assert config.garmin_email == "athlete@example.com"
        assert not hasattr(config, "intervals_api_key")

# Garmin Connect MCP Server

![Garmin Connect MCP Server](docs/heading.png)

A Model Context Protocol (MCP) server for Garmin Connect integration. Access your activities, health data, training metrics, and more through Claude and other LLMs.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/garmin-connect-mcp.svg)](https://pypi.org/project/garmin-connect-mcp/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue.svg)](https://github.com/eddmann/garmin-connect-mcp/pkgs/container/garmin-connect-mcp)

## Overview

This MCP server provides 38 tools across four independent data sources, organized into 12 categories:

- Activities (4 tools) - Query activities, view detailed metrics (incl. detailed splits), and edit or delete activities
- Analysis (2 tools) - Compare activities and find similar workouts
- Health & Wellness (5 tools) - Access health metrics, sleep, heart rate, activity data, and weekly step/stress/intensity trends
- Training (4 tools) - Analyze training periods, performance trends (incl. VO2max/HRV trends, FTP, lactate threshold), and training plans
- User Profile (1 tool) - Access profile, statistics, and personal records
- Challenges & Goals (3 tools) - Track goals, PRs, badges, badge challenges, and other challenges
- Devices & Gear (2 tools) - Manage devices and equipment
- Weight Management (2 tools) - Track weight data
- Nutrition (1 tool) - Daily food log, meals, and nutrition settings
- Other (3 tools) - Workouts, manual data entry, women's health tracking
- Intervals.icu (4 tools, optional) - Activities, training load (CTL/ATL/TSB), and planned-workout calendar from a separate Intervals.icu account — see [Intervals.icu Integration](#intervalsicu-integration-optional)
- Weather (7 tools, optional) - Forecasts from Open-Meteo (global, no key needed), AEMET (Spain), and MeteoCat (Catalonia) — see [Weather Integration](#weather-integration-optional)

Additionally, the server provides:

- 3 MCP Resources - Athlete profile, training readiness, and daily health for ongoing context
- 6 MCP Prompts - Templates for common queries (training analysis, sleep quality, readiness checks, activity analysis, run comparison, health summary)

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (the package requires Python 3.12+, which uv can manage), OR
- Docker

## Installation & Setup

### How Authentication Works

1. Credential Authentication - Run the setup command to save credentials
2. MFA Support - If MFA is enabled, the setup command prompts for your code
3. Token Storage - OAuth tokens saved to `~/.garminconnect/` and automatically refreshed
4. Persistence - Tokens persist across runs (UV on host, Docker requires volume mount)

### Option 1: Using uvx

```bash
uvx garmin-connect-mcp auth
```

This will prompt for your credentials, complete Garmin authentication, and save OAuth tokens
for the MCP server to reuse. It writes credentials to `~/.garminconnect.env` by default
and saves OAuth tokens under `~/.garminconnect/`.

If you prefer manual configuration, create `~/.garminconnect.env` yourself:

```bash
GARMIN_EMAIL=your-email@example.com
GARMIN_PASSWORD=your-password
```

### Option 2: Using Docker

```bash
# Pull the image
docker pull ghcr.io/eddmann/garmin-connect-mcp:latest
```

Then configure credentials using one of these methods:

#### Interactive Setup

```bash
# Create the env file first (Docker will create it as a directory if it doesn't exist)
touch garmin-connect-mcp.env

# Run the setup script and persist generated tokens
docker run -it --rm \
  -v "/ABSOLUTE/PATH/TO/garmin-connect-mcp.env:/app/.env" \
  -v "/ABSOLUTE/PATH/TO/.garminconnect-docker:/root/.garminconnect" \
  ghcr.io/eddmann/garmin-connect-mcp:latest \
  auth
```

This will prompt for your credentials, complete Garmin authentication, and save credentials to
`garmin-connect-mcp.env`. If you have MFA enabled, enter the code during this setup step.

#### Manual Setup

Create a `garmin-connect-mcp.env` file manually in your current directory:

```bash
GARMIN_EMAIL=your-email@example.com
GARMIN_PASSWORD=your-password
```

#### MFA Support for Docker

If you have MFA enabled on your Garmin account:

- Run the interactive setup command with `-it` so you can enter your MFA code
- The MCP server should then use saved tokens and should not prompt during runtime
- **Important**: Without token persistence, you'll need to authenticate again on every container restart
- **Recommended**: Mount the token directory as a volume during setup and server runs to persist tokens

To persist tokens across Docker runs, create a directory for tokens and mount it:

```bash
# Create token directory on host
mkdir -p ~/.garminconnect-docker

# Then use this directory in your Docker configuration (see Claude Desktop Configuration below)
```

## Claude Desktop Configuration

Add to your configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Using uvx

After running `uvx garmin-connect-mcp auth`, configure Claude Desktop to start the
published package:

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uvx",
      "args": ["garmin-connect-mcp"]
    }
  }
}
```

### Using Local Source

For development, run from a local checkout:

```bash
cd garmin-connect-mcp
uv sync
uv run garmin-connect-mcp auth
```

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/ABSOLUTE/PATH/TO/garmin-connect-mcp",
        "garmin-connect-mcp"
      ]
    }
  }
}
```

### Using Docker

#### Without Token Persistence (MFA required on every restart)

```json
{
  "mcpServers": {
    "garmin": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "/ABSOLUTE/PATH/TO/garmin-connect-mcp.env:/app/.env",
        "ghcr.io/eddmann/garmin-connect-mcp:latest"
      ]
    }
  }
}
```

#### With Token Persistence (Recommended for MFA users)

```json
{
  "mcpServers": {
    "garmin": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-v",
        "/ABSOLUTE/PATH/TO/garmin-connect-mcp.env:/app/.env",
        "-v",
        "/ABSOLUTE/PATH/TO/.garminconnect-docker:/root/.garminconnect",
        "ghcr.io/eddmann/garmin-connect-mcp:latest"
      ]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/.garminconnect-docker` with the absolute path to your token directory. On Windows, use something like `C:\\Users\\YOUR_USERNAME\\.garminconnect-docker`.

## Intervals.icu Integration (Optional)

A separate, independent tool set for [Intervals.icu](https://intervals.icu) — a training analysis platform that ingests activities from Garmin, Strava, Wahoo, Zwift, and others, and natively calculates training load (CTL/ATL/TSB). This is entirely optional: if the environment variables below aren't set, the Intervals.icu tools return a clear "not configured" error but every Garmin tool keeps working normally (and vice versa — Garmin credentials are never required to use the Intervals.icu tools).

Unlike Garmin, Intervals.icu authenticates with a simple API key rather than a login/token flow, so there's no `auth` setup command — just two environment variables:

1. Log in to [intervals.icu](https://intervals.icu) and open **Settings > Developer Settings**.
2. Generate an API key.
3. Note your Athlete ID (shown on the same page, formatted like `i12345`).
4. Add both to your `.env` (or `~/.garminconnect.env`, or however you're passing environment variables to the server):

```bash
INTERVALS_API_KEY=your_api_key
INTERVALS_ATHLETE_ID=i12345
```

No other configuration is needed — the server picks these up automatically on the next tool call.

## Weather Integration (Optional)

Three more separate, independent tool sets for weather forecasts. Like Intervals.icu, none of these require Garmin credentials (or each other) — each is entirely optional and only its own tools are affected if it isn't configured.

### Open-Meteo

No setup needed — [Open-Meteo](https://open-meteo.com) is free for non-commercial use (up to 10,000 calls/day) and needs no API key or registration. Works for any location worldwide.

### AEMET (Spain)

[AEMET](https://opendata.aemet.es) is Spain's national meteorological agency. Free, low-friction setup:

1. Request a key at [opendata.aemet.es/centrodedescargas/inicio](https://opendata.aemet.es/centrodedescargas/inicio) with just your email — the key arrives by email almost instantly.
2. Add it to your `.env`:

```bash
AEMET_API_KEY=your_api_key
```

AEMET's tools take a `municipio_code` — its own 5-digit INE municipality code (e.g. `08019` for Barcelona), not interchangeable with MeteoCat's codes below.

### MeteoCat (Catalonia)

[MeteoCat](https://www.meteo.cat) (Servei Meteorològic de Catalunya) covers Catalonia specifically. Free, but **registration has real friction** — plan for it:

- The registration form requires a **NIF/CIF**, even for personal/citizen use.
- You must explicitly choose which data subscription(s) to request — these tools only need the **"Predicció"** (forecast) subscription.
- Approval can take **up to ~7 days** to arrive by email after submitting the form.

Register at [apidocs.meteocat.gencat.cat](https://apidocs.meteocat.gencat.cat/documentacio/acces-ciutada-i-administracio/), then add the key once it arrives:

```bash
METEOCAT_API_KEY=your_api_key
```

MeteoCat's tools take a `codi_municipi` — MeteoCat's own municipality code, not interchangeable with AEMET's INE codes above. Only forecast endpoints are covered; live station observations (XEMA) require a separate subscription and lookup scheme and are out of scope for now.

### AVAMET (not included)

[AVAMET](https://www.avamet.org) (an amateur weather-station network covering Catalonia/Valencia) was investigated but isn't included: it has no public, self-service developer API — only a website and mobile app for viewing station data. If that changes, it can be added following the same pattern as the providers above.

## Usage

Ask Claude to interact with your Garmin data using natural language. The server provides tools, resources, and prompt templates to help you get started.

### Quick Start with MCP Prompts

Use built-in prompt templates for common queries (available via prompt suggestions in Claude):

- `analyze_recent_training` - Analyze my training over the past 30 days
- `sleep_quality_report` - Analyze sleep quality with recommendations
- `training_readiness_check` - Check if I'm ready to train hard today
- `activity_deep_dive` - Deep dive into a specific activity
- `compare_recent_runs` - Compare recent runs to track progress
- `health_summary` - Show comprehensive health overview

### Activities

```
"Show me my runs from the last 30 days"
"Get details for my half marathon yesterday including splits and heart rate zones"
"Show me the comments on my latest cycling activity"
```

### Training Analysis

```
"Analyze my training over the past 30 days"
"Compare my last three 10K runs"
"Find runs similar to my tempo workout from last week"
```

### Health & Wellness

```
"How did I sleep last night?"
"What's my Body Battery level today?"
"Show me my stress levels and recovery status"
"Am I ready to train hard today?"
```

_Note: The athlete profile resource (`garmin://athlete/profile`) and daily health resource (`garmin://health/today`) automatically provide ongoing context._

### Performance Metrics

```
"What's my VO2 max trend?"
"Show me my training readiness and recent stats"
```

_Note: List-returning tools use cursor-based pagination with default limits (10 items for activities, 7 for health data)._

## Available Tools

### Activities (4 tools)

| Tool                   | Description                                                            |
| ---------------------- | ---------------------------------------------------------------------- |
| `query_activities`     | Query activities with pagination (by ID, date range, or specific date) |
| `get_activity_details` | Get comprehensive activity details (splits, weather, HR zones, gear, optional typed splits/split summaries) |
| `get_activity_social`  | Get social details for an activity (likes, comments, kudos)            |
| `manage_activities`    | Rename, reclassify (with type lookup), or delete an activity — delete requires explicit confirmation |

### Analysis (2 tools)

| Tool                      | Description                                     |
| ------------------------- | ----------------------------------------------- |
| `compare_activities`      | Compare 2-5 activities side-by-side             |
| `find_similar_activities` | Find activities similar to a reference activity |

### Health & Wellness (5 tools)

| Tool                     | Description                                                                   |
| ------------------------ | ----------------------------------------------------------------------------- |
| `query_health_summary`   | Query daily health summaries with pagination (stats, readiness, Body Battery) |
| `query_sleep_data`       | Query sleep data with stages, scores, and HRV                                 |
| `query_heart_rate_data`  | Query heart rate data with resting HR                                         |
| `query_activity_metrics` | Query activity metrics (steps, stress, respiration, SpO2, etc.)               |
| `query_weekly_trends`    | Query week-by-week aggregates: steps, average stress, intensity minutes       |

### Training (4 tools)

| Tool                      | Description                                                                                 |
| ------------------------- | --------------------------------------------------------------------------------------------- |
| `analyze_training_period` | Analyze training over a time period with insights                                             |
| `get_performance_metrics` | Get performance metrics (VO2 max/HRV — single day or trend, hill score, endurance, FTP, lactate threshold) |
| `get_training_effect`     | Get training effect and progress summary                                                      |
| `query_training_plans`    | List training plans, or get plan detail / adaptive-plan detail by ID                          |

### User Profile (1 tool)

| Tool               | Description                                          |
| ------------------ | ---------------------------------------------------- |
| `get_user_profile` | Get comprehensive athlete profile with stats and PRs |

### Challenges & Goals (3 tools)

| Tool                      | Description                                                            |
| ------------------------- | ----------------------------------------------------------------------- |
| `query_goals_and_records` | Query goals, personal records, and race predictions                     |
| `query_challenges`        | Query badge challenges and other time-limited challenges (by status/type) |
| `query_badges`            | Query individual achievement badges — available catalog or in-progress (paginated) |

### Devices & Gear (2 tools)

| Tool            | Description                                                  |
| --------------- | ------------------------------------------------------------ |
| `query_devices` | Query device information (with settings, solar data, alarms) |
| `query_gear`    | Query gear and equipment (with defaults and usage stats)     |

### Weight Management (2 tools)

| Tool                 | Description                         |
| -------------------- | ----------------------------------- |
| `query_weight_data`  | Query weight data for date or range |
| `manage_weight_data` | Add or delete weight entries        |

### Nutrition (1 tool)

| Tool              | Description                                          |
| ----------------- | ----------------------------------------------------- |
| `query_nutrition` | Query daily food log, meals, and nutrition settings |

### Other (3 tools)

| Tool                  | Description                                      |
| --------------------- | ------------------------------------------------ |
| `manage_workouts`     | Workout management (list, get, download, upload, schedule, unschedule, delete) — delete requires explicit confirmation |
| `log_health_data`     | Log or delete body composition, blood pressure, hydration entries |
| `query_womens_health` | Query pregnancy and menstrual cycle data         |

### Intervals.icu (4 tools, optional)

Requires `INTERVALS_API_KEY` and `INTERVALS_ATHLETE_ID` — see [Intervals.icu Integration](#intervalsicu-integration-optional). A separate data source from the tools above; not affected by Garmin credentials.

| Tool                          | Description                                                             |
| ------------------------------ | ------------------------------------------------------------------------ |
| `intervals_list_activities`    | List activities for a date range, most recent first, optionally filtered by type |
| `intervals_get_activity_details` | Get full details for a single activity, incl. training load and zone distribution |
| `intervals_get_training_load`  | Get CTL/ATL/TSB ("Fitness"/"Fatigue"/"Form") for a date or date range   |
| `intervals_get_calendar`       | Query the calendar of planned workouts and other events                |

### Weather (7 tools, optional)

Three independent data sources, none affected by Garmin/Intervals.icu credentials or each other — see [Weather Integration](#weather-integration-optional).

#### Open-Meteo

No configuration required.

| Tool | Description |
| ---- | ----------- |
| `weather_openmeteo_current` | Current conditions (temperature, humidity, precipitation, wind) for any location worldwide |
| `weather_openmeteo_forecast` | Daily (and optionally hourly) forecast, up to 16 days ahead, for any location worldwide |

#### AEMET (Spain)

Requires `AEMET_API_KEY`.

| Tool | Description |
| ---- | ----------- |
| `weather_aemet_forecast_daily` | Official 8-day daily forecast for a Spanish municipality (INE code) |
| `weather_aemet_forecast_hourly` | Official 72-hour hourly forecast for a Spanish municipality (INE code) |

#### MeteoCat (Catalonia)

Requires `METEOCAT_API_KEY`.

| Tool | Description |
| ---- | ----------- |
| `weather_meteocat_forecast_municipal` | Official 8-day forecast for a Catalan municipality |
| `weather_meteocat_forecast_hourly` | Official 72-hour hourly forecast for a Catalan municipality |
| `weather_meteocat_uv_index` | Official 3-day UV index forecast for a Catalan municipality |

## MCP Resources

Resources provide ongoing context to the LLM without requiring explicit tool calls:

| Resource                      | Description                                        |
| ----------------------------- | -------------------------------------------------- |
| `garmin://athlete/profile`    | Athlete profile with stats, zones, and PRs         |
| `garmin://training/readiness` | Current training readiness and Body Battery        |
| `garmin://health/today`       | Today's health snapshot (steps, sleep, stress, HR) |

## MCP Prompts

Prompt templates for common queries (accessible via prompt suggestion in Claude):

| Prompt                     | Description                                         |
| -------------------------- | --------------------------------------------------- |
| `analyze_recent_training`  | Analyze training over a specified period            |
| `sleep_quality_report`     | Sleep quality analysis with recommendations         |
| `training_readiness_check` | Check if ready to train hard today                  |
| `activity_deep_dive`       | Deep dive into a specific activity with all metrics |
| `compare_recent_runs`      | Compare recent runs to identify trends              |
| `health_summary`           | Comprehensive health overview                       |

## License

MIT License - see [LICENSE](LICENSE) file for details

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Garmin Ltd., Intervals.icu, AEMET, the Servei Meteorològic de Catalunya (MeteoCat), Open-Meteo, or any of their affiliates. All product names, logos, and brands are property of their respective owners.

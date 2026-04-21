import tomllib
import os
from dataclasses import dataclass
from dotenv import load_dotenv

CONFIG_PATH = "session_config.toml"
ENV_PATH = ".env"


@dataclass
class Paths:
    working_dir: str
    obsidian_vault_dir: str
    obsidian_session_dir: str
    obsidian_campaign_data_dir: str


@dataclass
class RecordingConfig:
    speaker_name: str


@dataclass
class ObsidianConfig:
    vault_name: str
    session_notes_command_id: str


@dataclass
class ClaudeConfig:
    context_prompt: str


@dataclass
class FoundryConfig:
    url: str
    username: str
    password: str


@dataclass
class DiscordConfig:
    token: str          # from .env: DISCORD_BOT_TOKEN
    guild_id: int       # from session_config.toml [discord]
    session_channel_id: int  # channel for session announcements
    event_name: str          # display name for the scheduled event
    voice_channel_id: int    # voice channel the event takes place in (0 = external/FoundryVTT)
    event_image_path: str    # local path to image file for event cover (empty = none)
    wonder_dragon_art_path: str  # local path to ASCII art file for /WonderDragon (empty = none)


@dataclass
class GoogleCalendarConfig:
    event_name: str        # display name for the calendar event
    contact_group: str     # email to invite/notify (Google Group or individual)
    calendar_id: str       # "primary" or a specific calendar ID
    credentials_path: str  # path to OAuth2 client secret JSON from Google Cloud Console
    token_path: str        # path where the cached OAuth token is stored


@dataclass
class AppConfig:
    paths: Paths
    recording: RecordingConfig
    obsidian: ObsidianConfig
    claude: ClaudeConfig
    foundry: FoundryConfig
    discord: DiscordConfig
    google_calendar: GoogleCalendarConfig


def load_config(config_path: str = CONFIG_PATH) -> AppConfig:
    load_dotenv(ENV_PATH)

    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy session_config.toml and fill in your paths."
        )

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    paths_raw = raw.get("paths", {})
    recording_raw = raw.get("recording", {})
    obsidian_raw = raw.get("obsidian", {})
    claude_raw = raw.get("claude", {})

    missing = []
    for key in ("obsidian_vault_dir", "obsidian_session_dir", "obsidian_campaign_data_dir"):
        if not paths_raw.get(key):
            missing.append(f"paths.{key}")
    for key in ("vault_name",):
        if not obsidian_raw.get(key):
            missing.append(f"obsidian.{key}")
    if missing:
        raise ValueError(
            "session_config.toml is missing required values:\n  " + "\n  ".join(missing)
        )

    paths = Paths(
        working_dir=paths_raw.get("working_dir", "working"),
        obsidian_vault_dir=paths_raw["obsidian_vault_dir"],
        obsidian_session_dir=paths_raw["obsidian_session_dir"],
        obsidian_campaign_data_dir=paths_raw["obsidian_campaign_data_dir"],
    )

    recording = RecordingConfig(
        speaker_name=recording_raw.get("speaker_name", "Player"),
    )

    obsidian = ObsidianConfig(
        vault_name=obsidian_raw["vault_name"],
        session_notes_command_id=obsidian_raw.get("session_notes_command_id", ""),
    )

    claude = ClaudeConfig(
        context_prompt=claude_raw.get("context_prompt", ""),
    )

    foundry = FoundryConfig(
        url=os.getenv("FOUNDRY_URL", ""),
        username=os.getenv("FOUNDRY_USERNAME", ""),
        password=os.getenv("FOUNDRY_PASSWORD", ""),
    )

    discord_raw = raw.get("discord", {})
    discord_cfg = DiscordConfig(
        token=os.getenv("DISCORD_BOT_TOKEN", ""),
        guild_id=int(discord_raw.get("guild_id", 0)),
        session_channel_id=int(discord_raw.get("session_channel_id", 0)),
        event_name=discord_raw.get("event_name", "Next Session"),
        voice_channel_id=int(discord_raw.get("voice_channel_id", 0)),
        event_image_path=discord_raw.get("event_image_path", ""),
        wonder_dragon_art_path=discord_raw.get("wonder_dragon_art_path", ""),
    )

    gcal_raw = raw.get("google_calendar", {})
    gcal_cfg = GoogleCalendarConfig(
        event_name=gcal_raw.get("event_name", "TTRPG Session"),
        contact_group=gcal_raw.get("contact_group", ""),
        calendar_id=gcal_raw.get("calendar_id", "primary"),
        credentials_path=gcal_raw.get("credentials_path", ""),
        token_path=gcal_raw.get("token_path", "gcal_token.json"),
    )

    return AppConfig(
        paths=paths,
        recording=recording,
        obsidian=obsidian,
        claude=claude,
        foundry=foundry,
        discord=discord_cfg,
        google_calendar=gcal_cfg,
    )

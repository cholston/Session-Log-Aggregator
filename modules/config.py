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
class AppConfig:
    paths: Paths
    recording: RecordingConfig
    obsidian: ObsidianConfig
    claude: ClaudeConfig
    foundry: FoundryConfig


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

    return AppConfig(paths=paths, recording=recording, obsidian=obsidian, claude=claude, foundry=foundry)

"""
Post-Session Agent — orchestrates the full post-TTRPG-session workflow.

Usage:
    python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX"
    python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX" --transcription gemini
    python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX" --start-time "2026-04-13 19:00:00"

Re-run / recovery options (each skips earlier steps using saved state or provided paths):
    --audio-path path/to/audio.ogg   Skip Craig download; re-transcribe existing audio
    --transcript-path path/to/t.txt  Skip download + transcription entirely
    --skip-foundry --chat-log <path> Skip Foundry automation; provide chat log manually
    --transcription whisper|gemini   Switch backend (e.g. after a Gemini 503)
    --skip-claude                    Don't launch Claude Code at the end

A session_state.json file is written to the working directory after each step.
Re-running the same command resumes from the last successful step automatically.

Steps:
    1. Download FoundryVTT exports (campaign data macro + chat log)
    2. Download Craig recording ZIP, extract OGG, scrape start time
    3. Transcribe audio
    4. Merge transcript with FoundryVTT chat log
    5. Copy merged transcript + campaign data into Obsidian vault
    6. Launch Claude Code in the vault
"""

import argparse
import json
import os
import sys
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime

from modules.config import load_config
from modules.foundry_scraper import download_foundry_exports
from modules.craig_download import download_craig_recording
from modules.file_manager import copy_to_vault
from modules.mergesessionlogs import merge_logs
from modules.transcription import transcribe_whisper
from modules.transcription_gemini import transcribe_gemini

STATE_FILE = "session_state.json"


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

@dataclass
class SessionState:
    """Persists the output paths from each step so a failed run can resume."""
    craig_url: str
    working_dir: str
    start_time: str | None = None        # "YYYY-MM-DD HH:MM:SS"
    chat_log: str | None = None
    campaign_data: str | None = None
    ogg: str | None = None
    transcript: str | None = None
    merged: str | None = None
    vault_transcript: str | None = None
    vault_campaign_data: str | None = None

    @classmethod
    def load(cls, working_dir: str) -> "SessionState | None":
        path = os.path.join(working_dir, STATE_FILE)
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def create(cls, craig_url: str, working_dir: str) -> "SessionState":
        os.makedirs(working_dir, exist_ok=True)
        state = cls(craig_url=craig_url, working_dir=working_dir)
        state.save()
        return state

    def save(self):
        path = os.path.join(self.working_dir, STATE_FILE)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    def ready(self, attr: str) -> bool:
        """True if the attribute is set AND the file actually exists on disk."""
        val = getattr(self, attr, None)
        return bool(val and os.path.exists(val))


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #

def parse_args():
    p = argparse.ArgumentParser(
        description="Post-Session Agent: automate the post-TTRPG session workflow.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--craig-url",
        required=True,
        help="Craig recording URL, e.g. https://craig.horse/rec/XXXXX",
    )
    p.add_argument(
        "--start-time",
        default=None,
        help="Recording start time as 'YYYY-MM-DD HH:MM:SS' (overrides Craig page scrape and saved state)",
    )
    p.add_argument(
        "--transcription",
        choices=["whisper", "gemini"],
        default="gemini",
        help="Transcription backend (default: gemini). Change this to retry with a different engine.",
    )
    p.add_argument(
        "--skip-foundry",
        action="store_true",
        help="Skip FoundryVTT automation; requires --chat-log",
    )
    p.add_argument(
        "--chat-log",
        default=None,
        help="Path to an existing FoundryVTT chat log (use with --skip-foundry or to override saved state)",
    )
    p.add_argument(
        "--campaign-data",
        default=None,
        help="Path to an existing campaign data export (use with --skip-foundry or to override saved state)",
    )
    p.add_argument(
        "--audio-path",
        default=None,
        help="Path to an existing OGG/audio file — skips Craig download but still transcribes. Requires --start-time.",
    )
    p.add_argument(
        "--transcript-path",
        default=None,
        help="Path to an already-transcribed .txt file — skips download and transcription entirely. Requires --start-time.",
    )
    p.add_argument(
        "--next-session",
        default=None,
        metavar="DATETIME",
        help="Schedule the next session as a Discord event, e.g. '2026-04-26 19:00'",
    )
    p.add_argument(
        "--skip-claude",
        action="store_true",
        help="Do not launch Claude Code at the end; just drop files into the vault",
    )
    return p.parse_args()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def resolve_start_time(state: SessionState, arg_str: str | None, scraped: datetime | None) -> datetime:
    """Priority: CLI arg > state file > Craig scrape. Exits if none available."""
    if arg_str:
        try:
            return datetime.strptime(arg_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print(f"ERROR: --start-time '{arg_str}' must be in YYYY-MM-DD HH:MM:SS format.")
            sys.exit(1)
    if state.start_time:
        return datetime.strptime(state.start_time, "%Y-%m-%d %H:%M:%S")
    if scraped:
        return scraped
    print("ERROR: Recording start time could not be scraped from Craig and was not provided.")
    print("       Re-run with --start-time 'YYYY-MM-DD HH:MM:SS'")
    sys.exit(1)


def make_working_dir(base: str, date: datetime | None = None) -> str:
    date_str = (date or datetime.now()).strftime("%Y-%m-%d")
    return os.path.join(base, date_str)


def launch_claude(vault_dir: str, working_dir: str, prompt: str):
    print("\n--- Launching Claude Code for session notes review ---")
    # Write prompt to working dir, not the vault, so it doesn't appear in Obsidian
    prompt_file = os.path.abspath(os.path.join(working_dir, "_session_prompt.md"))
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    try:
        subprocess.run(
            ["claude", f"Read {prompt_file} and follow the instructions inside it."],
            cwd=vault_dir,
        )
    except FileNotFoundError:
        print("WARNING: 'claude' CLI not found on PATH.")
        print(f"  Prompt written to: {prompt_file}")
        print("  Open Claude Code manually in the vault and reference that file.")
        return
    try:
        os.remove(prompt_file)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    args = parse_args()
    config = load_config()

    # Determine working dir — use today's date; we may rename after getting start_time
    working_dir = make_working_dir(config.paths.working_dir)
    os.makedirs(working_dir, exist_ok=True)

    # Load or create session state
    state = SessionState.load(working_dir)
    if state is None:
        state = SessionState.create(craig_url=args.craig_url, working_dir=working_dir)
        print(f"New session started. Working dir: {working_dir}")
    else:
        print(f"Resuming session from state: {working_dir}")

    print("=" * 60)
    print("  Post-Session Agent")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # Step 1 — FoundryVTT exports
    # ------------------------------------------------------------------ #
    if args.chat_log:
        # Explicit override always wins
        state.chat_log = args.chat_log
        state.campaign_data = args.campaign_data or state.campaign_data
        state.save()
        print(f"\n[1/5] Using provided chat log: {state.chat_log}")

    elif args.skip_foundry:
        if not state.ready("chat_log"):
            print("ERROR: --skip-foundry requires --chat-log <path> (or a prior successful run)")
            sys.exit(1)
        print(f"\n[1/5] Skipping Foundry automation (state: {state.chat_log})")

    elif state.ready("chat_log"):
        print(f"\n[1/5] Foundry exports already done — skipping. ({state.chat_log})")

    else:
        if not config.foundry.url or not config.foundry.username:
            print("ERROR: FOUNDRY_URL and FOUNDRY_USERNAME must be set in .env")
            sys.exit(1)
        print("\n[1/5] Downloading FoundryVTT exports...")
        exports = download_foundry_exports(
            url=config.foundry.url,
            username=config.foundry.username,
            password=config.foundry.password,
            output_dir=working_dir,
        )
        state.chat_log = exports.get("chat_log")
        state.campaign_data = exports.get("campaign_data")
        state.save()

        if not state.chat_log:
            print("ERROR: FoundryVTT chat log download failed. Cannot continue.")
            sys.exit(1)
        if not state.campaign_data:
            print("WARNING: Campaign data macro download failed. Continuing without it.")

    # ------------------------------------------------------------------ #
    # Step 2 — Craig download (or use provided audio/transcript)
    # ------------------------------------------------------------------ #
    scraped_start = None

    if args.transcript_path:
        # Skip both download and transcription
        state.transcript = args.transcript_path
        state.save()
        print(f"\n[2/5] Using provided transcript, skipping audio. ({args.transcript_path})")

    elif args.audio_path:
        # Have audio, skip download
        state.ogg = args.audio_path
        state.save()
        print(f"\n[2/5] Using provided audio file, skipping Craig download. ({args.audio_path})")

    elif state.ready("ogg"):
        print(f"\n[2/5] Craig audio already downloaded — skipping. ({state.ogg})")

    else:
        print(f"\n[2/5] Downloading Craig recording from {args.craig_url}...")
        ogg_path, scraped_start = download_craig_recording(
            craig_url=args.craig_url,
            output_dir=working_dir,
            speaker_name=config.recording.speaker_name,
        )
        if not ogg_path:
            print("ERROR: Craig audio download failed.")
            sys.exit(1)
        state.ogg = ogg_path
        state.save()

    # Resolve start time (needed for transcription alignment)
    start_time = resolve_start_time(state, args.start_time, scraped_start)
    if state.start_time != start_time.strftime("%Y-%m-%d %H:%M:%S"):
        state.start_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
        state.save()
    print(f"  Recording start time: {start_time}")

    # Now that we have the start time, move working dir to the session date if needed
    session_dir = make_working_dir(config.paths.working_dir, start_time)
    if session_dir != working_dir and not os.path.exists(session_dir):
        import shutil
        shutil.move(working_dir, session_dir)
        working_dir = session_dir
        state.working_dir = working_dir
        # Update all stored paths to new location
        for attr in ("chat_log", "campaign_data", "ogg", "transcript", "merged"):
            val = getattr(state, attr)
            if val and val.startswith(os.path.join(config.paths.working_dir, datetime.now().strftime("%Y-%m-%d"))):
                setattr(state, attr, val.replace(
                    os.path.join(config.paths.working_dir, datetime.now().strftime("%Y-%m-%d")),
                    session_dir
                ))
        state.save()

    # ------------------------------------------------------------------ #
    # Step 3 — Transcription
    # ------------------------------------------------------------------ #
    if state.ready("transcript") and not args.transcript_path:
        print(f"\n[3/5] Transcript already exists — skipping. ({state.transcript})")

    elif not state.ready("transcript"):
        print(f"\n[3/5] Transcribing audio with {args.transcription}...")
        if args.transcription == "gemini":
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                print("ERROR: GEMINI_API_KEY not set in .env")
                sys.exit(1)
            transcript_path = transcribe_gemini(state.ogg, api_key)
        else:
            transcript_path = transcribe_whisper(state.ogg)

        state.transcript = transcript_path
        state.save()

    # ------------------------------------------------------------------ #
    # Step 4 — Merge
    # ------------------------------------------------------------------ #
    if state.ready("merged"):
        print(f"\n[4/5] Merged log already exists — skipping. ({state.merged})")

    else:
        print("\n[4/5] Merging transcript with chat log...")
        date_str = start_time.strftime("%Y-%m-%d")
        merged_path = os.path.join(working_dir, f"{date_str}-Transcript.md")
        merge_logs(
            fvtt_path=state.chat_log,
            transcript_path=state.transcript,
            output_path=merged_path,
            start_time=start_time,
            speaker_name=config.recording.speaker_name,
        )
        state.merged = merged_path
        state.save()
        print(f"  Merged log: {state.merged}")

    # ------------------------------------------------------------------ #
    # Step 5 — Copy to Obsidian vault
    # ------------------------------------------------------------------ #
    if state.ready("vault_transcript"):
        print(f"\n[5/5] Vault files already in place — skipping. ({state.vault_transcript})")

    else:
        print("\n[5/5] Copying files to Obsidian vault...")
        vault_paths = copy_to_vault(
            transcript_path=state.merged,
            campaign_data_path=state.campaign_data,
            obsidian_session_dir=config.paths.obsidian_session_dir,
            obsidian_campaign_data_dir=config.paths.obsidian_campaign_data_dir,
            session_date=start_time,
        )
        state.vault_transcript = vault_paths["transcript"]
        state.vault_campaign_data = vault_paths.get("campaign_data")
        state.save()

    print("\n" + "=" * 60)
    print("  All files ready.")
    print(f"  Session transcript : {state.vault_transcript}")
    if state.vault_campaign_data:
        print(f"  Campaign data      : {state.vault_campaign_data}")
    print(f"  State file         : {os.path.join(working_dir, STATE_FILE)}")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # Discord — schedule next session event
    # ------------------------------------------------------------------ #
    if args.next_session:
        print(f"\n[Discord] Scheduling next session: {args.next_session}")
        try:
            next_dt = datetime.strptime(args.next_session, "%Y-%m-%d %H:%M").astimezone()
        except ValueError:
            print("WARNING: --next-session must be 'YYYY-MM-DD HH:MM'. Skipping Discord event.")
            next_dt = None

        if next_dt:
            if not config.discord.token:
                print("WARNING: DISCORD_BOT_TOKEN not set in .env. Skipping Discord event.")
            elif not config.discord.guild_id:
                print("WARNING: discord.guild_id not set in session_config.toml. Skipping Discord event.")
            else:
                try:
                    from archimedes.actions import create_session_event
                    date_str = start_time.strftime("%Y-%m-%d")
                    event_id = create_session_event(
                        token=config.discord.token,
                        guild_id=config.discord.guild_id,
                        name=config.discord.event_name,
                        start_time=next_dt,
                        description=f"Post-session {date_str} — next up on {next_dt.strftime('%A, %B %-d')}",
                        voice_channel_id=config.discord.voice_channel_id,
                        image_path=config.discord.event_image_path,
                    )
                    print(f"  Discord event created (id: {event_id})")
                except Exception as exc:
                    print(f"WARNING: Discord event creation failed: {exc}")

    # ------------------------------------------------------------------ #
    # Claude Code handoff
    # ------------------------------------------------------------------ #
    if not args.skip_claude:
        rel_transcript = os.path.relpath(state.vault_transcript, config.paths.obsidian_vault_dir)
        rel_campaign = (
            os.path.relpath(state.vault_campaign_data, config.paths.obsidian_vault_dir)
            if state.vault_campaign_data
            else "(not available)"
        )
        prompt = config.claude.context_prompt.format(
            transcript_path=rel_transcript,
            campaign_data_path=rel_campaign,
        )
        launch_claude(config.paths.obsidian_vault_dir, working_dir, prompt)


if __name__ == "__main__":
    main()

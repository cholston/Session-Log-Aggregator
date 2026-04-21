# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Post-Session Agent: a full post-TTRPG-session automation pipeline. It logs into FoundryVTT to export the chat log and campaign data, downloads the Craig recording, transcribes it (locally via Whisper or via Google Gemini), merges everything into a timestamped session transcript, copies it into an Obsidian vault, and launches Claude Code to write session notes.

A GUI (`app.py`) also exists for manual one-off merges.

## Running the Application

```bash
# CLI post-session agent (automated workflow)
python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX?key=YYYYY"
python3 session_wrap.py --craig-url "..." --transcription whisper

# With Discord + Google Calendar scheduling for the next session
python3 session_wrap.py --craig-url "..." --next-session "2026-04-26 19:00"

# Test Google Calendar in isolation (no Craig URL needed)
python3 session_wrap.py --gcal-only --next-session "2026-04-26 19:00"

# Recovery / re-run options (each skips earlier steps using saved state)
python3 session_wrap.py --craig-url "..." --skip-foundry --chat-log path/to/chat.txt
python3 session_wrap.py --craig-url "..." --audio-path path/to/audio.ogg --start-time "2026-04-13 19:00:00"
python3 session_wrap.py --craig-url "..." --transcript-path path/to/t.txt --start-time "..."
python3 session_wrap.py --craig-url "..." --skip-claude

# Discord bot (standalone)
python3 archimedes.py

# GUI app (manual use)
python3 app.py
pythonw app.py   # Windows, no console window
```

VS Code launch configs: **"Python: Session Log App"** and **"Python: Session Wrap (CLI)"** in [.vscode/launch.json](.vscode/launch.json).

Note: `python` (without 3) is not on PATH on this machine — use `python3`.

## Key Files

**Entry points** (root):

| File | Purpose |
|---|---|
| [app.py](app.py) | GUI entry point (`LogAggregatorApp`, CustomTkinter) — manual one-off use |
| [session_wrap.py](session_wrap.py) | CLI orchestrator for the full automated post-session workflow |
| [archimedes.py](archimedes.py) | Standalone Discord bot entry point (Archimedes The Wonder Dragon) |

**Modules** (`modules/`):

| File | Purpose |
|---|---|
| [modules/config.py](modules/config.py) | Loads `session_config.toml` + `.env` into typed `AppConfig` dataclass |
| [modules/mergesessionlogs.py](modules/mergesessionlogs.py) | Core merge logic — parses FVTT logs + transcript, sorts, writes Markdown |
| [modules/transcription.py](modules/transcription.py) | Local Whisper transcription (`transcribe_whisper`) |
| [modules/transcription_gemini.py](modules/transcription_gemini.py) | Cloud Gemini transcription (`transcribe_gemini`) |
| [modules/foundry_scraper.py](modules/foundry_scraper.py) | Playwright automation for FoundryVTT — `download_foundry_exports` (macro + chat log), `download_foundry_chat_log` (GUI compat) |
| [modules/craig_download.py](modules/craig_download.py) | Playwright download of Craig ZIP, OGG extraction, start time scrape |
| [modules/file_manager.py](modules/file_manager.py) | Copies merged transcript + campaign data into Obsidian vault folders |
| [modules/gcal.py](modules/gcal.py) | Google Calendar event creation — resolves a Contacts label to emails via People API, creates event with attendees |

**Discord bot** (`archimedes/`):

| File | Purpose |
|---|---|
| [archimedes/bot.py](archimedes/bot.py) | `ArchimedesBot` class — loads cogs, syncs slash commands |
| [archimedes/actions.py](archimedes/actions.py) | One-shot async helpers (`create_session_event`, `post_message`) used by `session_wrap.py` without a persistent bot |
| [archimedes/cogs/session.py](archimedes/cogs/session.py) | `/schedule-session` and `/session-recap` slash commands |

**Config**:

| File | Purpose |
|---|---|
| [session_config.toml.template](session_config.toml.template) | Checked-in template — copy to `session_config.toml` and fill in values |
| `session_config.toml` | Non-secret config: paths, speaker name, vault settings, Claude prompt template, Discord IDs, GCal settings (gitignored) |
| `.env` | Secrets: `GEMINI_API_KEY`, `FOUNDRY_URL`, `FOUNDRY_USERNAME`, `FOUNDRY_PASSWORD`, `DISCORD_BOT_TOKEN` (gitignored) |
| `gcal_token.json` | Cached OAuth2 token written after first Google Calendar consent flow (gitignored) |

## Architecture

### CLI agent flow (`session_wrap.py`)
1. **Foundry exports**: `download_foundry_exports()` opens one browser session — clicks macro hotbar slot 1 (campaign data download), then the Export Chat Log button.
2. **Craig download**: `download_craig_recording()` navigates to the recording page, extracts `startTime` from embedded SvelteKit JSON (UTC, auto-converted to local time), clicks "Ogg Vorbis", waits for processing modal, downloads ZIP, extracts the speaker's OGG by matching `speaker_name`.
3. **Transcription**: `transcribe_whisper` or `transcribe_gemini` — output written to `working/YYYY-MM-DD/transcript.txt`.
4. **Merge**: `merge_logs()` converts timestamps to absolute `datetime`, clusters voice lines in 30-second windows, merges with FVTT entries, sorts, writes Markdown.
5. **Vault copy**: `copy_to_vault()` places `YYYY-MM-DD-Transcript.md` and `YYYY-MM-DD - foundry-snapshot.md` in configured Obsidian folders.
5.5. **Scheduling** (optional): if `--next-session` is provided, both Discord and Google Calendar events are created from a shared `next_dt`/`next_end_dt` (start + 2.5 h). Discord calls `archimedes.actions.create_session_event()` — spins up a temporary client and exits. Google Calendar calls `modules.gcal.create_calendar_event()` — resolves the configured Contacts label to attendee emails via the People API, then inserts the event.
6. **Claude Code handoff**: writes `_session_prompt.md` to the working dir (not the vault), launches `claude` CLI with the vault as cwd.

### Discord bot (`archimedes/`)
- **Persistent mode** (`archimedes.py`): full `ArchimedesBot` — loads cogs, syncs slash commands to the guild on startup. Add new cogs to `archimedes/cogs/` and register them in `COGS` list in `archimedes/bot.py`.
- **One-shot mode** (`archimedes/actions.py`): `create_session_event()` and `post_message()` spin up a minimal `discord.Client`, act on `on_ready`, then close. Safe to call synchronously from `session_wrap.py`.
- Slash commands are synced to the guild (instant) on every bot startup. Global sync (up to 1 hour) is not used.
- New cog pattern: create `archimedes/cogs/mycog.py` with a `setup(bot)` async function and add the module path to `COGS` in `bot.py`.

### GUI app flow (`app.py`)
1. User browses or downloads a FoundryVTT `.txt` chat log and an audio/transcript file.
2. If audio: transcribed via Whisper or Gemini.
3. `merge_logs()` merges and sorts, writes Markdown.
4. All long-running ops run on daemon threads; UI updates via `self.after(0, callback)`.

### Craig.horse Playwright notes
- Page is SvelteKit — wait for `networkidle` before interacting.
- Start time is embedded in a `<script>` tag as `startTime:"2026-04-13T23:02:47.365Z"` (UTC, no quotes around key). Extract with regex `startTime:"([^"]+)"` on `page.content()`. Convert UTC → local with `.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)`.
- Download flow: `dispatch_event("click")` on `button:has-text('Ogg Vorbis')` (normal `.click()` is blocked by modal backdrop) → wait for `button.svelte-1klcfz0` with text "Download" → `dispatch_event("click")`.
- Processing is server-side before the Download button appears. Short recordings take seconds; a full 4-hour session can take 3–5 min. Use a timeout of at least 360s on the Download button wait.
- ZIP track naming: `1-debinani.ogg` per user. Match against `config.recording.speaker_name`; fall back to first OGG if no match.

### Transcript timestamp formats
```
[MM:SS] Speaker text          ← Whisper / Gemini output
[MM:SS:ms] Speaker text       ← Gemini with milliseconds
```
Speaker name comes from `config.recording.speaker_name` (set in `session_config.toml`).

### FVTT chat log block format
```
[MM/DD/YYYY, HH:MM:SS AM/PM] Character Name
Message content
---
```

## Configuration

Fill in `session_config.toml`:
- `paths.working_dir` — staging area (default: `working/`); date-stamped subfolder created per session
- `paths.obsidian_vault_dir` — vault directory Claude Code is launched in
- `paths.obsidian_session_dir`, `paths.obsidian_campaign_data_dir` — destination folders in vault
- `recording.speaker_name` — used to select the right OGG track from Craig ZIP and attribute voice lines
- `discord.guild_id` — Discord server (guild) snowflake ID; used for slash command sync and event creation
- `discord.session_channel_id` — channel where session recap links are posted
- `google_calendar.contact_group` — Google Contacts label name (case-insensitive); resolved to member emails via People API
- `google_calendar.credentials_path` — path to OAuth2 client secret JSON downloaded from Google Cloud Console
- `google_calendar.token_path` — cached token path (default: `gcal_token.json`); auto-created on first run
- Secrets in `.env`: `FOUNDRY_URL`, `FOUNDRY_USERNAME`, `FOUNDRY_PASSWORD`, `GEMINI_API_KEY`, `DISCORD_BOT_TOKEN`

**Windows paths in TOML must use single quotes** (TOML literal strings) to avoid backslash escape issues:
```toml
obsidian_vault_dir = 'C:\Users\...\Obsidian\My Vault'
```

A `session_state.json` inside each `working/YYYY-MM-DD/` folder records step outputs for resume on failure. To retry from a specific step, null out the fields for that step and beyond.

## Dependencies

- Python 3.11+ (`tomllib` is stdlib)
- `customtkinter`, `openai-whisper`, `google-genai`, `playwright`, `python-dotenv`
- `discord.py>=2.0` — Discord bot
- `google-auth-oauthlib`, `google-api-python-client` — Google Calendar + People API
- `playwright install chromium` required for browser automation
- Gemini API key only needed for Gemini transcription mode
- `claude` CLI must be on PATH for the Claude Code handoff step

## Project status

### Pipeline (working end-to-end)
1. Foundry exports — macro slot 1 (campaign data) + Export Chat Log, single Playwright session
2. Craig ZIP download + OGG extraction
3. Transcription — Whisper (local) or Gemini (cloud)
4. Merge transcript + chat log → dated Markdown
5. Copy to Obsidian vault (`YYYY-MM-DD-Transcript.md`, `YYYY-MM-DD - foundry-snapshot.md`)
6. Discord + Google Calendar event creation (optional, `--next-session`); events default to 2.5 h duration
7. Claude Code handoff — writes `_session_prompt.md`, launches `claude` in vault dir

### Archimedes Discord bot (working)
- Standalone entry point `archimedes.py` connects and syncs slash commands to guild on startup
- `/schedule-session` — creates a guild scheduled event; reads `event_name`, `voice_channel_id`, `event_image_path` from `[discord]` config
- `/session-recap` — posts a notes URL to `session_channel_id`
- One-shot helpers in `archimedes/actions.py` used by `session_wrap.py` (no persistent bot needed)

### Google Calendar (working)
- `modules/gcal.py` — `create_calendar_event()` handles OAuth2 token caching, People API group resolution, and Calendar API event insertion
- Uses `[google_calendar]` section in `session_config.toml`; no new `.env` entries needed
- `--gcal-only --next-session "YYYY-MM-DD HH:MM"` skips the full pipeline for isolated testing
- Requires **Google Calendar API** and **Google People API** both enabled in the same Google Cloud project
- First run opens a browser for OAuth consent; token cached to `gcal_token.json` afterwards

### Deferred / not yet implemented
- Obsidian CLI publish automation
- Wire `post_message()` into `session_wrap.py` as a post-session announce step (helper exists, not called)
- Additional Archimedes cogs (bot is intentionally modular)

## Discord / discord.py gotchas

### Scheduled event image upload
`guild.create_scheduled_event(image=...)` requires **raw `bytes`**. discord.py calls `_bytes_to_base64_data(image)` internally, which runs `b64encode()` on whatever is passed.

- Passing a pre-built `"data:image/png;base64,..."` string causes double-encoding → malformed payload → API call hangs indefinitely with no error.
- Passing a Discord CDN URL string has the same result.
- Correct pattern: read the file as bytes and pass those directly; let discord.py encode.

```python
with open(image_path, "rb") as f:
    image_bytes = f.read()
kwargs["image"] = image_bytes  # discord.py encodes internally
```

### Naive datetime → local timezone on Windows
`naive_dt.astimezone(timezone.utc)` is unreliable on Windows — it can silently treat the datetime as UTC instead of converting from local time, causing events to be scheduled hours off.

Use `replace` with an explicitly derived local timezone instead:

```python
local_tz = datetime.now().astimezone().tzinfo
start_time = naive_dt.replace(tzinfo=local_tz)
```

## Google Calendar / People API gotchas

### Token scope changes
`Credentials.from_authorized_user_file` loads a cached token successfully even if the token is missing scopes added since it was created. `creds.valid` returns `True` and the error only surfaces when the API call is made. The fix is to check `set(SCOPES).issubset(set(creds.scopes or []))` after loading — `creds.scopes` is `None` on older tokens, so the `or []` is required to avoid the `and` short-circuiting and skipping re-auth.

### Contact group resolution
Google Contacts labels have no email address of their own. Resolution requires two People API calls:
1. `contactGroups().list()` — find the group `resourceName` by matching `name` (case-insensitive)
2. `contactGroups().get(maxMembers=500)` → `people().getBatchGet(personFields="emailAddresses")` — collect one address per member

If the group name doesn't match, the error prints all available `USER_CONTACT_GROUP` names.

### Google Cloud Console setup checklist
- Enable **Google Calendar API** and **Google People API** in the same project
- Create an **OAuth 2.0 client ID** (Desktop app type) and download the JSON as `credentials.json`
- Under **OAuth consent screen → Test users**, add your own Google account before the first run

## Rules

- **Do not modify files in the `testdata/` folder.** It holds static reference files.
- `testdata/`, `working/`, `archived/`, `.env`, `session_config.toml`, `run_app.bat` are all gitignored — do not commit them.

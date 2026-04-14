# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Post-Session Agent: a full post-TTRPG-session automation pipeline. It logs into FoundryVTT to export the chat log and campaign data, downloads the Craig recording, transcribes it (locally via Whisper or via Google Gemini), merges everything into a timestamped session transcript, copies it into an Obsidian vault, and launches Claude Code to write session notes.

A GUI (`app.py`) also exists for manual one-off merges.

## Running the Application

```bash
# CLI post-session agent (automated workflow)
python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX?key=YYYYY"
python3 session_wrap.py --craig-url "..." --transcription gemini

# Recovery / re-run options (each skips earlier steps using saved state)
python3 session_wrap.py --craig-url "..." --skip-foundry --chat-log path/to/chat.txt
python3 session_wrap.py --craig-url "..." --audio-path path/to/audio.ogg --start-time "2026-04-13 19:00:00"
python3 session_wrap.py --craig-url "..." --transcript-path path/to/t.txt --start-time "..."
python3 session_wrap.py --craig-url "..." --skip-claude

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

**Config** (gitignored):

| File | Purpose |
|---|---|
| [session_config.toml](session_config.toml) | Non-secret config: paths, speaker name, vault settings, Claude prompt template |
| [.env](.env) | Secrets: `GEMINI_API_KEY`, `FOUNDRY_URL`, `FOUNDRY_USERNAME`, `FOUNDRY_PASSWORD` |

## Architecture

### CLI agent flow (`session_wrap.py`)
1. **Foundry exports**: `download_foundry_exports()` opens one browser session — clicks macro hotbar slot 1 (campaign data download), then the Export Chat Log button.
2. **Craig download**: `download_craig_recording()` navigates to the recording page, extracts `startTime` from embedded SvelteKit JSON (UTC, auto-converted to local time), clicks "Ogg Vorbis", waits for processing modal, downloads ZIP, extracts the speaker's OGG by matching `speaker_name`.
3. **Transcription**: `transcribe_whisper` or `transcribe_gemini` — output written to `working/YYYY-MM-DD/transcript.txt`.
4. **Merge**: `merge_logs()` converts timestamps to absolute `datetime`, clusters voice lines in 30-second windows, merges with FVTT entries, sorts, writes Markdown.
5. **Vault copy**: `copy_to_vault()` places `YYYY-MM-DD-Transcript.md` and `YYYY-MM-DD - foundry-snapshot.md` in configured Obsidian folders.
6. **Claude Code handoff**: writes `_session_prompt.md` to the working dir (not the vault), launches `claude` CLI with the vault as cwd.

### GUI app flow (`app.py`)
1. User browses or downloads a FoundryVTT `.txt` chat log and an audio/transcript file.
2. If audio: transcribed via Whisper or Gemini.
3. `merge_logs()` merges and sorts, writes Markdown.
4. All long-running ops run on daemon threads; UI updates via `self.after(0, callback)`.

### Craig.horse Playwright notes
- Page is SvelteKit — wait for `networkidle` before interacting.
- Start time is in embedded script as `startTime:"2026-04-13T23:02:47.365Z"` (UTC) — parse with regex on `page.content()`.
- Download flow: `dispatch_event("click")` on "Ogg Vorbis" button (normal `.click()` is blocked by modal backdrop) → wait for `button.svelte-1klcfz0` with text "Download" → `dispatch_event("click")`. Processing can take 3–5 min for a full session.

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
- Secrets in `.env`: `FOUNDRY_URL`, `FOUNDRY_USERNAME`, `FOUNDRY_PASSWORD`, `GEMINI_API_KEY`

**Windows paths in TOML must use single quotes** (TOML literal strings) to avoid backslash escape issues:
```toml
obsidian_vault_dir = 'C:\Users\...\Obsidian\My Vault'
```

A `session_state.json` inside each `working/YYYY-MM-DD/` folder records step outputs for resume on failure. To retry from a specific step, null out the fields for that step and beyond.

## Dependencies

- Python 3.11+ (`tomllib` is stdlib)
- `customtkinter`, `openai-whisper`, `google-genai`, `playwright`, `python-dotenv`
- `playwright install chromium` required for browser automation
- Gemini API key only needed for Gemini transcription mode
- `claude` CLI must be on PATH for the Claude Code handoff step

## Rules

- **Do not modify files in the `testdata/` folder.** It holds static reference files.
- `testdata/`, `working/`, `archived/`, `.env`, `session_config.toml`, `run_app.bat` are all gitignored — do not commit them.

# TTRPG Post-Session Automation — Project Context

## Goal

Extend an existing Python application to automate the post-session workflow after a TTRPG session run in FoundryVTT. The result is a single CLI invocation that handles everything from audio download through wiki publishing, with one human review checkpoint for AI-generated content.

---

## Invocation Target

```bash
python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX" --next-session "2026-04-26 19:00"
```

These are the **only two manual inputs** required from the user after a session ends.

---

## Current Manual Workflow (13 Steps)

1. Run a macro in FoundryVTT that exports campaign data (JSON wrapped in a markdown file)
2. Export the FoundryVTT chat log
3. Schedule the next session in Google Calendar and send invites to players
4. Create a Discord event for the next session
5. Download the session audio recording from the Craig Discord bot (craig.horse)
6. Run a custom Python app that transcribes the audio and merges the transcript with the chat log — **the session start time is required for correct merge alignment**
7. Copy the merged chat log and campaign data into the Obsidian wiki folder
8. Take a screenshot of the FoundryVTT session screen
9. Open the Obsidian wiki folder in an AI tool (Claude Code)
10. Have the AI generate session notes and enrich the wiki based on session content
11. Run an Obsidian Templater macro that updates dynamic lists, then trigger Obsidian Publish
12. Capture the published URL for the session notes
13. Post the URL to the appropriate Discord channel

---

## Automation Plan

### What stays manual (by design or technical constraint)

- **Steps 1–2**: FoundryVTT macro trigger and chat log export. FoundryVTT is self-hosted on a local Ubuntu server (micro PC, local network) and does not expose a usable remote API for macro execution. User runs these as usual; the script watches the output folder for new files.
- **Steps 9–10 (review checkpoint)**: AI generates session notes and wiki enrichment proposals. User reviews and approves before anything is written to the wiki. No auto-commit.

### What gets automated

|Step|Method|
|---|---|
|3|Google Calendar API — create next session event, send player invites|
|4|Discord API — create server event|
|5|Playwright (headless) — download audio from craig.horse using provided URL|
|6|Existing Python transcription app — wired in with correct start timestamp|
|7|Python file copy to Obsidian vault folder|
|8|Screenshot via Obsidian CLI eval or pyautogui|
|9–10|Script assembles context file (transcription + chat log + wiki state + prompt) → user runs in Claude Code → approves output|
|11|Obsidian CLI (`obsidian eval`) triggers Templater macro + Publish|
|12–13|Capture published URL → Discord API posts to configured channel|

---

## Technical Stack & Constraints

### FoundryVTT

- Self-hosted on Ubuntu, local network
- Exports: campaign data as **JSON inside a markdown file** (Obsidian-compatible)
- No remote API available for macro triggering — file-watch approach only

### Craig Bot (Audio)

- User manually provides the Craig recording URL as a CLI argument
- Craig sends a DM to the user (not a channel message), so Discord bot cannot read it — self-bot approach is ToS violation, not used
- **Session start time**: attempt to extract from audio file metadata first; fall back to scraping the craig.horse recording page during Playwright download; final fallback is `--start-time` CLI arg
- Start time is critical for aligning transcript with FoundryVTT chat log timestamps

### Discord

- Needs a bot with permissions: read channel history, create events, send messages
- Bot cannot read user DMs (see Craig constraint above)
- Used for: creating next-session event (step 4), posting published wiki URL (step 13)

### Google Calendar

- Standard OAuth2 flow (one-time setup, token cached locally)
- Used for: creating next-session event with player invites (step 3)

### Obsidian

- Local vault on Windows machine
- **Obsidian CLI** (released Feb 2026, v1.12.0) — requires Catalyst License ($25 one-time)
- JavaScript execution: `obsidian eval "app.commands.executeCommandById('...')"`
- Used for: triggering Templater macro, triggering Obsidian Publish (step 11)
- No external plugins required beyond what's already installed (Templater assumed present)

### AI Enrichment (Steps 9–10)

- No Claude API key required
- Script assembles a structured context markdown file containing:
    - Merged transcript + chat log
    - Exported campaign data
    - Relevant existing wiki pages
    - Pre-written prompt template for session notes + wiki enrichment
- User feeds this file to Claude Code and reviews the output before approving
- Approved content is written to the Obsidian vault

### Existing Python App

- Already handles: audio transcription + merge with chat log
- **TODO for owner to clarify before build**: confirm entry point signature (CLI args vs. function call vs. script-with-config)

---

## Config File (to be created)

A `session_config.toml` (or `.env` + `config.toml`) should store:

```toml
[paths]
foundry_export_dir = ""       # Where FoundryVTT drops its exports
obsidian_vault_dir = ""       # Root of Obsidian vault
obsidian_campaign_dir = ""    # Campaign subfolder within vault
audio_staging_dir = ""        # Where Craig audio downloads land

[discord]
bot_token = ""
guild_id = ""
session_channel_id = ""       # Channel to post published URL
player_user_ids = []          # For event invites if needed

[google]
credentials_file = ""         # Path to OAuth credentials JSON
player_emails = []            # For calendar invites

[obsidian]
vault_name = ""               # For obsidian:// URI construction
publish_base_url = ""         # e.g. https://publish.obsidian.md/yourvault

[campaign]
name = ""
session_notes_template = ""   # Templater template name for session notes
```

---

## Module Structure (suggested)

```
session_wrap.py              # Orchestrator / entry point
modules/
  craig_download.py          # Playwright headless download + start time extraction
  foundry_watcher.py         # Watch export folder for new FoundryVTT files
  scheduling.py              # GCal + Discord event creation
  file_manager.py            # Copy exports to Obsidian vault
  ai_context_builder.py      # Assemble context file for Claude Code review
  obsidian_publish.py        # Obsidian CLI invocation (eval + publish)
  discord_announce.py        # Post URL to Discord channel
config.py                    # Load and validate config
```

The existing transcription/merge app should be imported as a module or called as a subprocess — whichever is cleaner given its current structure.

---

## Open Questions (resolve before building each module)

1. **Existing Python app entry point**: Is it a CLI (`python transcribe.py --audio foo.mp3 --chatlog bar.json`), an importable function, or a script you edit manually? This determines how `session_wrap.py` calls it.
2. **Folder paths**: Confirm FoundryVTT export directory, Obsidian vault path, and preferred audio staging location.
3. **Obsidian Publish URL pattern**: Is it predictable given campaign name + session name? (e.g. `https://publish.obsidian.md/yourvault/Campaign/Sessions/Session-42`) — needed for step 12.
4. **Templater macro name**: The exact command ID needed for `obsidian eval` to trigger your specific macro.
5. **Craig audio format**: What format do you download (FLAC, MP3, OGG)? Relevant for the transcription app input.
6. **Screenshot intent**: Is step 8 a FoundryVTT scene screenshot specifically, or just a desktop capture of whatever's on screen?

---

## One-Time Setup Checklist

- [ ] Google OAuth credentials (`credentials.json`) — [Google Cloud Console](https://console.cloud.google.com/)
- [ ] Discord bot token + permissions (read messages, create events, send messages)
- [ ] Obsidian Catalyst License (if not already held) — for CLI Early Access
- [ ] Playwright install: `pip install playwright && playwright install chromium`
- [ ] Populate `session_config.toml`
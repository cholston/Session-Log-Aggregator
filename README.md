What started as a humble script to smash two text files together has metastasized into a full post-session automation pipeline. It now logs into your FoundryVTT server to steal your own chat log, runs a macro to dump your campaign data, downloads your recording from Craig, transcribes it (locally via Whisper or by outsourcing it to Google), merges everything into a timestamped session transcript, drops the result into your Obsidian vault, and then opens Claude Code to write your session notes for you. All you have to do is paste a URL and wait.

If you also want it to schedule the next session, pass `--next-session "YYYY-MM-DD HH:MM"` and it will create a Discord event and a Google Calendar invite simultaneously. The calendar invite resolves a Google Contacts label to individual email addresses and sends them all invitations. Events default to 2.5 hours.

Archimedes is a Discord bot that lives in the same repo. He handles `/schedule-session` and `/session-recap` slash commands and is the spiritual successor to a mIRC bot of the same name.

The GUI still exists. It's fine.

## Setup

1. Copy `session_config.toml.template` to `session_config.toml` and fill in your values.
2. Create a `.env` file with your secrets (see below).
3. Install dependencies:
   ```
   pip install customtkinter openai-whisper google-genai playwright python-dotenv discord.py google-auth-oauthlib google-api-python-client
   playwright install chromium
   ```

### `.env` secrets
```
FOUNDRY_URL=https://your-foundry-server
FOUNDRY_USERNAME=your-username
FOUNDRY_PASSWORD=your-password
GEMINI_API_KEY=your-key
DISCORD_BOT_TOKEN=your-token
```

### Google Calendar setup
1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **Google Calendar API** and **Google People API**
3. Create an OAuth 2.0 credential (Desktop app) and download the JSON
4. Add yourself as a test user under OAuth consent screen → Test users
5. Set `credentials_path` in `session_config.toml` to the downloaded JSON
6. On first run a browser will open for consent; the token is cached to `gcal_token.json` after that

## Usage

```bash
# Full pipeline
python3 session_wrap.py --craig-url "https://craig.horse/rec/XXXXX?key=YYYYY"

# Full pipeline + schedule next session (Discord + Google Calendar)
python3 session_wrap.py --craig-url "..." --next-session "2026-04-26 19:00"

# Test Google Calendar in isolation (no Craig URL needed)
python3 session_wrap.py --gcal-only --next-session "2026-04-26 19:00"

# Recovery options
python3 session_wrap.py --craig-url "..." --skip-foundry --chat-log path/to/chat.txt
python3 session_wrap.py --craig-url "..." --audio-path path/to/audio.ogg --start-time "2026-04-13 19:00:00"
python3 session_wrap.py --craig-url "..." --transcript-path path/to/t.txt --start-time "..."
python3 session_wrap.py --craig-url "..." --skip-claude

# Discord bot
python3 archimedes.py

# GUI
python3 app.py
```

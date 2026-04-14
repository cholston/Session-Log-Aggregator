
from datetime import datetime, timedelta
import re


def merge_logs(fvtt_path, transcript_path, output_path, start_time, speaker_name="Player", voice_cluster_seconds=30):
    # Load full files
    with open(fvtt_path, 'r', encoding='utf-8') as f:
        fvtt_text = f.read()

    with open(transcript_path, 'r', encoding='utf-8') as f:
        google_text = f.read()

    # --- Parse FoundryVTT log ---
    fvtt_messages = []
    blocks = re.split(r'\n-+\n', fvtt_text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r'\[(.*?)\]\s*(.*?)\n(.*)', block, re.S)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%m/%d/%Y, %I:%M:%S %p")
        name = m.group(2).strip()
        content = m.group(3).rstrip()
        fvtt_messages.append((ts, name, content, 'fvtt'))

    # --- Parse Google voice transcript ---
    voice_lines = []

    for line in google_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r'\[(\d+):(\d+)(?::(\d+))?\]\s*(.*)', line)
        if not m:
            continue
        minutes, seconds, millis, text = m.groups()
        delta = timedelta(
            minutes=int(minutes),
            seconds=int(seconds),
            milliseconds=int(millis) if millis else 0
        )
        
        # We assume the user inputted local time corresponding to the time in the Fvtt logs
        actual_time = start_time + delta
        voice_lines.append((actual_time, text))

    # --- Group consecutive voice lines (30s window) ---
    grouped_voice = []
    current_ts = None
    current_text = []

    for ts, text in voice_lines:
        if current_ts is None:
            current_ts = ts
            current_text = [text]
        elif (ts - current_ts).total_seconds() <= voice_cluster_seconds:
            current_text.append(text)
        else:
            grouped_voice.append((current_ts, speaker_name, "\n".join(current_text), 'voice'))
            current_ts = ts
            current_text = [text]

    if current_ts is not None:
        grouped_voice.append((current_ts, speaker_name, "\n".join(current_text), 'voice'))

    # --- Merge and sort ---
    all_messages = fvtt_messages + grouped_voice
    all_messages.sort(key=lambda x: x[0])

    # --- Write merged output ---
    with open(output_path, "w", encoding="utf-8") as out:
        for ts, name, content, _ in all_messages:
            # We will format this differently to write standard Markdown.
            out.write(f"**[{ts.strftime('%#m/%#d/%Y, %#I:%M:%S %p')}] {name}**\n\n")
            out.write(content + "\n\n")
            out.write("---\n\n")

    return output_path

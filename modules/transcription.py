import os
import whisper

def transcribe_whisper(audio_path):
    """
    Transcribes an audio file using a locally-run OpenAI Whisper model.
    Produces a timeline-stamped transcription matching the expected output format.
    Returns the path to the saved temporary transcript text file.
    """
    try:
        print(f"Loading Whisper model...")
        model = whisper.load_model("base")

        print(f"Transcribing {audio_path}...")
        result = model.transcribe(audio_path, verbose=False)

    except Exception as e:
        # Re-raise with context so the GUI can catch it
        raise RuntimeError(f"Whisper transcription failed: {str(e)}") from e

    lines = []
    for segment in result.get("segments", []):
        start_sec = segment["start"]
        minutes = int(start_sec // 60)
        seconds = int(start_sec % 60)
        timestamp = f"[{minutes:02d}:{seconds:02d}]"
        text = segment["text"].strip()
        lines.append(f"{timestamp} {text}")

    transcript_text = "\n".join(lines)

    output_path = os.path.join(os.path.dirname(os.path.abspath(audio_path)), "transcript.txt")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
    except Exception as e:
        raise RuntimeError(f"Failed to write temporary transcript file: {str(e)}") from e

    print("Transcription complete.")
    return output_path

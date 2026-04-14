import os
from google import genai
from google.genai import types
import time

def transcribe_gemini(audio_path, api_key):
    """
    Uploads an audio file to Google Gemini and prompts it to generate
    a timeline-stamped transcription matching the expected output format.
    Returns the path to the saved temporary transcript text file.
    """
    try:
        client = genai.Client(api_key=api_key)

        print(f"Uploading {audio_path}...")
        audio_file = client.files.upload(file=audio_path)

        # Wait for processing if necessary
        while audio_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(2)
            audio_file = client.files.get(name=audio_file.name)
        print()

        if audio_file.state.name == "FAILED":
            raise Exception("Audio file processing failed on Google servers.")

        prompt = (
            "You are an expert transcriber. Transcribe the following audio file. "
            "Provide your transcription as a plain text log with timestamps. "
            "The format for each line MUST be `[MM:SS] Text content here` or `[MM:SS:ms] Text content here`."
            "Do not include any other markdown formatting or conversational text."
        )

        print("Generating Transcript...")
        
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=[audio_file, prompt]
        )
        
        # Optional cleanup of the remote file (good practice)
        try:
            client.files.delete(name=audio_file.name)
        except Exception as e:
            print(f"Warning: Failed to delete remote file: {e}")

        transcript_text = response.text
        
        output_path = os.path.join(os.path.dirname(os.path.abspath(audio_path)), "transcript.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        return output_path
    except Exception as e:
        # Re-raise with context so the GUI can catch it
        raise RuntimeError(f"Gemini transcription failed: {str(e)}") from e

"""
Download a Craig recording from craig.horse.

Craig workflow:
  1. Navigate to https://craig.horse/rec/<id>?key=<key>
  2. Wait for SvelteKit to render (networkidle)
  3. Extract startTime from the embedded JSON in page source
  4. Click the "Ogg Vorbis" button in the Multi-track section
  5. Wait for the ZIP file to download (Craig processes it server-side first)
  6. Extract the first .ogg file from the ZIP
  7. Return (ogg_path, start_datetime)
"""

import os
import re
import time
import zipfile
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright


# Craig timestamps are always UTC (ISO 8601 with Z suffix)
_DATETIME_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
]


def _parse_craig_start_time(page) -> datetime | None:
    """Extract startTime from the SvelteKit JSON embedded in the page source.
    Returns a naive UTC datetime or None if not found."""
    try:
        html = page.content()
        # SvelteKit embeds recording data in a script tag as:
        # startTime:"2026-04-13T23:02:47.365Z"  (no quotes around key)
        match = re.search(r'startTime:"([^"]+)"', html)
        if match:
            raw = match.group(1)
            for fmt in _DATETIME_FORMATS:
                try:
                    # Parse as UTC, then convert to local system time (handles DST automatically)
                    dt_utc = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    dt_local = dt_utc.astimezone().replace(tzinfo=None)
                    print(f"Craig start time (UTC): {dt_utc}  →  local: {dt_local}")
                    return dt_local
                except ValueError:
                    continue
    except Exception as e:
        print(f"Warning: could not parse start time from page source: {e}")

    return None


def _click_ogg_and_download(page):
    """Click the Ogg Vorbis format button, then confirm in the preview modal.

    Craig's flow:
      1. Click "Ogg Vorbis" → a modal appears showing ZIP contents
      2. Click the "Download" button in the modal → triggers the actual file download

    Returns the Playwright Download object or None.
    """
    # Step 1: click the format selector button
    format_btn = page.locator("button:has-text('Ogg Vorbis')").first
    if not format_btn.is_visible(timeout=5000):
        print("Error: 'Ogg Vorbis' button not found on page.")
        return None

    # Clicking "Ogg Vorbis" opens a modal; Craig then processes the recording
    # server-side (can take 3-5 min for a full session) and shows a Download button.
    # The modal backdrop intercepts Playwright's normal click, so we use
    # dispatch_event("click") to fire directly on the element.
    print("Clicking 'Ogg Vorbis' format button...")
    format_btn.dispatch_event("click")

    # Wait for the Download button to appear in the modal, then fire it.
    # <button class="svelte-1klcfz0">Download <span class="badge ...">NNNkb</span></button>
    print("Waiting for Craig to process recording (up to 6 min)...")
    try:
        download_btn = page.locator("button.svelte-1klcfz0").filter(has_text="Download").first
        download_btn.wait_for(state="visible", timeout=360000)
        print("Download button ready — triggering download...")
        with page.expect_download(timeout=60000) as dl_info:
            download_btn.dispatch_event("click")
        return dl_info.value
    except Exception as e:
        print(f"Error triggering download: {e}")
        return None


def _extract_ogg(zip_path: str, output_dir: str, speaker_name: str = "") -> str | None:
    """Extract the speaker's .ogg file from the ZIP and return its path.

    Craig names per-user tracks like "1-debinani.ogg". If speaker_name is set,
    prefer the file whose name contains that string (case-insensitive).
    Falls back to the first .ogg in the ZIP if no match is found.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        ogg_files = [name for name in zf.namelist() if name.lower().endswith(".ogg")]
        if not ogg_files:
            print(f"No .ogg files found in {zip_path}. Contents: {zf.namelist()}")
            return None

        print(f"OGG files in ZIP: {ogg_files}")
        target = ogg_files[0]
        if speaker_name:
            matches = [f for f in ogg_files if speaker_name.lower() in os.path.basename(f).lower()]
            if matches:
                target = matches[0]
                print(f"Matched speaker '{speaker_name}': {target}")
            else:
                print(f"Warning: no OGG file matching '{speaker_name}' found — using {target}")

        out_name = os.path.basename(target)
        out_path = os.path.join(output_dir, out_name)
        with zf.open(target) as src, open(out_path, "wb") as dst:
            dst.write(src.read())
        print(f"Extracted {out_name} to {out_path}")
        return out_path


def download_craig_recording(craig_url: str, output_dir: str = "testdata", speaker_name: str = "") -> tuple[str | None, datetime | None]:
    """Download a Craig recording and return (ogg_path, start_datetime).

    Args:
        craig_url:  Full URL to the Craig recording page, e.g. https://craig.horse/rec/XXXXX
        output_dir: Directory for downloaded ZIP and extracted OGG.

    Returns:
        Tuple of (path to extracted .ogg file, recording start datetime).
        Either value may be None if that step failed.
    """
    os.makedirs(output_dir, exist_ok=True)

    ogg_path = None
    start_time = None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_context().new_page()

            print(f"Navigating to {craig_url}...")
            page.goto(craig_url, wait_until="networkidle")

            # Scrape start time before triggering download navigation
            start_time = _parse_craig_start_time(page)
            if start_time:
                print(f"Craig recording start time: {start_time}")
            else:
                print("Warning: Could not scrape start time from Craig page.")

            # Trigger OGG download
            download = _click_ogg_and_download(page)
            if not download:
                print("Error: Craig download did not start.")
                browser.close()
                return None, start_time

            # Save the ZIP
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            zip_path = os.path.join(output_dir, f"craig-{timestamp}.zip")
            print(f"Saving ZIP to {zip_path}...")
            download.save_as(zip_path)

            browser.close()

        # Extract OGG from ZIP
        ogg_path = _extract_ogg(zip_path, output_dir, speaker_name)

        # Clean up ZIP
        try:
            os.remove(zip_path)
        except OSError:
            pass

    except Exception as e:
        print(f"Craig download failed: {e}")

    return ogg_path, start_time

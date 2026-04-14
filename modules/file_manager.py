"""Copy session outputs into the Obsidian vault."""

import os
import shutil
from datetime import datetime


def copy_to_vault(
    transcript_path: str,
    campaign_data_path: str | None,
    obsidian_session_dir: str,
    obsidian_campaign_data_dir: str,
    session_date: datetime | None = None,
) -> dict[str, str]:
    """Copy the merged transcript and campaign data export into the Obsidian vault.

    Args:
        transcript_path:          Path to the merged session transcript (.md)
        campaign_data_path:       Path to the Foundry campaign data export, or None
        obsidian_session_dir:     Vault folder where session notes live
        obsidian_campaign_data_dir: Vault folder where campaign data export is placed
        session_date:             Used to name the session note file; defaults to today

    Returns:
        Dict with keys 'transcript' and 'campaign_data' pointing to vault-side paths.
    """
    os.makedirs(obsidian_session_dir, exist_ok=True)
    os.makedirs(obsidian_campaign_data_dir, exist_ok=True)

    result = {}
    date_str = (session_date or datetime.now()).strftime("%Y-%m-%d")

    # Copy transcript → vault session dir, rename to date-based filename
    transcript_dest = os.path.join(obsidian_session_dir, f"{date_str}-Transcript.md")
    shutil.copy2(transcript_path, transcript_dest)
    print(f"Transcript copied to {transcript_dest}")
    result["transcript"] = transcript_dest

    # Copy campaign data if present
    if campaign_data_path and os.path.exists(campaign_data_path):
        campaign_dest = os.path.join(
            obsidian_campaign_data_dir, f"{date_str} - foundry-snapshot.md"
        )
        shutil.copy2(campaign_data_path, campaign_dest)
        print(f"Campaign data copied to {campaign_dest}")
        result["campaign_data"] = campaign_dest
    else:
        result["campaign_data"] = None

    return result

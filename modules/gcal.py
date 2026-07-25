"""
Google Calendar event creation for post-session scheduling.

Requires google-auth-oauthlib and google-api-python-client:
    pip install google-auth-oauthlib google-api-python-client

On first run, opens a browser for OAuth2 consent and caches the token to
token_path for all future runs.

contact_group is matched by name against your Google Contacts labels.
The People API resolves the label to member email addresses, which become
event attendees. If the cached token predates the contacts scope being added,
delete gcal_token.json and re-run to trigger a fresh OAuth consent.
"""

import json
import os
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts.readonly",
]


def _token_file_scopes(token_path: str) -> set[str]:
    """
    Read the scopes actually recorded in the cached token file.

    Do not use creds.scopes for this. Credentials.from_authorized_user_file
    only falls back to the file's scopes when its scopes argument is None —
    pass SCOPES and creds.scopes comes back as exactly SCOPES no matter what
    the token was granted, so comparing the two always says they match.
    """
    try:
        with open(token_path) as f:
            scopes = json.load(f).get("scopes") or []
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(scopes, str):
        scopes = scopes.split(" ")
    return set(scopes)


def _get_credentials(credentials_path: str, token_path: str) -> Credentials:
    creds = None
    if os.path.exists(token_path):
        # Force re-auth if the cached token is missing any required scope.
        if set(SCOPES).issubset(_token_file_scopes(token_path)):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def validate_credentials(
    credentials_path: str,
    token_path: str,
    calendar_id: str = "primary",
    contact_group: str = "",
) -> bool:
    """
    Check whether the cached OAuth token is still usable, without ever opening
    a browser. Prints a per-stage report and returns True only if both the
    Calendar and People APIs answered.

    An expired access token is not a failure on its own — they live about an
    hour, so the cached one is almost always stale between runs. The real test
    is whether the refresh token still works; a successful silent refresh is
    written back to token_path so the next run starts warm.
    """
    print(f"  Token file  : {token_path}")
    print(f"  Credentials : {credentials_path} "
          f"({'found' if os.path.exists(credentials_path) else 'MISSING'})")

    if not os.path.exists(token_path):
        print("  RESULT: no cached token - the next run will open the OAuth consent browser.")
        return False

    missing = set(SCOPES) - _token_file_scopes(token_path)
    if missing:
        print(f"  Scopes      : MISSING {sorted(missing)}")
        print(f"  RESULT: delete {token_path} and re-run to re-consent with the full scope set.")
        return False
    print("  Scopes      : ok (calendar.events + contacts.readonly)")

    creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    print(f"  Expiry      : {creds.expiry} UTC "
          f"({'still valid' if creds.valid else 'stale - will refresh'})")

    if not creds.valid:
        if not creds.refresh_token:
            print("  Refresh     : NO REFRESH TOKEN")
            print(f"  RESULT: delete {token_path} and re-run to re-consent.")
            return False
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            print(f"  Refresh     : FAILED - {exc}")
            print("  RESULT: the refresh token is dead. If the OAuth consent screen is still in")
            print("          'Testing' status, Google expires refresh tokens after 7 days.")
            print(f"          Delete {token_path} and re-run to re-consent.")
            return False
        print(f"  Refresh     : ok - new expiry {creds.expiry} UTC")
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    try:
        calendar_service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        calendar_service.events().list(
            calendarId=calendar_id,
            maxResults=1,
            timeMin=datetime.now(timezone.utc).isoformat(),
        ).execute()
        print(f"  Calendar API: ok (calendar '{calendar_id}' readable)")
    except Exception as exc:
        print(f"  Calendar API: FAILED - {type(exc).__name__}: {exc}")
        print("  RESULT: check that the Google Calendar API is enabled for this project.")
        return False

    try:
        people_service = build("people", "v1", credentials=creds, cache_discovery=False)
        if contact_group:
            emails = _resolve_contact_group(people_service, contact_group)
            print(f"  People API  : ok - group '{contact_group}' resolved to "
                  f"{len(emails)} attendee(s): {', '.join(emails)}")
        else:
            people_service.contactGroups().list(pageSize=1).execute()
            print("  People API  : ok (no contact_group configured, group lookup skipped)")
    except ValueError as exc:
        # Raised by _resolve_contact_group — the token is fine, the label isn't.
        print(f"  People API  : reachable, but group lookup failed - {exc}")
        return False
    except Exception as exc:
        print(f"  People API  : FAILED - {type(exc).__name__}: {exc}")
        print("  RESULT: check that the Google People API is enabled for this project.")
        return False

    print("  RESULT: token is active and both APIs work.")
    return True


def _resolve_contact_group(people_service, group_name: str) -> list[str]:
    """
    Look up a Google Contacts label by name and return all member email addresses.
    Raises ValueError if the group is not found or has no members with emails.
    """
    groups_result = people_service.contactGroups().list(pageSize=200).execute()
    groups = groups_result.get("contactGroups", [])

    match = next(
        (g for g in groups if g.get("name", "").lower() == group_name.lower()), None
    )
    if not match:
        available = [g.get("name") for g in groups if g.get("groupType") == "USER_CONTACT_GROUP"]
        raise ValueError(
            f"Contact group '{group_name}' not found. "
            f"Available groups: {available}"
        )

    resource_name = match["resourceName"]
    member_count = match.get("memberCount", 0)
    if member_count == 0:
        raise ValueError(f"Contact group '{group_name}' has no members.")

    group_detail = (
        people_service.contactGroups()
        .get(resourceName=resource_name, maxMembers=500)
        .execute()
    )
    member_resource_names = group_detail.get("memberResourceNames", [])
    if not member_resource_names:
        raise ValueError(f"Contact group '{group_name}' has no members.")

    batch = (
        people_service.people()
        .getBatchGet(
            resourceNames=member_resource_names,
            personFields="emailAddresses,names",
        )
        .execute()
    )

    emails = []
    for response in batch.get("responses", []):
        person = response.get("person", {})
        for addr in person.get("emailAddresses", []):
            value = addr.get("value", "").strip()
            if value:
                emails.append(value)
                break  # one address per person is enough

    if not emails:
        raise ValueError(f"No email addresses found for any member of '{group_name}'.")

    return emails


def create_calendar_event(
    credentials_path: str,
    token_path: str,
    calendar_id: str,
    event_name: str,
    start_time: datetime,
    end_time: datetime,
    contact_group: str,
    description: str = "",
) -> str:
    """
    Create a Google Calendar event and invite all members of a Google Contacts
    label (contact_group) by resolving their email addresses via the People API.

    Returns the event's web link.
    """
    creds = _get_credentials(credentials_path, token_path)
    calendar_service = build("calendar", "v3", credentials=creds)
    people_service = build("people", "v1", credentials=creds)

    print(f"  Resolving contact group '{contact_group}'...")
    emails = _resolve_contact_group(people_service, contact_group)
    print(f"  Found {len(emails)} attendee(s): {', '.join(emails)}")

    local_tz = datetime.now().astimezone().tzinfo

    def _as_aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=local_tz)

    event = {
        "summary": event_name,
        "description": description,
        "start": {"dateTime": _as_aware(start_time).isoformat()},
        "end": {"dateTime": _as_aware(end_time).isoformat()},
        "attendees": [{"email": e} for e in emails],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 24 * 60},
                {"method": "popup", "minutes": 30},
            ],
        },
    }

    result = (
        calendar_service.events()
        .insert(calendarId=calendar_id, body=event, sendUpdates="all")
        .execute()
    )

    return result.get("htmlLink", "")

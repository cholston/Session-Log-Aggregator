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

import os
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts.readonly",
]


def _get_credentials(credentials_path: str, token_path: str) -> Credentials:
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        # Force re-auth if the cached token is missing any required scope.
        # creds.scopes can be None for older tokens, treat that as empty.
        if creds and not set(SCOPES).issubset(set(creds.scopes or [])):
            creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


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

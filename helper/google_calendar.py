import os
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import dotenv_values

# Load env values
env_vars = dotenv_values(".env")
CALENDAR_ID = env_vars.get("CALENDAR_ID")

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_calendar_service():
    """Shows basic usage of the Google Calendar API."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    try:
        service = build('calendar', 'v3', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred while building calendar service: {error}')
        return None

# --- FINAL FIXED create_or_update_ipo_event function ---
def create_or_update_ipo_event(ipo_data, service, status_key=None):
    """
    Creates or updates a Google Calendar event for an IPO. 
    It ensures only one event per IPO exists (using a unique ID derived from the name).
    The event title is prefixed by the status_key (e.g., 'APPLY', 'REVIEW').
    """
    
    # --- FIX: Define the valid status keys and their prefixes ---
    # These map the AI decision and application status to a calendar title prefix.
    # The missing keys 'APPLY', 'REVIEW', and 'AVOID' have been added.
    STATUS_TITLE_PREFIX = {
        "APPLY": "📝 Apply - ",
        "REVIEW": "🔍 Review - ",
        "AVOID": "🚫 Avoid - ",
        "APPLIED": "✅ APPLIED - ",
        # Assuming LISTING_DATE is used for the Listing Date event type
        "LISTING_DATE": "🔔 Listing Date - ", 
    }
    
    ipo_name = ipo_data.get('LiveIPOName')

    # Handle both legacy and nested structures
    details = ipo_data.get('LiveIPODetails', {})
    subs = ipo_data.get('LiveIPOSubscriptionDetails', {})

    price_range = (
    ipo_data.get('PriceRange')
    or subs.get('IPO Price')
    )
    
    ipo_link = (
    ipo_data.get('Link')
    or details.get('ipo_link')
    )
    
    ipo_start_date_str = (
        ipo_data.get('IPO_Start_Date')
        or details.get('start_date')
    )
    ipo_end_date_str = (
        ipo_data.get('IPO_End_Date')
        or details.get('end_date')
    )
    listing_date_str = (
        ipo_data.get('Listing Date')
        or details.get('listing_date')
    )
    
    # Subscription info
    sub_total = subs.get('Total', 'N/A')
    sub_qib = subs.get('QIB', 'N/A')
    sub_nii = subs.get('NII', 'N/A')
    sub_rii = subs.get('RII', 'N/A')
    sub_gmp = subs.get('GMP', 'N/A')
    sub_pe = subs.get('P/E', 'N/A')
    
    if not service or not ipo_name or not ipo_start_date_str:
        print("Calendar: Missing service, IPO name, or start date. Skipping event creation.")
        return None

    # Determine the status prefix
    prefix = ""
    if status_key:
        # Use .upper() to ensure the key matches the defined map, regardless of case
        prefix = STATUS_TITLE_PREFIX.get(status_key.upper(), "")
        
        if not prefix and status_key.upper() in ["APPLY", "REVIEW", "AVOID"]:
            # This check is now redundant due to the fix, but kept for future debugging if new statuses appear.
            print(f"Calendar: Invalid status key: {status_key}. Using default prefix.")
            
    # Base title is just the IPO Name, used for searching existing events
    event_title_base = ipo_name 
    final_title = f"{prefix}{event_title_base}"

    # Determine event dates
    # IPO events are generally multi-day, spanning start to end date (inclusive)
    # The end date in Google Calendar API is exclusive, so we add one day to the IPO End Date.
    try:
        if ipo_end_date_str:
            start_date = datetime.datetime.strptime(ipo_start_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.strptime(ipo_end_date_str, '%Y-%m-%d').date()
            # Calendar end date is exclusive, so add one day to make it inclusive
            calendar_end_date = (end_date + datetime.timedelta(days=1)).isoformat()
            
            # Use the start date for the event ID to group all status updates
            event_id_base = f"{ipo_name.replace(' ', '').lower()}{start_date.strftime('%Y%m%d')}"
            
            # The event body uses the date range
            event_date_block = {
                'start': {'date': ipo_start_date_str},
                'end': {'date': calendar_end_date},
            }
            
        # Optional: Handle a specific LISTING_DATE event if it's the target status
        elif status_key == "LISTING_DATE" and listing_date_str:
            listing_date = datetime.datetime.strptime(listing_date_str, '%Y-%m-%d').date()
            calendar_end_date = (listing_date + datetime.timedelta(days=1)).isoformat()
            
            event_id_base = f"{ipo_name.replace(' ', '').lower()}listing{listing_date.strftime('%Y%m%d')}"
            
            event_date_block = {
                'start': {'date': listing_date_str},
                'end': {'date': calendar_end_date},
            }
        else:
            # Fallback for a single day event if only start date is available (rare for IPO)
            start_date = datetime.datetime.strptime(ipo_start_date_str, '%Y-%m-%d').date()
            calendar_end_date = (start_date + datetime.timedelta(days=1)).isoformat()
            
            event_id_base = f"{ipo_name.replace(' ', '').lower()}{start_date.strftime('%Y%m%d')}"
            
            event_date_block = {
                'start': {'date': ipo_start_date_str},
                'end': {'date': calendar_end_date},
            }

    except ValueError as e:
        print(f"Calendar: Error parsing dates for {ipo_name}: {e}. Skipping event.")
        return None

    # Construct the unique calendar ID for this specific event type (e.g., IPO_RANGE or LISTING)
    # This ID must be less than 1024 characters and only contain valid characters
    event_id = event_id_base.encode('utf-8').hex()[:26] # Google Calendar max length is 26 chars for ID

    # Generate the description content
    description = f"""
        **Recommendation**: {ipo_data.get('Recommendation', 'N/A')} ({ipo_data.get('RecommendationSource', 'N/A')})
        **IPO Date**: {ipo_start_date_str} → {ipo_end_date_str}
        **Listing Date**: {listing_date_str or 'N/A'}
        **Price Range**: ₹{price_range or 'N/A'}
        **Link**: {ipo_link or 'N/A'}

        📊 **Live Subscription (as of now)**  
        Total: {sub_total}×  
        QIB: {sub_qib}×  
        NII: {sub_nii}×  
        RII: {sub_rii}×  
        GMP: {sub_gmp}  
        P/E: {sub_pe}
        """.strip()
    
    # Add subscription details if available
    # subscription_details = ipo_data.get('SubscriptionDetails', {})
    # if subscription_details:
    #     description_lines.append("\n**Subscription Status (Total)**: {Total}".format(**subscription_details))
    #     description_lines.append(f"QIB: {subscription_details.get('QIB', 'N/A')}, NII: {subscription_details.get('NII', 'N/A')}, Retail: {subscription_details.get('Retail', 'N/A')}")
    #     description_lines.append(f"SHNI: {subscription_details.get('SHNI', 'N/A')}, BHNI: {subscription_details.get('BHNI', 'N/A')}")
    
    # description = '\n'.join(description_lines)

    event = {
        'id': event_id, # Use a predictable ID for upsert logic
        'summary': final_title,
        'description': description,
        **event_date_block,
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'popup', 'minutes': 60 * 24},  # 1 day reminder
            ],
        },
    }

    try:
        # 1. First, search for an existing event by querying for the IPO name in the summary
        q_term = f"{event_title_base}"
        now = datetime.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
        
        events_result = service.events().list(
            calendarId=CALENDAR_ID, 
            q=q_term,
            timeMin=now, # Search from now onwards
            maxResults=10, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        # Find the event that exactly matches the base IPO Name (ignoring the prefix)
        existing_event = next((e for e in events if e.get('summary', '').endswith(event_title_base)), None)

        if existing_event:
            # 4. If found, UPDATE the existing event
            event['summary'] = final_title # Ensure title is updated too
            # Remove the 'id' field for the update operation
            del event['id'] 
            updated_event = service.events().update(
                calendarId=CALENDAR_ID,
                eventId=existing_event['id'], 
                body=event
            ).execute()
            print(f"Calendar: Updated event for {event_title_base} (Found via Search).")
            return updated_event
        else:
            # 5. If not found by search, attempt INSERT using the predictable ID.
            # If a 409 (conflict) occurs here, it means the ID exists but was not searchable.
            new_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"Calendar: Created new event for {event_title_base}.")
            return new_event

    except HttpError as error:
        # --- CRITICAL HANDLING FOR 409 ---
        if error.resp.status == 409:
            print(f"Calendar Error during creation/update for {ipo_name}: Permanent ID conflict (409). You may need to wait for Google Calendar to purge the old ID.")
            return None # Fail gracefully to prevent crashing the bot
        else:
            # Handle all other errors
            print(f'Calendar Error during creation/update for {ipo_name}: {error}')
            return None

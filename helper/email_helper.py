import os
import re
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from time import sleep

# If modifying these scopes, delete the file token.json.
# We need 'readonly' to read emails.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify'] 
TOKEN_FILE = 'token_gmail.json' # Use a separate token file for clarity

def get_gmail_service():
    """Authenticates and returns the authorized Gmail API service object."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    try:
        service = build('gmail', 'v1', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred while building Gmail service: {error}')
        return None

def get_otp_from_email(service, subject_line, sender_email='HDFC Bank') -> str:
    """
    Searches for the latest unread email with a specific subject, 
    extracts the OTP, and marks the email as read.
    """
    # 1. Create the search query
    query = f'subject:"{subject_line}" from:"{sender_email}" is:unread'
    print(f"Searching for email with query: '{query}'")

    # Give the system time to send and receive the email
    # sleep(10) 

    # 2. Get the list of messages
    try:
        sleep(30)  # Wait before the first attempt
        response = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = response.get('messages', [])

        if not messages:
            print("No new email found. Retrying in 30 seconds...")
            sleep(30)
            # Second attempt to find the message
            response = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
            messages = response.get('messages', [])
            
            if not messages:
                print("No new email found. Retrying in 15 seconds...")
                sleep(15)
                # Second attempt to find the message
                response = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
                messages = response.get('messages', [])
                if not messages:
                    print("Could not find the OTP email after retries.")
                    return None
        
        print("Email found. Processing...")
        msg_id = messages[0]['id']
        msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg.get('payload', {})
        body_text = ""

        def extract_text_from_payload(payload):
            """Recursively extract text/plain or text/html body from Gmail message."""
            if not payload:
                return None

            mime_type = payload.get("mimeType", "")
            body = payload.get("body", {})
            data = body.get("data")

            # 1️⃣ Direct text/plain body
            if mime_type == "text/plain" and data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

            # 2️⃣ Some emails only have text/html, extract from there
            if mime_type == "text/html" and data:
                html_content = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                # Remove HTML tags just in case
                import re
                return re.sub(r"<[^>]+>", "", html_content)

            # 3️⃣ If the message has subparts, recurse
            parts = payload.get("parts", [])
            for part in parts:
                result = extract_text_from_payload(part)
                if result:
                    return result

            return None

        body_text = extract_text_from_payload(payload)

        # 4️⃣ Fallback: top-level data
        if not body_text and "data" in payload.get("body", {}):
            data = payload["body"]["data"]
            body_text = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        if not body_text:
            print("Error: Email body could not be extracted.")
            print("Debug payload structure:", list(payload.keys()))
            return None

        print("✅ Email body successfully extracted:")
        # print(body_text[:400])  # print first few lines for verification


        # 5. Extract the OTP using regex
        # Pattern: 'OTP to login is ' followed by 6 digits
        otp_match = re.search(r'OTP to login is (\d{6})', body_text)
        
        if otp_match:
            otp = otp_match.group(1)
            print(f"Successfully extracted OTP: {otp}")
            
            # 6. Mark the email as read
            service.users().messages().modify(
                userId='me', 
                id=msg_id, 
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print("Email marked as read.")
            return otp
        else:
            print("Error: Could not find OTP in the email body.")
            # print(f"Raw Email Body Snippet: {body_text[:200]}") # Debugging print
            return None

    except HttpError as error:
        print(f'Gmail API error: {error}')
        return None
    except Exception as e:
        print(f'An unexpected error occurred during email processing: {e}')
        return None
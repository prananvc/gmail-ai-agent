import os.path
import base64
import os  # Added for environment variables
import google.generativeai as genai  # Added for Gemini
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# --- Load .env variables ---
from dotenv import load_dotenv
load_dotenv()
# --- End Load .env variables ---

from google.adk.tools import FunctionTool

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
# --- Modified Scopes ---
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # Changed to allow sending/replyingE"
# --- End Modified Scopes ---
print("IMPORTANT: If you changed SCOPES, delete token.json and re-authenticate.")

# --- Gemini Configuration ---
# NOTE: In a real agent, manage API keys and model initialization securely
#       within the agent's setup or context.
try:
    # Configure the Gemini API key (Example: Load from environment or secure config)
    gemini_api_key = os.environ.get("GOOGLE_API_KEY") # Prioritize env var, remove default fallback for clarity
    # --- TEMPORARY DEBUG: Hardcode the new key ---
    # gemini_api_key = "AIzaSyCwje0v5U9NQ15wcFHjF10sXnsOuAILkdE"
    # print("[DEBUG] USING HARDCODED API KEY FOR TESTING!")
    # --- END TEMPORARY DEBUG ---
    if not gemini_api_key:
        # Make the error message clearer if key is not found
        raise ValueError("GOOGLE_API_KEY not found in environment variables. Please set it in the .env file.")
    genai.configure(api_key=gemini_api_key)
    # Initialize the Gemini model
    # gemini_model = genai.GenerativeModel('gemini-pro') # Use standard gemini-pro model
    # print("[DEBUG] Using gemini-pro model.") # ADDED DEBUG
    gemini_model = genai.GenerativeModel('gemini-1.5-flash') # Revert to gemini-1.5-flash
except ValueError as e:
    print(f"Error configuring Gemini: {e}")
    gemini_model = None
except Exception as e:
    print(f"An unexpected error occurred during Gemini configuration: {e}")
    gemini_model = None
# --- End Gemini Configuration ---


# --- Helper Function to Get Email Body ---
def get_email_body(payload):
    """Parses the email payload to find the text body."""
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain":
                data = part.get("body", {}).get("data")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8")
                    break  # Prefer plain text
            elif mime_type == "text/html":
                # Fallback to HTML if plain text not found yet
                if not body:
                    data = part.get("body", {}).get("data")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
            elif "parts" in part:
                # Recursively check nested parts
                nested_body = get_email_body(part)
                if nested_body:
                    body = nested_body
                    if mime_type == "text/plain":  # Prioritize plain text from nested parts
                        break
    elif payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8")

    # If body is still empty, check the top-level body (for non-multipart emails)
    if not body and payload.get("mimeType", "").startswith("text/"):
        data = payload.get("body", {}).get("data")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8")

    return body
# --- End Helper Function ---


# --- Added Function to List Recent Emails ---
def list_recent_emails(user_id: str, max_results: int) -> dict:
    """Lists the most recent emails from the user's inbox.

    Args:
        user_id: The user's email address or 'me'.
        max_results: The maximum number of emails to retrieve.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'emails' (a list of email details) on success,
        or 'error_message' on failure. Each email detail includes
        'id', 'threadId', 'subject', 'from', and 'date'.
    """
    service = get_gmail_service()
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}

    try:
        # List messages
        results = service.users().messages().list(
            userId=user_id, labelIds=['INBOX'], maxResults=max_results
        ).execute()
        messages = results.get('messages', [])

        if not messages:
            return {"status": "success", "emails": []} # Return success with empty list

        email_list = []
        for msg_stub in messages:
            msg_id = msg_stub['id']
            # Fetch metadata for each message
            msg = service.users().messages().get(
                userId=user_id, id=msg_id, format='metadata',
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()

            payload = msg.get('payload', {})
            headers = payload.get('headers', [])
            subject = 'No Subject'
            sender = 'Unknown Sender'
            date = 'No Date'

            for header in headers:
                name = header['name'].lower()
                if name == 'subject':
                    subject = header['value']
                elif name == 'from':
                    sender = header['value']
                elif name == 'date':
                    date = header['value']

            email_list.append({
                'id': msg_id,
                'threadId': msg.get('threadId'),
                'subject': subject,
                'from': sender,
                'date': date
            })

        return {"status": "success", "emails": email_list}

    except HttpError as error:
        return {"status": "error", "error_message": f"An API error occurred listing emails: {error}"}
    except Exception as e:
        return {"status": "error", "error_message": f"An unexpected error occurred listing emails: {e}"}
# --- End Added Function to List Recent Emails ---


# --- Summarization Function ---
def summarize_email_with_gemini(user_id: str, email_id: str) -> dict:
    """Fetches a specific email by its ID and summarizes its content using an LLM.
       Requires Gmail service to be available via get_gmail_service().

    Args:
        user_id: The user's email address or 'me'.
        email_id: The ID of the email message to summarize.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'summary', 'subject', 'original_body', 'sender_email',
        'thread_id', 'original_message_id', 'references' on success,
        or 'error_message' on failure.
    """
    service = get_gmail_service() # Get service when function is called
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}
    if not gemini_model:
        return {"status": "error", "error_message": "Gemini model not initialized."}

    try:
        # Get the full email content
        message = service.users().messages().get(userId=user_id, id=email_id, format='full').execute()
        payload = message.get('payload', {})
        thread_id = message.get('threadId') # Get thread ID

        # Extract headers
        headers = payload.get('headers', [])
        subject = 'No Subject'
        sender_email = ''
        original_message_id = ''
        references = ''
        for header in headers:
            name = header['name'].lower()
            if name == 'subject':
                subject = header['value']
            elif name == 'from':
                 if '<' in header['value'] and '>' in header['value']:
                    sender_email = header['value'][header['value'].find('<')+1:header['value'].find('>')]
                 else:
                    sender_email = header['value'] # Handle cases without <>
            elif name == 'message-id':
                original_message_id = header['value']
            elif name == 'references':
                references = header['value']


        # Extract body
        email_body = get_email_body(payload)

        if not email_body:
            return {"status": "error", "error_message": "Could not extract email body."}

        # Summarize using Gemini
        prompt = f"Summarize the following email concisely:\\n\\nSubject: {subject}\\n\\nBody:\\n{email_body[:3000]}\\n\\nSummary:" # Limit body length
        # --- ADDED DEBUG ---
        # Print the first 500 chars of the prompt to check its content
        # --- END ADDED DEBUG ---
        response = gemini_model.generate_content(prompt)

        return {
            "status": "success",
            "summary": response.text,
            "subject": subject,
            "original_body": email_body,
            "sender_email": sender_email, # Add sender
            "thread_id": thread_id, # Add thread ID
            "original_message_id": original_message_id, # Add message ID
            "references": references # Add references
        }

    except HttpError as error:
        return {"status": "error", "error_message": f"An API error occurred fetching email {email_id}: {error}"}
    except Exception as e:
        # Include the specific exception type and message in the error
        error_type = type(e).__name__
        return {"status": "error", "error_message": f"An unexpected error occurred during summarization: {error_type}: {e}"}
# --- End Summarization Function ---


# --- Added Function to Generate Reply ---
def generate_reply_with_gemini(original_subject: str, original_body: str) -> dict:
    """Generates a draft reply email body using an LLM based on the original email.

    Args:
        original_subject: The subject line of the email being replied to.
        original_body: The body content of the email being replied to.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'reply_body' on success or 'error_message' on failure.
    """
    if not gemini_model:
         return {"status": "error", "error_message": "Gemini model not initialized."}
    if not original_body:
        return {"status": "error", "error_message": "Cannot generate reply without original email body."}

    try:
        prompt = f"""Generate a helpful and concise reply draft for the following email.
        Keep the reply professional and address the main points. Do not include greetings or closings like "Hi" or "Best regards".

        Original Email Subject: {original_subject}
        Original Email Body:
        ---
        {original_body[:2000]}
        ---

        Generated Reply Draft:""" # Limit body length

        response = gemini_model.generate_content(prompt)
        return {"status": "success", "reply_body": response.text}

    except Exception as e:
        # Add print statement for debugging
        error_type = type(e).__name__
        return {"status": "error", "error_message": f"An error occurred during reply generation: {error_type}: {e}"}
# --- End Added Function to Generate Reply ---


# --- Added Function to Create Reply Message ---
def create_reply_message(sender, to, subject, reply_body, thread_id, original_message_id, references):
    """Create a MIME message for replying to an email thread."""
    message = MIMEMultipart('related')
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject

    # Set threading headers
    message['In-Reply-To'] = original_message_id
    message['References'] = references if references else original_message_id

    # Attach the reply body as plain text
    msg_text = MIMEText(reply_body, 'plain')
    message.attach(msg_text)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    return {'raw': raw_message, 'threadId': thread_id}
# --- End Added Function to Create Reply Message ---


# --- Added Function to Send Reply ---
def send_reply(user_id: str, to: str, sender: str, subject: str, reply_body: str, thread_id: str, original_message_id: str, references: str) -> dict:
    """Creates and sends a reply email within a specific thread.
       Requires Gmail service to be available via get_gmail_service().

    Args:
        user_id: The user's email address or 'me'.
        to: The recipient's email address.
        sender: The sender's email address (should be the authenticated user).
        subject: The subject line for the reply email.
        reply_body: The plain text content of the reply.
        thread_id: The ID of the thread to reply within.
        original_message_id: The Message-ID header of the message being replied to.
        references: The References header content for threading.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'message_id' on success or 'error_message' on failure.
    """
    service = get_gmail_service() # Get service when function is called
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}
    try:
        # Determine sender's actual email if 'me' is used
        if sender.lower() == 'me':
             profile = service.users().getProfile(userId='me').execute()
             actual_sender = profile.get('emailAddress')
             if not actual_sender:
                 return {"status": "error", "error_message": "Could not determine sender email address from profile."}
        else:
            actual_sender = sender

        # Ensure subject starts with Re: if it's a reply
        reply_subject = subject
        if not subject.lower().startswith("re:"):
            reply_subject = f"Re: {subject}"

        # Construct references header
        new_references = f"{references} {original_message_id}".strip() if references else original_message_id

        reply_message_dict = create_reply_message(
            sender=actual_sender, # Use actual sender email
            to=to,
            subject=reply_subject, # Use adjusted subject
            reply_body=reply_body,
            thread_id=thread_id,
            original_message_id=original_message_id,
            references=new_references # Use constructed references
        )
        message = service.users().messages().send(userId=user_id, body=reply_message_dict).execute()
        print(f"Reply sent successfully. Message ID: {message['id']}") # Keep console log for now
        return {"status": "success", "message_id": message['id']}
    except HttpError as error:
        print(f"An error occurred sending the reply: {error}") # Keep console log
        return {"status": "error", "error_message": f"An API error occurred sending the reply: {error}"}
    except Exception as e:
        print(f"An unexpected error occurred sending the reply: {e}") # Keep console log
        return {"status": "error", "error_message": f"An unexpected error occurred sending the reply: {e}"}
# --- End Added Function to Send Reply ---


# --- Added Function to Search Emails ---
def search_emails(query: str, user_id: str) -> dict:
    """Searches for emails matching the given query.

    Args:
        query: The search query string (e.g., 'from:someone subject:report').
        user_id: The user's email address or 'me'.
        max_results: The maximum number of emails to retrieve.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'emails' (a list of matching email details) on success,
        or 'error_message' on failure. Each email detail includes
        'id', 'threadId', 'subject', 'from', and 'date'.
    """
    service = get_gmail_service()
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}

    try:
        # Search messages using the query
        results = service.users().messages().list(
            userId=user_id, q=query, maxResults=5
        ).execute()
        messages = results.get('messages', [])

        if not messages:
            return {"status": "success", "emails": []} # Return success with empty list if no matches

        email_list = []
        for msg_stub in messages:
            msg_id = msg_stub['id']
            # Fetch metadata for each message
            msg = service.users().messages().get(
                userId=user_id, id=msg_id, format='metadata',
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()

            payload = msg.get('payload', {})
            headers = payload.get('headers', [])
            subject = 'No Subject'
            sender = 'Unknown Sender'
            date = 'No Date'

            for header in headers:
                name = header['name'].lower()
                if name == 'subject':
                    subject = header['value']
                elif name == 'from':
                    sender = header['value']
                elif name == 'date':
                    date = header['value']

            email_list.append({
                'id': msg_id,
                'threadId': msg.get('threadId'),
                'subject': subject,
                'from': sender,
                'date': date
            })

        return {"status": "success", "emails": email_list}

    except HttpError as error:
        return {"status": "error", "error_message": f"An API error occurred searching emails: {error}"}
    except Exception as e:
        return {"status": "error", "error_message": f"An unexpected error occurred searching emails: {e}"}
# --- End Added Function to Search Emails ---


# --- Authentication Function (Example - Adapt for Agent Context) ---
def get_gmail_service():
    """Authenticates and builds the Gmail API service."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}. Re-authenticating.")
                creds = None # Force re-authentication
        if not creds: # Handles both expired refresh token and no token cases
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    try:
        service = build("gmail", "v1", credentials=creds)
        print("Gmail service built successfully.")
        return service
    except Exception as e:
        print(f"Failed to build Gmail service: {e}")
        return None

# --- Added Function to Get Unread Count ---
def get_total_unread_count(user_id: str) -> dict:
    """Gets the total number of unread messages in the inbox.

    Args:
        user_id: The user's email address or 'me'.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'unread_count' on success or 'error_message' on failure.
    """
    service = get_gmail_service()
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}
    try:
        # Get the INBOX label details
        label_info = service.users().labels().get(userId=user_id, id='INBOX').execute()
        unread_count = label_info.get('messagesUnread', 0)
        return {"status": "success", "unread_count": unread_count}
    except HttpError as error:
        return {"status": "error", "error_message": f"An API error occurred getting unread count: {error}"}
    except Exception as e:
        return {"status": "error", "error_message": f"An unexpected error occurred getting unread count: {e}"}
# --- End Added Function ---

# --- Added Function to Get Today's Email Count ---
def get_emails_received_today_count(user_id: str) -> dict:
    """Gets the count of emails received in the inbox within the last 24 hours (approximates 'today').

    Args:
        user_id: The user's email address or 'me'.

    Returns:
        A dictionary containing the 'status' ('success' or 'error'),
        and either 'today_count' on success or 'error_message' on failure.
    """
    service = get_gmail_service()
    if not service:
        return {"status": "error", "error_message": "Failed to get Gmail service."}
    try:
        # Use a query to find messages newer than 1 day in the inbox
        # Note: 'newer_than:1d' typically covers the last 24 hours.
        query = "label:inbox newer_than:1d"
        results = service.users().messages().list(userId=user_id, q=query).execute()
        messages = results.get('messages', [])
        # The result only contains message stubs, count them.
        today_count = len(messages)
        # For very large counts, results might be paginated, estimate might be needed.
        # estimated_count = results.get('resultSizeEstimate', 0) # Alternative if needed
        return {"status": "success", "today_count": today_count}
    except HttpError as error:
        return {"status": "error", "error_message": f"An API error occurred counting today's emails: {error}"}
    except Exception as e:
        return {"status": "error", "error_message": f"An unexpected error occurred counting today's emails: {e}"}
# --- End Added Function ---

# --- REMOVE OLD TOOL BINDINGS --- 
# list_emails_tool = list_recent_emails
# summarize_email_tool = summarize_email_with_gemini
# generate_reply_tool = generate_reply_with_gemini
# send_reply_tool = send_reply
# search_emails_tool = search_emails
# get_gmail_service = get_gmail_service
# 
# print("ADK Function Tools created")
# --- END REMOVED BINDINGS ---



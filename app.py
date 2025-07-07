import gradio as gr
import os
from multi_tool_agent.gmail_agent_logic import (
    get_gmail_service,
    search_emails,
    summarize_email_with_gemini,
    generate_reply_with_gemini,
    send_reply,
    get_total_unread_count,
    get_emails_received_today_count,
    list_recent_emails
)
import google.generativeai as genai
from dotenv import load_dotenv
import json # Import json for parsing LLM response

# --- Configuration and Initialization ---
load_dotenv()
print("Attempted to load .env file for Gradio app.")

# Initialize Gemini Model (handle potential errors)
try:
    gemini_api_key = os.environ.get("GOOGLE_API_KEY")
    if not gemini_api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables. Please set it in the .env file and restart.")
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    print("Gemini model initialized successfully for Gradio app.")
except Exception as e:
    print(f"FATAL: Error initializing Gemini model: {e}")
    gemini_model = None # Indicate model is not available

# Initialize Gmail Service (Requires pre-existing token.json)
# NOTE: The initial OAuth flow needs to happen *before* starting this app.
# Run the original script once or create a dedicated auth script if token.json is missing.
print("Attempting to build Gmail service...")
gmail_service = get_gmail_service()
if not gmail_service:
    print("WARNING: Failed to build Gmail service. Check token.json and credentials.json.")
    # UI should reflect that Gmail functions are unavailable

# --- State Management (Simple Demo) ---
conversation_context = {
    "last_email_summary": None,
    "last_email_details": {}, # To store subject, body, sender, thread_id, etc.
    "last_reply_draft": None,
}

# --- LLM Prompt for Intent Recognition ---
CONTROLLER_PROMPT_TEMPLATE = """
You are the controller for a Gmail assistant. Analyze the user's message and determine the primary intent and necessary parameters based on the conversation history.

Available intents and their required parameters:
- LIST_RECENT: requires optional 'count' (integer, default 5) to list the most recent emails in the inbox.
- SEARCH: requires 'query' (e.g., "from:a@b.com subject:hello")
- SUMMARIZE_BY_ID: requires 'email_id'
- SUMMARIZE_LAST: requires context indicating a specific email (e.g., from a previous search or mention). Check context['last_email_details']['id'].
- GENERATE_REPLY: requires 'reply_instructions' (what the user wants to say) and context from a previously summarized email (context['last_email_details'] required).
- SEND_REPLY: requires confirmation (e.g., "yes", "send it") and context from a previously generated reply draft (context['last_reply_draft'] and context['last_email_details'] required).
- GET_UNREAD_COUNT: No parameters required.
- GET_TODAY_EMAIL_COUNT: No parameters required.
- GREETING/OTHER: if the intent is unclear, a simple greeting, or doesn't match the capabilities.

Conversation History:
{history_string}

Current User message: "{user_message}"

Current Context (JSON):
{context_json}

Based ONLY on the **Current User message** and the **Current Context**, determine the single most likely intent and extract the parameters.

Output your decision STRICTLY as a JSON object with 'intent' (string) and 'parameters' (dictionary) keys. If parameters are not applicable or derivable, use an empty dictionary {{}}.
Example for "list my last 3 emails": {{"intent": "LIST_RECENT", "parameters": {{"count": 3}}}}
Example for "search for emails from test@test.com": {{"intent": "SEARCH", "parameters": {{"query": "from:test@test.com"}}}}
Example for "summarize email with id 123": {{"intent": "SUMMARIZE_BY_ID", "parameters": {{"email_id": "123"}}}}
Example for "draft a reply saying thanks": {{"intent": "GENERATE_REPLY", "parameters": {{"reply_instructions": "saying thanks"}}}}
Example for "yes send it": {{"intent": "SEND_REPLY", "parameters": {{}}}}
Example for "how many unread emails do I have": {{"intent": "GET_UNREAD_COUNT", "parameters": {{}}}}
Example for "how many emails today": {{"intent": "GET_TODAY_EMAIL_COUNT", "parameters": {{}}}}
Example for "hello there": {{"intent": "GREETING/OTHER", "parameters": {{}}}}

JSON Response:
"""

# --- Chatbot Logic ---
def handle_chat(message, history):
    """
    Processes user message using an LLM controller, interacts with Gmail/Gemini tools.
    """
    global conversation_context # Use global for simplicity in this demo

    # Basic checks
    if not gmail_service:
        return "Error: Gmail service is not available. Please ensure authentication (token.json) is complete and restart."
    if not gemini_model:
         return "Error: Gemini model is not available. Check API key and configuration."

    # --- 1. Call LLM Controller ---
    # ADDED DEBUG:
    # print(f"[DEBUG] History object received: {history}") # Removed this print
    history_string = "\n".join([f"User: {h[0]}\nAssistant: {h[1]}" for h in history])
    # ADDED DEBUG: Check if history_string was created
    print(f"[DEBUG] history_string assigned (length: {len(history_string)}).") 
    context_json = json.dumps(conversation_context, indent=2)
    prompt = CONTROLLER_PROMPT_TEMPLATE.format(
        history_string=history_string,
        user_message=message,
        context_json=context_json
    )

    try:
        print(f"--- Sending Controller Prompt ---\n{prompt}\n------------------------------")
        controller_response = gemini_model.generate_content(prompt)
        print(f"--- Controller Response ---\n{controller_response.text}\n--------------------------- ")

        # Clean potential markdown/formatting issues
        cleaned_response_text = controller_response.text.strip().replace('```json', '').replace('```', '')
        decision = json.loads(cleaned_response_text)
        intent = decision.get("intent")
        parameters = decision.get("parameters", {})

    except json.JSONDecodeError as e:
        print(f"Error decoding controller JSON: {e}\nResponse was: {controller_response.text}")
        return "Sorry, I had trouble understanding that request (JSON Decode Error)."
    except Exception as e:
        print(f"Error during controller LLM call: {e}")
        return f"Sorry, an error occurred while processing your request: {e}"

    # --- 2. Execute Action based on Intent ---    response_text = "Sorry, I couldn't process that request based on the understood intent."
    try:
        if intent == "LIST_RECENT":
            count = parameters.get("count", 5) # Default to 5 if not specified
            try:
                count = int(count)
            except ValueError:
                count = 5 # Fallback if count is not a valid integer
            
            list_result = list_recent_emails(user_id='me', max_results=count)
            if list_result["status"] == "success" and list_result["emails"]:
                email_strings = []
                for email in list_result["emails"]:
                    email_str = (
                        f"Subject: {email.get('subject', 'N/A')}\n\n"  # Double newline
                        f"From: {email.get('from', 'N/A')}\n\n"      # Double newline
                        f"Date: {email.get('date', 'N/A')}"
                    )
                    email_strings.append(email_str)
                response_text = f"Here are your last {len(email_strings)} emails:\n\n" + "\n\n---\n\n".join(email_strings)
                # Store the first result's ID for potential follow-up
                conversation_context["last_email_details"] = list_result["emails"][0] # Store first found
                conversation_context["last_reply_draft"] = None # Clear any old draft
            elif list_result["status"] == "success":
                 response_text = "No emails found in your inbox."
            else:
                 response_text = f"Error listing recent emails: {list_result.get('error_message', 'Unknown error')}"

        elif intent == "SEARCH":
            query = parameters.get("query")
            if not query:
                response_text = "My controller understood you want to search, but didn't find search criteria. Please specify (e.g., 'from:...' or 'subject:...')."
            else:
                search_result = search_emails(query=query, user_id='me')
                if search_result["status"] == "success" and search_result["emails"]:
                    # Format emails for better readability in Markdown
                    email_strings = []
                    for email in search_result["emails"]:
                        email_str = (
                            f"Subject: {email.get('subject', 'N/A')}\n\n"  # Double newline
                            f"From: {email.get('from', 'N/A')}\n\n"      # Double newline
                            f"Date: {email.get('date', 'N/A')}"
                        )
                        email_strings.append(email_str)
                    
                    # Join with Markdown horizontal rule separator
                    response_text = "Found emails:\n\n" + "\n\n---\n\n".join(email_strings)
                        
                    # Store the first result's ID for potential follow-up
                    conversation_context["last_email_details"] = search_result["emails"][0] # Store first found
                    conversation_context["last_reply_draft"] = None # Clear any old draft
                elif search_result["status"] == "success":
                     response_text = "No emails found matching your query."
                else:
                     response_text = f"Error searching emails: {search_result.get('error_message', 'Unknown error')}"

        elif intent == "SUMMARIZE_BY_ID":
            email_id = parameters.get("email_id")
            if email_id:
                summary_result = summarize_email_with_gemini(user_id='me', email_id=email_id)
                if summary_result["status"] == "success":
                    response_text = f"Summary:\n{summary_result['summary']}"
                    conversation_context["last_email_summary"] = summary_result['summary']
                    conversation_context["last_email_details"] = summary_result # Store all details
                    conversation_context["last_reply_draft"] = None # Clear any old draft
                else:
                    response_text = f"Error summarizing email {email_id}: {summary_result.get('error_message', 'Unknown error')}"
            else:
                response_text = "My controller understood you want to summarize by ID, but didn't find an ID. Please provide it."

        elif intent == "SUMMARIZE_LAST":
             email_id = conversation_context["last_email_details"].get("id")
             if email_id:
                 summary_result = summarize_email_with_gemini(user_id='me', email_id=email_id)
                 if summary_result["status"] == "success":
                     response_text = f"Summary of the last mentioned email (ID: {email_id}):\n{summary_result['summary']}"
                     conversation_context["last_email_summary"] = summary_result['summary']
                     conversation_context["last_email_details"] = summary_result # Store all details
                     conversation_context["last_reply_draft"] = None # Clear any old draft
                 else:
                    response_text = f"Error summarizing email {email_id}: {summary_result.get('error_message', 'Unknown error')}"
             else:
                 response_text = "I don't have a 'last email' in context to summarize. Please search for or specify an email first."

        elif intent == "GENERATE_REPLY":
            instructions = parameters.get("reply_instructions", "")
            details = conversation_context.get("last_email_details", {})
            original_body = details.get("original_body")

            if original_body:
                # Combine original body with user instructions for the prompt
                generation_prompt_body = f"User wants reply to address: '{instructions}'\n\nOriginal Email Body:\n{original_body}"

                reply_result = generate_reply_with_gemini(
                    original_subject=details.get("subject", "No Subject"),
                    original_body=generation_prompt_body
                )
                if reply_result["status"] == "success":
                    response_text = f"Draft Reply:\n------\n{reply_result['reply_body']}\n------\n\nWould you like me to send this reply?"
                    conversation_context["last_reply_draft"] = reply_result['reply_body'] # Store draft
                else:
                    response_text = f"Error generating reply draft: {reply_result.get('error_message', 'Unknown error')}"
            else:
                response_text = "I need the context of an email (specifically its body) to generate a reply. Please summarize an email first."

        elif intent == "SEND_REPLY":
            details = conversation_context.get("last_email_details", {})
            draft = conversation_context.get("last_reply_draft")

            if (draft and details.get("sender_email") and details.get("subject") and
                details.get("thread_id") and details.get("original_message_id")):

                send_result = send_reply(
                    user_id='me',
                    to=details["sender_email"],
                    sender='me',
                    subject=details["subject"],
                    reply_body=draft,
                    thread_id=details["thread_id"],
                    original_message_id=details["original_message_id"],
                    references=details.get("references", "")
                 )
                if send_result["status"] == "success":
                    response_text = f"Reply sent successfully! Message ID: {send_result['message_id']}"
                    conversation_context["last_reply_draft"] = None # Clear draft after sending
                    # Optionally clear last_email_details too?
                else:
                     response_text = f"Error sending reply: {send_result.get('error_message', 'Unknown error')}"
            elif not draft:
                response_text = "There is no reply draft stored in context to send. Please generate one first."
            else:
                response_text = "I'm missing some details from the original email context (like sender, thread ID, or message ID) needed to send the reply. Please summarize the relevant email again."

        elif intent == "GET_UNREAD_COUNT":
            unread_result = get_total_unread_count(user_id='me')
            if unread_result["status"] == "success":
                response_text = f"You have {unread_result['unread_count']} unread emails in your inbox."
            else:
                response_text = f"Error getting unread count: {unread_result.get('error_message', 'Unknown error')}"

        elif intent == "GET_TODAY_EMAIL_COUNT":
            today_count_result = get_emails_received_today_count(user_id='me')
            if today_count_result["status"] == "success":
                response_text = f"You received approximately {today_count_result['today_count']} emails in the last 24 hours."
            else:
                response_text = f"Error counting today's emails: {today_count_result.get('error_message', 'Unknown error')}"

        elif intent == "GREETING/OTHER":
            # Simple response for greetings or unrecognized input
            response_text = "Hello! How can I help you with your Gmail today?"

        else: # Handles cases where intent is missing or unrecognized by the Python code
            response_text = f"Sorry, I received an unexpected intent ('{intent}') from the controller. I don't know how to handle that."

    except Exception as e:
        print(f"Error executing action for intent {intent}: {e}") # Log unexpected errors
        # Include traceback for debugging
        import traceback
        traceback.print_exc()
        response_text = f"An unexpected error occurred while executing the action: {e}"

    return response_text

# --- Gradio Interface ---
iface = gr.ChatInterface(
    fn=handle_chat,
    title="Gmail AI Agent (Natural Language)", # Updated Title
    description=(
        "Chat with your Gmail assistant using natural language. Examples:\n"
        "- 'Show my last 5 emails'\n"
        "- 'Find emails I got from boss@company.com about the project report'\n"
        "- 'Summarize the email with id 18abc9def0123456'\n"
        "- 'Can you summarize the last email we discussed?'\n"
        "- 'Draft a reply to that email saying I will look into it.'\n"
        "- 'Ok send the reply'\n"
        "- 'How many unread emails do I have?'\n"
        "- 'How many emails did I get today?'"
    ), # Updated Description
    chatbot=gr.Chatbot(height=600),
    textbox=gr.Textbox(placeholder="Type your message here...", container=False, scale=7), # Removed lines=3
    theme=gr.themes.Soft(), # Added theme
    # retry_btn=None, # Removed
    # undo_btn="Delete Previous", # Removed
    # clear_btn="Clear Conversation", # Removed
)

# --- Launch App ---
if __name__ == "__main__":
    if not gmail_service or not gemini_model:
         print("\n---")
         print("ERROR: Cannot launch Gradio UI because Gmail Service or Gemini Model failed to initialize.")
         print("Please check errors above, ensure token.json exists and GOOGLE_API_KEY is valid in .env.")
         print("---")
    else:
        print("Launching Gradio Interface...")
        iface.launch() 
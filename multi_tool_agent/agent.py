from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import the tools and service function from your quickstart file
# from .quickstart import (
from .gmail_agent_logic import (
    # summarize_email_tool, # Removed - Use function directly
    # generate_reply_tool,  # Removed - Use function directly
    # send_reply_tool,      # Removed - Use function directly
    get_gmail_service,
    # list_emails_tool,     # Removed - Use function directly
    # search_emails_tool,   # Removed - Use function directly
    generate_reply_with_gemini, # Function for generating draft
    summarize_email_with_gemini, # Function for summarizing
    send_reply,                 # Function for sending
    list_recent_emails,         # Function for listing
    search_emails              # Function for searching
)

# --- Agent Definition ---

# Define the instruction for the agent
# This tells the LLM how to behave and use the tools.
AGENT_INSTRUCTION = """
You are a helpful email assistant. Your goal is to process user requests related to their Gmail inbox.

Available Tools:
- list_recent_emails: Use this to get a list of the most recent emails (subject, sender, date, id). Useful if the user asks for "the latest email" or "recent emails".
- search_emails: Use this to find emails matching specific criteria (sender, subject, keywords). Useful if the user asks for emails "from someone" or "about something".
- summarize_email_with_gemini: Use this to fetch and summarize a specific email. You need the email_id.
- generate_reply_with_gemini: Use this to generate a draft reply based on an original email's subject and body.
- send_reply: Use this to send the generated reply. You need all the details like recipient ('to'), sender ('sender', usually 'me'), subject, body, thread_id, original_message_id, and references.

Workflow for Summarization:
1. If the user asks to summarize an email and provides an email_id, use 'summarize_email_with_gemini' directly with that ID.
2. If the user asks to summarize an email *without* providing an ID (e.g., "summarize the latest email", "summarize the email from John about the report"):
    a. First, use 'list_recent_emails' (for general requests like "latest") or 'search_emails' (for specific criteria like sender or subject) to find the relevant email(s).
    b. Identify the `email_id` of the most relevant email from the results (usually the first one if asking for "latest"). If multiple relevant emails are found, you might need to ask the user for clarification or pick the most recent one.
    c. Once you have the `email_id`, use 'summarize_email_with_gemini' to get the summary.
3. Present the summary to the user.

Workflow for Replying:
1. To reply to an email, you first need its details. If you don't have them from a recent summarization, follow the Summarization Workflow steps 1 or 2 to get the email details (summary, subject, body, sender, thread_id, message_id, references) using 'summarize_email_with_gemini'.
2. Use 'generate_reply_with_gemini' with the original subject and body obtained from the summary tool.
3. Show the generated reply draft to the user and **ask for confirmation** before sending.
4. If the user confirms, use the 'send_reply' tool with all the necessary information gathered from the summary tool and the generated reply body. Use 'me' as the user_id and sender.
5. Inform the user whether the reply was sent successfully or if an error occurred.
6. Handle errors gracefully by informing the user.
"""

# Create the list of tools for the agent
# Ensure list_emails_tool and search_emails_tool are included
agent_tools = [
    list_recent_emails,         # Use function name directly
    search_emails,              # Use function name directly
    summarize_email_with_gemini,# Use function name directly
    generate_reply_with_gemini, # Use function name directly
    send_reply,                 # Use function name directly
]

# Create the Agent instance
root_agent = Agent(
    model="gemini-2.0-flash-lite-001", 
    name='email_agent',
    description="An agent that helps with Gmail tasks such as listing, searching, summarizing and replying.",
    instruction=AGENT_INSTRUCTION,
    tools=agent_tools,
)

# --- Run Agent ---

if __name__ == "__main__":
    print("Starting Email Agent REPL...")
    print("Try prompts like: 'Summarize the latest email', 'Summarize email from <sender>', 'Reply to the email about <subject>'")
    print("Make sure credentials.json and potentially token.json are present.")

    # Ensure the Gmail service can be authenticated before starting REPL
    print("Attempting initial Gmail authentication...")
    if get_gmail_service():
        print("Gmail authentication successful.")
    else:
        print("Failed to authenticate Gmail service. Please check credentials.json and permissions.")
        print("Exiting.")

    session_service = InMemorySessionService()
    session = session_service.create_session(app_name="AI MAIL", user_id=1234, session_id=123)
    runner = Runner(agent=root_agent, app_name="AI MAIL", session_service=session_service)


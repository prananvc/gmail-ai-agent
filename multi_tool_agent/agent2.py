from google.adk.agents import Agent, LlmAgent, BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import the tools and service function from your quickstart file
from .quickstart import (
    summarize_email_tool,
    send_reply_tool,
    get_gmail_service,
    list_emails_tool,
    search_emails_tool,
    generate_reply_with_gemini,
)

# --- Agent Definition ---

# Define the instruction for the agent
# This tells the LLM how to behave and use the tools.
AGENT_INSTRUCTION = """
You are a helpful email assistant. Your goal is to process user requests related to their Gmail inbox. You must delegate tasks to the appropriate sub-agent based on their description. Do not execute tools directly.

Available Tools (handled by sub-agents):
- list_recent_emails: Use this to get a list of the most recent emails (subject, sender, date, id). Useful if the user asks for "the latest email" or "recent emails". Delegate to inbox_search_agent.
- search_emails: Use this to find emails matching specific criteria (sender, subject, keywords). Useful if the user asks for emails "from someone" or "about something". Delegate to inbox_search_agent.
- summarize_email_with_gemini: Use this to fetch and summarize a specific email. You need the email_id. Delegate to email_summarizing_agent.
- generate_reply_with_gemini: Use this to generate a draft reply based on an original email's subject and body. Delegate to email_reply_agent.
- send_reply: Use this to send the generated reply. You need all the details like recipient ('to'), sender ('sender', usually 'me'), subject, body, thread_id, original_message_id, and references. Delegate to email_sending_agent.

Workflow for Summarization:
1. If the user asks to summarize an email and provides an email_id, delegate to 'email_summarizing_agent' with the 'summarize_email_with_gemini' tool and the ID.
2. If the user asks to summarize an email *without* providing an ID (e.g., "summarize the latest email", "summarize the email from John about the report"):
    a. First, delegate to 'inbox_search_agent' using 'list_recent_emails' (for general requests like "latest") or 'search_emails' (for specific criteria like sender or subject) to find the relevant email(s).
    b. Identify the `email_id` of the most relevant email from the results. If multiple relevant emails are found, ask the user for clarification or pick the most recent one.
    c. Once you have the `email_id`, delegate to 'email_summarizing_agent' with the 'summarize_email_with_gemini' tool to get the summary.
3. Present the summary to the user.

Workflow for Replying:
1. To reply to an email, you first need its details. If you don't have them from a recent summarization, follow the Summarization Workflow steps 1 or 2 to get the email details (summary, subject, body, sender, thread_id, message_id, references) by delegating to the appropriate agents ('inbox_search_agent' then 'email_summarizing_agent').
2. Delegate to 'email_reply_agent' using 'generate_reply_with_gemini' with the original subject and body obtained from the summary tool.
3. Show the generated reply draft to the user and **ask for confirmation** before sending.
4. If the user confirms, delegate to 'email_sending_agent' using the 'send_reply' tool with all the necessary information gathered from the summary tool and the generated reply body. Use 'me' as the user_id and sender.
5. Inform the user whether the reply was sent successfully or if an error occurred.
6. Handle errors gracefully by informing the user.
"""

# Create the list of tools for the agent
# Ensure list_emails_tool and search_emails_tool are included
agent_tools = [
    list_emails_tool,
    search_emails_tool,
    summarize_email_tool,
    generate_reply_with_gemini,
    send_reply_tool,
]

EmailRetrievalAgent = Agent(
    model="gemini-2.0-flash-lite-001",
    name='inbox_search_agent',
    description="An agent that helps with listing recent emails or searching the gmail inbox based on criteria.",
    instruction=AGENT_INSTRUCTION,
    tools=[list_emails_tool, search_emails_tool],
)

EmailProcessingAgent = Agent(
    model="gemini-2.0-flash-lite-001",
    name='email_summarizing_agent',
    description="An agent that helps with summarizing specific emails using their ID.",
    instruction=AGENT_INSTRUCTION,
    tools=[summarize_email_tool],
)

ReplyGenerationAgent = Agent(
    model="gemini-2.0-flash-lite-001",
    name='email_reply_agent',
    description="An agent that helps with generating draft replies to emails.",
    instruction=AGENT_INSTRUCTION,
    tools=[generate_reply_with_gemini],
)

EmailSendingAgent = Agent(
    model="gemini-2.0-flash-lite-001",
    name='email_sending_agent',
    description="An agent that helps with sending email replies after they have been generated and confirmed.",
    instruction=AGENT_INSTRUCTION,
    tools=[send_reply_tool],
)

root_agent = LlmAgent(
    model="gemini-2.0-flash-lite-001", 
    name='email_coordinator_agent',
    description="A coordinator agent that understands user requests about Gmail and delegates tasks like listing, searching, summarizing, generating replies, and sending emails to specialized sub-agents.",
    instruction=AGENT_INSTRUCTION,
    sub_agents=[EmailRetrievalAgent, EmailProcessingAgent, ReplyGenerationAgent, EmailSendingAgent],
)

# --- Run Agent ---

if __name__ == "__main__":
    print("Starting Email Agent REPL...")
    print("Try prompts like: 'Summarize the latest email', 'Summarize email from <sender>', 'Reply to the email about <subject>'")

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


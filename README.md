# Gmail AI Agent

A conversational AI assistant for Gmail that allows you to interact with your emails using natural language. Built with Google's Gemini AI and Gmail API.

## Features

- 🔍 **Smart Email Search**: Find emails using natural language queries
- 📧 **Email Summarization**: Get AI-powered summaries of your emails
- ✍️ **Reply Generation**: Generate contextual replies to emails
- 📊 **Email Statistics**: Check unread counts and daily email statistics
- 💬 **Natural Language Interface**: Chat with your Gmail using conversational language
- 🌐 **Web Interface**: Clean, modern Gradio-based web UI

## Example Commands

- "Show my last 5 emails"
- "Find emails from boss@company.com about the project"
- "How many unread emails do I have?"
- "Summarize the last email"
- "Draft a reply saying I'll look into it"
- "Send the reply"

## Prerequisites

- Python 3.7+
- Gmail account
- Google Cloud Project with Gmail API enabled
- Google AI Studio API key (for Gemini)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd gmail-ai-agent/bitcamp-2025-new
```

### 2. Set Up Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate     # On Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the Gmail API
4. Go to Credentials → Create Credentials → OAuth 2.0 Client IDs
5. Download the credentials file and save as `credentials.json` in the project directory

### 5. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/)
2. Create an API key
3. Create a `.env` file in the project directory:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

### 6. Gmail Authentication

Run the app for the first time to complete OAuth flow:

```bash
python app.py
```

This will open a browser window for Gmail authentication and create a `token.json` file.

## Running the Application

```bash
cd bitcamp-2025-new
source venv/bin/activate
python app.py
```

The web interface will be available at `http://127.0.0.1:7860`

## Project Structure

```
bitcamp-2025-new/
├── app.py                 # Main Gradio web application
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables (not in repo)
├── credentials.json      # Gmail API credentials (not in repo)
├── token.json           # OAuth token (not in repo)
└── multi_tool_agent/
    ├── __init__.py
    ├── agent.py
    ├── agent2.py
    └── gmail_agent_logic.py  # Core Gmail API functions
```

## Security Notes

⚠️ **NEVER commit sensitive files to version control:**
- `.env` (contains API keys)
- `credentials.json` (Gmail API credentials)
- `token.json` (OAuth tokens)

These files are already included in `.gitignore`.

## Troubleshooting

### Common Issues

1. **"Gmail service not available"**
   - Check that `credentials.json` exists
   - Ensure Gmail API is enabled in Google Cloud Console
   - Re-run OAuth flow if `token.json` is missing

2. **"Gemini model not available"**
   - Verify `GOOGLE_API_KEY` in `.env` file
   - Check API key permissions in Google AI Studio

3. **"Module not found errors"**
   - Ensure virtual environment is activated
   - Run `pip install -r requirements.txt`

### Debug Mode

The application prints debug information to the console. Check terminal output for detailed error messages.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is for educational purposes. Please ensure compliance with Gmail API Terms of Service and Google AI API usage policies. 
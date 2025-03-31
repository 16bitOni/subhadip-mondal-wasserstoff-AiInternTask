# AI Email Assistant

An AI-powered personal email assistant capable of reading a user's Gmail inbox, understanding email context, storing emails in a database, and interacting with external tools (web search, Slack, calendar) to assist with email actions. The assistant can automatically draft or send replies, forward information, and schedule events based on email content.

## Features

- **Email Integration**: Authenticate to Gmail using OAuth2 and fetch emails from the inbox via the Gmail API
- **Parsing and Storage**: Parse email fields and store data in a SQLite or PostgreSQL database
- **Context Understanding**: Use OpenAI GPT models to interpret email content and intent
- **Tool Integration – Web Search**: Integrate web search to answer questions in emails
- **Tool Integration – Slack**: Send notifications to Slack for important emails
- **Tool Integration – Calendar**: Create calendar events for meetings mentioned in emails
- **Automated Reply Generation**: Draft and optionally send replies to emails

## Architecture Overview

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│                 │     │              │     │                 │
│   Gmail API     │◄────┤  Email       │◄────┤  Database       │
│                 │     │  Assistant   │─────►  (SQLite/       │
└─────────────────┘     │              │     │   PostgreSQL)   │
                        │              │     │                 │
┌─────────────────┐     │              │     └─────────────────┘
│                 │     │              │
│   OpenAI API    │◄────┤              │     ┌─────────────────┐
│                 │     │              │     │                 │
└─────────────────┘     │              │◄────┤  Slack API      │
                        │              │     │                 │
┌─────────────────┐     │              │     └─────────────────┘
│                 │     │              │
│   Google        │◄────┤              │
│   Calendar API  │     └──────────────┘
│                 │
└─────────────────┘
```

The core components of the system are:

1. **Gmail Service**: Handles authentication and interactions with the Gmail API
2. **LLM Service**: Interacts with OpenAI's API to understand emails and generate replies
3. **Search Service**: Performs web searches to gather information to answer questions
4. **Slack Service**: Sends notifications about important emails to Slack
5. **Calendar Service**: Creates and manages calendar events from email content
6. **Database**: Stores email data and actions taken for persistence and context
7. **Email Processor**: Orchestrates all services to handle email processing workflow

## Installation

### Prerequisites

- Python 3.9 or higher
- Google API credentials (for Gmail and Calendar)
- OpenAI API key
- (Optional) Slack bot token
- (Optional) Google Custom Search API key

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/ai-email-assistant.git
   cd ai-email-assistant
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create config directory and setup credentials:
   ```bash
   mkdir -p config
   ```

4. Create a `.env` file in the config directory based on the `.env.example`:
   ```bash
   cp config/.env.example config/.env
   ```

5. Configure your Google API credentials:
   - Go to the [Google Developer Console](https://console.developers.google.com/)
   - Create a new project and enable Gmail API and Google Calendar API
   - Create OAuth credentials and download as JSON to `config/credentials.json`

6. Update the `.env` file with your API keys and preferences

## Usage

### Run in Daemon Mode (Continuous Processing)

This will check for new emails at regular intervals:

```bash
python src/main.py --mode daemon --interval 300
```

### Process Inbox Once

Process unread emails in the inbox once and exit:

```bash
python src/main.py --mode process-inbox --limit 10
```

### Process a Specific Email

Process a specific email by its ID:

```bash
python src/main.py --mode process-email --email-id YOUR_EMAIL_ID
```

## Configuration Options

The application can be configured via environment variables in the `.env` file:

- `ENV`: Application environment (development, production)
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `GMAIL_API_CREDENTIALS_FILE`: Path to Google API credentials
- `GMAIL_API_TOKEN_FILE`: Path to Google API token
- `OPENAI_API_KEY`: OpenAI API key
- `LLM_MODEL`: OpenAI model to use (gpt-3.5-turbo, gpt-4, etc.)
- `DB_TYPE`: Database type (sqlite, postgres)
- `SLACK_BOT_TOKEN`: Slack bot token
- `CALENDAR_ID`: Google Calendar ID
- `EMAIL_FETCH_INTERVAL`: How often to fetch emails (seconds)
- `AUTO_REPLY_ENABLED`: Whether to allow automatic replies
- `AUTO_FORWARD_ENABLED`: Whether to allow automatic forwarding

## Technical Details

### Database Schema

The database stores:
- Email threads
- Individual emails
- Email attachments
- Actions taken on emails
- User preferences

### API Authentication

The application uses OAuth2 for Gmail and Calendar API authentication.

### LLM Integration

Email analysis and generation are performed using OpenAI's GPT models through API calls.

## Future Enhancements

- Web interface for monitoring and management
- Support for multiple email accounts
- Enhanced AI-driven prioritization
- Support for more complex email workflows
- Integration with more tools and services

## License

MIT

## Acknowledgments

- [Google API Python Client](https://github.com/googleapis/google-api-python-client)
- [OpenAI Python Client](https://github.com/openai/openai-python)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Slack SDK for Python](https://github.com/slackapi/python-slack-sdk)

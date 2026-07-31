# Yandex Mail MCP Server

MCP (Model Context Protocol) server for Yandex Mail. Enables ChatGPT,
Claude Desktop, and other MCP clients to read, search, draft, and send emails
via Yandex Mail.

## Features

- **List folders** — with decoded Russian folder names
- **Search emails** — by sender, subject, date, or custom IMAP queries (supports Cyrillic)
- **Read emails** — full content with text/HTML body
- **Download attachments** — save to disk
- **Create drafts** — save plain-text or HTML drafts without sending
- **Create reply drafts** — preserve the original conversation headers
- **Send emails** — plain text or HTML
- **Move/Delete emails** — organize your mailbox

## Installation

```bash
# Clone the repository
git clone https://github.com/HolyLittleGirl/yandex-mail-mcp.git
cd yandex-mail-mcp

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Yandex email and app password
```

## Yandex Setup

1. Go to [Yandex ID](https://id.yandex.ru/)
2. Enable **Two-Factor Authentication** (required for app passwords)
3. Go to **Security → App Passwords**
4. Create new app password for "Mail"
5. Copy the generated password to `.env`

## Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yandex-mail": {
      "command": "/path/to/yandex-mail-mcp/.venv/bin/python",
      "args": ["/path/to/yandex-mail-mcp/server.py"]
    }
  }
}
```

Restart Claude Desktop after configuration.

## Available Tools

| Tool | Description |
|------|-------------|
| `list_folders()` | List all mailbox folders |
| `search_emails(folder, query, limit)` | Search emails with IMAP queries |
| `read_email(folder, email_id)` | Read full email content |
| `download_attachment(folder, email_id, filename, save_dir)` | Download attachment to disk |
| `create_draft(to, subject, body, cc, bcc, html, draft_folder)` | Save a new draft without sending |
| `create_reply_draft(source_folder, email_id, body, cc, bcc, html, draft_folder)` | Save a reply draft linked to an existing email |
| `send_email(to, subject, body, cc, bcc, html)` | Send an email |
| `move_email(folder, email_id, destination)` | Move email to another folder |
| `delete_email(folder, email_id)` | Delete email (move to Trash) |

## Draft Safety

`create_draft` and `create_reply_draft` use IMAP `APPEND` with the
`\Draft` flag. They do not connect to SMTP and cannot send a message.

The Drafts folder is detected using the IMAP SPECIAL-USE `\Drafts`
attribute. If the mailbox does not expose that attribute, pass
`draft_folder` using either `name` or `imap_name` returned by
`list_folders()`.

For a reply to an existing email, prefer `create_reply_draft`. It:

- reads the original message without marking it as read;
- uses `Reply-To`, falling back to `From`;
- adds `Re:` only when the subject has no reply prefix;
- adds `In-Reply-To` and `References` so Yandex Mail can preserve the thread.

Example MCP call:

```text
create_reply_draft(
  source_folder="INBOX",
  email_id="42",
  body="Здравствуйте! Приглашаем вас на очную консультацию..."
)
```

## Search Query Examples

```
ALL                          # All emails
UNSEEN                       # Unread emails
FROM sender@example.com      # From specific sender
SUBJECT hello                # Subject contains "hello"
SINCE 01-Dec-2024            # Emails since date
UNSEEN FROM boss@company.com # Combined query
```

## Running Tests

```bash
source .venv/bin/activate
pytest test_server.py -v
pytest test_drafts.py -v
```

## License

MIT

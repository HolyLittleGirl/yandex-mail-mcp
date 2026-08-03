# Yandex Mail MCP Server

MCP (Model Context Protocol) server for Yandex Mail. The default safe profile
lets ChatGPT Work list, search, and read messages and save drafts for human
review. Sending, deleting, moving, and attachment downloads are disabled by
default.

## Features

- **List folders** — with decoded Russian folder names
- **Search emails** — by sender, subject, date, or custom IMAP queries (supports Cyrillic)
- **Read emails** — full content with text/HTML body
- **Create drafts** — save plain-text or HTML drafts without sending
- **Create reply drafts** — preserve the original conversation headers
- **Safe profile** — no sending, deleting, moving, or attachment downloads

## Ubuntu VM deployment

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-v2
sudo systemctl enable --now docker

git clone https://github.com/HolyLittleGirl/yandex-mail-mcp.git
cd yandex-mail-mcp
cp .env.example .env
nano .env

sudo docker compose up -d --build
sudo docker compose logs --tail=100
```

Set these values in `.env` before starting:

- `YANDEX_APP_PASSWORD`: Yandex application password;
- `MCP_BEARER_TOKEN`: a random admin secret generated with `openssl rand -hex 32`;
- `MCP_PUBLISH_IP`: the VM's private address;
- `MCP_PUBLIC_URL`: the public HTTPS URL ending in `/mcp`.

Publish the VM through a reverse proxy as `https://mail-mcp.example.com` to
`http://VM_IP:8000`. Do not forward port 8000 from the internet; expose only
HTTPS port 443 through the reverse proxy.

The remote endpoint uses Streamable HTTP. The default `static` mode requires
the bearer token. For ChatGPT OAuth, use the Keycloak deployment below and set
`MCP_AUTH_MODE=hybrid`; this keeps the private token available for diagnostics
while normal users sign in with short-lived Keycloak access tokens.

## OAuth for ChatGPT with Keycloak

The included deployment runs Keycloak 26.7 with PostgreSQL. Copy its example
configuration and use a separate HTTPS hostname for the authorization server:

```bash
cd deploy/keycloak
cp .env.example .env
openssl rand -base64 36
nano .env
sudo docker compose up -d
sudo docker compose logs --tail=100 keycloak
```

Publish `http://VM_IP:8080` through the reverse proxy under the hostname in
`KEYCLOAK_HOSTNAME`. Do not expose PostgreSQL or port 8080 directly to the
internet.

Create the `mailagent` realm in Keycloak and an optional client scope named
`mcp:tools`. Add an Audience mapper to that scope with the MCP endpoint as its
custom audience, for example `https://mail-mcp.example.com/mcp`. The resulting
access token must contain both:

```text
aud: https://mail-mcp.example.com/mcp
scope: mcp:tools
```

Then set the MCP environment:

```dotenv
MCP_AUTH_MODE=hybrid
MCP_OAUTH_ISSUER_URL=https://auth.example.com/realms/mailagent
MCP_OAUTH_AUDIENCE=https://mail-mcp.example.com/mcp
MCP_OAUTH_REQUIRED_SCOPES=mcp:tools
```

Restart the MCP container after changing `.env`. OAuth mode validates the JWT
signature from Keycloak's JWKS endpoint as well as its issuer, audience,
expiration, subject, and required scope.

## Local stdio installation

For local MCP clients, install the Python environment and keep
`MCP_TRANSPORT=stdio`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

## Available tools in the safe profile

| Tool | Description |
|------|-------------|
| `list_folders()` | List all mailbox folders |
| `search_emails(folder, query, limit)` | Search emails with IMAP queries |
| `read_email(folder, email_id)` | Read full email content |
| `create_draft(to, subject, body, cc, bcc, html, draft_folder)` | Save a new draft without sending |
| `create_reply_draft(source_folder, email_id, body, cc, bcc, html, draft_folder)` | Save a reply draft linked to an existing email |

The legacy attachment, send, move, and delete tools remain in the code for
compatibility but are not registered unless their explicit environment flags
are enabled. The clinic deployment always keeps those flags disabled.

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
pytest test_drafts.py -v
```

`test_server.py` contains live-mailbox integration tests and requires a test
mailbox. Do not run those tests against patient correspondence.

## License

MIT

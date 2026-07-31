# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-07-31

### Added
- Protected Streamable HTTP transport for remote MCP clients
- Static bearer-token verification for the private clinic endpoint
- Docker and Docker Compose deployment for an Ubuntu VM
- ChatGPT Work plugin with the patient-reply drafting skill

### Changed
- Default tool profile now exposes only read operations and draft creation
- Sending, deleting, moving, and attachment downloads require explicit opt-in
- Runtime logs go to stderr unless an explicit log file is configured

## [0.1.0] - 2026-07-31

### Added
- Save new messages as Yandex Mail drafts without sending
- Save reply drafts linked to source messages using `In-Reply-To` and `References`
- Automatic Drafts folder detection through IMAP SPECIAL-USE
- Optional explicit Drafts folder override
- Isolated unit tests for draft creation

### Changed
- Folder listing now supports both quoted and unquoted IMAP folder names
- Folder listing includes IMAP attributes
- MCP dependency is constrained to the compatible 1.x API

## [0.0.1] - 2025-12-22

### Added
- Initial release of Yandex Mail MCP Server
- List folders with decoded Russian names (IMAP UTF-7)
- Search emails with IMAP queries (FROM, SUBJECT, UNSEEN, etc.)
- Cyrillic/UTF-8 search support
- Read email content (text/HTML body)
- Download attachments to disk
- Send emails (plain text or HTML)
- Move emails between folders
- Delete emails (move to Trash)
- Behavioral tests with pytest

### Documentation
- README with installation and usage instructions
- Claude Desktop setup guide (CLAUDE_DESKTOP.md)
- Example environment configuration (.env.example)

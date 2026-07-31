"""
Yandex Mail MCP Server

Provides email tools for Claude Desktop via MCP protocol.
Uses IMAP for reading and SMTP for sending.
"""

import imaplib
import smtplib
import email
import re
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import formatdate, make_msgid
import os
import sys
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from imapclient import imap_utf7

VERSION = "0.1.0"

# Load environment variables from script's directory
SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

# Configure logging (not print - stdout is for MCP protocol)
logging.basicConfig(level=logging.INFO, filename=str(SCRIPT_DIR / "yandex_mail_mcp.log"))
logger = logging.getLogger(__name__)

# Yandex server settings
IMAP_SERVER = "imap.yandex.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.yandex.com"
SMTP_PORT = 587

# Credentials from environment
EMAIL = os.getenv("YANDEX_EMAIL")
PASSWORD = os.getenv("YANDEX_APP_PASSWORD")

# Create MCP server
mcp = FastMCP("Yandex Mail")


def decode_mime_header(header_value: str) -> str:
    """Decode MIME-encoded email header."""
    if not header_value:
        return ""
    decoded_parts = []
    for part, charset in decode_header(header_value):
        if isinstance(part, bytes):
            charset = charset or "utf-8"
            try:
                decoded_parts.append(part.decode(charset, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part)
    return "".join(decoded_parts)


@contextmanager
def imap_connection():
    """Context manager for IMAP connection."""
    if not EMAIL or not PASSWORD:
        raise ValueError("YANDEX_EMAIL and YANDEX_APP_PASSWORD must be set in .env")

    conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    try:
        conn.login(EMAIL, PASSWORD)
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


@contextmanager
def smtp_connection():
    """Context manager for SMTP connection."""
    if not EMAIL or not PASSWORD:
        raise ValueError("YANDEX_EMAIL and YANDEX_APP_PASSWORD must be set in .env")

    conn = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    try:
        conn.starttls()
        conn.login(EMAIL, PASSWORD)
        yield conn
    finally:
        try:
            conn.quit()
        except Exception:
            pass


def decode_folder_name(imap_name: str) -> str:
    """Decode IMAP modified UTF-7 folder name to readable string."""
    try:
        return imap_utf7.decode(imap_name.encode())
    except Exception:
        return imap_name


def parse_imap_list_item(item: bytes) -> Optional[dict]:
    """Parse one IMAP LIST response into attributes and folder names."""
    if not isinstance(item, bytes):
        return None

    decoded = item.decode("utf-8", errors="replace")
    match = re.match(
        r'^\((?P<attributes>[^)]*)\)\s+(?P<delimiter>"(?:\\.|[^"])*"|NIL)\s+'
        r'(?P<name>"(?:\\.|[^"])*"|.+)$',
        decoded,
    )
    if not match:
        return None

    raw_name = match.group("name").strip()
    if raw_name.startswith('"') and raw_name.endswith('"'):
        raw_name = raw_name[1:-1]
        raw_name = raw_name.replace(r"\\", "\\").replace(r"\"", '"')

    return {
        "attributes": match.group("attributes").split(),
        "imap_name": raw_name,
        "name": decode_folder_name(raw_name),
    }


def resolve_drafts_folder(conn, requested_folder: Optional[str] = None) -> str:
    """
    Resolve the mailbox used for drafts.

    Prefer the IMAP SPECIAL-USE ``\\Drafts`` attribute. A caller can override
    the folder using either its human-readable or raw IMAP name.
    """
    status, folder_data = conn.list()
    if status != "OK":
        raise Exception("Failed to list folders while resolving Drafts")

    folders = [
        parsed
        for item in folder_data
        if (parsed := parse_imap_list_item(item)) is not None
    ]

    if requested_folder:
        requested = requested_folder.casefold()
        for folder in folders:
            if (
                folder["imap_name"].casefold() == requested
                or folder["name"].casefold() == requested
            ):
                return folder["imap_name"]
        raise Exception(f"Draft folder not found: {requested_folder}")

    for folder in folders:
        attributes = {attribute.casefold() for attribute in folder["attributes"]}
        if r"\drafts" in attributes:
            return folder["imap_name"]

    fallback_names = {"drafts", "черновики"}
    for folder in folders:
        if (
            folder["imap_name"].casefold() in fallback_names
            or folder["name"].casefold() in fallback_names
        ):
            return folder["imap_name"]

    raise Exception(
        "Drafts folder not found. Pass draft_folder with the folder name "
        "returned by list_folders()."
    )


def build_draft_message(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
):
    """Build a MIME message suitable for saving as an IMAP draft."""
    if not EMAIL:
        raise ValueError("YANDEX_EMAIL must be set in .env")
    if not to or not to.strip():
        raise ValueError("Draft recipient must not be empty")

    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=EMAIL.rsplit("@", 1)[-1])
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    return msg


def append_draft(conn, msg, draft_folder: Optional[str] = None) -> dict:
    """Append a MIME message to the resolved Drafts folder."""
    resolved_folder = resolve_drafts_folder(conn, draft_folder)
    status, response = conn.append(
        resolved_folder,
        r"\Draft",
        imaplib.Time2Internaldate(datetime.now().astimezone()),
        msg.as_bytes(),
    )
    if status != "OK":
        raise Exception(f"Failed to save draft in folder: {resolved_folder}")

    response_text = [
        item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
        for item in (response or [])
    ]
    return {
        "status": "draft_saved",
        "folder": decode_folder_name(resolved_folder),
        "imap_folder": resolved_folder,
        "imap_response": response_text,
    }


@mcp.tool()
def list_folders() -> list[dict]:
    """
    List all mail folders in the Yandex mailbox.

    Returns list of folders with:
    - name: Human-readable folder name (decoded from IMAP UTF-7)
    - imap_name: Raw IMAP folder name (use this for other operations like search_emails)
    """
    with imap_connection() as conn:
        status, folder_data = conn.list()
        if status != "OK":
            raise Exception("Failed to list folders")

        return [
            {
                "name": parsed["name"],
                "imap_name": parsed["imap_name"],
                "attributes": parsed["attributes"],
            }
            for item in folder_data
            if (parsed := parse_imap_list_item(item)) is not None
        ]


def build_imap_search_criteria(query: str) -> list[str]:
    """
    Parse user-friendly query into IMAP search criteria with proper quoting.

    Handles: FROM, TO, CC, BCC, SUBJECT, BODY, TEXT
    These keywords need their values quoted for IMAP.
    """
    if not query or query.upper() == "ALL":
        return ["ALL"]

    # Keywords that need their following value quoted
    keywords_needing_quotes = {"FROM", "TO", "CC", "BCC", "SUBJECT", "BODY", "TEXT"}

    result = []
    tokens = query.split()
    i = 0

    while i < len(tokens):
        token = tokens[i]
        upper_token = token.upper()

        if upper_token in keywords_needing_quotes and i + 1 < len(tokens):
            # This keyword needs the next value quoted
            value = tokens[i + 1]
            # Remove existing quotes if any, then add proper quotes
            value = value.strip('"\'')
            result.append(upper_token)
            result.append(f'"{value}"')
            i += 2
        else:
            result.append(token)
            i += 1

    return result


@mcp.tool()
def search_emails(
    folder: str = "INBOX",
    query: str = "ALL",
    limit: int = 20
) -> list[dict]:
    """
    Search emails in a folder.

    Args:
        folder: Mailbox folder (default: INBOX). Use list_folders() to see available folders.
        query: IMAP search query. Examples:
            - "ALL" - all emails
            - "UNSEEN" - unread emails
            - "FROM sender@example.com" - from specific sender
            - "SUBJECT hello" - subject contains "hello"
            - "SINCE 01-Dec-2024" - emails since date
            - "BEFORE 31-Dec-2024" - emails before date
            - Can combine: "UNSEEN FROM boss@company.com"
        limit: Maximum number of emails to return (default: 20)

    Returns list of email summaries with id, subject, from, date.
    """
    with imap_connection() as conn:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            raise Exception(f"Failed to select folder: {folder}")

        # Search emails with properly quoted criteria
        criteria = build_imap_search_criteria(query)

        # Use UTF-8 charset for non-ASCII queries (Cyrillic, etc.)
        has_non_ascii = any(ord(c) > 127 for c in query)
        if has_non_ascii:
            # For UTF-8 search, we need to pass criteria as a single string
            criteria_str = " ".join(criteria)
            status, message_ids = conn.search("UTF-8", criteria_str.encode("utf-8"))
        else:
            status, message_ids = conn.search(None, *criteria)

        if status != "OK":
            raise Exception(f"Search failed: {query}")

        ids = message_ids[0].split()
        # Get most recent emails (last N)
        ids = ids[-limit:] if len(ids) > limit else ids
        ids = list(reversed(ids))  # Most recent first

        emails = []
        for msg_id in ids:
            # Fetch headers only for performance
            status, msg_data = conn.fetch(msg_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if status != "OK":
                continue

            raw_header = msg_data[0][1]
            msg = email.message_from_bytes(raw_header)

            subject = decode_mime_header(msg.get("Subject", ""))
            from_addr = decode_mime_header(msg.get("From", ""))
            date_str = msg.get("Date", "")

            emails.append({
                "id": msg_id.decode("utf-8"),
                "subject": subject,
                "from": from_addr,
                "date": date_str
            })

        return emails


@mcp.tool()
def read_email(folder: str, email_id: str) -> dict:
    """
    Read full email content by ID.

    Args:
        folder: Mailbox folder containing the email
        email_id: Email ID from search_emails() result

    Returns email with subject, from, to, date, body_text, body_html, attachments list.
    """
    with imap_connection() as conn:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            raise Exception(f"Failed to select folder: {folder}")

        status, msg_data = conn.fetch(email_id.encode(), "(RFC822)")
        if status != "OK":
            raise Exception(f"Failed to fetch email: {email_id}")

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = decode_mime_header(msg.get("Subject", ""))
        from_addr = decode_mime_header(msg.get("From", ""))
        to_addr = decode_mime_header(msg.get("To", ""))
        date_str = msg.get("Date", "")

        body_text = ""
        body_html = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append({
                            "filename": decode_mime_header(filename),
                            "content_type": content_type,
                            "size": len(part.get_payload(decode=True) or b"")
                        })
                elif content_type == "text/plain" and not body_text:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body_text = payload.decode(charset, errors="replace")
                elif content_type == "text/html" and not body_html:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or "utf-8"
                    body_html = payload.decode(charset, errors="replace")
        else:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or "utf-8"
            if msg.get_content_type() == "text/html":
                body_html = payload.decode(charset, errors="replace")
            else:
                body_text = payload.decode(charset, errors="replace")

        return {
            "id": email_id,
            "subject": subject,
            "from": from_addr,
            "to": to_addr,
            "date": date_str,
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments
        }


@mcp.tool()
def download_attachment(
    folder: str,
    email_id: str,
    filename: str,
    save_dir: Optional[str] = None
) -> dict:
    """
    Download an email attachment to disk.

    Args:
        folder: Mailbox folder containing the email
        email_id: Email ID from search_emails() result
        filename: Attachment filename to download (from read_email attachments list)
        save_dir: Directory to save the file (default: ~/Downloads)

    Returns dict with saved file path and size.
    """
    # Default save directory
    if save_dir is None:
        save_dir = str(Path.home() / "Downloads")

    save_path = Path(save_dir)
    if not save_path.exists():
        save_path.mkdir(parents=True, exist_ok=True)

    with imap_connection() as conn:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            raise Exception(f"Failed to select folder: {folder}")

        status, msg_data = conn.fetch(email_id.encode(), "(RFC822)")
        if status != "OK":
            raise Exception(f"Failed to fetch email: {email_id}")

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        # Find the attachment
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" not in content_disposition:
                continue

            part_filename = part.get_filename()
            if part_filename:
                decoded_filename = decode_mime_header(part_filename)
                if decoded_filename == filename:
                    # Found the attachment
                    payload = part.get_payload(decode=True)
                    if payload:
                        # Save to file
                        file_path = save_path / decoded_filename
                        with open(file_path, "wb") as f:
                            f.write(payload)

                        return {
                            "status": "downloaded",
                            "filename": decoded_filename,
                            "path": str(file_path),
                            "size": len(payload),
                            "content_type": part.get_content_type()
                        }

        raise Exception(f"Attachment not found: {filename}")


@mcp.tool()
def create_draft(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False,
    draft_folder: Optional[str] = None,
) -> dict:
    """
    Save a new email in Yandex Mail Drafts without sending it.

    Args:
        to: Recipient email address (comma-separated for multiple).
        subject: Draft subject.
        body: Draft body in plain text or HTML.
        cc: CC recipients (optional, comma-separated).
        bcc: BCC recipients (optional, comma-separated).
        html: Treat body as HTML when True.
        draft_folder: Optional Drafts folder override. Use a name returned by
            list_folders(). By default the IMAP ``\\Drafts`` folder is used.

    Returns confirmation that the draft was saved. This tool never uses SMTP
    and never sends the message.
    """
    msg = build_draft_message(
        to=to,
        subject=subject,
        body=body,
        cc=cc,
        bcc=bcc,
        html=html,
    )

    with imap_connection() as conn:
        result = append_draft(conn, msg, draft_folder)

    return {
        **result,
        "to": to,
        "subject": subject,
        "cc": cc,
        "bcc": bcc,
    }


@mcp.tool()
def create_reply_draft(
    source_folder: str,
    email_id: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False,
    draft_folder: Optional[str] = None,
) -> dict:
    """
    Save a reply draft for an existing email without sending it.

    The recipient is taken from Reply-To, falling back to From. The draft
    receives a reply subject plus In-Reply-To and References headers so mail
    clients can keep it in the original conversation.

    Args:
        source_folder: Folder containing the original email.
        email_id: Email ID returned by search_emails().
        body: Reply body in plain text or HTML.
        cc: CC recipients for the draft (optional, comma-separated).
        bcc: BCC recipients for the draft (optional, comma-separated).
        html: Treat body as HTML when True.
        draft_folder: Optional Drafts folder override. Use a name returned by
            list_folders(). By default the IMAP ``\\Drafts`` folder is used.

    Returns confirmation that the reply draft was saved. This tool never uses
    SMTP and never sends the message.
    """
    with imap_connection() as conn:
        status, _ = conn.select(source_folder, readonly=True)
        if status != "OK":
            raise Exception(f"Failed to select folder: {source_folder}")

        status, msg_data = conn.fetch(email_id.encode(), "(BODY.PEEK[])")
        if status != "OK" or not msg_data or not msg_data[0]:
            raise Exception(f"Failed to fetch email: {email_id}")

        raw_email = msg_data[0][1]
        original = email.message_from_bytes(raw_email)

        recipient = decode_mime_header(
            original.get("Reply-To") or original.get("From", "")
        )
        if not recipient:
            raise Exception("Original email has no Reply-To or From address")

        original_subject = decode_mime_header(original.get("Subject", ""))
        if re.match(r"^\s*(re|aw|sv|ответ)\s*:", original_subject, re.IGNORECASE):
            reply_subject = original_subject
        else:
            reply_subject = f"Re: {original_subject}"

        original_message_id = (original.get("Message-ID") or "").strip()
        references = " ".join(original.get_all("References", []))
        if original_message_id and original_message_id not in references:
            references = f"{references} {original_message_id}".strip()

        draft = build_draft_message(
            to=recipient,
            subject=reply_subject,
            body=body,
            cc=cc,
            bcc=bcc,
            html=html,
            in_reply_to=original_message_id or None,
            references=references or None,
        )
        result = append_draft(conn, draft, draft_folder)

    return {
        **result,
        "to": recipient,
        "subject": reply_subject,
        "cc": cc,
        "bcc": bcc,
        "source_folder": source_folder,
        "source_email_id": email_id,
    }


@mcp.tool()
def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    html: bool = False
) -> dict:
    """
    Send an email via Yandex SMTP.

    Args:
        to: Recipient email address (comma-separated for multiple)
        subject: Email subject
        body: Email body (plain text or HTML based on html flag)
        cc: CC recipients (optional, comma-separated)
        bcc: BCC recipients (optional, comma-separated)
        html: If True, body is treated as HTML (default: False)

    Returns confirmation with message ID.
    """
    if not EMAIL:
        raise ValueError("YANDEX_EMAIL must be set in .env")

    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to
    if cc:
        msg["Cc"] = cc

    # Build recipient list
    recipients = [addr.strip() for addr in to.split(",")]
    if cc:
        recipients.extend([addr.strip() for addr in cc.split(",")])
    if bcc:
        recipients.extend([addr.strip() for addr in bcc.split(",")])

    with smtp_connection() as conn:
        conn.send_message(msg, EMAIL, recipients)

    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "cc": cc,
        "bcc": bcc
    }


@mcp.tool()
def move_email(folder: str, email_id: str, destination: str) -> dict:
    """
    Move an email to another folder.

    Args:
        folder: Source folder containing the email
        email_id: Email ID to move
        destination: Destination folder name

    Returns confirmation of move.
    """
    with imap_connection() as conn:
        status, _ = conn.select(folder)
        if status != "OK":
            raise Exception(f"Failed to select folder: {folder}")

        # Copy to destination
        status, _ = conn.copy(email_id.encode(), destination)
        if status != "OK":
            raise Exception(f"Failed to copy email to: {destination}")

        # Mark original as deleted
        status, _ = conn.store(email_id.encode(), "+FLAGS", "\\Deleted")
        if status != "OK":
            raise Exception("Failed to mark original as deleted")

        # Expunge to actually delete
        conn.expunge()

        return {
            "status": "moved",
            "email_id": email_id,
            "from_folder": folder,
            "to_folder": destination
        }


@mcp.tool()
def delete_email(folder: str, email_id: str) -> dict:
    """
    Delete an email (move to Trash).

    Args:
        folder: Folder containing the email
        email_id: Email ID to delete

    Returns confirmation of deletion.
    """
    # Yandex uses "Trash" folder (may also be localized)
    trash_folder = "Trash"

    with imap_connection() as conn:
        status, _ = conn.select(folder)
        if status != "OK":
            raise Exception(f"Failed to select folder: {folder}")

        # Try to move to Trash
        status, _ = conn.copy(email_id.encode(), trash_folder)
        if status != "OK":
            # If Trash doesn't work, try marking as deleted
            status, _ = conn.store(email_id.encode(), "+FLAGS", "\\Deleted")
            if status != "OK":
                raise Exception("Failed to delete email")
            conn.expunge()
            return {
                "status": "deleted_permanently",
                "email_id": email_id,
                "folder": folder
            }

        # Mark original as deleted
        conn.store(email_id.encode(), "+FLAGS", "\\Deleted")
        conn.expunge()

        return {
            "status": "moved_to_trash",
            "email_id": email_id,
            "folder": folder
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")

"""Unit tests for Yandex Mail draft creation."""

import asyncio
from contextlib import contextmanager
from email import message_from_bytes

import pytest

import server


class FakeImapConnection:
    """Small IMAP fake covering the operations used by draft tools."""

    def __init__(self, original_message: bytes | None = None):
        self.original_message = original_message
        self.append_call = None
        self.select_call = None
        self.fetch_call = None

    def list(self):
        return "OK", [
            br'(\HasNoChildren) "/" INBOX',
            br'(\HasNoChildren \Drafts) "/" Drafts',
        ]

    def append(self, folder, flags, internal_date, message):
        self.append_call = {
            "folder": folder,
            "flags": flags,
            "internal_date": internal_date,
            "message": message,
        }
        return "OK", [b"[APPENDUID 123 456] Append completed"]

    def select(self, folder, readonly=False):
        self.select_call = {"folder": folder, "readonly": readonly}
        return "OK", [b"1"]

    def fetch(self, email_id, query):
        self.fetch_call = {"email_id": email_id, "query": query}
        return "OK", [(b"1 (BODY[] {100})", self.original_message), b")"]


def install_fake_connection(monkeypatch, fake):
    """Replace the real IMAP connection context manager with a fake."""

    @contextmanager
    def fake_connection():
        yield fake

    monkeypatch.setattr(server, "imap_connection", fake_connection)
    monkeypatch.setattr(server, "EMAIL", "clinic@example.com")
    return fake


def test_default_safe_profile_exposes_only_read_and_draft_tools():
    tools = asyncio.run(server.mcp.list_tools())
    tool_map = {tool.name: tool for tool in tools}

    assert set(tool_map) == {
        "list_folders",
        "search_emails",
        "read_email",
        "create_draft",
        "create_reply_draft",
    }
    assert tool_map["search_emails"].annotations.readOnlyHint is True
    assert tool_map["create_reply_draft"].annotations.destructiveHint is False


def test_static_bearer_token_verifier_accepts_only_configured_token():
    verifier = server.StaticBearerTokenVerifier(
        "configured-secret",
        "https://mail-mcp.example.com/mcp",
    )

    accepted = asyncio.run(verifier.verify_token("configured-secret"))
    rejected = asyncio.run(verifier.verify_token("wrong-secret"))

    assert accepted is not None
    assert accepted.scopes == ["mail:read", "mail:draft"]
    assert rejected is None


def test_keycloak_verifier_accepts_expected_audience_and_scope(monkeypatch):
    verifier = server.KeycloakJWTTokenVerifier(
        issuer="https://auth.example.com/realms/mailagent",
        audience="https://mail-mcp.example.com/mcp",
        jwks_url="https://auth.example.com/realms/mailagent/certs",
        required_scopes=["mcp:tools"],
    )

    class SigningKey:
        key = "public-key"

    monkeypatch.setattr(
        verifier.jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SigningKey(),
    )
    monkeypatch.setattr(
        server.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "user-123",
            "azp": "chatgpt-client",
            "scope": "openid mcp:tools",
        },
    )

    accepted = asyncio.run(verifier.verify_token("signed-jwt"))

    assert accepted is not None
    assert accepted.client_id == "chatgpt-client"
    assert accepted.resource == "https://mail-mcp.example.com/mcp"
    assert accepted.scopes == ["openid", "mcp:tools"]


def test_keycloak_verifier_rejects_missing_scope(monkeypatch):
    verifier = server.KeycloakJWTTokenVerifier(
        issuer="https://auth.example.com/realms/mailagent",
        audience="https://mail-mcp.example.com/mcp",
        jwks_url="https://auth.example.com/realms/mailagent/certs",
        required_scopes=["mcp:tools"],
    )

    class SigningKey:
        key = "public-key"

    monkeypatch.setattr(
        verifier.jwks_client,
        "get_signing_key_from_jwt",
        lambda token: SigningKey(),
    )
    monkeypatch.setattr(
        server.jwt,
        "decode",
        lambda *args, **kwargs: {"sub": "user-123", "scope": "openid"},
    )

    assert asyncio.run(verifier.verify_token("signed-jwt")) is None


def test_hybrid_verifier_keeps_static_admin_token(monkeypatch):
    static_verifier = server.StaticBearerTokenVerifier(
        "admin-secret",
        "https://mail-mcp.example.com/mcp",
        ["mcp:tools"],
    )
    oauth_verifier = server.KeycloakJWTTokenVerifier(
        issuer="https://auth.example.com/realms/mailagent",
        audience="https://mail-mcp.example.com/mcp",
        jwks_url="https://auth.example.com/realms/mailagent/certs",
        required_scopes=["mcp:tools"],
    )
    monkeypatch.setattr(
        oauth_verifier,
        "verify_token",
        lambda token: pytest.fail("OAuth verifier should not be called"),
    )
    verifier = server.HybridTokenVerifier(static_verifier, oauth_verifier)

    accepted = asyncio.run(verifier.verify_token("admin-secret"))

    assert accepted is not None
    assert accepted.scopes == ["mcp:tools"]


def test_parse_imap_list_item_handles_unquoted_folder():
    parsed = server.parse_imap_list_item(
        br'(\HasNoChildren \Drafts) "/" Drafts'
    )

    assert parsed == {
        "attributes": [r"\HasNoChildren", r"\Drafts"],
        "imap_name": "Drafts",
        "name": "Drafts",
    }


def test_resolve_drafts_folder_uses_special_use_attribute():
    fake = FakeImapConnection()

    assert server.resolve_drafts_folder(fake) == "Drafts"


def test_create_draft_appends_message_without_smtp(monkeypatch):
    fake = install_fake_connection(monkeypatch, FakeImapConnection())

    result = server.create_draft(
        to="patient@example.com",
        subject="Запись в клинику",
        body="Приглашаем вас на очную консультацию.",
    )

    assert result["status"] == "draft_saved"
    assert result["folder"] == "Drafts"
    assert fake.append_call["folder"] == "Drafts"
    assert fake.append_call["flags"] == r"\Draft"

    message = message_from_bytes(fake.append_call["message"])
    assert message["From"] == "clinic@example.com"
    assert message["To"] == "patient@example.com"
    assert server.decode_mime_header(message["Subject"]) == "Запись в клинику"
    assert message.get_payload(decode=True).decode("utf-8") == (
        "Приглашаем вас на очную консультацию."
    )


def test_create_draft_keeps_cc_and_bcc(monkeypatch):
    fake = install_fake_connection(monkeypatch, FakeImapConnection())

    server.create_draft(
        to="patient@example.com",
        subject="Subject",
        body="Body",
        cc="manager@example.com",
        bcc="audit@example.com",
    )

    message = message_from_bytes(fake.append_call["message"])
    assert message["Cc"] == "manager@example.com"
    assert message["Bcc"] == "audit@example.com"


def test_create_reply_draft_preserves_thread_headers(monkeypatch):
    original = (
        b"From: Patient <patient@example.com>\r\n"
        b"Reply-To: reply@example.com\r\n"
        b"To: clinic@example.com\r\n"
        b"Subject: Question\r\n"
        b"Message-ID: <original@example.com>\r\n"
        b"References: <older@example.com>\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Original body"
    )
    fake = install_fake_connection(
        monkeypatch, FakeImapConnection(original_message=original)
    )

    result = server.create_reply_draft(
        source_folder="INBOX",
        email_id="42",
        body="Reply body",
    )

    assert fake.select_call == {"folder": "INBOX", "readonly": True}
    assert fake.fetch_call == {"email_id": b"42", "query": "(BODY.PEEK[])"}
    assert result["to"] == "reply@example.com"
    assert result["subject"] == "Re: Question"

    message = message_from_bytes(fake.append_call["message"])
    assert message["To"] == "reply@example.com"
    assert message["In-Reply-To"] == "<original@example.com>"
    assert message["References"] == (
        "<older@example.com> <original@example.com>"
    )


def test_create_reply_draft_does_not_duplicate_reply_prefix(monkeypatch):
    original = (
        b"From: patient@example.com\r\n"
        b"Subject: Re: Question\r\n"
        b"Message-ID: <original@example.com>\r\n"
        b"\r\n"
        b"Original body"
    )
    install_fake_connection(
        monkeypatch, FakeImapConnection(original_message=original)
    )

    result = server.create_reply_draft("INBOX", "7", "Reply body")

    assert result["subject"] == "Re: Question"


def test_create_draft_requires_recipient(monkeypatch):
    install_fake_connection(monkeypatch, FakeImapConnection())

    with pytest.raises(ValueError, match="recipient"):
        server.create_draft(to="", subject="Subject", body="Body")

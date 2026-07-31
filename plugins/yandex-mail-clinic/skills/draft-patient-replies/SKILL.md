---
name: draft-yandex-patient-replies
description: Find selected patient messages in Yandex Mail by a configured folder OR a subject phrase, review their contents, and save safe reply drafts for manager approval. Use for ophthalmology-clinic inbox triage, patient-email review, invitation-focused replies, and creating Yandex Mail drafts that must never be sent automatically.
---

# Draft Yandex Patient Replies

Use only the bundled `yandex-mail-clinic` MCP tools. Read
[`references/reply-policy.md`](references/reply-policy.md) before drafting a
patient reply.

## Select messages

1. Resolve the target folder and subject phrase from the user's request or the
   established clinic configuration.
2. If neither value is known, ask for at least one. Do not guess folder names or
   subject phrases.
3. Treat the conditions as **OR**, never AND:
   - include messages located in the target folder;
   - include messages whose subject contains the target phrase.
4. Call `list_folders` before using a human-readable folder name. Use the
   returned `imap_name` in subsequent tool calls.
5. Search the target folder and the subject condition separately. Unless the
   user names another base folder for subject searches, search `INBOX`.
6. Deduplicate results by the pair `folder + email id`.

## Review and draft

1. Present the selected message list before creating drafts unless the user
   explicitly asks to process every matching message.
2. Read each selected message with `read_email`.
3. Identify the patient's actual question and any requested next step. Do not
   infer a diagnosis from symptoms or attachments.
4. Draft a concise, empathetic reply in Russian. Prefer inviting the patient to
   contact or visit the clinic for an in-person assessment.
5. Use only confirmed clinic facts. If a price, doctor, schedule, preparation
   rule, treatment statement, or contact detail is not supplied in approved
   materials, do not invent it.
6. Save the response with `create_reply_draft` so the original thread headers
   are preserved.
7. Report the source message, draft recipient, subject, and save result.

## Safety boundary

- Never claim to diagnose, prescribe, interpret tests, or replace a physician.
- Never call or request sending, deleting, moving, or attachment-download
  operations.
- Never state that a message was sent. Say only that a draft was saved.
- Keep a human manager as the final reviewer and sender.
- Stop and ask for clarification when the patient's identity, intended
  recipient, or clinic facts are ambiguous.


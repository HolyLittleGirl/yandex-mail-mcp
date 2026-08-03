---
name: draft-yandex-patient-replies
description: Find selected patient messages in Yandex Mail using either a chosen folder or a subject phrase, review their contents, and save safe reply drafts for manager approval. Use for ophthalmology-clinic inbox triage, patient-email review, invitation-focused replies, and Yandex Mail drafts that must never be sent automatically.
---

# Draft Yandex Patient Replies

Use the bundled `yandex-mail-clinic` MCP tools. Read
[`references/reply-policy.md`](references/reply-policy.md) before drafting.

## Choose one selector

Use exactly one selection method for each run:

- **Folder mode:** select messages from one chosen folder.
- **Subject mode:** select messages whose subject contains one chosen phrase.

Never combine folder and subject as simultaneous conditions. If both are
provided without a clear choice, ask which selector to use.

For folder mode, call `list_folders`, resolve the human-readable name to its
`imap_name`, then call `search_emails` for that folder. For subject mode, search
`INBOX` unless the user explicitly names another search location. Deduplicate
results by `folder + email id`.

## Review and draft

1. Present the selected message list before creating drafts unless the user
   explicitly asks to process every matching message.
2. Read each selected message with `read_email`.
3. Identify the patient's actual question and requested next step. Do not infer
   a diagnosis from symptoms, test results, or attachments.
4. Draft a concise, empathetic reply in Russian. Prefer inviting the patient to
   contact or visit the clinic for an in-person assessment.
5. Use only confirmed clinic facts. Never invent a price, doctor, schedule,
   preparation rule, medical statement, address, phone number, or signature.
6. Save with `create_reply_draft` so the original thread is preserved.
7. Report the source message, recipient, subject, and draft-save result.

## Optional mailbox organization

Use `move_email` only when the tool is available and the user explicitly asks
to organize messages. Before moving anything:

1. Search and show the complete matching message list.
2. Resolve the destination with `list_folders` and use its exact `imap_name`.
3. State the source folder, destination folder, and number of messages.
4. Ask for confirmation immediately before the first move.

After confirmation, move only the listed messages and report each result. A
move is not deletion, but it changes mailbox state and must never be inferred
from a request that only asks to search, review, or draft replies.

For labels, use `list_email_labels` or `get_email_labels` first and select the
exact existing IMAP keyword. Show the matching messages, requested label, and
whether it will be added or removed. Ask for confirmation immediately before
the first `set_email_label` call, then change only the listed messages and
report every result.

## Safety boundary

- Never diagnose, prescribe, interpret tests, or replace a physician.
- Never send, delete, or download attachments.
- Never move messages without an explicit organization request, a preview,
  and confirmation of the exact source messages and destination folder.
- Never add or remove labels without an explicit request, preview, and
  confirmation of the exact messages, label, and operation.
- Never state that a message was sent; say only that a draft was saved.
- Keep a human manager as final reviewer and sender.
- Stop and ask when identity, recipient, selector, or clinic facts are unclear.
- For urgent symptoms, medication questions, treatment changes,
  post-operative complications, legal complaints, or payment disputes, flag
  the message for human review and prepare only a neutral acknowledgement when
  explicitly requested.

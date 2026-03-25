"""
Built-in skill: Gmail
=======================
Read, search, and send emails.

Setup: Google OAuth credentials (see docs/google-setup.md)
"""

import os
import logging
import base64
from email.mime.text import MIMEText

from rook.skills.base import Skill, tool
from rook.core.config import cfg

logger = logging.getLogger(__name__)


def _get_gmail_service():
    """Get authenticated Gmail service."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = os.path.join(cfg.base_dir, "token.json")
    if not os.path.exists(token_path):
        return None, "token.json not found. Run OAuth flow first."

    creds = Credentials.from_authorized_user_file(token_path)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds), None


def _get_body(payload: dict) -> str:
    """Extract email body from Gmail payload."""
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        if part.get("parts"):
            result = _get_body(part)
            if result:
                return result
    return ""


class EmailSkill(Skill):
    name = "email"
    description = "Gmail — read, search, and send emails"
    version = "1.0"

    def __init__(self):
        super().__init__()
        self.enabled = cfg.google_enabled

    @tool(
        "search_emails",
        "Search Gmail messages by query (e.g. 'from:boss', 'subject:invoice', 'is:unread')",
        {"type": "object", "properties": {
            "query": {"type": "string", "description": "Gmail search query"},
            "max_results": {"type": "integer", "description": "Max emails to return (default 5)"},
        }, "required": ["query"]}
    )
    def search_emails(self, query: str, max_results: int = 5) -> str:
        service, err = _get_gmail_service()
        if err:
            return err

        max_results = max(1, min(15, max_results))
        result = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return f"[0 results: {query}]"

        lines = [f"[{len(messages)} emails: {query}]"]
        for msg_ref in messages:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()

            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            frm = headers.get("From", "unknown")
            subject = headers.get("Subject", "(no subject)")
            date = headers.get("Date", "")[:22]

            body = _get_body(msg.get("payload", {}))
            snippet = body[:200].replace("\n", " ").strip() if body else msg.get("snippet", "")

            lines.append(f"\n  From: {frm}\n  Subject: {subject}\n  Date: {date}\n  {snippet}{'...' if len(snippet) >= 200 else ''}")

        return "\n".join(lines)

    @tool(
        "send_email",
        "Send an email via Gmail",
        {"type": "object", "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject"},
            "body": {"type": "string", "description": "Email body text"},
        }, "required": ["to", "subject", "body"]}
    )
    def send_email(self, to: str, subject: str, body: str) -> str:
        service, err = _get_gmail_service()
        if err:
            return err

        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        try:
            sent = service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            return f"Email sent to {to} (subject: {subject})"
        except Exception as e:
            return f"Failed to send: {e}"


skill = EmailSkill()

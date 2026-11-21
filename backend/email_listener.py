"""Email in (IMAP) and email out (SMTP or Resend)."""
import email
import hashlib
import html
import imaplib
import re
import smtplib
from email.header import decode_header, make_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from backend.config import config
from backend.utils import log, parse_sender


# ---------------------------------------------------------------- reading
def connect_imap() -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(config.IMAP_SERVER)
    mail.login(config.EMAIL_USER, config.EMAIL_PASS)
    return mail


def _decode_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def extract_body(msg: email.message.Message) -> str:
    """Prefer text/plain; fall back to text/html with tags stripped. Skips attachments."""
    plain, html_body = "", ""
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if "attachment" in str(part.get("Content-Disposition", "")).lower():
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not plain:
            plain = _decode_part(part)
        elif ctype == "text/html" and not html_body:
            html_body = _decode_part(part)
    return plain.strip() or _html_to_text(html_body)


def parse_raw_email(raw: bytes, uid: str = "") -> dict:
    msg = email.message_from_bytes(raw)
    subject = _decode_header(msg.get("Subject", ""))
    sender_raw = msg.get("From", "")
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:  # rare, but the DB needs a unique key
        message_id = "gen-" + hashlib.sha1(f"{uid}{sender_raw}{subject}".encode()).hexdigest()
    return {
        "uid": uid,
        "message_id": message_id[:255],
        "sender": parse_sender(sender_raw),
        "subject": subject,
        "body": extract_body(msg),
    }


def fetch_unread_emails(limit: int = 20) -> list[dict]:
    """Return up to `limit` unread emails. They stay UNSEEN until mark_as_seen() is called,
    so a crash mid-processing never loses an email."""
    mail = connect_imap()
    records: list[dict] = []
    try:
        mail.select("INBOX")
        status, data = mail.uid("search", None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return records
        for uid in data[0].split()[:limit]:
            status, parts = mail.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            for part in parts:
                if isinstance(part, tuple):
                    records.append(parse_raw_email(part[1], uid.decode()))
                    break
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    return records


def mark_as_seen(uids: list[str]) -> None:
    if not uids:
        return
    mail = connect_imap()
    try:
        mail.select("INBOX")
        for uid in uids:
            mail.uid("store", uid, "+FLAGS", "\\Seen")
    finally:
        try:
            mail.logout()
        except Exception:
            pass


# ---------------------------------------------------------------- sending
def build_match_html(item_name: str, matched_details: str, contact_email: str, confidence: float) -> str:
    # html.escape: values come from emails written by strangers, never trust them in HTML
    item_name, matched_details, contact_email = (
        html.escape(str(item_name)), html.escape(str(matched_details)), html.escape(str(contact_email)),
    )
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px;">
          <h2 style="color: #2b6cb0;">MailSync AI — Possible Match Found</h2>
          <p>Our system matched your report for <strong>{item_name}</strong>
             with a confidence of <strong>{confidence * 100:.1f}%</strong>.</p>
          <div style="background-color: #f7fafc; padding: 15px; border-left: 4px solid #2b6cb0; margin: 15px 0;">
            <p style="margin:0;"><strong>Matched report:</strong> {matched_details}</p>
          </div>
          <p>The other person's contact: <a href="mailto:{contact_email}">{contact_email}</a></p>
          <p>Please write to them to confirm it is the same item. A match is a suggestion, not a guarantee.</p>
          <hr style="border:none; border-top: 1px solid #eee; margin: 20px 0;">
          <p style="font-size: 12px; color: #718096;">Sent automatically by MailSync AI Campus Lost &amp; Found.</p>
        </div>
      </body>
    </html>
    """


def _send_via_resend(to_email: str, subject: str, html_body: str) -> None:
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {config.RESEND_API_KEY}"},
        json={"from": config.RESEND_FROM, "to": [to_email], "subject": subject, "html": html_body},
        timeout=30,
    )
    resp.raise_for_status()


def _send_via_smtp(to_email: str, subject: str, html_body: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, config.EMAIL_USER, to_email
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(config.EMAIL_USER, config.EMAIL_PASS)
        server.send_message(msg)


def send_match_notification(to_email: str, item_name: str, matched_details: str,
                            contact_email: str, confidence: float) -> bool:
    subject = f"MailSync AI: possible match for your {item_name}"
    html_body = build_match_html(item_name, matched_details, contact_email, confidence)

    if config.DRY_RUN_EMAIL:
        log.info("[DRY RUN] would email %s | %s | contact=%s | %.1f%%",
                 to_email, subject, contact_email, confidence * 100)
        return True
    try:
        if config.RESEND_API_KEY:
            _send_via_resend(to_email, subject, html_body)
        else:
            _send_via_smtp(to_email, subject, html_body)
        return True
    except Exception as exc:
        log.error("Failed to send email to %s: %s", to_email, exc)
        return False

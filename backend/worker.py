"""Background worker: checks the inbox every POLL_INTERVAL seconds.
Run with:  python -m backend.worker
"""
import logging
import time

from backend.ai_parser import parse_email_content
from backend.config import config
from backend.email_listener import fetch_unread_emails, mark_as_seen
from backend.matcher import is_duplicate, process_and_match_item
from backend.utils import log

MAX_FAILURES = 3
_failures: dict[str, int] = {}


def handle_email(rec: dict) -> bool:
    """Process one email. Returns True when it is finished (so it can be marked as read)."""
    if not rec["sender"] or rec["sender"] == config.EMAIL_USER.lower():
        return True  # no valid sender, or an email from ourselves
    if is_duplicate(rec["message_id"]):
        return True
    parsed = parse_email_content(rec["subject"], rec["body"])
    if not parsed["is_lost_or_found"]:
        log.info("Ignored noise: %s", rec["subject"][:60])
        return True
    result = process_and_match_item(parsed, rec["sender"], rec["message_id"])
    log.info("Processed '%s' -> %s", rec["subject"][:60], result["status"])
    return True


def run_once() -> int:
    done_uids = []
    emails = fetch_unread_emails()
    for rec in emails:
        try:
            if handle_email(rec):
                done_uids.append(rec["uid"])
        except Exception as exc:
            n = _failures.get(rec["message_id"], 0) + 1
            _failures[rec["message_id"]] = n
            log.error("Failed on '%s' (attempt %d/%d): %s", rec["subject"][:60], n, MAX_FAILURES, exc)
            if n >= MAX_FAILURES:  # give up on poison emails so they don't block forever
                done_uids.append(rec["uid"])
    mark_as_seen(done_uids)
    return len(emails)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    missing = config.missing("EMAIL_USER", "EMAIL_PASS", "SUPABASE_URL", "SUPABASE_KEY", "LLM_API_KEY")
    if missing:
        raise SystemExit(f"Missing settings in .env: {', '.join(missing)}")
    log.info("MailSync worker started. Checking %s every %ds", config.EMAIL_USER, config.POLL_INTERVAL)
    while True:
        try:
            count = run_once()
            if count:
                log.info("Checked inbox: %d new email(s)", count)
        except Exception as exc:  # network blip, IMAP login problem, etc.
            log.error("Inbox check failed: %s", exc)
        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()

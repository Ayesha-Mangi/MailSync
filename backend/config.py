"""Central settings. Everything comes from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # Mailbox (IMAP to read, SMTP to send)
    EMAIL_USER = os.getenv("EMAIL_USER", "")
    EMAIL_PASS = os.getenv("EMAIL_PASS", "")
    IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")  # optional: used instead of SMTP if set
    RESEND_FROM = os.getenv("RESEND_FROM", "MailSync AI <onboarding@resend.dev>")

    # LLM used for extraction
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()  # 'groq' or 'openai'
    LLM_MODEL = os.getenv("LLM_MODEL", "")  # optional override

    # Embeddings (pick ONE; the DB column size must match EMBEDDING_DIM)
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai").lower()  # 'openai' or 'local'
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", 384 if EMBEDDING_PROVIDER == "local" else 1536))

    # Database
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    # Behaviour
    MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", 0.78))
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 20))  # seconds between inbox checks
    DRY_RUN_EMAIL = _bool("DRY_RUN_EMAIL", False)  # log emails instead of sending
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")  # optional shared secret for /webhook/email
    MAX_BODY_CHARS = int(os.getenv("MAX_BODY_CHARS", 4000))

    def missing(self, *names: str) -> list[str]:
        return [n for n in names if not getattr(self, n)]


config = Config()

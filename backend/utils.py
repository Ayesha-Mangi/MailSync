"""Small helpers shared across modules."""
import functools
import logging
import random
import re
import time
from email.utils import parseaddr

log = logging.getLogger("mailsync")


def retry(attempts: int = 3, base_delay: float = 1.0, exceptions: tuple = (Exception,)):
    """Retry a function with exponential backoff (1s, 2s, 4s ... plus a little jitter)."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if i == attempts - 1:
                        raise
                    delay = base_delay * (2 ** i) + random.uniform(0, base_delay / 2)
                    log.warning("%s failed (%s). Retry %d/%d in %.1fs",
                                fn.__name__, exc, i + 1, attempts - 1, delay)
                    time.sleep(delay)

        return wrapper

    return decorator


def parse_sender(raw: str) -> str:
    """'Ali Khan <ali@uni.edu>' -> 'ali@uni.edu'. Returns '' if no valid address."""
    addr = parseaddr(raw or "")[1].strip().lower()
    return addr if "@" in addr else ""


def mask_email(addr: str) -> str:
    """'johndoe@uni.edu' -> 'jo***@uni.edu' (for the public dashboard)."""
    addr = str(addr or "")
    if "@" not in addr:
        return addr
    local, domain = addr.rsplit("@", 1)
    return f"{local[:2]}***@{domain}"


_PHONE_RE = re.compile(r"(?<![\w])(?:\+?\d[\d\s\-().]{7,}\d)(?![\w])")


def redact_phones(text: str) -> str:
    """Replace phone-number-like strings with [phone hidden]."""
    return _PHONE_RE.sub("[phone hidden]", str(text or ""))


def truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit]

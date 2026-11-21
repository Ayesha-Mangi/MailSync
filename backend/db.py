"""One shared Supabase client."""
from functools import lru_cache

from supabase import Client, create_client

from backend.config import config


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    missing = config.missing("SUPABASE_URL", "SUPABASE_KEY")
    if missing:
        raise RuntimeError(f"Missing settings in .env: {', '.join(missing)}")
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

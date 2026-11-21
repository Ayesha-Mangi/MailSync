# MailSync AI — Autonomous Campus Email Lost & Found

Reads a campus inbox, uses an LLM to pull out item details, stores them with vector embeddings in
Supabase (pgvector), matches lost items with found items, emails both people, and shows everything
on a Streamlit dashboard.

```
Email -> worker (IMAP) -> LLM extraction -> embedding -> Supabase/pgvector -> match -> emails + dashboard
```

## Folder map
| File | Job |
| --- | --- |
| `database/schema.sql` | Tables, HNSW index, `match_items()` search function |
| `backend/config.py` | Reads `.env` |
| `backend/utils.py` | Retry with backoff, email parsing/masking, phone redaction |
| `backend/db.py` | Shared Supabase client |
| `backend/email_listener.py` | Read inbox (IMAP), send alerts (SMTP or Resend) |
| `backend/ai_parser.py` | LLM extraction + validation, embeddings |
| `backend/matcher.py` | Dedupe, store, match, notify |
| `backend/worker.py` | Polls the inbox every `POLL_INTERVAL` seconds |
| `backend/api.py` | FastAPI: `/webhook/email`, `/items`, `/matches`, `/items/{id}/resolve` |
| `frontend/app.py` | Streamlit dashboard (feed, simulator, matches + analytics) |
| `tests/` | 19 offline tests (no API keys needed) |

## Setup
1. `python -m venv venv && source venv/bin/activate` (Windows: `venv\Scripts\activate`)
2. `pip install -r requirements.txt`
3. Supabase: create a project, open **SQL Editor**, paste and run `database/schema.sql`.
4. `cp .env.example .env` and fill it in. Start with `DRY_RUN_EMAIL=true` so no real emails go out.
   - Gmail needs an **App password** (Google Account -> Security -> 2-Step Verification -> App passwords).
   - Use the Supabase **service_role** key and never commit `.env`.
   - Groq does not offer embeddings, so set `OPENAI_API_KEY`, or use `EMBEDDING_PROVIDER=local`.
5. Run three terminals from the project root:
   ```
   python -m backend.worker                      # reads the inbox
   uvicorn backend.api:app --reload --port 8000  # optional: webhook + REST API
   streamlit run frontend/app.py                 # dashboard
   ```
6. Run the tests: `pytest`

## Using local embeddings (no OpenAI key)
`pip install sentence-transformers`, set `EMBEDDING_PROVIDER=local`, and in `schema.sql` change every
`1536` to `384` **before** creating the tables. One database can only use one embedding size.

## Tuning the threshold
`MATCH_THRESHOLD=0.78` is the value from the spec. Different embedding models score differently:
if real lost/found pairs are not matching, try 0.65-0.70 (and watch for false matches).
Use the simulator tab to test your own examples.

## Demo (90 seconds)
1. Tab 2, paste: "Lost my silver MacBook Pro with a sticker near the Science Library desks around 2pm" -> Process.
2. Paste: "Found an Apple laptop, silver, with a sticker on the lid, at the library study area" (other sender) -> Process.
3. Tab 3 shows the matched pair with its similarity bar. Click "Mark as resolved" to finish.

## Behaviour notes
- Emails stay unread until fully processed, so a crash never loses one. After 3 failures an email is skipped.
- Contact details are shared only in the match emails (the other person's address), never on the dashboard.
- A match needs similarity >= threshold, opposite intent, the same category (or one side "Other"), and a different sender.
- Match emails are suggestions: people must confirm with each other that it is the same item.

"""HTTP API.  Run with:  uvicorn backend.api:app --reload --port 8000"""
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel

from backend.ai_parser import parse_email_content
from backend.config import config
from backend.db import get_supabase
from backend.matcher import is_duplicate, process_and_match_item
from backend.utils import mask_email, parse_sender, redact_phones

app = FastAPI(title="MailSync AI Service API")


class InboundPayload(BaseModel):
    subject: str
    body: str
    sender: str
    message_id: str


def _check_secret(secret: Optional[str]) -> None:
    if config.WEBHOOK_SECRET and secret != config.WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhook/email")
def receive_email_webhook(payload: InboundPayload, background_tasks: BackgroundTasks,
                          x_webhook_secret: Optional[str] = Header(default=None)):
    _check_secret(x_webhook_secret)
    sender = parse_sender(payload.sender)
    if not sender:
        raise HTTPException(status_code=422, detail="sender is not a valid email address")
    if is_duplicate(payload.message_id):
        return {"status": "ignored", "reason": "Message-ID already processed"}

    parsed = parse_email_content(payload.subject, payload.body)
    if not parsed["is_lost_or_found"]:
        return {"status": "ignored", "reason": "Non-lost/found email"}

    background_tasks.add_task(process_and_match_item, parsed, sender, payload.message_id)
    return {"status": "queued", "extracted": parsed}


@app.get("/items")
def get_items(status: Optional[str] = None, intent: Optional[str] = None):
    """Public list. Emails are masked and embeddings are never returned."""
    cols = "id,intent,item_name,category,color,brand,location,event_date_time,summary,status,sender_email,created_at"
    query = get_supabase().table("items").select(cols).order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    if intent:
        query = query.eq("intent", intent)
    rows = query.execute().data
    for r in rows:
        r["sender_email"] = mask_email(r["sender_email"])
        r["summary"] = redact_phones(r["summary"])
    return rows


@app.get("/matches")
def get_matches():
    return get_supabase().table("matches").select("*").order("created_at", desc=True).execute().data


@app.patch("/items/{item_id}/resolve")
def resolve_item(item_id: str):
    res = get_supabase().table("items").update({"status": "resolved"}).eq("id", item_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "updated", "data": [{"id": r["id"], "status": r["status"]} for r in res.data]}
